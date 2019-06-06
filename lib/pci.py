# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: 2019 IBM
# Author: Narasimhan V <sim@linux.vnet.ibm.com>

"""
Module for all PCI devices related functions.
"""


import re
import os
import commands
import platform


def get_domains():
    """
    Gets all PCI domains.
    Example, it returns ['0000', '0001', ...]

    :return: List of PCI domains.
    """
    cmd = "lspci -D"
    output = commands.getoutput(cmd)
    if output:
        domains = []
        for line in output.splitlines():
            domains.append(line.split(":")[0])
        return list(set(domains))
    return []


def get_pci_addresses():
    """
    Gets list of PCI addresses in the system.
    Does not return the PCI Bridges/Switches.

    :return: list of full PCI addresses including domain (0000:00:14.0)
    """
    addresses = []
    cmd = "lspci -D"
    for line in commands.getoutput(cmd).splitlines():
        if not get_pci_prop(line.split()[0], 'Class').startswith('06'):
            addresses.append(line.split()[0])
    return addresses


def get_num_interfaces_in_pci(dom_pci_address):
    """
    Gets number of interfaces of a given partial PCI address starting with
    full domain address.

    :param dom_pci_address: Partial PCI address including domain
                            address (0000, 0000:00:1f, 0000:00:1f.2, etc)

    :return: number of devices in a PCI domain.
    """
    count = 0
    cmd = "ls -l /sys/class/*/ -1"
    output = commands.getoutput(cmd)
    if output:
        filt = '/%s' % dom_pci_address
        for line in output.splitlines():
            if filt in line:
                count += 1
    return count


def get_disks_in_pci_address(pci_address):
    """
    Gets disks in a PCI address.

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: list of disks in a PCI address.
    """
    disks_path = "/dev/disk/by-path/"
    disk_list = []
    for dev in os.listdir(disks_path):
        if pci_address in dev:
            link = os.readlink(os.path.join(disks_path, dev))
            disk_list.append(os.path.abspath(os.path.join(disks_path, link)))
    return disk_list


def get_disks_in_interface(interface):
    """
    Gets disks in a PCI interface.

    :param interface: interface (host1, nvme0, etc)

    :return: list of disks in a PCI interface
    """
    disks_path = "/sys/block/"
    disk_list = []
    for dev in os.listdir(disks_path):
        link = os.readlink(os.path.join(disks_path, dev))
        if "/%s/" % interface in link:
            disk_list.append('/dev/%s' % dev)
    return disk_list


def get_multipath_wwids(disks_list):
    """
    Get mpath wwid for given scsi disks

    :param disks_list: list of disks(/dev/sda, /dev/sdaa, ...)

    :return: list of mpath wwids
    """
    wwid_list = []
    for line in commands.getoutput('lsscsi -i').splitlines():
        for disk in disks_list:
            if disk == line.split()[-2] and line.split()[-1] != '-':
                wwid_list.append(line.split()[-1])
    existing_wwids = []
    if not os.path.isfile("/etc/multipath/wwids"):
        return []
    with open('/etc/multipath/wwids', 'r') as wwid_file:
        for line in wwid_file:
            if '#' not in line:
                existing_wwids.append(line.split('/')[1])
    return [mpath for mpath in list(set(wwid_list)) if mpath in existing_wwids]


def get_multipath_disks(wwids_list):
    """
    Get mpath disk names for given wwids

    :param disks_list: list of disks(360050768028383d7f000000000000022, ...)

    :return: list of mpath disks
    """
    mpath_list = []
    for wwid in wwids_list:
        disk = commands.getoutput("multipath -l %s" % wwid).split()[0]
        mpath_list.append("/dev/mapper/%s" % disk)
    return mpath_list


def get_root_disks():
    """
    Gets the PCI address of the root disk.

    :return: list of root disk.
    """
    root_disk = []
    root_part = commands.getoutput('df -h /').splitlines()[-1].split()[0]
    for line in commands.getoutput('lsblk -sl %s' % root_part).splitlines():
        if 'disk' in line:
            root_disk.append('/dev/%s' % line.split()[0])
    return root_disk


def get_nics_in_pci_address(pci_address):
    """
    Gets network interface(nic) in a PCI address.

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: list of network interfaces in a PCI address.
    """
    return get_interfaces_in_pci_address(pci_address, "net")


