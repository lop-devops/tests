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
        print(f'Interface not found {e}')


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


def get_vnic_interface_names():
    '''
    Gets all vNIC interface names.

    :return: list of virtual interface names.
    '''
    vnic_list = []
    for input_string in runcmd("lsdevinfo -c")[1].splitlines():
        if 'vnic' in input_string:
            pattern = r'name="([^"]+)"'
            match = re.search(pattern, input_string)
            if match:
                name = match.group(1)
                vnic_list.append(name)
    return vnic_list


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
        print(f'Interface not found {e}')


def virtual_info(interface):
    '''
    Get the information for given virtual interface.

    parameter: interface: Name of Interface.
    :return: list of dictinaries of virtual interface information.
    '''
    virtual_list = []
    virtual_dict = {}
    virtual_dict['interfaces'] = get_vnic_interface_names()
    virtual_dict['macaddress'] = get_mac_address(interface)
    virtual_dict['mac_id'] = "".join(virtual_dict['macaddress'].split(':'))
    virtual_dict['public_interface_ip'] = get_host_public_ip()
    virtual_dict['driver'] = get_driver(interface)
    if virtual_dict['driver'] == "ibmvnic":
        virtual_dict['adapter_type'] = 'vnic'

    virtual_list.append(virtual_dict)
    return virtual_list
