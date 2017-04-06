# Copyright (C) IBM Corp. 2016-2017.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Python wrapper for avocado
# Author: Satheesh Rajendran<sathnaga@linux.vnet.ibm.com>

import os
import re
import commands
import sys
import argparse
import ConfigParser
import binascii
from shutil import copyfile
from lib.logger import logger_init

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = "%s/config/wrapper/env.conf" % BASE_PATH
TEST_CONF_PATH = "%s/config/tests/" % BASE_PATH
CONFIGFILE = ConfigParser.SafeConfigParser()
CONFIGFILE.read(CONFIG_PATH)
INPUTFILE = ConfigParser.SafeConfigParser()
AVOCADO_REPO = CONFIGFILE.get('repo', 'avocado')
AVOCADO_VT_REPO = CONFIGFILE.get('repo', 'avocado_vt')
TEST_REPOS = CONFIGFILE.get('repo', 'tests').split(',')
REPOS = [AVOCADO_REPO, AVOCADO_VT_REPO]
TEST_DIR = "%s/tests" % BASE_PATH
DATA_DIR = "%s/data" % BASE_PATH
LOG_DIR = "%s/results" % BASE_PATH

logger = logger_init(filepath=BASE_PATH).getlogger()


class TestSuite():

    def __init__(self, name, resultdir, vt_type, test=None, mux=None):
        self.id = binascii.b2a_hex(os.urandom(20))
        self.name = str(name)
        self.shortname = "_".join(self.name.split('_')[1:])
        self.job_dir = None
        self.type = str(name.split('_')[0])
        self.resultdir = resultdir
        self.conf = None
        self.test = test
        self.mux = mux
        self.run = "Not_Run"
        self.runsummary = None
        self.runlink = None
        if self.type == 'guest':
            self.vt_type = vt_type
        else:
            self.vt_type = None

    def jobdir(self):
        cmd = 'grep %s %s/*/id|grep job-' % (self.id, self.resultdir)
        status, output = commands.getstatusoutput(cmd)
        if status == 0:
            self.job_dir = "/".join(output.split('/')[:-1])
        return self.job_dir

    def config(self):
        if self.type == 'guest':
            local_cfg = "%s/%s/%s/%s.cfg" % (TEST_CONF_PATH,
                                             self.type, self.vt_type,
                                             self.shortname)
            if not os.path.isfile(local_cfg):
                return self.conf
            cfg = "%s/avocado-vt/backends/%s/cfg/%s.cfg" % (DATA_DIR,
                                                            self.vt_type,
                                                            self.shortname)
            cmd = 'cp -f %s %s' % (local_cfg, cfg)
            os.system(cmd)
            self.conf = cfg
        elif self.type == 'host':
            local_cfg = "%s/%s/%s.cfg" % (TEST_CONF_PATH,
                                          self.type,
                                          self.shortname)
            if not os.path.isfile(local_cfg):
                return self.conf
            self.conf = local_cfg
        return self.conf

    def runstatus(self, status, summary="Tests Executed", link=None):
        self.run = status
        self.runsummary = summary
        self.runlink = link


def get_dist():
    """
    Return the distribution
    """
    dist = None
    if os.path.isfile('/etc/os-release'):
        fd = open('/etc/os-release', 'r')
        for line in fd.readlines():
            if line.startswith("ID="):
                try:
                    line.replace('"', '')
                    dist = re.findall("ID=(\S+)", line)[0]
                except:
                    pass
        fd.close()
    return dist


def get_avocado_bin():
    """
    Get the avocado executable path
    """
    logger.debug("Running 'which avocado'")
    status, avocado_binary = commands.getstatusoutput('which avocado')
    if status != 0:
        logger.error("avocado command not installed or not found in path")
        sys.exit(1)
    else:
        return avocado_binary