def get_interfaces_in_pci_address(pci_address, pci_class):
    """
    Gets interface in a PCI address.

    e.g: host = pci.get_interfaces_in_pci_address("0001:01:00.0", "net")
         ['enP1p1s0f0']
         host = pci.get_interfaces_in_pci_address("0004:01:00.0", "scsi_host")
         ['host6']

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)
    :param class: Adapter class (FC(fc_host), FCoE(net), NIC(net), SCSI(scsi)..)
    :return: list of generic interfaces in a PCI address.
    """
    pci_class_path = "/sys/class/%s/" % pci_class
    if not pci_class or not os.path.isdir(pci_class_path):
        return ""
    return [interface for interface in os.listdir(pci_class_path)
            if pci_address in os.readlink(os.path.join(pci_class_path,
                                                       interface))]


def get_pci_class_name(pci_address):
    """
    Gets PCI class name for given PCI bus address

    e.g: >>> pci.get_pci_class_name("0000:01:00.0")
             'scsi_host'

    :param pci_address: Any segment of a PCI address(1f, 0000:00:if, ...)

    :return: class name for corresponding PCI bus address
    """
    pci_class_dic = {'0104': 'scsi_host', '0c04': 'scsi_host', '0280': 'net',
                     '0c03': 'scsi_host', '0200': 'net', '0108': 'nvme',
                     '0106': 'ata_port', '0207': 'net'}
    pci_class_id = get_pci_prop(pci_address, "Class")
    if pci_class_id not in pci_class_dic:
        return ""
    return pci_class_dic.get(pci_class_id)


def get_pci_type(pci_address):
    """
    Gets PCI type for given PCI bus address

    e.g: >>> pci.get_pci_class_name("0000:01:00.0")
             'fc'

    :param pci_address: Any segment of a PCI address(1f, 0000:00:if, ...)

    :return: type for corresponding PCI bus address
    """
    pci_class_dic = {'0104': 'raid', '0c04': 'fc', '0280': 'infiniband',
                     '0c03': 'usb', '0200': 'network', '0108': 'nvme',
                     '0207': 'infiniband'}
    pci_class_id = get_pci_prop(pci_address, "Class")
    if pci_class_id not in pci_class_dic:
        return ""
    return pci_class_dic.get(pci_class_id)


def get_firmware(pci_address):
    """
    Gets firmware of a pci_address

    :param pci_address: PCI address(0000:00:if.0, ...)

    :return: firmware for its interface
    """
    class_name = get_pci_class_name(pci_address)
    interface = get_interfaces_in_pci_address(pci_address, class_name)
    firmware = ''
    if not interface:
        return firmware
    interface = interface[0]
    if class_name == 'net':
        for line in commands.getoutput('ethtool -i %s' % interface).splitlines():
            if 'firmware-version' in line:
                firmware = line.split()[1]
                break
    else:
        for name in ['firmware_rev', 'fwrev', 'fw_version']:
            filename = "/sys/class/%s/%s/%s" % (class_name, interface, name)
            if os.path.isfile(filename):
                with open(filename, 'r') as fw_file:
                    firmware = fw_file.read().strip('\t\r\n\0').split()[0]
                    firmware = firmware.strip(',')
    return firmware


def get_pci_fun_list(pci_address):
    """
    Gets list of functions in the given PCI address.
    Example: in address 0000:03:00, functions are 0000:03:00.0 and 0000:03:00.1

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: list of functions in a PCI address.
    """
    return list(dev for dev in get_pci_addresses() if pci_address in dev)


def get_slot_from_sysfs(full_pci_address):
    """
    Gets the PCI slot of given address.

    :note: Specific for ppc64 processor.

    :param full_pci_address: Full PCI address including domain (0000:03:00.0)

    :return: Removed port related details using re, only returns till
             physical slot of the adapter.
    """
    if 'ppc64' not in platform.processor():
        return ""
    if not os.path.isfile('/sys/bus/pci/devices/%s/devspec' % full_pci_address):
        return
    filename = "/sys/bus/pci/devices/%s/devspec" % full_pci_address
    with open(filename, 'r') as file_obj:
        devspec = file_obj.read()
    if not os.path.isfile("/proc/device-tree/%s/ibm,loc-code" % devspec):
        return
    filename = "/proc/device-tree/%s/ibm,loc-code" % devspec
    with open(filename, 'r') as file_obj:
        slot = file_obj.read()
    slot_ibm = re.match(r'((\w+)[.])+(\w+)-[P(\d+)-]*C(\d+)', slot)
    if slot_ibm:
        return slot_ibm.group()
    slot_openpower = re.match(r'(\w+)[\s]*(\w+)(\d*)', slot)
    if slot_openpower:
        return slot_openpower.group()
    return ""


