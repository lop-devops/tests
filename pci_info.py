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
from lib.logger import logger_init

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = "%s/config/wrapper/pci_input.conf" % BASE_PATH
CONFIGFILE = configparser.SafeConfigParser()
CONFIGFILE.optionxform = str
CONFIGFILE.read(CONFIG_PATH)
BASE_INPUTFILE_PATH = "%s/config/inputs" % BASE_PATH
input_path = "io_input.txt"
INPUTFILE = configparser.ConfigParser()
INPUTFILE.optionxform = str
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
    test_suites = []
    input_file_string = ""
    input_params = []
    additional_params = args.add_params.split()

    # fetching additional parameters with comma seperated to input
    # when multiple entires provided.
    if config_type == 'vnic':
        if len(additional_params) != 0:
            additional_params = args.add_params.split(",")

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
                    if config_type == 'vnic':
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
        key = param.split('=')[0]
        # handling additional params per pci
        if '::' in key:
            pci_root = key.split('::')[0].split('.')[0]
            if pci_root != pci['pci_root']:
                continue
            key = key.split('::')[1]

        # check if the newly added additional param is same
        # as inputfile assign the values directly
        if key in inputfile_dict:
            inputfile_dict[key] = param.split('=')[1]
        else:
            # if it is completly new then directly write to new input file
            value = param.split('=')[1]
            INPUTFILE.set(new_cfg, key, "\"%s\"" % value)

    # append the remaining input file entries to the new input file
    for inputkey, inputvalue in inputfile_dict.items():
        INPUTFILE.set(new_cfg, inputkey, "%s" % inputvalue)

    return test_suites, input_file_string, input_params


def create_config(interface_details, config_type):
    """
    Creates avocado test suite / config file, and input file needed for yaml files in that config files.

    Parameters:
        interface_details(list): The detailed differnet Interface parameters in list format.
        config_type (str): The type of configuration to generate. Ex: PCI, vNIC etc.
    """
    if config_type == 'pci':
        for pci in interface_details:
            if pci['is_root_disk']:
                logger.debug("ignoring pci address %s as it contains root disk", pci['pci_root'])
                continue
            cfg_name = "_".join(pci['pci_root'].split(':'))
            orig_cfg = "io_%s_fvt" % pci['adapter_type']
            new_cfg = "io_%s_%s_fvt" % (pci['adapter_type'], cfg_name)
            inputfile = "%s/io_%s_input.txt" % (BASE_INPUTFILE_PATH, pci['adapter_type'])
            if not os.path.exists("config/tests/host/%s.cfg" % orig_cfg):
                logger.debug("ignoring pci address %s as there is no cfg for %s", pci['pci_root'], pci['adapter_type'])
                continue
            test_suites, input_file_string, input_params = create_config_inputs(orig_cfg, new_cfg, inputfile, pci, config_type='pci')

    if config_type == 'vnic':
        for virtual in interface_details:
            cfg_name = virtual['adapter_type']
            orig_cfg = "io_%s_dynamic_fvt" % virtual['adapter_type']
            new_cfg = "io_%s_%s_dymamic_fvt" % (virtual['interfaces'][0], cfg_name)
            inputfile = "%s/io_%s_input.txt" % (BASE_INPUTFILE_PATH, virtual['adapter_type'])
            if not os.path.exists("config/tests/host/%s.cfg" % orig_cfg):
                logger.debug("ignoring vnic address as there is no cfg for %s", virtual['adapter_type'])
                continue
            test_suites, input_file_string, input_params = create_config_inputs(orig_cfg, new_cfg, inputfile, virtual, config_type='vnic')

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
    parser.add_argument('--vnic', dest='vnic_int', action='store', default='env3',
                        help='vNIC interface name')
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
                        help='Additional parameters(key=value) to the input file, space separated')
    args = parser.parse_args()

    try:
        if args.vnic_int:
            vnic_details = virtual.virtual_info(args.vnic_int)
        elif args.pci_addr:
            pci_details = pci.pci_info(args.pci_addr, pci_type=args.pci_type, pci_blocklist=args.pci_addr_blocklist, type_blocklist=args.type_blocklist)
        else:
            pci_details = pci.all_pci_info(pci_type=args.pci_type, pci_blocklist=args.pci_addr_blocklist, type_blocklist=args.type_blocklist)
    except Exception as e:
        if args.vnic_int:
            logger.info("vNIC interface not found")
        else:
            logger.info("No PCI Found")
        sys.exit(0)

    if args.show_info:
        if args.pci_addr:
            pprint(pci_details)
        elif args.vnic_int:
            pprint(vnic_details)

    if args.create_cfg:
        if args.vnic_int:
            cmd = create_config(interface_details=vnic_details, config_type='vnic')
            logger.info(cmd)
        else:
            cmd = create_config(interface_details=pci_details, config_type='pci')
            logger.info(cmd)
    if args.run_test:
        os.system(cmd)
