#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Kernel test application
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
#            @v0.0 - Initial update
# @TODO    :
#
#

import os
import argparse
import logging
from klibs import KernelTest, supported_configs, supported_archs, supported_oldconfigs

def is_valid_dir(parser, arg):
    if not os.path.isdir(arg):
        yes = {'yes', 'y', 'ye', ''}
        print 'The directory {} does not exist'.format(arg)
        print 'Press y to create new directory'
        choice = raw_input().lower()
        if choice in yes:
            os.makedirs(arg)
        else:
            parser.error('The directory {} does not exist'.format(arg))

    return os.path.abspath(arg)

def is_valid_json(parser, arg):
    if not os.path.exists(arg):
        with open(arg, 'w'):
            pass

    return os.path.abspath(arg)

def add_cli_options(parser):

    subparsers = parser.add_subparsers(help='commands')

    compile_parser = subparsers.add_parser('compile', help='Run compile test')
    compile_parser.set_defaults(which='use_compile')

    sparse_parser = subparsers.add_parser('sparse', help='Run sparse test')
    sparse_parser.set_defaults(which='use_sparse')

    smatch_parser = subparsers.add_parser('smatch', help='Run smatch test')
    smatch_parser.set_defaults(which='use_smatch')

    checkpatch_parser = subparsers.add_parser('checkpatch', help='Run checkpatch test')
    checkpatch_parser.set_defaults(which='use_checkpatch')

    for sub_parser in [compile_parser, sparse_parser, smatch_parser]:
        sub_parser.add_argument('arch', choices=supported_archs, help='Arch to be tested')
        sub_parser.add_argument('--configs', default=[], nargs='*', dest='config_list',
                                help='Choose configs in %s' % (supported_configs + supported_oldconfigs))
        sub_parser.add_argument('--cflags', default=[], nargs='*', dest='cflags', help='cflags')
        sub_parser.add_argument('--cc', default='', dest='cc', help='Cross Compile')
        sub_parser.add_argument('--config-name', default='', dest='config_name', help='Config Name')
        sub_parser.add_argument('--config-src', default=None, dest='config_src', help='Config source')

    json_parser = subparsers.add_parser('use_json', help='Use given JSON file for test')
    json_parser.set_defaults(which='use_json')
    json_parser.add_argument('config_data', help='Json config file')

    parser.add_argument('-i', '--kernel-dir', action='store', dest='source_dir',
                        type=lambda x: is_valid_dir(parser, x),
                        default=os.getcwd(),
                        help='Kerenl source directory')
    parser.add_argument('--out', action='store', dest='out', default=None, help='Kerenl output directory')
    parser.add_argument('--out-json', action='store', dest='out_json', type=lambda x: is_valid_json(parser, x),
                        default=None, help='Kerenl output results json file')
    parser.add_argument('--branch', default=None, dest='branch', help='Kernel branch name')
    parser.add_argument('--rname', default=None, dest='rname', help='Kernel remote name')
    parser.add_argument('--rurl', default=None, dest='rurl', help='Kernel remote name')
    parser.add_argument('--head', default=None, dest='head', help='Head commit ID')
    parser.add_argument('--base', default=None, dest='base', help='Base commit ID')
    parser.add_argument('-l', '--log', action='store', dest='log_file',
                        nargs='?',
                        const=os.path.join(os.getcwd(), 'ktest.log'),
                        help='Kernel test log file')
    parser.add_argument('-d', '--debug', action='store_true', dest='debug',
                        help='Enable debug option')

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description='Script used for running automated kerenl compilation testing')

    add_cli_options(parser)

    args = parser.parse_args()

    if args.log_file is not None:
        if not os.path.exists(args.log_file):
            open(os.path.exists(args.log_file), 'w+').close()
            hdlr = logging.FileHandler(args.log_file)
            formatter = logging.Formatter('%(message)s')
            hdlr.setFormatter(formatter)
            logger.addHandler(hdlr)

    if args.debug:
            logger.setLevel(logging.DEBUG)

    print args

    obj= None

    if args.which == 'use_json':
        obj = KernelTest(args.source_dir, args.config_data, args.out, args.rname, args.rurl, args.branch,
                         args.head, args.base, args.out_json, logger=logger)
        obj.auto_test()
    else:
        obj = KernelTest(args.source_dir, None, args.out, args.rname, args.rurl, args.branch,
                         args.head, args.base, args.out_json, logger=logger)

    if obj:
        if args.which == 'use_compile':
            obj.compile_list(args.arch, args.config_list, args.cc, args.cflags, args.config_name, args.config_src)
        if args.which == 'use_sparse':
            obj.sparse_list(args.arch, args.config_list, args.cc, args.cflags, args.config_name, args.config_src)
        if args.which == 'use_smatch':
            obj.smatch_list(args.arch, args.config_list, args.cc, args.cflags, args.config_name, args.config_src)
        if args.which == 'use_checkpatch':
            obj.run_checkpatch()

        if args.out_json is not None:
            obj.dump_results(args.out_json)

        obj.print_results()

    else:
        logger.error("Invalid kernel output obj")