def env_check():
    """
    Check if the environment is proper
    """
    
    logger.info("Check for environment")
    not_found = []
    dist = get_dist()
    if 'ubuntu' in dist:
        env_deps = CONFIGFILE.get('deps_ubuntu', 'packages').split(',')
    elif 'sles' in dist:
        env_deps = CONFIGFILE.get('deps_sles', 'packages').split(',')
    elif  'centos' in dist:
        env_deps = CONFIGFILE.get('deps_centos', 'packages').split(',')
    elif 'rhel' in dist:
        env_deps = CONFIGFILE.get('deps_rhel', 'packages').split(',')
    else:
        # Not able to find the distribution, try use rpm
        env_deps = CONFIGFILE.get('deps_centos', 'packages').split(',')

    for dep in env_deps:
        if 'ubuntu' in dist:
            cmd = "dpkg -l|grep  ' %s'" % dep
        else:
            cmd = "rpm -qa|grep %s" % dep
        status, output = commands.getstatusoutput(cmd)
        if status != 0:
            logger.debug("Output: %s", output)
            not_found.append(dep)
    if not_found:
        if args.no_deps_check:
            logger.warning(
                "No dependancy check flag is set, proceeding with bootstrap")
            logger.info("Please install following "
                        "dependancy packages %s", " ".join(not_found))
        else:
            logger.error("Please install following "
                         "dependancy packages %s", " ".join(not_found))
            sys.exit(1)


def is_avocado_plugin_avl(plugin):
    """
    Check if the given avocado plugin installed
    """
    cmd = 'avocado plugins|grep %s' % plugin
    status, output = commands.getstatusoutput(cmd)
    if status != 0:
        logger.warning("Avocado %s plugin not installed", plugin)
        return False
    else:
        return True


def need_bootstrap():
    """
    Check if bootstrap required
    :return: True if bootstrap is needed
    """
    logger.info("Check if bootstrap required")
    needsBootstrap = False
    # Check for avocado
    status, output = commands.getstatusoutput('avocado')
    if 'command not ' in output:
        logger.info("Avocado needs to be installed")
        needsBootstrap = True
    # Check for avocado-vt
    for plugin in ['vt', 'vt-list', 'vt-bootstrap']:
        if not is_avocado_plugin_avl(plugin):
            logger.info("Avocado %s plugin needs to installed", plugin)
            needsBootstrap = True
    # Check for avocado-tests
    for repo in TEST_REPOS:
        repo_name = repo.split('/')[-1].split('.')[0]
        if not os.path.isdir(os.path.join(TEST_DIR, repo_name)):
            logger.info("Test needs to be downloaded/updated")
            needsBootstrap = True
    return needsBootstrap


def get_repo(repo, basepath, install=False):
    """
    To get given repo cloned/updated and install
    :param repo: repo link
    :param basepath: base path where the repository has to be downloaded
    :param install: To enable the flag to install the repo
    """
    repo_name = repo.split('/')[-1].split('.')[0]
    repo_path = os.path.join(basepath, repo_name)
    if os.path.isdir(repo_path):
        logger.info("Updating the repo: %s in %s", repo_name, repo_path)
        cmd = "cd %s;git remote update;git merge origin master" % repo_path
        try:
            commands.getstatusoutput(cmd)
        except Exception, error:
            logger.error("Failed to update %s ", error)
            sys.exit(1)
    else:
        cmd = "cd %s;git clone %s %s" % (basepath, repo, repo_name)
        try:
            commands.getstatusoutput(cmd)
        except Exception, error:
            logger.error("Failed to clone %s", error)
            sys.exit(1)
    if install:
        install_repo(repo_path)


def install_repo(path):
    """
    Install the given repo
    :param repo: repository path
    """
    logger.info("Installing repo: %s", path)
    cmd = "cd %s;make requirements;python setup.py install" % path
    try:
        status, output = commands.getstatusoutput(cmd)
        if status != 0:
            logger.debug("%s", output)
            logger.error("Error while installing: %s\n%s",
                         path.split('/')[-1], status)
            sys.exit(1)
        else:
            logger.debug("%s", output)
    except Exception, error:
        logger.error("Failed with exception during installing %s\n%s",
                     path.split('/')[-1], error)
        sys.exit(1)


def install_optional_plugin(plugin):
    """
    To install optional avocado plugin
    :param plugin: optional plugin name
    """
    if not is_avocado_plugin_avl(plugin):
        logger.info("Installing optional plugin: %s", plugin)
        plugin_path = "%s/avocado/optional_plugins/%s" % (BASE_PATH, plugin)
        if os.path.isdir(plugin_path):
            cmd = "cd %s;python setup.py install" %  plugin_path
            status, output = commands.getstatusoutput(cmd)
            if status != 0:
                logger.error("Error installing optional plugin: %s", plugin)
        else:
            logger.warning("optional plugin %s is not present in path %s,"
                           " skipping install", plugin, plugin_path)
    else:
        # plugin already installed
        pass


