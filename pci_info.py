#!/usr/bin/env python

from pprint import pprint
from lib import pci
import argparse
import shutil
import os
import sys
import ConfigParser
from lib.logger import logger_init

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = "%s/config/wrapper/pci_input.conf" % BASE_PATH
CONFIGFILE = ConfigParser.SafeConfigParser()
CONFIGFILE.optionxform = str
CONFIGFILE.read(CONFIG_PATH)
input_path = "io_input.txt"
INPUTFILE = ConfigParser.ConfigParser()
INPUTFILE.optionxform = str

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
            logger.debug("ignoring pci address %s as it contains root disk", pci['pci_root'])
            continue

        # copy template cfg files and create new ones
        cfg_name = "_".join(pci['pci_root'].split(':'))
        orig_cfg = "io_%s_fvt" % pci['adapter_type']
        new_cfg = "io_%s_%s_fvt" % (pci['adapter_type'], cfg_name)
        if not os.path.exists("config/tests/host/%s.cfg" % orig_cfg):
            logger.debug("ignoring pci address %s as there is no cfg for %s", pci['pci_root'], pci['adapter_type'])
            continue
        shutil.copy("config/tests/host/%s.cfg" % orig_cfg, "config/tests/host/%s.cfg" % new_cfg)
        test_suites.append("host_%s" % new_cfg)

        # adding info to input file
        if not CONFIGFILE.has_section(orig_cfg) and not additional_params:
            continue
        input_params = CONFIGFILE.items(orig_cfg)
        if not input_params:
            continue
        INPUTFILE.add_section(new_cfg)
        for param in input_params:
            try:
                key = param[0]
                if ':' not in param[1]:
                    value = pci[param[1]]
                else:
                    index = param[1].split(':')[0]
                    index_exact = param[1].split(':')[1]
                    if index_exact == 'all':
                        value = ",".join(pci[index])
                    else:
                        value = pci[index][int(index_exact)]
                INPUTFILE.set(new_cfg, key, "\"%s\"" % value)
            except:
                pass
        for param in additional_params:
            key = param.split('=')[0]
            value = param.split('=')[1]
            INPUTFILE.set(new_cfg, key, "\"%s\"" % value)
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
    parser.add_argument('--pci-address-blacklist', dest='pci_addr_blacklist',
                        action='store', default='',
                        help='pci address which need not be considered, comma separated')
    parser.add_argument('--type', dest='type',
                        action='store', default='',
                        help='type of adapters, comma separated')
    parser.add_argument('--type-blacklist', dest='type_blacklist',
                        action='store', default='',
                        help='type of adapters to blacklist, comma separated')
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
        pci_details = pci.pci_info(args.pci_addr, type=args.type, pci_blacklist=args.pci_addr_blacklist, type_blacklist=args.type_blacklist)
    else:
        pci_details = pci.all_pci_info(type=args.type, pci_blacklist=args.pci_addr_blacklist, type_blacklist=args.type_blacklist)
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
