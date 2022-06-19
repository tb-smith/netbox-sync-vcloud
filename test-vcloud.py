
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#  Copyright (c) 2020 - 2022 Ricardo Bartels. All rights reserved.
#
#  netbox-sync.py
#
#  This work is licensed under the terms of the MIT license.
#  For a copy, see file LICENSE.txt included in this
#  repository or visit: <https://opensource.org/licenses/MIT>.

self_description = """
Sync objects from various sources to NetBox
"""


from datetime import datetime

from module.common.misc import grab, get_relative_time
from module.common.cli_parser import parse_command_line
from module.common.logging import setup_logging
from module.common.configuration import get_config_file, open_config_file, get_config
from module.netbox.connection import NetBoxHandler
from module.netbox.inventory import NetBoxInventory
from module.netbox.object_classes import *
from module.sources import instantiate_sources


default_config_file_path = "./settings.ini"
args = parse_command_line(self_description=self_description,
                          version=__version__,
                          version_date=__version_date__,
                          url=__url__,
                          default_config_file_path=default_config_file_path)

# get config file path
config_file = get_config_file(args.config_file)

# get config handler
config_handler = open_config_file(config_file)