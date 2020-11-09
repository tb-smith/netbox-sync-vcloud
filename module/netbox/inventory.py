
import pprint

import json

from ipaddress import ip_address, ip_network, ip_interface, IPv6Network, IPv4Network, IPv4Address, IPv6Address


from module.netbox.object_classes import *
from module.common.logging import get_logger
from module.common.support import perform_ptr_lookups

log = get_logger()

class NetBoxInventory:

    base_structure = dict()
    resolved_dependencies = list()

    primary_tag = None

    def __init__(self):
        for object_type in NetBoxObject.__subclasses__():

            self.base_structure[object_type.name] = list()


    def get_by_id(self, object_type, id=None):

        if object_type not in NetBoxObject.__subclasses__():
            raise AttributeError("'%s' object must be a sub class of '%s'." %
                                 (object_type.__name__, NetBoxObject.__name__))

        if id is None or self.base_structure[object_type.name] is None:
            return None

        for object in self.base_structure[object_type.name]:

            if object.nb_id == id:
                return object


    def get_by_data(self, object_type, data=None):

        if object_type not in NetBoxObject.__subclasses__():
            raise AttributeError("'%s' object must be a sub class of '%s'." %
                                 (object_type.__name__, NetBoxObject.__name__))


        if data is None or len(self.get_all_items(object_type)) == 0:
            return

        if not isinstance(data, dict):
            raise ValueError(f"Attribute data must be type 'dict' got: {data}")

        # shortcut if data contains valid id
        data_id = data.get("id")
        if data_id is not None and data_id != 0:
            return self.get_by_id(object_type, id=data_id)

        # try to find by name
        if data.get(object_type.primary_key) is not None:
            object_name_to_find = None
            results = list()
            for object in self.get_all_items(object_type):

                if object_name_to_find is None:
                    object_name_to_find = object.get_display_name(data, including_second_key=True)

                if object_name_to_find == object.get_display_name(including_second_key=True):
                    return object

            """
                # Todo:
                #   * try to compare second key if present.

                if object_name_to_find is None:
                    object_name_to_find = object.get_display_name(data)

                if object_name_to_find == object.get_display_name():
                    results.append(object)

            # found exactly one match
            # ToDo:
            # * add force secondary key if one object has a secondary key

            if len(results) == 1:
                #print(f"found exact match: {object_name_to_find}")
                return results[0]

            # compare secondary key
            elif len(results) > 1:

                object_name_to_find = None
                for object in results:

                    if object_name_to_find is None:
                        object_name_to_find = object.get_display_name(data, including_second_key=True)
                        #print(f"get_by_data(): Object Display Name: {object_name_to_find}")

                    if object_name_to_find == object.get_display_name(including_second_key=True):
                        return object
            """

        # try to match all data attributes
        else:

            for object in self.get_all_items(object_type):
                all_items_match = True
                for attr_name, attr_value in data.items():

                    if object.data.get(attr_name) != attr_value:
                        all_items_match = False
                        break

                if all_items_match == True:
                    return object

                """
                if data.get(object_type.primary_key) is not None and \
                    object.resolve_attribute(object_type.primary_key) == object.resolve_attribute(object_type.primary_key, data=data):

                    # object type has a secondary key, lets check if it matches
                    if getattr(object_type, "secondary_key", None) is not None and data.get(object_type.secondary_key) is not None:

                        if object.resolve_attribute(object_type.secondary_key) == object.resolve_attribute(object_type.secondary_key, data=data):
                            return_data.append(object)

                    # object has no secondary key but the same name, add to list
                    else:
                        return_data.append(object)
                """
        return None

    def add_item_from_netbox(self, object_type, data=None):
        """
        only to be used if data is read from NetBox and added to inventory
        """

        # create new object
        new_object = object_type(data, read_from_netbox=True, inventory=self)

        # add to inventory
        self.base_structure[object_type.name].append(new_object)

        return

    def add_update_object(self, object_type, data=None, read_from_netbox=False, source=None):

        if data is None:
            # ToDo:
            #   * proper error handling
            log.error("NO DATA")
            return

        this_object = self.get_by_data(object_type, data=data)

        if this_object is None:
            this_object = object_type(data, read_from_netbox=read_from_netbox, inventory=self, source=source)
            self.base_structure[object_type.name].append(this_object)
            if read_from_netbox is False:
                log.debug(f"Created new {this_object.name} object: {this_object.get_display_name()}")

        else:
            this_object.update(data, read_from_netbox=read_from_netbox, source=source)
            log.debug2("Updated %s object: %s" % (this_object.name, this_object.get_display_name()))

        return this_object

    def resolve_relations(self):

        log.debug("Start resolving relations")
        for object_type in NetBoxObject.__subclasses__():

            for object in self.get_all_items(object_type):

                object.resolve_relations()

        log.debug("Finished resolving relations")

    def get_all_items(self, object_type):

        if object_type not in NetBoxObject.__subclasses__():
            raise ValueError("'%s' object must be a sub class of '%s'." %
                                 (object_type.__name__, NetBoxObject.__name__))

        return self.base_structure.get(object_type.name, list())


    def get_all_interfaces(self, object):

        if not isinstance(object, (NBVMs, NBDevices)):
            raise ValueError(f"Object must be a '{NBVMs.name}' or '{NBDevices.name}'.")

        interfaces = list()
        if isinstance(object, NBVMs):
            for int in self.get_all_items(NBVMInterfaces):
                if grab(int, "data.virtual_machine") == object:
                    interfaces.append(int)

        if isinstance(object, NBDevices):
            for int in self.get_all_items(NBInterfaces):
                if grab(int, "data.device") == object:
                    interfaces.append(int)

        return interfaces


    def tag_all_the_things(self, netbox_handler):

        # ToDo:
        # * DONE: add main tag to all objects retrieved from a source
        # * Done: add source tag all objects of that source
        # * check for orphaned objects
        #   * DONE: objects tagged by a source but not present in source anymore (add)
        #   * DONE: objects tagged as orphaned but are present again (remove)


        for object_type in NetBoxObject.__subclasses__():

            for object in self.get_all_items(object_type):

                # if object was found in source
                if object.source is not None:
                    object.add_tags([netbox_handler.primary_tag, object.source.source_tag])

                    # if object was orphaned remove tag again
                    if netbox_handler.orphaned_tag in object.get_tags():
                        object.remove_tags(netbox_handler.orphaned_tag)

                # if object was tagged by this program in previous runs but is not present
                # anymore then add the orphaned tag
                else:
                    if netbox_handler.primary_tag in object.get_tags():
                        object.add_tags(netbox_handler.orphaned_tag)

    def update_all_ip_addresses(self):

        def _return_longest_match(ip_to_match=None, list_of_prefixes=None):

            if ip_to_match is None or list_of_prefixes is None:
                return

            if not isinstance(ip_to_match, (IPv4Address, IPv6Address)):
                try:
                    ip_to_match = ip_address(ip_to_match)
                except ValueError:
                    return

            if not isinstance(list_of_prefixes, list):
                return

            sanatized_list_of_prefixes = list()
            for prefix in list_of_prefixes:

                if not isinstance(prefix, (IPv4Network, IPv6Network)):
                    try:
                        sanatized_list_of_prefixes.append(ip_network(prefix))
                    except ValueError:
                        return
                else:
                    sanatized_list_of_prefixes.append(prefix)

            current_longest_matching_prefix_length = 0
            current_longest_matching_prefix = None

            for prefix in sanatized_list_of_prefixes:

                if ip_to_match in prefix and \
                    prefix.prefixlen >= current_longest_matching_prefix_length:

                    current_longest_matching_prefix_length = prefix.prefixlen
                    current_longest_matching_prefix = prefix

            return current_longest_matching_prefix


        log.info("Trying to math IPs to existing prefixes")

        all_prefixes = self.get_all_items(NBPrefixes)
        all_addresses = self.get_all_items(NBIPAddresses)

        # store IP addresses to look them up in bulk
        ip_lookup_dict = dict()

        # prepare prefixes
        # dict of simple prefixes to pass to function for longest match
        prefixes_per_site = dict()
        # dict of prefix objects so we don't need to search for them again
        prefixes_per_site_objects = dict()
        for this_prefix in all_prefixes:

            # name of the site or None (as string)
            prefix_site = str(grab(this_prefix, "data.site.data.name"))

            if prefixes_per_site.get(prefix_site) is None:
                prefixes_per_site[prefix_site] = list()
                prefixes_per_site_objects[prefix_site] = dict()

            prefix = ip_network(grab(this_prefix, "data.prefix"))

            prefixes_per_site[prefix_site].append(prefix)

            prefixes_per_site_objects[prefix_site][str(prefix)] = this_prefix


        # iterate over all IP addresses and try to match them to a prefix
        for ip in all_addresses:

            # ignore IPs which are not handled by any source
            if ip.source is None:
                continue

            # ignore unassigned IPs
            if grab(ip, "data.assigned_object_id") is None:
                continue

            # get IP and prefix length
            ip_a, ip_prefix_length = grab(ip, "data.address", fallback="").split("/")

            # check if we meant to look up DNS host name for this IP
            if grab(ip, "source.dns_name_lookup", fallback=False) is True:

                if ip_lookup_dict.get(ip.source) is None:

                    ip_lookup_dict[ip.source] = {
                        "ips": list(),
                        "servers": grab(ip, "source.custom_dns_servers")
                    }

                ip_lookup_dict[ip.source].get("ips").append(ip_a)


            object_site = "None"
            assigned_device_vm = None
            # name of the site or None (as string)
            # -> NBInterfaces -> NBDevices -> NBSites
            if grab(ip, "data.assigned_object_type") == "dcim.interface":
                object_site = str(grab(ip, "data.assigned_object_id.data.device.data.site.data.name"))
                assigned_device_vm = grab(ip, "data.assigned_object_id.data.device")

            # -> NBVMInterfaces -> NBVMs -> NBClusters -> NBSites
            elif grab(ip, "data.assigned_object_type") == "virtualization.vminterface":
                object_site = str(grab(ip, "data.assigned_object_id.data.virtual_machine.data.cluster.data.site.data.name"))
                assigned_device_vm = grab(ip, "data.assigned_object_id.data.virtual_machine")

            # set/update/remove primary IP addresses


            log.debug2("Trying to find prefix for IP: %s" % ip.get_display_name())

            log.debug2(f"Site name for this IP: {object_site}")


            # test site prefixes first
            matching_site_name = object_site
            matching_site_prefix = _return_longest_match(ip_a, prefixes_per_site.get(object_site))

            # nothing was found then check prefixes with site name
            if matching_site_prefix is None:

                matching_site_name = "None"
                matching_site_prefix = _return_longest_match(ip_a, prefixes_per_site.get(matching_site_name))

            # no matching prefix found, give up
            if matching_site_prefix is None:
                continue

            log.debug2(f"Found IP '{ip_a}' matches prefix '{matching_site_prefix}' in site '{matching_site_name.replace('None', 'undefined')}'")

            # get matching prefix object
            prefix_object = prefixes_per_site_objects.get(matching_site_name).get(str(matching_site_prefix))

            if prefix_object is None:
                continue

            # check if prefix net size and ip address prefix length match
            if matching_site_prefix.prefixlen != int(ip_prefix_length):
                interface_object = grab(ip, "data.assigned_object_id")
                log.warning(f"IP prefix length of '{ip_a}/{ip_prefix_length}' ({interface_object.get_display_name()}) doesn't match network prefix length '{matching_site_prefix}'!")

            data = dict()

            vrf = grab(prefix_object, "data.vrf.id")
            tenant = grab(prefix_object, "data.tenant.id")

            if vrf is not None and str(vrf) != str(grab(ip, "data.vrf.id")):
                data["vrf"] = vrf

            # only overwrite tenant if not already defined
            # ToDo: document behavior
            if tenant is not None and grab(ip, "data.tenant.id") is None and str(tenant) != str(grab(ip, "data.tenant.id")):
                data["tenant"] = tenant

            if len(data.keys()) > 0:
                ip.update(data=data)


        log.debug("Starting to look up PTR records for IP addresses")

        # now perform DNS requests to look up DNS names for IP addresses
        for source, data in ip_lookup_dict.items():

            if len(data.get("ips")) == 0:
                continue

            # get DNS names for IP addresses:
            records = perform_ptr_lookups(data.get("ips"), data.get("servers"))

            for ip in all_addresses:

                if ip.source != source:
                    continue

                ip_a = grab(ip, "data.address", fallback="").split("/")[0]

                dns_name = records.get(ip_a)

                if dns_name is not None:

                    ip.update(data = {"dns_name": dns_name})

        log.debug("Finished to look up PTR records for IP addresses")

    def set_primary_ips(self):

        for nb_object_class in [NBDevices, NBVMs]:

            for object in self.get_all_items(nb_object_class):

                if object.source is None:
                    continue

                if nb_object_class == NBDevices:

                    log.debug2(f"Trying to find ESXi Management Interface for '{object.get_display_name()}'")

                    management_interface = None
                    for interface in self.get_all_items(NBInterfaces):

                        if grab(interface, "data.device") == object:

                            if "management" in grab(interface, "data.description", fallback="").lower():
                                management_interface = interface
                                break

                    if management_interface is None:
                        continue

                    log.debug2(f"Found Management interface '{management_interface.get_display_name()}'")

                    ipv4_assigned = False
                    ipv6_assigend = False

                    for ip in self.get_all_items(NBIPAddresses):

                        #if grab(ip, "data.address") == "10.100.5.28/24":
                        #    print(ip)
                         #   print(management_interface)

                        if grab(ip, "data.assigned_object_id") == management_interface:

                            log.debug2(f"Found Management IP '{ip.get_display_name()}'")

                            ip_version = None

                            try:
                                ip_version = ip_address(grab(ip, "data.address", fallback="").split("/")[0]).version
                            except ValueError:
                                pass

                            if ip_version == 4 and ipv4_assigned == False:
                                log.debug2(f"Assigning IP '{ip.get_display_name()}' as primary IP v4 address to '{object.get_display_name()}'")
                                if grab(object, "data.primary_ip4.address") != grab(ip, "data.address"):
                                    object.update(data = {"primary_ip4": ip.nb_id})
                                    ipv4_assigned = True
                                else:
                                    log.debug2("primary IP v4 did not change")

                            if ip_version == 6 and ipv6_assigned == False:
                                log.debug2(f"Assigning IP '{ip.get_display_name()}' as primary IP v6 address to '{object.get_display_name()}'")
                                if grab(object, "data.primary_ip6.address") != grab(ip, "data.address"):
                                    object.update(data = {"primary_ip6": ip.nb_id})
                                    ipv6_assigned = True
                                else:
                                    log.debug2("primary IP v6 did not change")


                #if nb_object_class == NBDevices:

    def to_dict(self):

        output = dict()
        for nb_object_class in NetBoxObject.__subclasses__():

            output[nb_object_class.name] = list()

            for object in self.base_structure[nb_object_class.name]:
                output[nb_object_class.name].append(object.to_dict())

        return output

    def __str__(self):

        return json.dumps(self.to_dict(), sort_keys=True, indent=4)

# EOF
