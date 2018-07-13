#!/usr/bin/python
#
# Linux kernel compilation and config  classes
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
import re
import logging
import multiprocessing
from shutil import copy
import sys
import tempfile
import subprocess
import errno
from pyshell import PyShell

MAKE_CMD = '/usr/bin/make'

def assert_exists(name, message=None, logger=None):
    if not os.path.exists(os.path.abspath(name)):
        if logger is not None:
            logger.error(("%s does not exist" % name) if message is None else message)
        raise IOError(("%s does not exist" % name) if message is None else message)

def copy2(src, dest):
    try:
        copy(src, dest)
    except IOError as e:
        # ENOENT(2): file does not exist, raised also on missing dest parent dir
        if e.errno != errno.ENOENT:
            raise
        # try creating parent directories
        os.makedirs(os.path.dirname(dest))
        copy(src, dest)

set_val = lambda k, v: v if k is None else k

class KernelConfig(object):
    """
    This class is used for mangling the kernel config file.
    Supported operations are,
        * enable_config: Enables given config option,
        * module_config: Makes given config option as module,
        * disable_config: Disable given config option,
        * merge_config: Merge given config list.
    """
    def __init__(self, src, out=None, bkup=True, logger=None):
        """
        KerenelConfig init function()
        :param src: Kernel config source
        :param out: Output path of modified kernel config. if none, src will be used as out.
        :param bkup: Enable if you want to keep backup of src config.
        :param logger: Logger object.
        """
        self.logger = logger or logging.getLogger(__name__)
        assert_exists(src, "%s kernel config does not exits" % src, logger=self.logger)
        self.src = src
        self.out = set_val(out, src)
        self.bkup = self.src + '.bkup' if bkup is True else self.src
        self.choices = ['y', 'm', 'n']

    def _format_config(self, option, value):
        return option + "=%s\n" % value if value in ["y", "m"] else "# " + option + " is not set\n"

    def _config_exists(self, option, content):
        for choice in self.choices:
            if self._format_config(option, choice) == content:
                return True

        return False

    def _mod_config(self, option, value, in_file=None, out_file=None):

        cfg_src = self.src if in_file is None else in_file

        if value not in self.choices:
            raise Exception("Invalid config set %s option" % value)

        tmp_file = tempfile.NamedTemporaryFile(mode='w+t')

        with open(cfg_src) as cfgobj:
            for line in cfgobj:
                if not self._config_exists(option, line):
                    tmp_file.write(line)
                else:
                    tmp_file.write(self._format_config(option, value))
        cfgobj.close()

        tmp_file.seek(0)

        if out_file is not None:
            copy2(tmp_file.name, out_file)
        else:
            copy2(cfg_src, self.bkup)
            copy2(tmp_file.name, self.out)

        tmp_file.close()

        return True

    def enable_config(self, option, out_file=None):
        """
        Enables the given config option. Usage is,
        enable_config("CONFIG_EFI")
        :param option: CONFIG_* option.
        :param out_file: Outfile for modified config.
        :return: True | False
        """
        return self._mod_config(option, 'y', out_file=out_file)

    def module_config(self, option, out_file=None):
        """
        Modularize the given config option. Usage is,
        module_config("CONFIG_EFI")
        :param option: CONFIG_* option.
        :param out_file: Outfile for modified config.
        :return: True | False
        """
        return self._mod_config(option, 'm', out_file=out_file)

    def disable_config(self, option, out_file=None):
        """
        Disable the given config option. Usage is,
        disable_config("CONFIG_EFI")
        :param option: CONFIG_* option.
        :param out_file: Outfile for modified config.
        :return: True | False
        """
        return self._mod_config(option, 'n',  out_file=out_file)

    def merge_config(self, diff_cfg, out_file=None):
        """
        Merge given config list to src config.
        :param diff_cfg: Config list in list format or a new file.
        :param out_file: Outfile for modified config.
        :return: True | False
        """
        update_list = []
        diff_list = []

        if type(diff_cfg) is list:
            diff_list = diff_cfg
        else:
            assert_exists(diff_cfg, logger=self.logger)
            with open(diff_cfg) as diffobj:
                diff_list = diffobj.read().splitlines()
            diffobj.close()

        for line in diff_list:
            option = line.split('=')[0].strip()
            value = line.split('=')[1].strip()
            if not option.startswith("CONFIG_") or value not in self.choices:
                self.logger.error("Invalid config : %s or value : %s" % (option, value))
                return False
            else:
                update_list.append((option, value))

        in_file = None
        for item in update_list:
            self._mod_config(item[0], item[1], in_file=in_file, out_file=out_file)
            if out_file is not None:
                in_file = out_file

        return True

def is_valid_kernel(src, logger=None):
    """
    Check if the given source is a valid kernel and return True|False status.
    :param src: Kernel source path.
    :param logger: Logger object.
    :return: True | False
    """
    logger = logger or logging.getLogger(__name__)

    def parse_makefile(data, field):
        regex = r"%s = (.*)" % field
        match = re.search(regex, data)
        if match:
            return match.group(1)
        else:
            None

    if os.path.exists(os.path.join(src, 'Makefile')):
        with open(os.path.join(src, 'Makefile'), 'r') as makefile:
            _makefile = makefile.read()
            if parse_makefile(_makefile, "VERSION") is None:
                logger.error("Missing VERSION field in Makefile")
                return False
            if parse_makefile(_makefile, "PATCHLEVEL") is None:
                logger.error("Missing PATCHLEVEL field in Makefile")
                return False
            if parse_makefile(_makefile, "SUBLEVEL") is None:
                logger.error("Missing SUBLEVEL field in Makefile")
                return False
            if parse_makefile(_makefile, "EXTRAVERSION") is None:
                logger.warn("Missing EXTRAVERSION field in Makefile")
            if parse_makefile(_makefile, "NAME") is None:
                logger.error("Missing NAME field in Makefile")
                return False

        return True

    logger.error("%s Invalid kernel source directory", src)

    return False