def create_config(logdir):
    """
    Create the local avocado config file
    :param logdir: Log directory
    """
    logger.info("Creating Avocado Config")
    config = ConfigParser.ConfigParser()
    os.system("mkdir -p ~/.config/avocado")
    avocado_conf = '%s/.config/avocado/avocado.conf' % os.environ['HOME']
    config.add_section('datadir.paths')
    config.set('datadir.paths', 'base_dir', BASE_PATH)
    config.set('datadir.paths', 'test_dir', TEST_DIR)
    config.set('datadir.paths', 'data_dir', DATA_DIR)
    config.set('datadir.paths', 'logs_dir', logdir)

    config.add_section('sysinfo.collect')
    config.set('sysinfo.collect', 'enabled', True)
    config.set('sysinfo.collect', 'profiler', True)
    with open(avocado_conf, 'w+') as conf:
        config.write(conf)


def vt_bootstrap(guestos):
    """
    Guest image downloading
    """
    avocado_bin = get_avocado_bin()
    logger.info("Downloading the guest os image")
    cmd = '%s vt-bootstrap --vt-guest-os %s --yes-to-all' % (avocado_bin,
                                                             guestos)
    os.system(cmd)


def bootstrap():
    """
    Prepare the environment for execution
    """
    env_clean()
    logger.info("Bootstraping")
    # Check if the avocado and avocado-vt installed in the system
    for repo in REPOS:
        get_repo(repo, BASE_PATH, True)
    avocado_bin = get_avocado_bin()
    # bootstrap_vt
    libvirt_cmd = '%s vt-bootstrap --vt-type libvirt \
                    --vt-no-downloads --yes-to-all' % avocado_bin
    os.system(libvirt_cmd)
    qemu_cmd = '%s vt-bootstrap --vt-type qemu --vt-no-downloads' % avocado_bin
    os.system(qemu_cmd)
    for repo in TEST_REPOS:
        os.system('mkdir -p %s' % TEST_DIR)
        get_repo(repo, TEST_DIR)


def run_test(testsuite, args=None):
    """
    To run given testsuite
    :param testsuite: Testsuite object which has details about the tests
    :param args: if any additional arguments
    """
    test_type = testsuite.type
    vt_type = testsuite.vt_type
    avocado_bin = get_avocado_bin()
    if 'guest' in test_type:
        conf = testsuite.config()
        logger.info("Running Guest Tests Suite %s", testsuite.shortname)
        cmd = "%s run --vt-type %s --vt-config %s \
                --force-job-id %s" % (avocado_bin, vt_type, conf, testsuite.id)
    if 'host' in test_type:
        logger.info("Running Host Tests Suite %s", testsuite.shortname)
        cmd = "%s run %s" % (avocado_bin, testsuite.test)
        if testsuite.mux:
            cmd += " -m %s" %os.path.join(TEST_DIR, testsuite.mux)
        cmd += " --force-job-id %s" % testsuite.id

    if args:
        cmd += " %s" % args
    try:
        logger.debug("Running: %s", cmd)
        os.system(cmd)
    except Exception, error:
        logger.info("Running testsuite %s failed with error\n%s",
                    testsuite.name, error)
        testsuite.runstatus("Not_Run", "command execution failed")
        return
    result_link = "%s/html/results.html" % testsuite.jobdir()
    testsuite.runstatus("Run", "Sucussfully executed", result_link)
    return


def env_clean():
    """
    Clean/uninstall avocado and autotest
    """
    logger.info("Uninstalling avocado and autotest from environment")
    for package in ['avocado', 'avocado_plugins_vt', 'autotest']:
        cmd = "yes|pip uninstall %s" % package
        try:
            (status, output) = commands.getstatusoutput(cmd)
        except:
            logger.error("Error in removing %s package: %s", package, output)


