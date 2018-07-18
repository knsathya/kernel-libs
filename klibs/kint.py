#!/usr/bin/env python
#
# Linux Kernel intergration script
#
# Copyright (C) 2018 Sathya Kuppuswamy
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# @Author  : Sathya Kupppuswamy(sathyaosid@gmail.com)
# @History :
#            @v0.0 - Basic class support
# @TODO    : 
#
#

import os
import logging, logging.config
import pkg_resources
import tempfile
from shutil import rmtree, move

from jsonparser import JSONParser
from decorators import format_h1
from pyshell import GitShell, PyShell
from send_email import Email


class KernelInteg(object):
    def __init__(self, repo_dir, cfg, repo_head=None, emailcfg=None, logger=None):
        """
        Constructor of KernelInteg class.
        :rtype: object
        :param cfg: Kernel Integration Json config file.
        :param schema: Kernel Integration Json schema file.
        :param head: SHA-ID or Tag of given branch.
        :param repo_dir: Repo directory.
        :param subject_prefix: Prefix for email subject.
        :param skip_rr_cache: Skip rr cache if set True.
        :param logger: Logger object
        """
        self.logger = logger or logging.getLogger(__name__)
        self.schema = pkg_resources.resource_filename('klibs', 'schemas/integ-schema.json')
        self.emailschema = pkg_resources.resource_filename('klibs', 'schemas/email-schema.json')

        self.cfgobj = JSONParser(self.schema, cfg, extend_defaults=True, os_env=True, logger=self.logger)
        self.cfg = self.cfgobj.get_cfg()

        # Update email configs.
        if emailcfg is not None:
            self.emailobj = Email(emailcfg, self.logger)
        else:
            self.emailobj = None

        self.remote_list = self.cfg['remote-list']
        self.repos = self.cfg['repo-list']
        self.int_list = self.cfg['int-list']

        self.repo_dir = repo_dir
        self.sh = PyShell(wd=self.repo_dir, logger=self.logger)

        # All git commands will be executed in repo directory.
        self.logger.info(format_h1("Initalizing repo", tab=2))
        self.git = GitShell(wd=self.repo_dir, init=True, logger=self.logger)

        # Add git remote and fetch the tags.
        self.logger.info(format_h1("Add remote", tab=2))
        for remote in self.remote_list:
            self.git.add_remote(remote['name'], remote['url'])
            self.git.cmd("fetch", remote['name'])

        valid_repo_head = False

        def is_valid_head(head):

            if len(head) == 0:
                return False

            ret, out, err = self.git.cmd('show', head)
            if ret == 0:
                return True

            return False

        # Check if the repo head is valid.
        if len(repo_head) > 0:
            if is_valid_head(repo_head) is False:
                raise Exception("Invalid repo head %s" % repo_head)
            else:
                valid_repo_head = True

         #if repo head is given in config file, check whether its valid, make exception if not valid.
        for repo in self.repos:
            if valid_repo_head is True:
                repo['repo-head'] = repo_head
            else:
                if is_valid_head(repo['repo-head']) is False:
                    raise Exception("Invalid repo head %s" % repo['repo-head'])

    def clean_repo(self):
        """
        Clean the git repo and delete all local branches.
        :return: None
        """
        self.logger.info(format_h1("Cleaning repo", tab=2))

        self.git.cmd("reset", "--hard")
        self.git.cmd("clean", "-fdx")

        local_branches = [x.strip() for x in self.git.cmd('branch')[1].splitlines()]
        for branch in local_branches:
            if branch.startswith('* '):
                continue
                self.git.cmd("branch", "-D", branch)

    def _smb_sync(self, dest, remote, rdir, username='', password='', options=[]):

        cmd = ["//" + remote + '/' + rdir]

        if len(password) > 0:
            cmd.append(password)
        else:
            cmd.append("-N")

        if len(username) > 0:
            cmd.append("-U")
            cmd.append(username)

        cmd = ['smbclient'] + cmd + options

        ret, out, err = self.sh.cmd(' '.join(cmd), shell=True, wd=dest)
        if ret != 0:
            self.logger.error(err)
            self.logger.error(out)

    def _git_sync(self, dest, remote, rbranch, mode='push', msg='Upload updated cache', op='download'):

        uret = self.git.cmd('remote get-url %s' % remote)
        if uret[0] != 0:
            self.logger.error("Invalid sync remote %s branch %s" % (remote, rbranch))
            return False

        git = GitShell(wd=dest, init=True, remote_list=[(remote, uret[1])], logger=self.logger)

        if op == "download":
            git.cmd('clean -xdf')
            git.cmd('fetch', remote)
            git.cmd('checkout', remote + '/' + rbranch)
        elif op == "upload":
            git.cmd('add', '.')
            with tempfile.NamedTemporaryFile() as msg_file:
                msg_file.write(msg)
                msg_file.seek(0)
                git.cmd('commit -s -F %s' % msg_file.name)
            if mode == 'refs-for':
                rbranch = 'refs/for/%s' % rbranch
            if not git.valid_branch(remote, rbranch) or mode == 'force-push':
                git.cmd('push', '-f', remote, 'HEAD:%s' % rbranch)
            else:
                git.cmd('push', remote, 'HEAD:%s' % rbranch)

    def _config_rr_cache(self, options):
        """
        Config git re re re cache.
        :options: Dict with rr-cache options.
            use-auto-merge - Enable rerere.autoupdate if set True, otherwise do nothing.
            use-remote-cache - Get remote cache params if set True, otherwise no remote rerere cache is available.
            remote-cache-params - Parms for remote cache.
                                - sync-protocol - Remote sync protocol (SMB, Rsync)
                                - server-name - Name of the remote server.
                                - Share-point - Name of the share folder.

        :return:
        """
        if options is None:
            return

        cache_dir = os.path.join(self.repo_dir, '.git', 'rr-cache')
        old_dir = os.path.join(self.repo_dir, '.git', 'rr-cache.old')

        self.git.cmd("config", "rerere.enabled", "true")

        def init_state(roptions):
            if os.path.exists(cache_dir):
                if roptions['sync-protocol'] != 'git':
                    if os.path.exists(old_dir):
                        self.sh.cmd('rm -fr %s' %  old_dir, shell=True)
                    self.sh.cmd('mv', cache_dir, old_dir, shell=True)
                    self.sh.cmd('mkdir -p %s' % cache_dir, shell=True)
            else:
                    self.sh.cmd('mkdir -p %s' % cache_dir, shell=True)

        # Check and enable auto merge
        if options['use-auto-merge']:
            self.git.cmd("config", "rerere.autoupdate", "true")

        # Check and add remote cache
        if options['use-remote-cache']:
            roptions = options['remote-cache-params']
            init_state(roptions)
            if roptions['sync-protocol'] == 'smb':
                self._smb_sync(cache_dir, roptions['url'], roptions['remote-dir'], roptions['username'],
                               roptions['password'], roptions['sync-options'])
            elif roptions['sync-protocol'] == 'git':
                self._git_sync(cache_dir, roptions['url'], roptions['branch'], roptions['mode'])

    def _reset_rr_cache(self, options):
        """
        Reset git rerere cache
        :param params: Dict with remote cache related params.
        :return:
        """
        if options is None:
            return

        cache_dir = os.path.join(self.repo_dir, '.git', 'rr-cache')
        old_dir = os.path.join(self.repo_dir, '.git', 'rr-cache.old')

        self.git.cmd("config", "rerere.enabled", "false")

        def reset_state(roptions):
            if options['use-remote-cache']:
                if roptions['sync-protocol'] != 'git':
                    if os.path.exists(old_dir):
                        if os.path.exists(cache_dir):
                            self.sh.cmd('rm -fr %s' % cache_dir, shell=True)
                        self.sh.cmd('mv', old_dir, cache_dir, shell=True)

        if options['upload-remote-cache'] and os.path.exists(cache_dir):
            if options['use-remote-cache']:
                roptions = options['remote-cache-params']
                if roptions['sync-protocol'] == 'smb':
                    self._smb_sync(cache_dir, roptions['url'], roptions['remote-dir'], roptions['username'],
                                   roptions['password'], roptions['upload-options'])
                elif roptions['sync-protocol'] == 'git':
                    self._git_sync(cache_dir, roptions['url'], roptions['branch'], roptions['mode'],
                                   '\n'.join(roptions['upload-msg']), op='upload')

        reset_state(options['remote-cache-params'])

    def _merge_branches(self, mode, merge_list, dest, options, sendemail=False, sub_prefix='', rrupload_header=''):
        """
        Merge the branches given in merge_list and create a output branch.
        Basic logic is,
        if mode is rebase, then git rebase all branches in merge_list onto to dest branch.
        if mode is merge, then git merge/pull all branches on top of dest branch.
        if mode is replace, then simple checkout will be done.
        :param mode:  Rebase, merge, pull
        :param merge_list: List of (remote, branch) tupule.
        :param dest: Dest branch name.
        :param params: Dict with merge params.
        use-rr-cache -  Use git rerere cache.
        no-ff - Set True if you want to disable fast forward in merge.
        add-log - Set True if you want to add merge log.

        :return: True
        """

        def merge_cmd(remote=None, rbranch=None, no_ff=False, add_log=False, abort=False):
            options = []

            if no_ff:
                options.append('--no-ff')
            if add_log:
                options.append('--log')

            if abort is True:
                return ' '.join(['merge', '--abort'])

            if remote is not None and len(remote) > 0:
                return ' '.join(['pull', ' '.join(options), rbranch])
            else:
                return ' '.join(['merge', ' '.join(options), rbranch])


        def send_email(remote, branch, status, out, err):

            if not sendemail:
                return

            subject = [] if len(sub_prefix) == 0 else [sub_prefix]
            content = []

            if mode == 'merge':
                subject.append('Merge')
            elif mode == 'rebase':
                subject.append('Rebase')
            elif mode == 'replace':
                subject.append('Replace')

            if remote is not None and len(remote) > 0:
                branch = remote + '/' + branch

            subject.append(branch)

            if status:
                subject.append('passed')
            else:
                subject.append('failed')

            uret = self.git.cmd('remote get-url %s' % remote)
            url = remote
            if uret[0] == 0:
                url = uret[1].strip()

            content.append('')
            content.append('Head: %s' % self.git.head_sha())
            content.append('Base: %s' % self.git.base_sha())
            content.append('Dest Branch: %s' % dest)
            content.append('Remote: %s' % url)
            content.append('Remote Branch: %s' % branch)
            content.append('Status: %s' % "Passed" if status else "Failed")
            content.append('\n')
            content.append(format_h1("Output log"))
            content.append(out)
            content.append('\n')
            content.append(format_h1("Error log"))
            content.append(err)

            self.emailobj.send_email(' '.join(subject), '\n'.join(content))

        def add_rrcache_msg(remote, branch):
            if options["use-rr-cache"]:
                if options['rr-cache']['upload-remote-cache']:
                    rcoptions = options['rr-cache']['remote-cache-params']
                    if len(rcoptions['upload-msg']) == 0:
                        msg = rrupload_header if len(rrupload_header) > 0 else dest
                        rcoptions['upload-msg'].append('rrcache: upload %s results of %s' % (mode, msg))
                    if len(rcoptions['upload-msg']) == 1:
                        rcoptions['upload-msg'].append('\n')
                    uret = self.git.cmd('remote get-url %s' % remote)
                    url = uret[1].strip() if uret[0] == 0 and len(uret[1]) > 0 else branch 
                    rcoptions['upload-msg'].append("Includes %s resolution of %s" % (mode, url))

        if options["use-rr-cache"]:
            self._config_rr_cache(options["rr-cache"])

        for remote, branch in merge_list:
            ret = 0, '', ''
            if mode == "merge":
                self.git.cmd("checkout", dest)
                self.logger.info(merge_cmd(remote, branch, options['no-ff'], options['add-log']))
                ret = self.git.cmd(merge_cmd(remote, branch, options['no-ff'], options['add-log']))
            elif mode == "rebase":
                self.git.cmd("checkout", remote + '/' + branch if remote !='' else branch)
                ret = self.git.cmd("rebase", dest)
            elif mode == "replace":
                ret = self.git.cmd("checkout", remote + '/' + branch if remote != '' else branch)

            if self.git.inprogress() or ret != 0:
                if options["rr-cache"]["use-auto-merge"]:
                    if len(self.git.cmd('rerere diff')[1]) < 2:
                        if mode == "merge":
                            self.git.cmd('commit', '-as', '--no-edit')
                        elif mode == "rebase":
                            self.git.cmd('rebase', '--continue')

                if self.git.inprogress():
                    send_email(remote, branch, False, ret[1], ret[2])

                    while True:
                        print('Please resolve the issue and then press y to continue')
                        choice = raw_input().lower()
                        if choice in ['yes', 'y', 'ye', '']:
                            if self.git.inprogress():
                                continue
                            else:
                                break
            add_rrcache_msg(remote, branch)

            if mode == "rebase" and not self.git.inprogress():
                self.git.cmd("branch", '-D', dest)
                self.git.cmd("checkout", '-b', dest)

        if options['use-rr-cache']:
            self._reset_rr_cache(options["rr-cache"])

        return True


    def _upload_repo(self, branch_name, upload_options):
        """
        Upload the given branch to a remote patch.
        supported upload modes are force-push, push and refs-for (for Gerrit).
        :param branch_name: Name of the local branch.
        :param upload_options: Dict with upload related params.
        url - Name of the git remote.
        branch - Remote branch of git repo.
        :return: Nothing.
        """
        self.logger.info(format_h1("Uploading %s", tab=2) % branch_name)

        _force = True if upload_options['mode'] == 'force-push' else False
        _use_refs = True if upload_options['mode'] == 'refs-for' else False

        self.git.push(branch_name, upload_options['url'], upload_options['branch'], force=_force,
                      use_refs=_use_refs)

    def _create_repo(self, repo):
        """
        Merge the branches given in source-list and create list of output branches as specificed by dest-list option.
        :param repo: Dict with kernel repo options. Check "repo-params" section in kernel integration schema file for
        more details.
        :return: Nothing
        """
        self.logger.info(format_h1("Create %s repo", tab=2) % repo['repo-name'])

        merge_list = []
        status = True

        # Clean existing git operations
        try:
            self.git.cmd('merge --abort')
            self.git.cmd('rebase --abort')
            self.git.cmd('cherry-pick --abort')
            self.git.cmd('revert --abort')
        except:
            pass

        # Get source branches
        for srepo in repo['source-list']:
            if srepo['skip'] is True:
                continue
            if self.git.valid_branch(srepo['url'], srepo['branch']) is False:
                raise Exception("Dependent repo %s/%s does not exits" % (srepo['url'], srepo['branch']))
            else:
                merge_list.append((srepo['url'], srepo['branch']))

        # Create destination branches
        dest_branches = []
        try:
            for dest_repo in repo['dest-list']:

                if self.git.valid_branch('', dest_repo['local-branch']):
                    ret = self.git.cmd("branch", "-D", dest_repo['local-branch'])[0]
                    if ret != 0:
                        Exception("Deleting branch %s failed" % dest_repo['local-branch'])

                self.git.cmd("checkout", repo['repo-head'], "-b", dest_repo['local-branch'])

                if len(merge_list) > 0:
                    self._merge_branches(dest_repo['merge-mode'], merge_list,
                                         dest_repo['local-branch'],
                                         dest_repo['merge-options'],
                                         repo['send-email'],
                                         repo['email-prefix'],
                                         repo['repo-name'])
                dest_branches.append(dest_repo['local-branch'])
        except Exception as e:
            self.logger.error(e, exc_info=True)
            for branch in dest_branches:
                self.git.cmd("branch", "-D", branch)[0]
        else:
            self.logger.info("repo %s creation successfull" % repo['repo-name'])

        # Compare destination branches
        if status is True:
            if len(repo['dest-list']) > 1:
                base_repo = repo['dest-list'][0]
                for dest_repo in repo['dest-list']:
                    ret, out, err = self.git.cmd('diff', base_repo['local-branch'], dest_repo['local-branch'])
                    if ret != 0:
                        status = False
                        break
                    else:
                        if len(out) > 0:
                            status = False
                            self.logger.error("Destination branches %s!=%s" %
                                              (base_repo['local-branch'], dest_repo['local-branch']))
                            break
                        else:
                            self.logger.info("Destination branches %s==%s" %
                                              (base_repo['local-branch'], dest_repo['local-branch']))
        else:
            self.logger.warn("Skipping destination branch comparison")

        # Upload the destination branches
        if status is True:
            for dest_repo in repo['dest-list']:
                if dest_repo['upload-copy'] is True:
                    upload_options = dest_repo['upload-options']
                    self._upload_repo(dest_repo['local-branch'], upload_options)
        else:
            self.logger.warn("Skipping destination branch upload")

        if repo['send-email']:
            subject = [] if len(repo['email-prefix']) == 0 else [repo['email-prefix']]
            content = []

            subject.append("integration")

            if status:
                subject.append('passed')
            else:
                subject.append('failed')
            
            content.append(format_h1("This repo integration includes:"))
            content.append(format_h1("Following source branches:"))
            content.append('')
            for rname, rbranch in merge_list:
                url = rname
                if len(rname) == 0:
                    rname = 'local-branch'
                else:
                    uret = self.git.cmd('remote get-url %s' % rname)
                    if uret[0] == 0:
                      rname = uret[1].strip()
                content.append('Remote: %s' % rname)
                content.append('Branch: %s' % rbranch)
                content.append('')

            content.append(format_h1("Following destination branches:"))
            content.append('')

            for dest_repo in repo['dest-list']:
                content.append('Branch: %s' % dest_repo['local-branch'])
                content.append('Merge Mode: %s' % dest_repo['merge-mode'])
                if dest_repo['upload-copy'] is True:
                    content.append('Uploaded branch to,')
                    upload_options = dest_repo['upload-options']
                    rurl = upload_options['url']
                    for ritem in self.remote_list:
                        if ritem['name'] == rurl:
                            rurl = ritem['url']
                            break
                    content.append('Upload Remote: %s' % rurl)
                    content.append('Upload Branch: %s' % upload_options['branch'])
                    content.append('')
 
            self.emailobj.send_email(' '.join(subject), '\n'.join(content))

        return status

    def _get_repo_by_name(self, name):
        """
        Get repo Dict from "repos" list in given Json config file.
        :param name: Name of the repo
        :return: repo Dict reference or None if not valid repo found.
        """
        for repo in self.repos:
            if repo['repo-name'] ==  name:
                return repo

        return None

    def start(self, name, skip_dep=False):
        """
        Generate kernel and its depndent branches.
        :param name: Name of the kernel repo.
        :param skip_dep: Skip creating dependent repos.
        :return: None
        """
        dep_list = []
        # First get the dep list
        for item in self.int_list:
            if item["repo"] == name:
                dep_list = item["dep-repos"]

        int_list =  dep_list if not skip_dep else []
        int_list += [name]

        for name in int_list:
            repo = self._get_repo_by_name(name)
            if repo is not None:
                self._create_repo(repo)
            else:
                self.logger.error("Repo %s does not exist\n" % name)
                return False

        return True
