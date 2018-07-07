# -*- coding: utf-8 -*-
#
# Email class test script
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

from __future__ import absolute_import

import pkg_resources
import os
import unittest
import pyshell
import logging
import re
import kernel_libs as klibs

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(message)s')
logger.setLevel(logging.INFO)

class PyShellTest(unittest.TestCase):
    def test_email_cfg(self):
        cfg_file = pkg_resources.resource_filename('tests', 'config/email-config.json')
        email = klibs.Email(cfg=cfg_file, logger=logger)
        email.send_email("test", "Hi! How are you!!")
::

if __name__ == '__main__':
    unittest.main()