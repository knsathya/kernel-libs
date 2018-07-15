#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Linux Kernel test script
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
import collections
import argparse
import re
import pkg_resources

from jsonparser import JSONParser
from build_kernel import BuildKernel, is_valid_kernel
from decorators import format_h1
from pyshell import PyShell, GitShell

CHECK_PATCH_SCRIPT='scripts/checkpatch.pl'

supported_configs = ['allyesconfig', 'allmodconfig', 'allnoconfig', 'defconfig', 'randconfig']
supported_oldconfigs = ['olddefconfig', 'oldconfig']
supported_archs = ['x86_64', 'i386', 'arm64']

class KernelResults(object):
    def __init__(self, src=None, old_cfg=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.schema = pkg_resources.resource_filename('klibs', 'schemas/results-schema.json')
        self.src = src
        self.results = {}
        self.kernel_params = {}
        self.static_results = []
        self.checkpatch_results = {}
        self.bisect_results = {}
        self.custom_configs = []

        res_obj = {}

        self.kernel_params["head"] = ""
        self.kernel_params["base"] = ""
        self.kernel_params["branch"] = ""
        self.kernel_params["version"] = "Linux"

        for arch in supported_archs:
            self.add_arch(arch)

        self.checkpatch_results["status"] = "N/A"
        self.checkpatch_results["warning_count"] = 0
        self.checkpatch_results["error_count"] = 0

        self.bisect_results["status"] = "N/A"
        self.bisect_results["patch-list"] = []

        res_obj["kernel-params"] = self.kernel_params
        res_obj["static-test"] = self.static_results
        res_obj["checkpatch"] = self.checkpatch_results
        res_obj["bisect"] = self.bisect_results

        self.cfgobj = JSONParser(self.schema, res_obj, extend_defaults=True)
        self.results = self.cfgobj.get_cfg()

        if old_cfg is not None:
            self.update_results(old_cfg)

    def get_static_obj(self, arch):
        for index, obj in enumerate(self.static_results):
            if isinstance(obj, dict) and obj.has_key("arch_name") and obj["arch_name"] == arch:
                return index, obj

        return -1, None

    def add_arch(self, arch):
        if arch is None or len(arch) == 0:
            return False

        if self.get_static_obj(arch)[1] is None:
            obj = {}
            obj["arch_name"] = arch
            self.static_results.append(obj)

            for config in supported_configs + self.custom_configs:
                self.add_config(config)

        return True

    def add_config(self, name):
        if name is None or len(name) == 0:
            return False

        for obj in self.static_results:
            if not obj.has_key(name):
                obj[name] = {}
                obj[name]["compile-test"] = {}
                obj[name]["compile-test"]["status"] = "N/A"
                obj[name]["compile-test"]["warning_count"] = 0
                obj[name]["compile-test"]["error_count"] = 0
                obj[name]["sparse-test"] = {}
                obj[name]["sparse-test"]["status"] = "N/A"
                obj[name]["sparse-test"]["warning_count"] = 0
                obj[name]["sparse-test"]["error_count"] = 0
                obj[name]["smatch-test"] = {}
                obj[name]["smatch-test"]["status"] = "N/A"
                obj[name]["smatch-test"]["warning_count"] = 0
                obj[name]["smatch-test"]["error_count"] = 0

        if name not in supported_configs and name not in self.custom_configs:
            self.custom_configs.append(name)

        return True

    def update_results(self, new_cfg):
        try:
            new_results = JSONParser(self.schema, new_cfg, extend_defaults=True).get_cfg()
            param1 = self.results["kernel-params"]
            param2 = new_results["kernel-params"]
            for field in ["head", "base", "branch", "version"]:
                if (param1[field] != param2[field]) and (param1[field] != "" if field != "version" else "Linux"):
                    Exception("%s field values does not match", field)
        except Exception as e:
            self.logger.warning("Invalid results config file\n")
            self.logger.warning(e)
        else:
            self.results = self.merge_results(self.results, new_results)

    def _update_static_test_results(self, type, arch, config, status, warning_count=0, error_count=0):
        for obj in self.results["static-test"]:
            if obj['arch_name'] == arch:
                obj[config][type]["status"] = "Passed" if status else "Failed"
                obj[config][type]["warning_count"] = warning_count
                obj[config][type]["error_count"] = error_count

    def update_compile_test_results(self, arch, config, status, warning_count=0, error_count=0):
        self._update_static_test_results("compile-test", arch, config, status, warning_count, error_count)

    def update_sparse_test_results(self, arch, config, status, warning_count=0, error_count=0):
        self._update_static_test_results("sparse-test", arch, config, status, warning_count, error_count)

    def update_smatch_test_results(self, arch, config, status, warning_count=0, error_count=0):
        self._update_static_test_results("smatch-test", arch, config, status, warning_count, error_count)

    def update_checkpatch_results(self, status, warning_count=None, error_count=None):
        self.results["checkpatch"]["status"] = "Passed" if status else "Failed"
        if warning_count is not None:
            self.results["checkpatch"]["warning_count"] = warning_count
        if error_count is not None:
            self.results["checkpatch"]["error_count"] = error_count

    def update_kernel_params(self, version=None, branch=None, base=None, head=None):
        if version is not None:
            self.results["kernel-params"]["version"] = version
        if branch is not None:
            self.results["kernel-params"]["branch"] = branch
        if base is not None:
            self.results["kernel-params"]["base"] = base
        if head is not None:
            self.results["kernel-params"]["head"] = head

    def kernel_info(self):
        out = ''
        if self.src is not None:
            out += 'Kernel Info:\n'
            out += "\tVersion: %s\n" % self.results["kernel-params"]["version"]
            out += "\tBranch: %s\n" % self.results["kernel-params"]["branch"]
            out += "\tHead: %s\n" % self.results["kernel-params"]["head"]
            out += "\tBase: %s\n" % self.results["kernel-params"]["base"]

        return out + '\n'

    def static_test_results(self):
        width = len(max(supported_configs + self.custom_configs, key=len)) * 2
        out = 'Static Test Results:\n'
        for obj in self.results["static-test"]:
            out += '\t%s results:\n' % obj['arch_name']
            for config in supported_configs + self.custom_configs:
                out += '\t\t%s results:\n' % config
                for type in ["compile-test", "sparse-test", "smatch-test"]:
                    out += '\t\t\t%s results:\n' % type
                    out += ('\t\t\t\t%-' + str(width) + 's: %s\n') % ("status", obj[config][type]["status"])
                    out += ('\t\t\t\t%-' + str(width) + 's: %s\n') % ("warning", obj[config][type]["warning_count"])
                    out += ('\t\t\t\t%-' + str(width) + 's: %s\n') % ("error", obj[config][type]["error_count"])

        return out + '\n'

    def checkpatch_test_results(self):
        out = 'Checkpatch Test Results:\n'
        out += '\tstatus       : %s\n' % self.checkpatch_results["status"]
        out += '\twarning_count: %s\n' % self.checkpatch_results["warning_count"]
        out += '\terror_count  : %s\n' % self.checkpatch_results["error_count"]

        return out + '\n'

    def bisect_test_results(self):
        out = 'Bisect Test Results:\n'
        out += '\tstatus       : %s\n' % self.bisect_results["status"]

        return out + '\n'

    def get_test_results(self, test_type="compile"):
        out = ''
        out += self.kernel_info()
        if test_type == "static":
            out += self.static_test_results()
        elif test_type == "checkpatch":
            out += self.checkpatch_test_results()
        elif test_type == "all":
            out += self.static_test_results()
            out += self.checkpatch_test_results()

        return out

    def print_test_results(self, test_type="compile"):
        self.logger.info(self.get_test_results(test_type))

    def merge_results(self, dest, src):

        if isinstance(src, collections.Mapping):
            for key, value in src.iteritems():
                dest[key] = self.merge_results(dest[key], src[key])
        elif isinstance(src, (list, tuple)):
            for index, value in enumerate(src):
                dest[index] = self.merge_results(dest[index], src[index])
        else:
            dest = src

        return dest

    def dump_results(self, outfile):
        fobj = open(outfile, 'w+')
        fobj.truncate()
        fobj.close()
        raw_input("Continue to write to file")
        self.cfgobj.dump_cfg(outfile)

class KernelTest(object):

    def __init__(self, src, cfg=None, out=None, rname=None, rurl=None, branch=None, head=None, base=None,
                 res_cfg=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.src = src
        self.out = os.path.join(self.src, 'out') if out is None else os.path.absapth(out)
        self.branch = branch
        self.rname = rname
        self.rurl = rurl
        self.head = head
        self.base = base
        self.valid_git = False
        self.schema = pkg_resources.resource_filename('klibs', 'schemas/test-schema.json')
        self.cfg = None
        self.cfgobj = None
        self.resobj = KernelResults(self.src, old_cfg=res_cfg, logger=self.logger)
        self.git = GitShell(wd=self.src, logger=logger)
        self.sh = PyShell(wd=self.src, logger=logger)
        self.checkpatch_source = CHECK_PATCH_SCRIPT
        self.custom_configs = []

        if self.rname is not None and len(self.rname) > 0:
            if not os.path.exists(self.src):
                os.makedirs(self.src)
            if not self.git.valid():
                self.git.init()
            self.git.add_remote(rname, rurl)
            self.git.cmd('fetch %s' % rname)
            self.branch = self.rname + '/' + self.branch

        self.valid_git = True if self.git.valid() else False

        if self.valid_git:
            if self.branch is not None and len(self.branch) > 0:
                if self.git.cmd('checkout', branch)[0] != 0:
                    self.logger.error("Git checkout command failed in %s", self.src)
                    return
            else:
                self.branch = self.git.current_branch()

            #update base & head if its not given
            if self.head is None:
                self.head = self.git.head_sha()
            if self.base is None:
                self.base = self.git.base_sha()

            self.resobj.update_kernel_params(base=self.base, head=self.head, branch=self.branch)

        if not is_valid_kernel(src, logger):
            return

        self.version = BuildKernel(self.src).uname

        if len(self.version) > 0:
            self.resobj.update_kernel_params(version=self.version)

        if cfg is not None:
            self.cfgobj = JSONParser(self.schema, cfg, extend_defaults=True, os_env=True, logger=logger)
            self.cfg = self.cfgobj.get_cfg()

    def auto_test(self):
        self.logger.info(format_h1("Running kernel tests from json", tab=2))

        status = True

        static_config = self.cfg.get("static-config", None)

        def static_test(obj, cobj, config):
            status = True

            if cobj["compile-test"]:
                current_status = self.compile(obj["arch_name"], config, obj["compiler_options"]["CC"],
                                              obj["compiler_options"]["cflags"],
                                              cobj.get('name', None), cobj.get('source', None))
                if current_status is False:
                    self.logger.error("Compilation of arch:%s config:%s failed\n" % (obj["arch_name"],
                                                                                     cobj.get('name', config)))

                status &= current_status

            if obj[config]["sparse-test"]:
                current_status = self.sparse(obj["arch_name"], config, obj["compiler_options"]["CC"],
                                             obj["compiler_options"]["cflags"],
                                             cobj.get('name', None), cobj.get('source', None))
                if current_status is False:
                    self.logger.error("Sparse test of arch:%s config:%s failed\n" % (obj["arch_name"],
                                                                                     cobj.get('name', config)))

                status &= current_status

            return status


        if static_config is not None and static_config["enable"] is True:
            # Compile standard configs
            for obj in static_config["test-list"]:

                for config in supported_configs:
                    status &= static_test(obj, obj[config], config)

                # Compile custom configs
                for cobj in obj["customconfigs"]:
                    if cobj['name'] not in self.custom_configs:
                        self.custom_configs.append(cobj['name'])

                    self.resobj.add_config(cobj['name'])

                    status &= static_test(obj, cobj, cobj['defaction'])

        checkpatch_config = self.cfg.get("checkpatch-config", None)

        if checkpatch_config is not None and checkpatch_config["enable"] is True:
            if len(checkpatch_config["source"]) > 0:
                self.checkpatch_source = checkpatch_config["source"]
            status &= self.run_checkpatch()[0]

        return status

    def _compile(self, arch='', config='', cc='', cflags=[], name='', cfg=None):

        custom_config = False

        if arch not in supported_archs:
            self.logger.error("Invalid arch/config %s/%s" % (arch, config))
            return False

        if config not in supported_configs:
            if cfg is None or len(cfg) == 0 or name is None or len(name) == 0:
                self.logger.error("Invalid arch/config %s/%s" % (arch, config))
                return False
            else:
                if name not in self.custom_configs:
                    self.custom_configs.append(name)

                self.resobj.add_config(name)

                custom_config = True

        out_dir = os.path.join(self.out, arch, name if custom_config else config)

        kobj = BuildKernel(src_dir=self.src, out_dir=out_dir, arch=arch, cc=cc, cflags=cflags,logger=self.logger)

        # If custom config source is given, use it.
        if custom_config:
            kobj.copy_newconfig(cfg)

        getattr(kobj, 'make_' + config)()

        ret, out, err = kobj.make_kernel()

        def parse_results(outputlog, errorlog, status):
            data = errorlog.split('\n')

            warning_count = len(filter(lambda x: True if "warning:" in x else False, data))
            error_count = len(filter(lambda x: True if "error:" in x else False, data))

            return status, warning_count, error_count

        status = True if ret == 0 else False

        if not status:
            self.logger.error(err)

        return parse_results(out, err, status)

    def compile(self, arch='', config='', cc='', cflags=[], name='', cfg=None):

        status, warning_count, error_count = self._compile(arch, config, cc, cflags, name, cfg)

        name = config if name is None or len(name) == 0 else name

        self.resobj.update_compile_test_results(arch, name, status, warning_count, error_count)

        return status

    def sparse(self, arch='', config='', cc='', cflags=[], name='', cfg=None):

        sparse_flags = []

        if len(filter(lambda x: True if re.match(r'C=\d', x) else False, cflags)) == 0:
            sparse_flags.append("C=2")

        if len(filter(lambda x: True if re.match(r'CHECK=(.*)?sparse(.*)?', x) else False, cflags)) == 0:
            sparse_flags.append('CHECK="/usr/bin/sparse"')

        status, warning_count, error_count = self._compile(arch, config, cc, sparse_flags + cflags, name, cfg)

        name = config if name is None or len(name) == 0 else name

        self.resobj.update_sparse_test_results(arch, name, status, warning_count, error_count)

        return status

    def smatch(self, arch='', config='', cc='', cflags=[], name='', cfg=None):

        smatch_flags = []

        if len(filter(lambda x: True if re.match(r'C=\d', x) else False, cflags)) == 0:
            smatch_flags.append("C=2")

        if len(filter(lambda x: True if re.match(r'CHECK=(.*)?smatch(.*)?', x) else False, cflags)) == 0:
            smatch_flags.append('CHECK="smatch -p=kernel"')

        status, warning_count, error_count = self._compile(arch, config, cc, smatch_flags + cflags, name, cfg)

        name = config if name is None or len(name) == 0 else name

        self.resobj.update_smatch_test_results(arch, name, status, warning_count, error_count)

        return status


    def compile_list(self, arch='', config_list=[], cc='', cflags=[], name='', cfg=None):
        self.logger.info(format_h1("Running compile tests", tab=2))
        result = []

        for config in config_list:
            result.append(self.compile(arch, config, cc, cflags, name, cfg))

        return result

    def sparse_list(self, arch='', config_list=[], cc='', cflags=[], name='', cfg=None):
        self.logger.info(format_h1("Running sparse tests", tab=2))
        result = []

        for config in config_list:
            result.append(self.sparse(arch, config, cc, cflags, name, cfg))

        return result

    def smatch_list(self, arch='', config_list=[], cc='', cflags=[], name='', cfg=None):
        self.logger.info(format_h1("Running smatch tests", tab=2))
        result = []

        for config in config_list:
            result.append(self.smatch(arch, config, cc, cflags, name, cfg))

        return result

    def run_sparse(self):
        self.logger.info(format_h1("Run sparse Script", tab=2))

        return True

    def run_checkpatch(self):

        self.logger.info(format_h1("Runing checkpatch script", tab=2))

        self.enable_checkpatch = True

        get_val = lambda x, y: getattr(self, y) if x is None else x

        gerrorcount = 0
        gwarningcount = 0

        try:
            if self.valid_git is False:
                raise Exception("Invalid git repo")

            if not os.path.exists(os.path.join(self.src, CHECK_PATCH_SCRIPT)):
                raise Exception("Invalid checkpatch script")

            ret, count, err = self.git.cmd('rev-list', '--count',  str(self.base) + '..'+ str(self.head))
            if ret != 0:
                raise Exception("git rev-list command failed")

            self.logger.debug("Number of patches between %s..%s is %d", self.base, self.head, int(count))

            def parse_results(data):
                regex = r"total: ([0-9]*) errors, ([0-9]*) warnings,"
                match = re.search(regex, data)
                if match:
                    return int(match.group(1)), int(match.group(2))

                return 0, 0

            prev_index = 0
            for index in range(1, int(count) + 1):
                commit_range = str(self.head) + '~' + str(index) + '..' + str(self.head) + '~' + str(prev_index)
                ret, out, err = self.sh.cmd(os.path.join(self.src, CHECK_PATCH_SCRIPT), '-g', commit_range)
                lerrorcount, lwarningcount = parse_results(out)
                if lerrorcount != 0 or lwarningcount != 0:
                    self.logger.info(out)
                    self.logger.info(err)
                gerrorcount = gerrorcount + int(lerrorcount)
                gwarningcount = gwarningcount + int(lwarningcount)
                self.logger.info("lerror:%d lwarning:%d gerror:%d gwarning:%d\n", lerrorcount, lwarningcount, gerrorcount, gwarningcount)
                prev_index = index
        except Exception as e:
            self.logger.error(e)
            self.resobj.update_checkpatch_results(False, gwarningcount, gerrorcount)
            return False
        else:
            self.resobj.update_checkpatch_results(True, gwarningcount, gerrorcount)
            return True

    def print_results(self, test_type='all'):
        self.resobj.print_test_results(test_type=test_type)

    def get_results(self, test_type='all'):
        return self.resobj.get_test_results(test_type=test_type)

    def dump_results(self, outfile):
        self.resobj.dump_results(outfile)