def edit_mux_file(test_config_name, mux_file_path):
    """
    Edit the mux file with input given in  input config file.
    """
    if not args.inputfile:
        return
    INPUTFILE.read(args.inputfile)
    if INPUTFILE.has_section(test_config_name):
        input_dic = {}
        for input_line in INPUTFILE.items(test_config_name):
            input_dic[input_line[0]] = input_line[1]
    else:
        logger.debug("Section %s not found in input file", test_config_name)

    with open(mux_file_path) as mux_fp:
        mux_str = mux_fp.read()

    mux_str_edited = []
    for line in mux_str.splitlines():
        if len(line) == 0 or line.lstrip()[0] == '#':
            continue
        for key, value in input_dic.iteritems():
            temp_line = line.split(":")
            mux_key = temp_line[0]
            mux_value = temp_line[1]
            if key == mux_key.strip():
                line = line.replace('%s' % line.strip(), '%s: %s' % (key, value))
        mux_str_edited.append(line)

    with open(mux_file_path, 'w') as mux_fp:
        mux_fp.write(str("\n".join(mux_str_edited)))


def parse_test_config(test_config_file):
    """
    Parses Test Config file and returns list of indivual tests dictionaries,
    with test path and yaml file path.
    """
    test_config_type = test_config_file[:test_config_file.find("_")]
    test_config_name = test_config_file[test_config_file.find("_") + 1:]
    test_config_file = "%s/%s/%s.cfg" % (TEST_CONF_PATH, test_config_type,
                                         test_config_name)
    if not os.path.isfile(test_config_file):
        logger.error("Test Config %s not present", test_config_file)
    else:
        with open(test_config_file, 'r') as fp:
            test_config_contents = fp.read()
        test_list = []
        mux_flag = 0
        for line in test_config_contents.splitlines():
            test_dic = {}
            if line.startswith("#"):
                continue
            line = line.split()
            test_dic['test'] = line[0]
            test_path = os.path.join(TEST_DIR, test_dic['test'])
            if not os.path.isfile(test_path):
                logger.debug("%s does not exist", test_path)
                continue
            test_dic['name'] = test_dic['test'].split("/")[-1].split(".")[0]
            if len(line) > 1:
                test_dic['mux'] = line[1]
                mux_file = os.path.join(TEST_DIR, test_dic['mux'])
                if not os.path.isfile(mux_file):
                    logger.debug("%s does not exist", mux_file)
                    continue
                edit_mux_file(test_config_name, mux_file)
                mux_flag = 1
            test_list.append(test_dic)
        if mux_flag == 0:
            single_test_dic = {}
            single_test_dic['name'] = test_config_name
            single_test_dic['test'] = ''
            for test in test_list:
                single_test_dic['test'] += " %s" % test['test']
            return [single_test_dic]
        return test_list


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bootstrap', dest='bootstrap',
                        action='store_true', default=False,
                        help="Prepares the environment for test")
    parser.add_argument('--run-suite', dest='run_suite',
                        action='store', default=None,
                        help="Indicate which test suite(s) to run")
    parser.add_argument('--output-dir', dest='outputdir',
                        action='store', default=None,
                        help="Specify the custom test results directory")
    parser.add_argument('--input-file', dest='inputfile',
                        action='store', default=None,
                        help="Provide an optional input file")
    parser.add_argument('--verbose', dest='verbose',
                        action='store_true', default=False,
                        help="Enable verbose output on the console")
    parser.add_argument('--only-filter', dest='only_filter',
                        action='store', default=None,
                        help='Add additional specific avocado tests or features to the guest test suite')
    parser.add_argument('--no-filter', dest='no_filter',
                        action='store', default=None,
                        help='Exclude specific avocado tests or features from the guest test suite')
    parser.add_argument('--additional-args', dest='add_args',
                        action='store', default=None,
                        help="Pass additional arguments to the command")
    parser.add_argument('--guest-os', dest='guest_os',
                        action='store', default='CentOS.7.2.ppc64le',
                        help="Specify the Guest OS. Default: CentOS.7.2.ppc64le")
    parser.add_argument('--vt', dest='vt_type',
                        action='store', choices=['qemu', 'libvirt'],
                        default='libvirt',
                        help="Provide VT: qemu or libvirt. Default: libvirt")
    parser.add_argument('--install', dest='install_guest',
                        action='store_true', default=False,
                        help="Install the Guest VM. Highly recommended for guest tests.")
    parser.add_argument('--no-download', dest='no_guest_download',
                        action='store_true', default=False,
                        help='Skip the guest image download')
    parser.add_argument('--no-deps-check', dest="no_deps_check",
                        action='store_true', default=False,
                        help="Skip check for dependancy packages")
    parser.add_argument('--clean', dest="clean",
                        action='store_true', default=False,
                        help="Remove/Uninstall autotest and avocado from the system")

    args = parser.parse_args()
    env_check()
    additional_args = ' --output-check-record all'
    if args.verbose:
        additional_args = ' --show-job-log'
    if args.outputdir:
        # Check if it valid path
        if not os.path.isdir(os.path.abspath(args.outputdir)):
            raise ValueError("No output dir")
        outputdir = os.path.join(args.outputdir, 'results')
    else:
        outputdir = os.path.join(BASE_PATH, 'results')

    additional_args += ' --job-results-dir %s' % outputdir

    if (args.bootstrap or need_bootstrap()):
        create_config(outputdir)
        bootstrap()
        # Install optional plugins from config file
        plugins = CONFIGFILE.get('plugins', 'optional').split(',')
        for plugin in plugins:
            install_optional_plugin(plugin)
        # Copy if any isos present in the local folder
        dst_iso_path = "%s/avocado-vt/isos/linux/" % DATA_DIR
        if not os.path.isdir(dst_iso_path):
            os.system('mkdir -p %s' % dst_iso_path)
        for fle in os.listdir("%s/isos" % BASE_PATH):
            if fle.endswith(".iso"):
                file_path = os.path.join(BASE_PATH, 'isos', fle)
                dst_file = os.path.join(dst_iso_path, fle)
                copyfile(file_path, dst_file)

    if args.inputfile:
        if not os.path.isfile(args.inputfile):
            logger.debug("Input file %s not found. Continuing without input file", args.inputfile)
            args.inputfile = None

    if args.run_suite:
        test_suites = args.run_suite.split(',')
        if args.install_guest:
            test_suites.insert(0, 'guest_install')
        Testsuites = {}
        # Validate if given test suite is available
        # run Guest tests
        Testsuites_list = []
        for test_suite in test_suites:
            if 'host' in test_suite:
                test_list = parse_test_config(test_suite)
                if test_list is None:
                    Testsuites[test_suite] = TestSuite(test_suite, outputdir,
                                                       args.vt_type)
                    Testsuites[test_suite].runstatus("Cant_Run",
                                                     "Config file not present")
                    continue
                for test in test_list:
                    if not test.has_key('mux'):
                        test['mux'] = ''
                    test_suite_name = "%s_%s" % (test_suite, test['name'])
                    Testsuites[test_suite_name] = TestSuite(test_suite_name,
                                                            outputdir, args.vt_type,
                                                            test['test'], test['mux'])
                    Testsuites_list.append(test_suite_name)

            if 'guest' in test_suite:
                Testsuites[test_suite] = TestSuite(str(test_suite),
                                                   outputdir, args.vt_type)
                Testsuites_list.append(str(test_suite))
                if not Testsuites[test_suite].config():
                    Testsuites[test_suite].runstatus("Cant_Run",
                                                     "Config file not present")
                    continue

                # Lets make sure we have the default image boot straped
                if not args.no_guest_download:
                    vt_bootstrap(args.guest_os)
                only_filter = None
                if args.only_filter:
                    only_filter = args.only_filter
                if args.guest_os:
                    if only_filter:
                        only_filter += ' %s' % args.guest_os
                    else:
                        only_filter = args.guest_os
                if only_filter:
                    additional_args += ' --vt-only-filter \
                                        "%s"' % only_filter
                if args.no_filter:
                    additional_args += ' --vt-no-filter "%s"' % args.no_filter
            if args.add_args:
                additional_args += " %s" % args.add_args

        # Run Tests
        for test_suite in Testsuites_list:
            if not Testsuites[test_suite].run == "Cant_Run":
                run_test(Testsuites[test_suite], additional_args)

        # List the final output
        logger.info("Summary of test results can be found below:")
        print "%-25s %-10s %-85s %-20s" % ('TestSuite', 'Testrun', 'ResultLink', 'Summary')

        for test_suite in Testsuites_list:
            print '%-25s %-10s %-85s %-20s' % (Testsuites[test_suite].name,
                                               Testsuites[test_suite].run,
                                               Testsuites[test_suite].runlink,
                                               Testsuites[test_suite].runsummary)
    if args.clean:
        env_clean()