def get_kernel_version(src, logger=None):
    """
    Get the kernel version of given source.
    :param src: Kernel source path.
    :param logger: Logger object.
    :return: None on error. Otherwise, kernel source in Linux-xx.yy-rcx format.
    """
    logger = logger or logging.getLogger(__name__)

    if not is_valid_kernel(src, logger):
        return None

    return PyShell(wd=src, logger=logger).cmd("make", "kernelversion")[1].strip()

class BuildKernel(object):
    """
    Wrapper class for building Linux kernel for given arch/config option.

    Supported config targets are,
        make_config(),
        make_nconfig(),
        make_menuconfig(),
        make_xconfig(),
        make_gconfig(),
        make_oldconfig(),
        make_localmodconfig(),
        make_localyesconfig(),
        make_defconfig(),
        make_savedefconfig,
        make_allnoconfig,
        make_allyesconfig,
        make_allmodconfig,
        make_alldefconfig ,
        make_randconfig,
        make_listnewconfig,
        make_olddefconfig,
        make_kvmconfig,
        make_xenconfig,
        make_tinyconfig.

    Supported build targets are,
        make_all(),
        make_vmlinux(),
        make_modules(),
        make_modules_install(),
        make_kernelrelease(),
        make_kernelversion(),
        make_headers_install().

    Supported clean targets are,
        make_clean(),
        make_mrproper(),
        make_distclean().

    """

    def __init__(self, src_dir=None, arch=None, cc=None, cflags=None, out_dir=None, threads=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)

        self.src = os.path.abspath(set_val(src_dir, os.getcwd()))
        self.out = os.path.abspath(set_val(out_dir, os.path.join(self.src, 'out')))
        self.cfg = os.path.abspath(os.path.join(self.out, '.config'))
        self._makefile = None
        self.threads = set_val(threads, multiprocessing.cpu_count())
        self.clags = set_val(cflags, [])
        self.arch =  set_val(arch, "x86_64")
        self.cc = cc

        try:
            with open(os.path.join(self.src, 'Makefile'), 'r') as makefile:
                self._makefile = makefile.read()
        except:
            self.logger.error("%s Invalid kernel source directory", self.src)
            raise IOError

        self.uname = PyShell(wd=src_dir, logger=logger).cmd("make", "kernelversion")[1].strip()

        self.config_targets = ["config", "nconfig", "menuconfig", "xconfig", "gconfig", "oldconfig",
                               "localmodconfig", "localyesconfig", "defconfig", "savedefconfig",
                               "allnoconfig", "allyesconfig", "allmodconfig", "alldefconfig" ,
                               "randconfig", "listnewconfig", "olddefconfig", "kvmconfig", "xenconfig",
                               "tinyconfig"]

        self.clean_targets = ["clean", "mrproper", "distclean"]

        self.build_targets =["all", "vmlinux", "modules", "modules_install", "kernelrelease", "kernelversion",
                             "headers_install"]

        for target in self.config_targets +  self.clean_targets + self.build_targets:
            def make_variant(self, target=target, flags=[], log=False, dryrun=False):
                self._make_target(target=target, flags=flags, log=log, dryrun=dryrun)
            setattr(self.__class__, 'make_' + target , make_variant)

    def _exec_cmd(self, cmd, log=False, dryrun=False):
        self.logger.debug("BuildKernel: Executing %s", ' '.join(map(lambda x: str(x), cmd)))

        shell = PyShell(logger=self.logger)

        return shell.cmd(*cmd, out_log=log, dry_run=dryrun)

    def _make_target(self, target=None, flags=[], log=False, dryrun=False):

        mkcmd = [MAKE_CMD] + self.clags + ['-j%d' % self.threads, "ARCH=%s" % self.arch, "O=%s" % self.out, "-C", self.src]

        # Make sure out dir exists
        if not os.path.exists(self.out):
            os.makedirs(self.out)

        if self.cc is not None and len(self.cc) > 0 :
            mkcmd.append("CROSS_COMPILE=%s" % self.cc)

        mkcmd += flags

        if target is not None:
            mkcmd.append(target)

        ret, out, err = self._exec_cmd(mkcmd, log=log, dryrun=dryrun)
        if ret != 0:
            self.logger.error(' '.join(mkcmd) + " Command failed")

        self.logger.debug(out)

        return ret, out, err

    def copy_newconfig(self, cfg):
        if not os.path.exists(cfg):
            return -1, '', 'Config %s does not exists' % cfg
        copy(cfg, self.cfg)

    def make_kernel(self, flags=[], log=False, dryrun=False):
        assert_exists(self.cfg, "No config file found in %s" % self.cfg, logger=self.logger)
        return self._make_target(flags=flags, log=log, dryrun=dryrun)

    def merge_config(self, diff_cfg, dryrun=False):
        kobj = KernelConfig(self.cfg, logger=self.logger)
        kobj.merge_config(diff_cfg)

    def __str__(self):
        return self.uname
