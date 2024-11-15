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
# Copyright: 2024 IBM
# Author: Shaik Abdulla <abdulla1@linux.vnet.ibm.com>

"""
Module for all Virtual devices related functions.
"""

import re
import os
import platform

from .helper import runcmd
from lib.logger import logger_init
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
logger = logger_init(filepath=BASE_PATH).getlogger()

def get_mac_address(interface):
    '''
    Gets the mac_address of given interface.
    parameter: interface: Name of Interface.

    :return: string of MAC address.
    '''
    try:
        for line in runcmd("ip a s dev %s" % interface)[1].splitlines():
            if 'link/ether' in line:
                mac_address = line.split()[1]
                return mac_address
    except Exception as e:
        logger.debug(f'Interface not found {e}')


def get_driver(interface):
    '''
    Gets associated driver/module of given interface.
    parameter: interface: Name of Interface.

    :return: string of driver name.
    '''
    for line in runcmd("ethtool -i  %s" % interface)[1].splitlines():
        if line.startswith('driver:'):
            driver = line.split(': ')[1].strip()
            return driver


def get_virtual_interface_names(interface_type):
    '''
    Gets all virtual interface names of a given type.


    :param interface_type: Type of interface (e.g. 'l-lan', 'vnic')
    :return: list of virtual interface names.
    '''
    try:
        interface_list = []
        for input_string in runcmd("lsdevinfo -c")[1].splitlines():
            if interface_type in input_string:
                pattern = r'name="([^"]+)"'
                match = re.search(pattern, input_string)
                if match:
                    name = match.group(1)
                    if interface_type == 'l-lan' and name == "net0":
                        continue
                    interface_list.append(name)
        return interface_list
    except Exception as e:
        logger.debug(f"Error while getting interface list {e}")


def get_veth_interface_names():
    return get_virtual_interface_names('l-lan')


def get_vnic_interface_names():
    return get_virtual_interface_names('vnic')


def get_hnv_interface_names():
    '''
    Gets all HNV interface names.

    :return: list of HNV interface names.
    '''
    hnv_interface_list = []
    bonding_dir = '/proc/net/bonding/'
    if os.path.exists(bonding_dir):
        bond_interfaces = os.listdir(bonding_dir)
        hnv_interface_list.extend(bond_interfaces)
    else:
        logger.debug("No HNV interfaces found.")
    return hnv_interface_list


def get_host_public_ip():
    '''
    Gets system's Public IP address.

    :return: string of Public IP address.
    '''
    try:
        lines = runcmd("ip a s dev net0")[1]
        ip_pattern = r'inet\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        match = re.search(ip_pattern, lines)
        if match:
            return match.group(1)
    except Exception as e:
        logger.debug(f'Interface not found {e}')


def virtual_info(interface):
    '''
    Get the information for given virtual interface.

    parameter: interface: Name of Interface.
    :return: list of dictinaries of virtual interface information.
    '''
    virtual_list = []
    virtual_dict = {}
    virtual_dict['macaddress'] = get_mac_address(interface)
    virtual_dict['public_interface_ip'] = get_host_public_ip()
    virtual_dict['driver'] = get_driver(interface)

    if virtual_dict['driver'] == "ibmvnic":
        virtual_dict['interfaces'] = get_vnic_interface_names()
        virtual_dict['adapter_type'] = 'vnic'

    if virtual_dict['driver'] == "ibmveth":
        virtual_dict['interfaces'] = get_veth_interface_names()
        virtual_dict['adapter_type'] = 'veth'

    if virtual_dict['driver'] == "bonding":
        virtual_dict['interfaces'] = get_hnv_interface_names()
        virtual_dict['adapter_type'] = 'hnv'

    virtual_list.append(virtual_dict)
    return virtual_list
