# -*- coding: utf-8 -*-
#  for load data from vmWare vCloud Director try onne
#  netbox-sync.py
#
#  This work is licensed under the terms of the MIT license.
#  For a copy, see file LICENSE.txt included in this
#  repository or visit: <https://opensource.org/licenses/MIT>.
# based on Pyvcloud Examples list-vapps.py  

from ipaddress import ip_network
import os
import glob
import json
import re
import math
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
from pyvcloud.vcd.vapp import VApp
from pyvcloud.vcd.vm import VM
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
        "cluster_tenant_relation": None,
        "cluster_site_relation": None,
        "vdc_include_filter": None,
        "vdc_exclude_filter": None
    }

    init_successful = False
    inventory = None
    name = None
    source_tag = None
    source_type = "vcloud_director"
    enabled = False
    vcloudClient = None
    device_object = None
    site_name = None
    #vcd_org     

    def __init__(self, name=None, settings=None, inventory=None):
  
        if name is None:
            raise ValueError(f"Invalid value for attribute 'name': '{name}'.")

        self.inventory = inventory
        self.name = name

        self.parse_config_settings(settings)

        self.source_tag = f"Source: {name}"
        self.site_name = f"vCloudDirector: {name}"

        self.create_api_session(settings)

        if self.enabled is False:
            log.info(f"Source '{name}' is currently disabled. Skipping")
            return

        self.init_successful = True

        self.permitted_clusters = dict()
        # self.interface_adapter_type_dict = dict()


    def parse_config_settings(self, config_settings):
        """
        Validate parsed settings from config file

        Parameters
        ----------
        config_settings: dict
            dict of config settings

        """
        
        validation_failed = False
        for setting in ["vcloud_url", "vcloud_org", "username", "password"]:
            if config_settings.get(setting) is None:
                log.error(f"Config option '{setting}' in 'source/{self.name}' can't be empty/undefined")
                validation_failed = True

        for relation_option in [x for x in self.settings.keys() if "relation" in x]:
            
            if config_settings.get(relation_option) is None:
                continue

            relation_data = list()

            relation_type = relation_option.split("_")[1]

            # obey quotations to be able to add names including a comma
            # thanks to: https://stackoverflow.com/a/64333329
            for relation in re.split(r",(?=(?:[^\"']*[\"'][^\"']*[\"'])*[^\"']*$)",
                                     config_settings.get(relation_option)):

                object_name = relation.split("=")[0].strip(' "')
                relation_name = relation.split("=")[1].strip(' "')

                if len(object_name) == 0 or len(relation_name) == 0:
                    log.error(f"Config option '{relation}' malformed got '{object_name}' for "
                              f"object name and '{relation_name}' for {relation_type} name.")
                    validation_failed = True

                try:
                    re_compiled = re.compile(object_name)
                except Exception as e:
                    log.error(f"Problem parsing regular expression '{object_name}' for '{relation}': {e}")
                    validation_failed = True
                    continue

                relation_data.append({
                    "object_regex": re_compiled,
                    f"assigned_name": relation_name
                })

            config_settings[relation_option] = relation_data


    def apply(self):
        """
        Main source handler method. This method is called for each source from "main" program
        to retrieve data from it source and apply it to the NetBox inventory.

        Every update of new/existing objects fot this source has to happen here.

        First try to find and iterate over each inventory file.
        Then parse the system data first and then all components.
        """
        # add tags
        self.add_necessary_base_objects()
        
        vdc_org = self.get_vcloud_org(self.vcloudClient)
        self.add_datacenter( {"name": vdc_org.get_name() } )

        vdc_list = self.get_vdc_list(vdc_org)

        allvm_org_list = dict()

        for vdc in vdc_list:
            log.info(f"Add virtual cluster for '{vdc_org.get_name()}")
            self.add_cluster(vdc,vdc_org.get_name())
            #print(vdc)
            vm_list = list()
            vdc_resource = vdc_org.get_vdc(vdc['name'])
            vdc_obj = VDC(self.vcloudClient, resource=vdc_resource)
            vapp_list = vdc_obj.list_resources(EntityType.VAPP)
            for vapp in vapp_list:
                vapp_name = vapp.get('name')
                vapp_resource = vdc_obj.get_vapp(vapp_name)
                vapp_obj = VApp(self.vcloudClient, resource=vapp_resource)
                vm_resource = vapp_obj.get_all_vms()
                log.debug(f"Found '{len(vm_resource)}' vm in '{vapp_name}'")
                # get vapp vm count first
                #allvm_org_list[vdc['name']][vapp_name] = []
                vapp_vm = list()
                for vm_res in vm_resource:
                    log.debug(f"Get vm data ....")
                    vapp_vm = VM(self.vcloudClient, resource=vm_res)
                    vmName = vm_res.attrib["name"]
                    #allvm_org_list[vdc_name][vapp_name].append({
                    vm_data = {
                        'name'    : vmName, 
                        'active'  : vapp_vm.is_powered_on(),
                        'hardware': vapp_vm.list_virtual_hardware_section(is_disk=True),
                        'network' : vapp_vm.list_nics()
                    }
                    disk_size = 0
                    for hw_element in vm_data['hardware']:
                        if grab(hw_element,'diskElementName'):
                            disk_size += grab(hw_element,'diskVirtualQuantityInBytes')
                    # get disk size in GB
                    p = math.pow(1024, 3)
                    disk_size = round(disk_size / p, 0)
                    print(f"disk is: '{disk_size}' GB for '{vmName}'" )
                    
                    break

                #print(type(vm_resource))
                break
        #for view_name, view_details in object_mapping.items():
        self.vcloudClient.logout()


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
        requests.packages.urllib3.disable_warnings()
        client = Client(settings['vcloud_url'],
            verify_ssl_certs=True,
            log_file='pyvcloud.log',
            log_requests=True,
            log_headers=True,
            log_bodies=True)
        client.set_highest_supported_version()
        client.set_credentials(BasicLoginCredentials(settings['username'], settings['vcloud_org'], settings['password']))
        self.enabled = True
        self.vcloudClient = client

    def get_vcloud_org(self, client):
        org_resource = client.get_org()
        return Org(client, resource=org_resource)        

    def get_vdc_list(self, org):
        vdc_list = org.list_vdcs()
        return vdc_list

    def get_vapp(self, vdc):
        vapp_list = False
        return vapp_list

    @staticmethod
    def passes_filter(name, include_filter, exclude_filter):
        """
        checks if object name passes a defined object filter.

        Parameters
        ----------
        name: str
            name of the object to check
        include_filter: regex object
            regex object of include filter
        exclude_filter: regex object
            regex object of exclude filter

        Returns
        -------
        bool: True if all filter passed, otherwise False
        """

        # first includes
        if include_filter is not None and not include_filter.match(name):
            log.debug(f"Object '{name}' did not match include filter '{include_filter.pattern}'. Skipping")
            return False

        # second excludes
        if exclude_filter is not None and exclude_filter.match(name):
            log.debug(f"Object '{name}' matched exclude filter '{exclude_filter.pattern}'. Skipping")
            return False

        return True


    def get_object_relation(self, name, relation, fallback=None):
        """

        Parameters
        ----------
        name: str
            name of the object to find a relation for
        relation: str
            name of the config variable relation (i.e: vm_tag_relation)
        fallback: str
            fallback string if no relation matched

        Returns
        -------
        data: str, list, None
            string of matching relation or list of matching tags
        """

        resolved_list = list()
        for single_relation in grab(self, relation, fallback=list()):
            object_regex = single_relation.get("object_regex")
            if object_regex.match(name):
                resolved_name = single_relation.get("assigned_name")
                log.debug2(f"Found a matching {relation} '{resolved_name}' ({object_regex.pattern}) for {name}.")
                resolved_list.append(resolved_name)

        if grab(f"{relation}".split("_"), "1") == "tag":
            return resolved_list

        else:
            resolved_name = fallback
            if len(resolved_list) >= 1:
                resolved_name = resolved_list[0]
                if len(resolved_list) > 1:
                    log.debug(f"Found {len(resolved_list)} matches for {name} in {relation}."
                              f" Using first on: {resolved_name}")

            return resolved_name


    def get_site_name(self, object_type, object_name, cluster_name=""):
        """
        Return a site name for a NBCluster or NBDevice depending on config options
        host_site_relation and cluster_site_relation

        Parameters
        ----------
        object_type: (NBCluster, NBDevice)
            object type to check site relation for
        object_name: str
            object name to check site relation for
        cluster_name: str
            cluster name of NBDevice to check for site name

        Returns
        -------
        str: site name if a relation was found
        """

        if object_type not in [NBCluster, NBDevice]:
            raise ValueError(f"Object must be a '{NBCluster.name}' or '{NBDevice.name}'.")

        log.debug2(f"Trying to find site name for {object_type.name} '{object_name}'")

        # check if site was provided in config
        relation_name = "host_site_relation" if object_type == NBDevice else "cluster_site_relation"

        site_name = self.get_object_relation(object_name, relation_name)

        if object_type == NBDevice and site_name is None:
            site_name = self.permitted_clusters.get(cluster_name) or \
                        self.get_site_name(NBCluster, object_name, cluster_name)
            log.debug2(f"Found a matching cluster site for {object_name}, using site '{site_name}'")

        # set default site name
        if site_name is None:
            site_name = self.site_name
            log.debug(f"No site relation for '{object_name}' found, using default site '{site_name}'")

        return site_name


    def add_datacenter(self, obj):
        """
        Add a cloud director org as a NBClusterGroup to NetBox

        Parameters
        ----------
        obj: name: value

        """        
        name = get_string_or_none(grab(obj, "name"))

        if name is None:
            return

        log.debug(f"Parsing cloud director org: {name}")

        self.inventory.add_update_object(NBClusterGroup, data={"name": name}, source=self)

    def add_cluster(self, obj, group):
        """
        Add a vCloud director VDC as a NBCluster to NetBox. Cluster name is checked against
        cluster_include_filter and cluster_exclude_filter config setting. Also adds
        cluster and site_name to "self.permitted_clusters" so hosts and VMs can be
        checked if they are part of a permitted cluster.

        Parameters
        ----------
        obj: vim.ClusterComputeResource
            cluster to add
        """

        name = get_string_or_none(grab(obj, "name"))

        site_name = self.get_object_relation(name, 'cluster_site_relation')
        log.debug(f"Try get '{self.settings['vcloud_org']}' site_relation for '{self.settings['cluster_site_relation']}'  is a '{site_name}'")

        #group = get_string_or_none(grab(obj, "parent.parent.name"))

        if name is None or group is None:
            return

        log.debug(f"Parsing vcloud VDC: {name}")
        # need add filter
        #if self.passes_filter(name, self.vdc_include_filter, self.vdc_exclude_filter) is False:
        #    return


        # need add mapping for site name from cfg
        site_name = self.get_site_name(NBCluster, name)       

        data = {
            "name": name,
            "type": {"name": "vCloud director VDC"},
            "group": {"name": group},
            "site": {"name": site_name}
        }
        
        tenant_name = self.get_object_relation(name, "cluster_tenant_relation")
        if tenant_name is not None:
            data["tenant"] = {"name": tenant_name}
        #
        #cluster_tags = self.get_object_relation(name, "cluster_tag_relation")
        #cluster_tags.extend(self.get_object_tags(obj))
        #if len(cluster_tags) > 0:
        #    data["tags"] = cluster_tags

        self.inventory.add_update_object(NBCluster, data=data, source=self)

        self.permitted_clusters[name] = site_name
    
    def add_virtual_machine(self, obj):
        """
        Parse a VDC VM add to NetBox once all data is gathered.

        Parameters
        ----------
        obj: 
            virtual machine object to parse
        """
        
        name = obj.name
       
        log.debug(f"Parsing VCD VM: {name}")

        # get VM power state
        status = "active" if get_string_or_none(obj.active) else "offline"

    def update_basic_data(self):
        """
        Returns
        -------

        """

        # add source identification tag
        self.inventory.add_update_object(NBTag, data={
            "name": self.source_tag,
            "description": f"Marks objects synced from vCenter '{self.name}' "
                           f"({self.host_fqdn}) to this NetBox Instance."
        })

        # update virtual site if present
        this_site_object = self.inventory.get_by_data(NBSite, data={"name": self.site_name})

        if this_site_object is not None:
            this_site_object.update(data={
                "name": self.site_name,
                "comments": f"A default virtual site created to house objects "
                            "that have been synced from this vCenter instance "
                            "and have no predefined site assigned."
            })