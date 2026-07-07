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

All public functions accept an optional `runner` keyword argument.
When omitted (or None) the local `runcmd()` helper is used.
When a :class:`lib.helper.RemoteRunner` instance is passed, every shell
command is executed on the remote machine over SSH instead, enabling
remote interface discovery without any other code changes.

Example — local (default behaviour, unchanged):
    from lib import virtual
    info = virtual.virtual_info('eth0')

Example — remote:
    from lib.helper import RemoteRunner
    from lib import virtual
    with RemoteRunner(host='192.168.1.10', username='root', password='s3cr3t') as r:
        info = virtual.virtual_info('eth0', runner=r)
"""

import re
import os

from .helper import runcmd
from lib.logger import logger_init
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
logger = logger_init(filepath=BASE_PATH).getlogger()


def _run(cmd, runner=None, ignore_status=False):
    """
    Internal helper: dispatch *cmd* to either the local runcmd() or a
    RemoteRunner instance.

    :param cmd: Shell command string to execute.
    :param runner: Optional RemoteRunner instance. Uses local runcmd when None.
    :param ignore_status: Passed through to the underlying runner.
    :return: (status, output) tuple.
    """
    if runner is not None:
        return runner.runcmd(cmd, ignore_status=ignore_status)
    return runcmd(cmd, ignore_status=ignore_status)


def get_mac_address(interface, runner=None):
    '''
    Gets the mac_address of given interface.

    :param interface: Name of Interface.
    :param runner: Optional RemoteRunner for remote execution.
    :return: string of MAC address.
    '''
    try:
        for line in _run("ip a s dev %s" % interface, runner=runner)[1].splitlines():
            if 'link/ether' in line:
                mac_address = line.split()[1]
                return mac_address
    except Exception as e:
        logger.debug(f'Interface not found {e}')


def get_driver(interface, runner=None):
    '''
    Gets associated driver/module of given interface.

    :param interface: Name of Interface.
    :param runner: Optional RemoteRunner for remote execution.
    :return: string of driver name.
    '''
    for line in _run("ethtool -i  %s" % interface, runner=runner)[1].splitlines():
        if line.startswith('driver:'):
            driver = line.split(': ')[1].strip()
            return driver


def get_virtual_interface_names(interface_type, runner=None):
    '''
    Gets all virtual interface names of a given type.

    :param interface_type: Type of interface (e.g. 'l-lan', 'vnic')
    :param runner: Optional RemoteRunner for remote execution.
    :return: list of virtual interface names.
    '''
    try:
        interface_list = []
        for input_string in _run("lsdevinfo -c", runner=runner)[1].splitlines():
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


def get_veth_interface_names(runner=None):
    return get_virtual_interface_names('l-lan', runner=runner)


def get_vnic_interface_names(runner=None):
    return get_virtual_interface_names('vnic', runner=runner)


def get_hnv_interface_names(runner=None):
    '''
    Gets all HNV interface names.

    :param runner: Optional RemoteRunner for remote execution.
    :return: list of HNV interface names.
    '''
    hnv_interface_list = []
    if runner is not None:
        # On a remote host we cannot use os.path / os.listdir directly;
        # instead we list the bonding proc directory via SSH.
        status, output = _run("ls /proc/net/bonding/ 2>/dev/null", runner=runner, ignore_status=True)
        if status == 0 and output.strip():
            hnv_interface_list.extend(output.strip().splitlines())
        else:
            logger.debug("No HNV interfaces found on remote host.")
    else:
        bonding_dir = '/proc/net/bonding/'
        if os.path.exists(bonding_dir):
            bond_interfaces = os.listdir(bonding_dir)
            hnv_interface_list.extend(bond_interfaces)
        else:
            logger.debug("No HNV interfaces found.")
    return hnv_interface_list


def get_interface_ip(interface, runner=None):
    '''
    Gets the IPv4 address assigned to a given interface.

    :param interface: Name of the network interface.
    :param runner: Optional RemoteRunner for remote execution.
    :return: string of IPv4 address, or None if not found.
    '''
    try:
        lines = _run("ip a s dev %s" % interface, runner=runner, ignore_status=True)[1]
        ip_pattern = r'inet\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        match = re.search(ip_pattern, lines)
        if match:
            return match.group(1)
    except Exception as e:
        logger.debug(f'Could not get IP for interface {interface}: {e}')
    return None


def get_host_public_ip(runner=None):
    '''
    Gets system's Public IP address.

    :param runner: Optional RemoteRunner for remote execution.
    :return: string of Public IP address.
    '''
    try:
        lines = _run("ip a s dev net0", runner=runner)[1]
        ip_pattern = r'inet\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        match = re.search(ip_pattern, lines)
        if match:
            return match.group(1)
    except Exception as e:
        logger.debug(f'Interface not found {e}')


def virtual_info(interface, runner=None):
    '''
    Get the information for given virtual interface.

    :param interface: Name of Interface.
    :param runner: Optional RemoteRunner instance. When provided, all
                   underlying commands are executed on the remote host
                   over SSH instead of locally.
    :return: list of dictionaries of virtual interface information.
    '''
    virtual_list = []
    virtual_dict = {}
    virtual_dict['macaddress'] = get_mac_address(interface, runner=runner)
    virtual_dict['public_interface_ip'] = get_host_public_ip(runner=runner)
    virtual_dict['driver'] = get_driver(interface, runner=runner)

    if virtual_dict['driver'] == "ibmvnic":
        virtual_dict['interfaces'] = get_vnic_interface_names(runner=runner)
        virtual_dict['adapter_type'] = 'vnic'

    if virtual_dict['driver'] == "ibmveth":
        virtual_dict['interfaces'] = get_veth_interface_names(runner=runner)
        virtual_dict['adapter_type'] = 'veth'

    if virtual_dict['driver'] == "bonding":
        virtual_dict['interfaces'] = get_hnv_interface_names(runner=runner)
        virtual_dict['adapter_type'] = 'hnv'

    virtual_list.append(virtual_dict)
    return virtual_list
