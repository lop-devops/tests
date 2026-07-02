#!/usr/bin/env python3

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
# Copyright: 2023 IBM
# Author: Narasimhan V <sim@linux.vnet.ibm.com>
# Author: Manvanthara Puttashankar <manvanth@linux.vnet.ibm.com>
# Author: Shaik Abdulla <abdulla1@linux.vnet.ibm.com>

from pprint import pprint
from lib import pci
from lib import virtual
import argparse
import shutil
import os
import sys
import configparser
from lib.pci import is_sriov
from lib.logger import logger_init
from lib.helper import is_rhel8, RemoteRunner
from lib.hmc import HMCClient, get_hmc_ip_from_lsrsrc, get_hmc_password_from_secrets_manager
from typing import Optional

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = "%s/config/wrapper/pci_input.conf" % BASE_PATH
CONFIGFILE = configparser.ConfigParser()
CONFIGFILE.optionxform = str  # type: ignore[assignment]
CONFIGFILE.read(CONFIG_PATH)
BASE_INPUTFILE_PATH = "%s/config/inputs" % BASE_PATH
input_path = "io_input.txt"
INPUTFILE = configparser.ConfigParser()
INPUTFILE.optionxform = str  # type: ignore[assignment]
args: Optional[argparse.Namespace] = None

logger = logger_init(filepath=BASE_PATH).getlogger()


def create_config_inputs(orig_cfg, new_cfg, inputfile, interface, config_type):
    """
    1. Creates modified configuration file name according to type of interface from original configuration file
    2. Generates string with "input file option" along with input file,
    3. Generates input parametes of specific device type interface.

    Parameters:
        orig_cfg (str): The name of the original configuration file.
        new_cfg (str): The name of the new configuration file to be generated with
                       according to interface type.
        inputfile (str): The path to the input file containing configuration data.
        interface (list): The details of Interface in list format.
        config_type (str): The type of configuration to generate. Ex: PCI, vNIC etc.

    Returns:
        test_suites :: A list, having configuration[cfg] files of different set.
        input_file_string :: A string, with extension of "--input-file" option.
        input_params:: A list, of different input parameters of specific interface.
    """
    assert args is not None, "args must be initialized before calling create_config_inputs"
    test_suites = []
    input_file_string = ""
    input_params = []
    additional_params = args.add_params.split()
    if len(additional_params) != 0:
        additional_params = args.add_params.split(",")

    # Copy configuration file
    shutil.copy("config/tests/host/%s.cfg" % orig_cfg, "config/tests/host/%s.cfg" % new_cfg)

    test_suites.append("host_%s" % new_cfg)

    # adding info to input file
    if not CONFIGFILE.has_section(orig_cfg) and not additional_params:
        return
    input_params = CONFIGFILE.items(orig_cfg)
    if not input_params:
        return

    INPUTFILE.add_section(new_cfg)

    # read the input file content and store in dict
    inputfile_dict = {}
    with open(inputfile, 'r') as file:
        for line in file:
            # Check if the line starts with '#' or '[' and skip it
            if line.startswith('#') or line.startswith('['):
                continue

            # Split each line by '=' to separate key and value
            parts = line.strip().split('=')

            # Ensure there are exactly two parts (key and value)
            if len(parts) == 2:
                inputkey, inputvalue = parts[0].strip(), parts[1].strip()
                inputfile_dict[inputkey] = inputvalue

    # input params
    for param in input_params:
        try:
            key = param[0]
            if ':' not in param[1]:
                value = interface[param[1]]
            else:
                index = param[1].split(':')[0]
                index_exact = param[1].split(':')[1]
                if index_exact == 'all':

                    # adding only first two available vNIC interfaces when
                    # multiple vNIC interfaces are available in system.
                    if config_type in ('vnic', 'veth', 'hnv'):
                        value = " ".join(str(item) for item in interface[index][:2])
                    else:
                        value = " ".join(interface[index])
                else:
                    value = interface[index][int(index_exact)]
                    if len(interface[index]) > 1:
                        del interface[index][int(index_exact)]
            # remove the duplicate inputfile enteries
            if key in inputfile_dict:
                del inputfile_dict[key]
            INPUTFILE.set(new_cfg, key, "\"%s\"" % value)

        except:
            pass

    # additional params
    for param in additional_params:
        key = param.split('=')[0].strip()
        # handling additional params per pci
        if '::' in key:
            pci_root = key.split('::')[0].split('.')[0]
            if pci_root != interface.get('pci_root', ''):
                continue
            key = key.split('::')[1]

        # check if the newly added additional param is same
        # as inputfile assign the values directly
        if key in inputfile_dict:
            inputfile_dict[key] = '"%s"' % param.split('=', 1)[1].strip()
        else:
            # if it is completly new then directly write to new input file
            value = param.split('=', 1)[1].strip()
            INPUTFILE.set(new_cfg, key, "\"%s\"" % value)

    # append the remaining input file entries to the new input file
    for inputkey, inputvalue in inputfile_dict.items():
        INPUTFILE.set(new_cfg, inputkey, "%s" % inputvalue)

    return test_suites, input_file_string, input_params


