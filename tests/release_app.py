#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Kernel release application
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
from klibs import KernelRelease

def is_valid_dir(parser, arg):
    if not os.path.isdir(arg):
        yes = {'yes', 'y', 'ye', ''}
        print('The directory {} does not exist'.format(arg))
        print('Press y to create new directory')
        choice = raw_input().lower()
        if choice in yes:
            os.makedirs(arg)
        else:
            parser.error('The directory {} does not exist'.format(arg))

    return os.path.abspath(arg)

def add_cli_options(parser):

    subparsers = parser.add_subparsers(help='commands')

    def tag_type(arg):
        tag_list = arg.split(',')
        return (tag_list[0], tag_list[1])

    bundle_parser = subparsers.add_parser('bundle', help='Create git bundle')
    bundle_parser.set_defaults(which='bundle')
    bundle_parser.add_argument('--mode', action='store', default='branch', dest='mode',
                               choices=['branch', 'diff', 'commit_count'],
                               help='git bundle mode')
    bundle_parser.add_argument('--count', action='store', type=int, default=0,
                               dest='commit_count',
                               help='Bundle commit count')
    bundle_parser.add_argument('--head', default=None, dest='head', help='Head commit ID')
    bundle_parser.add_argument('--base', default=None, dest='base', help='Base commit ID')

    quilt_parser = subparsers.add_parser('quilt', help='Create quilt patchset')
    quilt_parser.set_defaults(which='quilt')
    quilt_parser.add_argument('--head', default=None, dest='head', help='Head commit ID')
    quilt_parser.add_argument('--base', default=None, dest='base', help='Base commit ID')
    quilt_parser.add_argument('--sed-file', default=None, dest='sed_file', help='Sed file with regex')
    quilt_parser.add_argument('--audit-file', default=None, dest='audit_file', help='Audit script')

    tar_parser = subparsers.add_parser('tar', help='Create kernel tar source')
    tar_parser.set_defaults(which='tar')
    tar_parser.add_argument('--skip-files', default=['.git'], nargs='*', dest='skip_files', help='skip files')

    upload_parser = subparsers.add_parser('upload', help='Upload kernel to remote branch')
    upload_parser.set_defaults(which='upload')

    json_parser = subparsers.add_parser('use_json', help='Use given JSON file for release')
    json_parser.set_defaults(which='use_json')
    json_parser.add_argument('config_data', help='Json config file')

    for sub_parser in [bundle_parser, quilt_parser, tar_parser, upload_parser]:
        sub_parser.add_argument('--out', default=None, dest='outfile', help='output file/folder path')
        sub_parser.add_argument('--upload', action='store_true', dest='upload', help='upload the file/folder')
        sub_parser.add_argument('--branch', default=None, dest='branch', help='Kernel branch name')
        sub_parser.add_argument('--rname', default=None, dest='rname', help='Kernel remote name')
        sub_parser.add_argument('--rurl', default=None, dest='rurl', help='Kernel remote name')
        sub_parser.add_argument('--rbranch', default=None, dest='rbranch', help='Kernel remote branch name')
        sub_parser.add_argument('--rdir', default='.', dest='rdir', help='Remote patch directory')
        sub_parser.add_argument('--commit-msg', default="Quilt commit", dest='commit_msg',
                                  help='Commmit message')
        sub_parser.add_argument('--use-refs', action='store_true', dest='use_refs', help='use refs for push')
        sub_parser.add_argument('--force-push', action='store_true', dest='force_push', help='force push')
        sub_parser.add_argument('--clean-update', action='store_true', dest='clean_update', help='Clean update')
        sub_parser.add_argument('--tag-list', default=None, nargs='*', dest="tag_list", type=tag_type, help='tag list')


    parser.add_argument('-j', action='store_true', dest='use_json', help='Use Json parser')

    parser.add_argument('-i', '--kernel-dir', action='store', dest='source_dir',
                        type=lambda x: is_valid_dir(parser, x),
                        default=os.getcwd(),
                        help='Kerenl source directory')
    parser.add_argument('-l', '--log', action='store', dest='log_file',
                        nargs='?',
                        const=os.path.join(os.getcwd(), 'ktest.log'),
                        help='Kernel test log file')
    parser.add_argument('-d', '--debug', action='store_true', dest='debug',
                        help='Enable debug option')

if __name__ == "__main__":
    ret = True
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description='Script used for gnerating kernel output')

    add_cli_options(parser)

    args = parser.parse_args()

    print(args)

    if args.log_file is not None:
        if not os.path.exists(args.log_file):
            open(os.path.exists(args.log_file), 'w+').close()
            hdlr = logging.FileHandler(args.log_file)
            formatter = logging.Formatter('%(message)s')
            hdlr.setFormatter(formatter)
            logger.addHandler(hdlr)

    if args.debug:
        logger.setLevel(logging.DEBUG)

    if args.which == 'use_json':
        obj = KernelRelease(src=args.source_dir, cfg=args.config_data, logger=logger)
        obj.auto_release()
    else:
        obj = KernelRelease(src=args.source_dir, logger=logger)

    if obj:
        out = None
        if args.which == 'bundle':
            out = obj.generate_git_bundle(args.outfile, args.mode, args.branch, args.head, args.base, args.commit_count)

        if args.which == 'quilt':
            out = obj.generate_quilt(args.branch, args.base, args.head, args.outfile, args.sed_file, args.audit_file)

        if args.which == 'tar':
            obj.generate_tar_gz(args.outfile, args.branch, args.skip_files)

        if out is not None:
            obj.git_upload(out, None, True, None, args.commit_msg, False,
                           (args.rname, args.rurl, args.rbranch, args.rdir),
                           args.use_refs, args.force_push, args.clean_update,
                           args.tag_list)

    else:
        logger.error("Invalid kernel output obj")
