#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Kernel integration application
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
import yaml
import argparse
import logging
from klibs import KernelInteg

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

def setup_logging(default_path, default_level=logging.INFO, env_key='LOG_CFG'):
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = yaml.safe_load(f.read())
            logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)

    return logging.getLogger(__name__)

def add_cli_options(parser):

    parser.add_argument('config', action='store', help='staging config')

    parser.add_argument('-i', '--repo-dir', action='store', dest='repo_dir',
                        type=lambda x: is_valid_dir(parser, x),
                        default=os.getcwd(),
                        help='Kerenl repo directory')
    parser.add_argument('--email-config', action='store', dest='emailcfg',
                        default=None,
                        help='Email config')
    parser.add_argument('--skip-dep', action='store_true', dest='skip_dep',
                        default=False,
                        help='skip creating dependent repos')
    parser.add_argument('--name', action='store', dest='repo_name', default=None, help='Integrate specific repo')
    parser.add_argument('--kernel-head', action='store', dest='kernel_tag', default=None,
                        help='SHA ID or tag of kernel HEAD')



if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description='Script used for dev-bkc/LTS Kerenl Integration')

    add_cli_options(parser)

    args = parser.parse_args()

    obj = KernelInteg(args.repo_dir, os.path.abspath(args.config), args.kernel_tag, args.emailcfg, logger=logger)

    obj.start(args.repo_name, args.skip_dep)