def get_slot_list():
    """
    Gets list of PCI slots in the system.

    :note: Specific for ppc64 processor.

    :return: list of slots in the system.
    """
    return list(set(get_slot_from_sysfs(dev) for dev in get_pci_addresses()))


def get_pci_id_from_sysfs(full_pci_address):
    """
    Gets the PCI ID from sysfs of given PCI address.

    :param full_pci_address: Full PCI address including domain (0000:03:00.0)

    :return: PCI ID of a PCI address from sysfs.
    """
    path = "/sys/bus/pci/devices/%s" % full_pci_address
    if os.path.isdir(path):
        path = "%s/%%s" % path
        return ":".join(["%04x" % int(open(path % param).read(), 16)
                         for param in ['vendor', 'device', 'subsystem_vendor',
                                       'subsystem_device']])
    return ""


def get_pci_prop(pci_address, prop):
    """
    Gets specific PCI ID of given PCI address. (first match only)

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)
    :param part: prop of PCI ID.

    :return: specific PCI ID of a PCI address.
    """
    cmd = "lspci -Dnvmm -s %s" % pci_address
    output = commands.getoutput(cmd)
    if output:
        for line in output.splitlines():
            if prop == line.split(':')[0]:
                return line.split()[-1]
    return ""


def get_pci_id(pci_address):
    """
    Gets PCI id of given address. (first match only)

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: PCI ID of a PCI address.
    """
    pci_id = []
    for params in ['Vendor', 'Device', 'SVendor', 'SDevice']:
        output = get_pci_prop(pci_address, params)
        if not output:
            return ""
        pci_id.append(output)
    if pci_id:
        return ":".join(pci_id)


def get_pci_prop_name(pci_address, prop):
    """
    Gets specific PCI ID of given PCI address. (first match only)

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)
    :param prop: prop of PCI ID.

    :return: specific PCI ID of a PCI address.
    """
    cmd = "lspci -Dvmm -s %s" % pci_address
    output = commands.getoutput(cmd)
    if output:
        for line in output.splitlines():
            if prop == line.split(':')[0]:
                return " ".join(line.split()[1:])
    return ""


def get_pci_name(pci_address):
    """
    Gets PCI id of given address. (first match only)

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: PCI ID of a PCI address.
    """
    pci_name = []
    for params in ['Vendor', 'Device']:
        output = get_pci_prop_name(pci_address, params)
        if not output:
            return
        pci_name.append(output)
    if pci_name:
        return " ".join(pci_name)
    return ""


def get_driver(pci_address):
    """
    Gets the kernel driver in use of given PCI address. (first match only)

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: driver of a PCI address.
    """
    cmd = "lspci -ks %s" % pci_address
    output = commands.getoutput(cmd)
    if output:
        for line in output.splitlines():
            if 'Kernel driver in use:' in line:
                return line.rsplit(None, 1)[-1]
    return ""


def ioa_details():
    """
    Gets the IPR IOA details and returns

    return: list of dics, with keys ioa, serial, remote serial, pci, status
    """
    cmd = "iprconfig -c show-ioas"
    show_ioas = commands.getoutput(cmd)
    ioas = []
    if show_ioas:
        for line in show_ioas.splitlines():
            if 'Operational' in line:
                ioa = line.split()[0]
                serial = r_serial = pci = status = ''
                cmd = 'iprconfig -c show-details %s' % ioa
                ioa_details = commands.getoutput(cmd)
                for line in ioa_details.splitlines():
                    if line.startswith('PCI Address'):
                        pci = line.split()[-1]
                    if line.startswith('Serial Number'):
                        serial = line.split()[-1]
                    if line.startswith('Remote Adapter Serial Number'):
                        r_serial = line.split()[-1]
                    if line.startswith('Current Dual Adapter State'):
                        status = line.split()[-1]
                ioas.append({'ioa': ioa, 'pci': pci, 'serial': serial, 'r_serial': r_serial, 'status': status})
    return ioas


