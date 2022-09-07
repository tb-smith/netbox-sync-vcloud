#!/usr/bin/env python3
# Pyvcloud Examples
#
# Copyright (c) 2017-2018 VMware, Inc. All Rights Reserved.
#
# This product is licensed to you under the
# Apache License, Version 2.0 (the "License").
# You may not use this product except in compliance with the License.
#
# This product may include a number of subcomponents with
# separate copyright notices and license terms. Your use of the source
# code for the these subcomponents is subject to the terms and
# conditions of the subcomponent's license, as noted in the LICENSE file.
#
# Illustrates how to list all vApps within a single vDC.

import sys
from pyvcloud.vcd.client import BasicLoginCredentials
from pyvcloud.vcd.client import Client
from pyvcloud.vcd.client import EntityType
from pyvcloud.vcd.org import Org
from pyvcloud.vcd.vdc import VDC
from pyvcloud.vcd.vapp import VApp
from pyvcloud.vcd.vm import VM
import requests

# Collect arguments.
if len(sys.argv) != 5:
    print("Usage: python3 {0} host org user password ".format(sys.argv[0]))
    sys.exit(1)
host = sys.argv[1]
org = sys.argv[2]
user = sys.argv[3]
password = sys.argv[4]
#vdc = sys.argv[5]

# Disable warnings from self-signed certificates.
requests.packages.urllib3.disable_warnings()

# Login. SSL certificate verification is turned off to allow self-signed
# certificates.  You should only do this in trusted environments.
print("Logging in: host={0}, org={1}, user={2}".format(host, org, user))
client = Client(host,
                verify_ssl_certs=False,
                log_file='pyvcloud.log',
                log_requests=True,
                log_headers=True,
                log_bodies=True)
client.set_highest_supported_version()
client.set_credentials(BasicLoginCredentials(user, org, password))

print("Fetching Org...")
org_resource = client.get_org()
org = Org(client, resource=org_resource)

vdc_list = org.list_vdcs()

print("Fetching VDC...")

allvm_org_list = dict()

for vdc in vdc_list: 
    vdc_name = (vdc['name'])
    vdc_resource = org.get_vdc(vdc_name)
    vdc = VDC(client, resource=vdc_resource)
    allvm_org_list[vdc_name] = {}
    print("Fetching vApps....")
    vapps = vdc.list_resources(EntityType.VAPP)
    vm_list = list()
    for vapp in vapps:
        vapp_name = vapp.get('name')
        vapp_resource = vdc.get_vapp(vapp_name)

        vapp_obj = VApp(client, resource=vapp_resource)
        #print(f"vapp_obj:{vapp_obj}")
        #print(type(vm_resource))

        print("Fetching VM...")
        vm_resource = vapp_obj.get_all_vms()
        # get vapp vm count first
        allvm_org_list[vdc_name][vapp_name] = []
        vapp_vm = list()
        for vm_res in vm_resource:
            
            vapp_vm = VM(client, resource=vm_res)
            vmName = vm_res.attrib["name"]
            #vapp_vm.list_virtual_hardware_section()
            allvm_org_list[vdc_name][vapp_name].append({
                'name': vmName, 
                'hardware': vapp_vm.list_virtual_hardware_section(is_disk=True),
                'network' : vapp_vm.list_nics()
                #'disk'    : vapp_vm.list_storage_profile() 

            })
            #print(f"vm_name:{vmName}") 
            break

        #print(type(vm_resource))
        break
print(f"vm info is {allvm_org_list}")
# Log out.
print("Logging out")
client.logout()
