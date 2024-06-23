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

from pprint import pprint
from lib import pci
import argparse
import shutil
import os
import sys
import configparser
from lib.logger import logger_init
from lib.helper import is_rhel8

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = "%s/config/wrapper/pci_input.conf" % BASE_PATH
CONFIGFILE = configparser.SafeConfigParser()
CONFIGFILE.optionxform = str
CONFIGFILE.read(CONFIG_PATH)
BASE_INPUTFILE_PATH = "%s/config/inputs" % BASE_PATH
input_path = "io_input.txt"
INPUTFILE = configparser.ConfigParser()
INPUTFILE.optionxform = str
args = None

logger = logger_init(filepath=BASE_PATH).getlogger()


def create_config(pci_list):
    """
    Creates avocado test suite / config file, and input file needed for yaml files in that config files.
    """
    test_suites = []
    input_file_string = ""
    input_params = []
    additional_params = args.add_params.split()
    for pci in pci_list:
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
        else:
            orig_cfg = "io_%s_fvt" % pci['adapter_type']
            new_cfg = "io_%s_%s_fvt" % (pci['adapter_type'], cfg_name)
            inputfile = "%s/io_%s_input.txt" % (
                BASE_INPUTFILE_PATH, pci['adapter_type'])
        if not os.path.exists("config/tests/host/%s.cfg" % orig_cfg):
            logger.debug("ignoring pci address %s as there is no cfg for %s",
                         pci['pci_root'], pci['adapter_type'])
            continue
        shutil.copy("config/tests/host/%s.cfg" %
                    orig_cfg, "config/tests/host/%s.cfg" % new_cfg)
        test_suites.append("host_%s" % new_cfg)

        # adding info to input file
        if not CONFIGFILE.has_section(orig_cfg) and not additional_params:
            continue
        input_params = CONFIGFILE.items(orig_cfg)
        if not input_params:
            continue
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
                    value = pci[param[1]]
                else:
                    index = param[1].split(':')[0]
                    index_exact = param[1].split(':')[1]
                    if index_exact == 'all':
                        value = " ".join(pci[index])
                    else:
                        value = pci[index][int(index_exact)]
                        if len(pci[index]) > 1 and not key == 'pci_device':
                            del pci[index][int(index_exact)]
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

    test_suites = ",".join(test_suites)

    # write to input file
    if input_params:
        with open(input_path, 'w+') as input:
            INPUTFILE.write(input)
        input_file_string = "--input-file %s" % input_path

    # generate avocado-setup command line
    if test_suites:
        cmd = "python avocado-setup.py --run-suite %s %s" % (
            test_suites, input_file_string)
        return cmd
    return ""


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pci-address', dest='pci_addr',
                        action='store', default='',
                        help='pci address, comma separated')
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
    if args.pci_addr:
        pci_details = pci.pci_info(args.pci_addr, pci_type=args.pci_type,
                                   pci_blocklist=args.pci_addr_blocklist, type_blocklist=args.type_blocklist)
    else:
        pci_details = pci.all_pci_info(
            pci_type=args.pci_type, pci_blocklist=args.pci_addr_blocklist, type_blocklist=args.type_blocklist)
    if not pci_details:
        logger.info("No PCI Found")
        sys.exit(0)
    if args.show_info:
        pprint(pci_details)
    if args.create_cfg:
        cmd = create_config(pci_details)
        logger.info(cmd)
    if args.run_test:
        os.system(cmd)