def create_config_file(interface_details, config_type):
    """
    Creates avocado test suite / config file, and input file needed for yaml files in that config files.

    Parameters:
        interface_details(list): The detailed differnet Interface parameters in list format.
        config_type (str): The type of configuration to generate. Ex: vNIC, HNV, vETH etc.
    """
    for virtual in interface_details:
        cfg_name = virtual['adapter_type']
        orig_cfg = "io_%s_fvt" % virtual['adapter_type']
        new_cfg = "io_%s_stress_fvt" % virtual['adapter_type']
        inputfile = "%s/io_%s_input.txt" % (BASE_INPUTFILE_PATH, virtual['adapter_type'])

        if not os.path.exists("config/tests/host/%s.cfg" % orig_cfg):
            logger.debug("ignoring hnv address as there is no cfg for %s", virtual['adapter_type'])
            continue

        return create_config_inputs(orig_cfg, new_cfg, inputfile, virtual, config_type=config_type)

    # If we reach here, interface_details was empty or all items were skipped
    logger.warning("No valid virtual interface config found in create_config_file")
    return None


def create_config(interface_details, config_type):
    """
    Creates avocado test suite / config file, and input file needed for yaml files in that config files.
    """
    test_suites = []
    input_file_string = ""
    input_params = []

    if config_type == 'pci':
        for pci in interface_details:
            if pci['is_root_disk']:
                logger.debug(
                    "ignoring pci address %s as it contains root disk", pci['pci_root'])
                continue

            # copy template cfg files and create new ones
            cfg_name = "_".join(pci['pci_root'].split(':'))
            if pci['adapter_type'] == 'nvmf' and is_rhel8():
                orig_cfg = "io_%s_rhel8_fvt" % pci['adapter_type']
                new_cfg = "io_%s_rhel8_%s_fvt" % (pci['adapter_type'], cfg_name)
                inputfile = "%s/io_%s_rhel8_input.txt" % (
                    BASE_INPUTFILE_PATH, pci['adapter_type'])
            elif pci['adapter_type'] == 'network' and is_sriov(
                    pci['pci_root']):
                orig_cfg = "io_nic_sriov_fvt"
                new_cfg = "io_nic_sriov_%s_fvt" % cfg_name
                inputfile = "%s/io_nic_sriov_input.txt" % BASE_INPUTFILE_PATH
            else:
                orig_cfg = "io_%s_fvt" % pci['adapter_type']
                new_cfg = "io_%s_%s_fvt" % (pci['adapter_type'], cfg_name)
                inputfile = "%s/io_%s_input.txt" % (
                    BASE_INPUTFILE_PATH, pci['adapter_type'])
            if not os.path.exists("config/tests/host/%s.cfg" % orig_cfg):
                logger.debug("ignoring pci address %s as there is no cfg for %s",
                             pci['pci_root'], pci['adapter_type'])
                continue

            result = create_config_inputs(orig_cfg, new_cfg, inputfile, pci, config_type='pci')
            if result is None:
                logger.warning("No input params found for %s; skipping input file generation", orig_cfg)
                continue
            test_suites, input_file_string, input_params = result

    if config_type in ('vnic', 'veth', 'hnv'):
        result = create_config_file(interface_details, config_type)
        if result is None:
            logger.warning("No input params found for virtual interface; skipping input file generation")
            return ""
        test_suites, input_file_string, input_params = result

    test_suites = ",".join(test_suites)

    # write to input file
    if input_params:
        with open(input_path, 'w+') as input:
            INPUTFILE.write(input)
        input_file_string = "--input-file %s" % input_path

    # generate avocado-setup command line
    if test_suites:
        cmd = "python avocado-setup.py --run-suite %s %s" % (test_suites, input_file_string)
        return cmd
    return ""


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pci-address', dest='pci_addr',
                        action='store', default='',
                        help='pci address, comma separated')
    parser.add_argument('--vnic', dest='vnic_int', action='store', nargs='?', const='vnic_default', default=None,
                        help='vNIC interface name')
    parser.add_argument('--veth', dest='veth_int', action='store', nargs='?', const='veth_default', default=None,
                        help='vETH interface name')
    parser.add_argument('--hnv', dest='hnv_int', action='store', nargs='?', const='hnv_default', default=None,
                        help='HNV interface name')
    parser.add_argument('--pci-address-blocklist', dest='pci_addr_blocklist',
                        action='store', default='',
                        help='pci address which need not be considered, comma separated')
    parser.add_argument('--type', dest='pci_type',
                        action='store', default='All',
                        help='type of adapters, comma separated')
    parser.add_argument('--type-blocklist', dest='type_blocklist',
                        action='store', default='',
                        help='type of adapters to blocklist, comma separated')
    parser.add_argument('--show-info', dest='show_info',
                        action='store_true', default=False,
                        help='Show the pci details')
    parser.add_argument('--create-config', dest='create_cfg',
                        action='store_true', default=False,
                        help='Create test config and input files')
    parser.add_argument('--run-test', dest='run_test',
                        action='store_true', default=False,
                        help='Run the test suite using created test config and input files')
    parser.add_argument('--additional-params', dest='add_params',
                        action='store', default='',
                        help='Additional parameters(key=value) to the input file, comma separated')
    parser.add_argument('--params-file', dest='params_file',
                        action='store', default=None,
                        help='Path to a file containing dynamic key=value parameters '
                             '(one per line) to inject into the input file at runtime. '
                             'Useful for Jenkins CR runs where IO adapters, LPAR names, '
                             'IPs etc. change per build without editing the base input file. '
                             'Lines starting with # are treated as comments and ignored. '
                             'Values in --params-file are merged with --additional-params; '
                             '--additional-params takes precedence on duplicate keys. '
                             'Example file content:\n'
                             '  interface=eth0\n'
                             '  lpar=lpar1\n'
                             '  wwpn=0x500507680d1e4c00')
    parser.add_argument('--remote-server', dest='remote_server',
                        action='store', default=None,
                        help='Hostname or IP of the remote machine to gather interface details from')
    parser.add_argument('--remote-user', dest='remote_user',
                        action='store', default='root',
                        help='SSH username for the remote machine (used with --remote-server, default: root)')
    parser.add_argument('--remote-password', dest='remote_password',
                        action='store', default=None,
                        help='SSH password for the remote machine (used with --remote-server)')
    parser.add_argument('--hmc-ip', dest='hmc_ip',
                        action='store', default=None,
                        help='HMC hostname or IP address to query for managed system name')
    parser.add_argument('--hmc-user', dest='hmc_user',
                        action='store', default='hscroot',
                        help='HMC SSH username (default: hscroot)')
    parser.add_argument('--hmc-password', dest='hmc_password',
                        action='store', default=None,
                        help='HMC SSH password (required with --hmc-ip)')
    args = parser.parse_args()

    if args.params_file:
        if not os.path.isfile(args.params_file):
            logger.error("Params file not found: %s", args.params_file)
            sys.exit(1)
        # Connection/credential keys are read from the file and injected
        # directly into args (if not already set via CLI). They are NOT
        # forwarded into add_params so they never end up in the mux input file.
        _CREDENTIAL_KEYS = {
            'peer_public_ip':  'remote_server',
            'hmc_ip':          'hmc_ip',
        }
        # These keys set an args attribute AND are forwarded to the input file.
        _CREDENTIAL_KEYS_ALSO_FORWARD = {
            'peer_password':   'remote_password',
            'hmc_pwd':   'hmc_password',
            'vios_pwd':  'vios_pwd',
        }
        file_params = []
        with open(args.params_file, 'r') as pf:
            for line in pf:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' not in line:
                    logger.warning("Skipping invalid line in params file (no '='): %s", line)
                    continue
                key = line.split('=')[0].strip()
                value = line.split('=', 1)[1].strip()
                if key in _CREDENTIAL_KEYS:
                    attr = _CREDENTIAL_KEYS[key]
                    # CLI value always wins; only set from file if not already provided
                    if not getattr(args, attr, None):
                        setattr(args, attr, value)
                        logger.debug("%s loaded from params file", key)
                    else:
                        logger.debug("%s already set via CLI, ignoring params file value", key)
                elif key in _CREDENTIAL_KEYS_ALSO_FORWARD:
                    attr = _CREDENTIAL_KEYS_ALSO_FORWARD[key]
                    # Set args attribute (credential use)
                    if not getattr(args, attr, None):
                        setattr(args, attr, value)
                        logger.debug("%s loaded from params file (credential)", key)
                    # Also forward to input file
                    file_params.append(line)
                else:
                    file_params.append(line)
        if file_params:
            # Build a set of keys already in --additional-params so they take precedence
            cli_keys = set()
            if args.add_params:
                for p in args.add_params.split(','):
                    p = p.strip()
                    if '=' in p:
                        cli_keys.add(p.split('=')[0].strip())
            # Append only file params whose keys are NOT already in --additional-params
            merged = [p for p in file_params if p.split('=')[0].strip() not in cli_keys]
            if args.add_params:
                args.add_params = args.add_params.rstrip(',') + ',' + ','.join(merged)
            else:
                args.add_params = ','.join(merged)
            logger.info("Loaded %d param(s) from params file: %s", len(merged), args.params_file)

    # Validate remote args: server + user + password must all be available
    # (each can come from CLI or from --params-file: peer_public_ip / peer_password)
    if args.remote_server and not args.remote_user:
        parser.error("--remote-server requires --remote-user "
                     "(provide via CLI or add 'peer_username=<value>' to --params-file)")
    if args.remote_server and not args.remote_password:
        parser.error("--remote-server requires --remote-password "
                     "(provide via CLI or add 'peer_password=<value>' to --params-file)")

    # Auto-detect HMC IP from lsrsrc IBM.MCP if not supplied
    if not args.hmc_ip:
        detected_ip = get_hmc_ip_from_lsrsrc()
        if detected_ip:
            logger.info("Auto-detected HMC IP: %s", detected_ip)
            args.hmc_ip = detected_ip

    # Auto-fetch HMC password from secrets manager if not supplied
    if args.hmc_ip and not args.hmc_password:
        fetched_pwd = get_hmc_password_from_secrets_manager()
        if fetched_pwd:
            logger.info("HMC password retrieved from secrets manager")
            args.hmc_password = fetched_pwd
        else:
            logger.warning(
                "Could not auto-fetch HMC password. "
                "Provide it manually via --hmc-password to enable manageSystem lookup."
            )

    # Build an optional RemoteRunner when --remote-server is supplied.
    # The runner is passed down to virtual.* functions so every shell
    # command executes on the remote host over SSH instead of locally.
    _runner = None
    if args.remote_server:
        logger.info("Remote mode: connecting to %s as %s", args.remote_server, args.remote_user)
        _runner = RemoteRunner(
            host=args.remote_server,
            username=args.remote_user,
            password=args.remote_password,
        )

    # Local interface discovery always runs on the local machine (no runner).
    # The runner is used exclusively for gathering peer_* remote details below.
    if args.vnic_int == 'vnic_default':
        vnic_ifaces = virtual.get_vnic_interface_names()
        if vnic_ifaces:
            args.vnic_int = vnic_ifaces[0]
        else:
            logger.error("No vNIC interfaces found")
            sys.exit(1)

    if args.veth_int == 'veth_default':
        veth_ifaces = virtual.get_veth_interface_names()
        if veth_ifaces:
            args.veth_int = veth_ifaces[0]
        else:
            logger.error("No vETH interfaces found")
            sys.exit(1)

    if args.hnv_int == 'hnv_default':
        hnv_ifaces = virtual.get_hnv_interface_names()
        if hnv_ifaces:
            args.hnv_int = hnv_ifaces[0]
        else:
            logger.error("No HNV interfaces found")
            sys.exit(1)

    # Initialize all interface detail variables to satisfy type checker
    vnic_details = []
    veth_details = []
    hnv_details = []
    pci_details = []

    try:
        if args.vnic_int:
            vnic_details = virtual.virtual_info(args.vnic_int)
        elif args.veth_int:
            veth_details = virtual.virtual_info(args.veth_int)
        elif args.hnv_int:
            hnv_details = virtual.virtual_info(args.hnv_int)
        elif args.pci_addr:
            pci_details = pci.pci_info(args.pci_addr, pci_type=args.pci_type, pci_blocklist=args.pci_addr_blocklist, type_blocklist=args.type_blocklist)
        else:
            pci_details = pci.all_pci_info(pci_type=args.pci_type, pci_blocklist=args.pci_addr_blocklist, type_blocklist=args.type_blocklist)
    except Exception as e:
        if args.vnic_int:
            logger.info("vNIC interface not found")
        else:
            logger.info("No PCI Found")
        if _runner:
            _runner.close()
        sys.exit(0)

    # ------------------------------------------------------------------ #
    # manageSystem: query HMC for the managed system name of the local LPAR.
    # Requires --hmc-ip and --hmc-password. Uses lparstat to get LPAR name,
    # then searches all managed systems on the HMC for a match.
    # ------------------------------------------------------------------ #
    _manage_system = ''
    if args.hmc_ip:
        try:
            import subprocess as _sp
            _lpar_name_out = _sp.getoutput(
                "lparstat -i 2>/dev/null | grep 'Partition Name' | awk -F': ' '{print $2}'"
            ).strip()
            if _lpar_name_out:
                logger.info("Local LPAR name detected: %s", _lpar_name_out)
                with HMCClient(hmc_ip=args.hmc_ip, username=args.hmc_user,
                               password=args.hmc_password) as hmc:
                    _manage_system = hmc.get_managed_system_for_lpar(_lpar_name_out) or ''
                logger.info("Managed system resolved: %s", _manage_system)
            else:
                logger.warning("Could not determine local LPAR name via lparstat; skipping manageSystem lookup")
        except Exception as _hmc_err:
            logger.warning("HMC lookup failed: %s", _hmc_err)

    # Inject manageSystem + VIOS info into all virtual interface detail dicts
    _vios_names = ''
    _vios_ip = ''
    if args.hmc_ip and args.hmc_password and _manage_system:
        try:
            with HMCClient(hmc_ip=args.hmc_ip, username=args.hmc_user,
                           password=args.hmc_password) as hmc:
                _vios_info = hmc.get_vios_info(_manage_system)
                _vios_names = _vios_info.get('vios_names', '')
                _vios_ip = _vios_info.get('vios_ip', '')
                logger.info("VIOS names: %s  VIOS IPs: %s", _vios_names, _vios_ip)
        except Exception as _vios_err:
            logger.warning("Could not retrieve VIOS info: %s", _vios_err)

    for _details in [
        vnic_details if args.vnic_int else [],
        veth_details if args.veth_int else [],
        hnv_details if args.hnv_int else [],
    ]:
        for _d in _details:
            _d['manageSystem'] = _manage_system
            _d['vios_names'] = _vios_names
            _d['vios_ip'] = _vios_ip

    # ------------------------------------------------------------------ #
    # host_ip: derive 192.168.10.<last_octet> from the local public IP.
    # Applied for vnic/veth/hnv regardless of whether --remote-server is set.
    # ------------------------------------------------------------------ #
    for _details in [
        vnic_details if args.vnic_int else [],
        veth_details if args.veth_int else [],
        hnv_details if args.hnv_int else [],
    ]:
        for _d in _details:
            pub_ip = _d.get('public_interface_ip', '') or ''
            if pub_ip:
                last_octet = pub_ip.split('.')[-1]
                _d['host_ip'] = '192.168.10.%s' % last_octet

                # Assign host_ips based on number of interfaces
                num_interfaces = len(_d.get('interfaces', []))
                if num_interfaces > 1:
                    _d['host_ips'] = '192.168.10.%s 192.168.20.%s' % (last_octet, last_octet)
                    _d['netmasks'] = '255.255.255.0 255.255.255.0'
                else:
                    _d['host_ips'] = '192.168.10.%s' % last_octet
                    _d['netmasks'] = '255.255.255.0'

                logger.info(
                    "Derived host_ip=%s host_ips=%s from public_interface_ip=%s (interfaces: %d)",
                    _d['host_ip'], _d['host_ips'], pub_ip, num_interfaces,
                )
            else:
                _d['host_ip'] = ''
                _d['host_ips'] = ''
                logger.debug("public_interface_ip not available; host_ip/host_ips left empty")
            _d['netmask'] = '255.255.255.0'

    # ------------------------------------------------------------------ #
    # Peer enrichment: when --remote-server is given, gather peer_* fields
    # from the remote machine and inject them into the local vnic/veth/hnv
    # details dict so pci_input.conf mappings (peer_ip, peer_ips,
    # peer_interfaces, peer_public_ip) are resolved automatically.
    # ------------------------------------------------------------------ #
    if _runner and args.vnic_int:
        try:
            logger.info("Gathering peer vNIC details from remote host %s", args.remote_server)
            peer_ifaces = virtual.get_vnic_interface_names(runner=_runner) or []
            # peer_interfaces: first two vNIC interface names (space-separated)
            peer_interfaces_val = " ".join(peer_ifaces[:2])
            # peer_ip: IP of the first remote vNIC interface
            peer_ip_val = ""
            if peer_ifaces:
                peer_ip_val = virtual.get_interface_ip(peer_ifaces[0], runner=_runner) or ""
            # peer_ips: IPs of the first two remote vNIC interfaces (space-separated)
            peer_ips_list = []
            for iface in peer_ifaces[:2]:
                ip = virtual.get_interface_ip(iface, runner=_runner)
                if ip:
                    peer_ips_list.append(ip)
            peer_ips_val = " ".join(peer_ips_list)
            # peer_public_ip: public IP of the remote host (net0)
            peer_public_ip_val = virtual.get_host_public_ip(runner=_runner) or ""

            # Inject into the first (and only) dict in vnic_details
            vnic_details[0]['peer_ip'] = peer_ip_val
            vnic_details[0]['peer_ips'] = peer_ips_val
            vnic_details[0]['peer_interfaces'] = peer_interfaces_val
            vnic_details[0]['peer_public_ip'] = peer_public_ip_val
            logger.info(
                "Peer info injected: peer_ip=%s peer_ips=%s peer_interfaces=%s peer_public_ip=%s",
                peer_ip_val, peer_ips_val, peer_interfaces_val, peer_public_ip_val,
            )
        except Exception as peer_err:
            logger.warning("Could not gather peer details from %s: %s", args.remote_server, peer_err)

    if _runner and args.veth_int:
        try:
            logger.info("Gathering peer vETH details from remote host %s", args.remote_server)
            peer_ifaces = virtual.get_veth_interface_names(runner=_runner) or []
            peer_interfaces_val = " ".join(peer_ifaces[:2])
            peer_ip_val = virtual.get_interface_ip(peer_ifaces[0], runner=_runner) if peer_ifaces else ""
            peer_ips_val = " ".join(filter(None, [virtual.get_interface_ip(i, runner=_runner) for i in peer_ifaces[:2]]))
            peer_public_ip_val = virtual.get_host_public_ip(runner=_runner) or ""
            veth_details[0]['peer_ip'] = peer_ip_val or ""
            veth_details[0]['peer_ips'] = peer_ips_val
            veth_details[0]['peer_interfaces'] = peer_interfaces_val
            veth_details[0]['peer_public_ip'] = peer_public_ip_val
        except Exception as peer_err:
            logger.warning("Could not gather peer details from %s: %s", args.remote_server, peer_err)

    if _runner and args.hnv_int:
        try:
            logger.info("Gathering peer HNV details from remote host %s", args.remote_server)
            peer_ifaces = virtual.get_hnv_interface_names(runner=_runner) or []
            peer_interfaces_val = " ".join(peer_ifaces[:2])
            peer_ip_val = virtual.get_interface_ip(peer_ifaces[0], runner=_runner) if peer_ifaces else ""
            peer_ips_val = " ".join(filter(None, [virtual.get_interface_ip(i, runner=_runner) for i in peer_ifaces[:2]]))
            peer_public_ip_val = virtual.get_host_public_ip(runner=_runner) or ""
            hnv_details[0]['peer_ip'] = peer_ip_val or ""
            hnv_details[0]['peer_ips'] = peer_ips_val
            hnv_details[0]['peer_interfaces'] = peer_interfaces_val
            hnv_details[0]['peer_public_ip'] = peer_public_ip_val
        except Exception as peer_err:
            logger.warning("Could not gather peer details from %s: %s", args.remote_server, peer_err)

    if args.show_info:
        if args.pci_addr:
            pprint(pci_details)
        elif args.vnic_int:
            pprint(vnic_details)
        elif args.veth_int:
            pprint(veth_details)
        elif args.hnv_int:
            pprint(hnv_details)

    cmd = ""
    if args.create_cfg:
        if args.vnic_int:
            cmd = create_config(interface_details=vnic_details, config_type='vnic')
            logger.info(cmd)
        elif args.veth_int:
            cmd = create_config(interface_details=veth_details, config_type='veth')
            logger.info(cmd)
        elif args.hnv_int:
            cmd = create_config(interface_details=hnv_details, config_type='hnv')
            logger.info(cmd)
        else:
            cmd = create_config(interface_details=pci_details, config_type='pci')
            logger.info(cmd)

    if args.run_test:
        os.system(cmd)

    # Always close the SSH connection when done
    if _runner:
        _runner.close()