def get_primary_ioa(pci_address):
    """
    Gets the Primary IPR IOA in the given PCI address

    :param pci_address: PCI Address (0000:00:1f, 0000:00:1f.1, ...)

    :return: primary IOA
    """
    for ioa_detail in ioa_details():
        if pci_address in ioa_detail['pci'] and 'Primary' in ioa_detail['status']:
            return ioa_detail['ioa']
    return ''


def get_secondary_ioa(primary_ioa):
    """
    Gets the Secondary IPR IOA in the given Primary IPR IOA

    :param primary_ioa: Primary IPR IOA (sg1, sg22, ...)

    :return: secondary IOA
    """
    details = ioa_details()
    serial = ''
    for ioa_detail in details:
        if primary_ioa == ioa_detail['ioa']:
            serial = ioa_detail['r_serial']
    if not serial:
        return ''
    for ioa_detail in details:
        if serial == ioa_detail['serial']:
            return ioa_detail['ioa']
    return ''


def pci_info(pci_addrs, blacklist=''):
    """
    Get all the information for given PCI addresses (comma separated).

    :param pci_addrs: PCI addresses

    :return: list of dictionaries of PCI information
    """
    if not pci_addrs:
        return []
    pci_addrs = pci_addrs.split(',')

    pci_addrs = [pci_addr.split('.')[0] for pci_addr in pci_addrs]
    pci_addrs = list(set(pci_addrs))
    if blacklist:
        blacklist = blacklist.split(',')
        blacklist = [pci_addr.split('.')[0] for pci_addr in blacklist]
        pci_addrs = [pci_addr for pci_addr in pci_addrs if pci_addr not in blacklist]
    pci_addrs.sort()
    pci_list = []

    for pci_addr in pci_addrs:
        pci_dic = {}
        root_disks = get_root_disks()
        pci_dic['functions'] = get_pci_fun_list(pci_addr)
        pci_dic['pci_root'] = pci_addr
        pci_dic['adapter_description'] = get_pci_name(pci_dic['functions'][0])
        pci_dic['adapter_id'] = get_pci_id(pci_dic['functions'][0])
        pci_dic['adapter_type'] = get_pci_type(pci_dic['functions'][0])
        pci_dic['driver'] = get_driver(pci_dic['functions'][0])
        pci_dic['slot'] = get_slot_from_sysfs(pci_dic['functions'][0])
        pci_dic['interfaces'] = []
        pci_dic['class'] = get_pci_class_name(pci_dic['functions'][0])
        for fun in pci_dic['functions']:
            pci_dic['interfaces'].extend(get_interfaces_in_pci_address(fun, pci_dic['class']))
        pci_dic['firmware'] = get_firmware(pci_dic['functions'][0])
        pci_dic['disks'] = []
        for interface in pci_dic['interfaces']:
            pci_dic['disks'].extend(get_disks_in_interface(interface))
        pci_dic['disks'] = list(set(pci_dic['disks']))
        pci_dic['mpath_wwids'] = []
        pci_dic['mpath_disks'] = []
        if pci_dic['class'] == 'scsi_host':
            pci_dic['mpath_wwids'] = get_multipath_wwids(pci_dic['disks'])
            pci_dic['mpath_disks'] = get_multipath_disks(pci_dic['mpath_wwids'])
        pci_dic['infiniband_interfaces'] = []
        if pci_dic['adapter_type'] == 'infiniband':
            for fun in pci_dic['functions']:
                pci_dic['infiniband_interfaces'].extend(get_interfaces_in_pci_address(fun, 'infiniband'))
        if pci_dic['adapter_type'] == 'raid':
            for fun in pci_dic['functions']:
                pci_dic['primary_ioa'] = get_primary_ioa(fun)
                pci_dic['secondary_ioa'] = get_secondary_ioa(pci_dic['primary_ioa'])
        pci_dic['is_root_disk'] = False
        for disk in pci_dic['disks']:
            for root_disk in root_disks:
                if root_disk in disk:
                    pci_dic['is_root_disk'] = True
                    break
        pci_list.append(pci_dic)
    return pci_list


def all_pci_info(blacklist=''):
    """
    Get all the information for all PCI addresses in the system.

    :return: list of dictionaries of PCI information
    """
    pci_addrs = get_pci_addresses()
    return pci_info(",".join(pci_addrs), blacklist=blacklist)
