# -*- coding: utf-8 -*-
#  for load data from vmWare vCloud Director try onne
#  netbox-sync.py
#
#  This work is licensed under the terms of the MIT license.
#  For a copy, see file LICENSE.txt included in this
#  repository or visit: <https://opensource.org/licenses/MIT>.

from ipaddress import ip_network
import os
import glob
import json
#from xml.etree.ElementTree import tostring

from packaging import version

from module.sources.common.source_base import SourceBase
from module.common.logging import get_logger
from module.common.misc import grab, get_string_or_none
from module.common.support import normalize_mac_address, ip_valid_to_add_to_netbox
from module.netbox.object_classes import (
    NetBoxInterfaceType,
    NBTag,
    NBManufacturer,
    NBDeviceType,
    NBPlatform,
    NBClusterType,
    NBClusterGroup,
    NBDeviceRole,
    NBSite,
    NBCluster,
    NBDevice,
    NBInterface,
    NBIPAddress,
    NBPrefix,
    NBTenant,
    NBVRF,
    NBVLAN,
    NBPowerPort,
    NBInventoryItem,
    NBCustomField
)

# Import Modules for Vcloud Director
import sys
from pyvcloud.vcd.client import BasicLoginCredentials
from pyvcloud.vcd.client import Client
from pyvcloud.vcd.client import EntityType
from pyvcloud.vcd.org import Org
from pyvcloud.vcd.vdc import VDC
import requests

log = get_logger()


class CheckCloudDirector(SourceBase):
    """
    Source class to import check_redfish inventory files
    """

    dependent_netbox_objects = [
        NBTag,
        NBManufacturer,
        NBDeviceType,
        NBPlatform,
        NBClusterType,
        NBClusterGroup,
        NBDeviceRole,
        NBSite,
        NBCluster,
        NBDevice,
        NBInterface,
        NBIPAddress,
        NBPrefix,
        NBTenant,
        NBVRF,
        NBVLAN,
        NBPowerPort,
        NBInventoryItem,
        NBCustomField
    ]

    settings = {
        "enabled": True,
        "vcloud_url": None,
        "username": None,
        "password": None,
        "vcloud_org": None,
        "permitted_subnets": None,
        "overwrite_host_name": False,
        "overwrite_interface_name": False,
        "overwrite_interface_attributes": True,
    }

    init_successful = False
    inventory = None
    name = None
    source_tag = None
    source_type = "vcloud_director"
    enabled = False
    pyVcloudSession = None
    device_object = None    

    def __init__(self, name=None, settings=None, inventory=None):
  
        if name is None:
            raise ValueError(f"Invalid value for attribute 'name': '{name}'.")

        self.inventory = inventory
        self.name = name

        self.parse_config_settings(settings)

        self.source_tag = f"Source: {name}"

        self.pyVcloudSession = self.create_api_session(settings)

        if self.enabled is False:
            log.info(f"Source '{name}' is currently disabled. Skipping")
            return

        # self.init_successful = True

        # self.interface_adapter_type_dict = dict()

        self.pyVcloudSession.logout()

    def parse_config_settings(self, config_settings):
        """
        Validate parsed settings from config file

        Parameters
        ----------
        config_settings: dict
            dict of config settings

        """

        validation_failed = False
        for setting in ["vcloud_url", "vlcoud_org", "username", "password"]:
            # for debug
            #print('setting is:\n', tostring(setting) )
            if config_settings.get(setting) is None:
                log.error(f"Config option '{setting}' in 'source/{self.name}' can't be empty/undefined")
                validation_failed = True

    def apply(self):
        """
        Main source handler method. This method is called for each source from "main" program
        to retrieve data from it source and apply it to the NetBox inventory.

        Every update of new/existing objects fot this source has to happen here.

        First try to find and iterate over each inventory file.
        Then parse the system data first and then all components.
        """
        self.add_necessary_base_objects()

        object_mapping = {
            "datacenter": {
                "view_type": vim.Datacenter,
                "view_handler": self.add_datacenter
            },
            "cluster": {
                "view_type": vim.ClusterComputeResource,
                "view_handler": self.add_cluster
            },
            "network": {
                "view_type": vim.dvs.DistributedVirtualPortgroup,
                "view_handler": self.add_port_group
            },
            "host": {
                "view_type": vim.HostSystem,
                "view_handler": self.add_host
            },
            "virtual machine": {
                "view_type": vim.VirtualMachine,
                "view_handler": self.add_virtual_machine
            },
            "offline virtual machine": {
                "view_type": vim.VirtualMachine,
                "view_handler": self.add_virtual_machine
            }
        }

    def add_necessary_base_objects(self):
        """
        Adds/updates source tag and all custom fields necessary for this source.
        """

        # add source identification tag
        self.inventory.add_update_object(NBTag, data={
            "name": self.source_tag,
            "description": f"Marks objects synced from vcloud director '{self.name}' to this NetBox Instance."
        })

    def create_api_session(self, settings):
        #print(settings)
        log.info(f"Create API session for '{self.name}'")
        client = Client(settings['vcloud_url'],
            verify_ssl_certs=True,
            log_file='pyvcloud.log',
            log_requests=True,
            log_headers=True,
            log_bodies=True)
        client.set_highest_supported_version()
        client.set_credentials(BasicLoginCredentials(settings['username'], settings['vcloud_org'], settings['password']))
        self.enabled = True
        return client