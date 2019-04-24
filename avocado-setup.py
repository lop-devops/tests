# Copyright (C) IBM Corp. 2016.
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
import shutil
import time
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
NORUNTEST_PATH = "%s/config/wrapper/no_run_tests.conf" % BASE_PATH
TEST_CONF_PATH = "%s/config/tests/" % BASE_PATH
CONFIGFILE = ConfigParser.SafeConfigParser()
CONFIGFILE.read(CONFIG_PATH)
NORUNTESTFILE = ConfigParser.SafeConfigParser()
NORUNTESTFILE.read(NORUNTEST_PATH)
INPUTFILE = ConfigParser.SafeConfigParser()
INPUTFILE.optionxform = str
AVOCADO_REPO = CONFIGFILE.get('repo', 'avocado')
AVOCADO_VT_REPO = CONFIGFILE.get('repo', 'avocado_vt')
TEST_REPOS = CONFIGFILE.get('repo', 'tests').split(',')
REPOS = [AVOCADO_REPO, AVOCADO_VT_REPO]
TEST_DIR = "%s/tests" % BASE_PATH
DATA_DIR = "%s/data" % BASE_PATH
LOG_DIR = "%s/results" % BASE_PATH

logger = logger_init(filepath=BASE_PATH).getlogger()


class TestSuite():
    guest_add_args = ""
    host_add_args = ""

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

    def runstatus(self, status, summary="Tests Executed", link=''):
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
                    line = line.replace('"', '')
                    dist = re.findall("ID=(\S+)", line)[0]
                except:
                    pass
        fd.close()
    return dist


def get_dist_ver():
    """
    Return the distribution version ex: 15
    """
    dist_ver = None
    if os.path.isfile('/etc/os-release'):
        fd = open('/etc/os-release', 'r')
        for line in fd.readlines():
            if line.startswith("VERSION="):
                try:
                    line = line.replace('"', '')
                    dist_ver = re.findall("VERSION=(\S+)", line)[0]
                except:
                    pass
        fd.close()
    return re.match('(\d*)(\.)*(\d+)', dist_ver).group()


def get_machine_type():
    """
    Return What kind of machine example: pHyp/PowerNV
    """
    machine_type = None
    cpuinfo = '/proc/cpuinfo'
    if os.path.isfile(cpuinfo):
        fd = open(cpuinfo, 'r')
        for line in fd.readlines():
            if 'PowerNV' in line:
                machine_type = 'PowerNV'
            elif 'pSeries' in line:
                machine_type = 'pHyp'
        fd.close()
    return machine_type


def get_env_type():
    """
    Return what environment the system is: Distro, Version, Type
    """
    dist = get_dist()
    dist_ver = get_dist_ver()
    machine_type = get_machine_type()
    env_type = dist
    if os.uname()[-1] == 'ppc64':
        env_type += 'be'
    if dist == "sles" and dist_ver == "15":
        env_type += dist_ver
    elif dist == "rhel" and dist_ver == "8.0":
        env_type += dist_ver
    if machine_type == "pHyp":
        env_type += "_pHyp"
    return env_type


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


def pip_install():
    """
    install package using pip
    """
    logger.info("install packages via pip interface")

    pip_cmd = 'pip%s' % sys.version_info[0]

    if CONFIGFILE.has_section('pip-package'):
        package = CONFIGFILE.get('pip-package', 'package').split(',')
        for dep in package:
            cmd = '%s install %s' % (pip_cmd, dep)
            status, output = commands.getstatusoutput(cmd)
            if status != 0:
                logger.error(
                    'Package installation via pip failed: package  %s' % dep)
                sys.exit(1)
            else:
                logger.debug("%s package installation successful" % dep)


def env_check():
    """
    Check if the environment is proper
    """
    logger.info("Check for environment")
    # create a folder to store all edited multiplexer files
    if not os.path.isdir("/tmp/mux/"):
        logger.info("Creating temporary mux dir")
        os.makedirs("/tmp/mux/")
    not_found = []
    env_type = get_env_type()
    if CONFIGFILE.has_section('deps_%s' % env_type):
        env_deps = CONFIGFILE.get('deps_%s' % env_type, 'packages').split(',')
    else:
        # Not able to find the distribution, try use rpm
        env_deps = CONFIGFILE.get('deps_centos', 'packages').split(',')

    for dep in env_deps:
        if 'ubuntu' in env_type:
            cmd = "dpkg -l|grep  ' %s'" % dep
        else:
            cmd = "rpm -qa|grep %s" % dep
        status, output = commands.getstatusoutput(cmd)
        if status != 0:
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
    pip_install()


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
    logger.debug("Check if bootstrap required")
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
        err_str = "Failed to update %s repository:" % repo_name
        try:
            status, output = commands.getstatusoutput(cmd)
            if status != 0:
                logger.error("%s %s", err_str, output)
                sys.exit(1)
            logger.debug("%s", output)
        except Exception, error:
            logger.error("%s %s ", err_str, error)
            sys.exit(1)
    else:
        err_str = "Failed to clone %s repository:" % repo_name
        cmd = "cd %s;git clone %s %s" % (basepath, repo, repo_name)
        try:
            status, output = commands.getstatusoutput(cmd)
            if status != 0:
                logger.error("%s %s", err_str, output)
                sys.exit(1)
            logger.debug("%s", output)
        except Exception, error:
            logger.error("%s %s", err_str, error)
            sys.exit(1)
    if install:
        install_repo(repo_path)


def install_repo(path):
    """
    Install the given repo
    :param repo: repository path
    """
    logger.info("Installing repo: %s", path)
    cmd = "cd %s;make requirements;make requirements-selftests;python setup.py install" % path
    try:
        err_str = "Failed to install %s repository:" % path.split('/')[-1]
        status, output = commands.getstatusoutput(cmd)
        if status != 0:
            logger.error("%s %s", err_str, output)
            sys.exit(1)
        logger.debug("%s", output)
    except Exception, error:
        logger.error("%s %s", err_str, error)
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
            cmd = "cd %s;python setup.py install" % plugin_path
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
    config.set('sysinfo.collect', 'per_test', True)

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
    err_str = "Failed to Download Guest OS. Error:"
    try:
        status, output = commands.getstatusoutput(cmd)
        if status != 0:
            logger.info("%s %s", err_str, output)
            sys.exit(1)
        logger.debug("%s", output)
    except Exception, error:
        logger.error("%s %s ", err_str, error)
        sys.exit(1)


def bootstrap():
    """
    Prepare the environment for execution
    """
    env_clean()
    logger.info("Bootstrapping")
    # Check if the avocado and avocado-vt installed in the system
    for repo in REPOS:
        get_repo(repo, BASE_PATH, True)
    avocado_bin = get_avocado_bin()
    # bootstrap_vt
    logger.info("Bootstrapping vt libvirt")
    libvirt_cmd = '%s vt-bootstrap --vt-type libvirt \
                  --vt-update-providers --vt-skip-verify-download-assets \
                  --yes-to-all' % avocado_bin
    err_str = "Failed to bootstrap vt libvirt. Error:"
    try:
        status, output = commands.getstatusoutput(libvirt_cmd)
        if status != 0:
            logger.error("%s %s", err_str, output)
            sys.exit(1)
        logger.debug("%s", output)
    except Exception, error:
        logger.error("%s %s ", err_str, error)
        sys.exit(1)
    logger.info("Bootstrapping vt qemu")
    qemu_cmd = '%s vt-bootstrap --vt-type qemu --vt-update-providers \
               --vt-skip-verify-download-assets --yes-to-all' % avocado_bin
    err_str = "Failed to bootstrap vt qemu. Error:"
    try:
        status, output = commands.getstatusoutput(qemu_cmd)
        if status != 0:
            logger.error("%s %s", err_str, output)
            sys.exit(1)
        logger.debug("%s", output)
    except Exception, error:
        logger.error("%s %s ", err_str, error)
        sys.exit(1)
    for repo in TEST_REPOS:
        try:
            logger.info("creating test repo dir %s", TEST_DIR)
            status, output = commands.getstatusoutput('mkdir -p %s' % TEST_DIR)
            logger.debug("%s", output)
        except Exception, error:
            logger.error("Failed to create test repo dir. Error: %s", error)
            sys.exit(1)
        get_repo(repo, TEST_DIR)


def run_test(testsuite, avocado_bin):
    """
    To run given testsuite
    :param testsuite: Testsuite object which has details about the tests
    :param avocado_bin: Executable path of avocado
    """
    logger.info('')
    if 'guest' in testsuite.type:
        guest_args = TestSuite.guest_add_args
        logger.info("Running Guest Tests Suite %s", testsuite.shortname)
        if "sanity" in testsuite.shortname:
            guest_args = " --vt-only-filter %s " % args.guest_os
        cmd = "%s run --vt-type %s --vt-config %s \
                --force-job-id %s %s" % (avocado_bin, testsuite.vt_type,
                                         testsuite.config(),
                                         testsuite.id, guest_args)
    if 'host' in testsuite.type:
        logger.info("Running Host Tests Suite %s", testsuite.shortname)
        cmd = "%s run %s" % (avocado_bin, testsuite.test)
        if testsuite.mux:
            cmd += " -m %s" % os.path.join(TEST_DIR, testsuite.mux)
        cmd += " --force-job-id %s %s" % (testsuite.id, TestSuite.host_add_args)

    try:
        logger.info("Running: %s", cmd)
        status = os.system(cmd)
        status = int(bin(int(status))[2:].zfill(16)[:-8], 2)
        if status >= 2:
            testsuite.runstatus("Not_Run", "Command execution failed")
            return
    except Exception, error:
        logger.error("Running testsuite %s failed with error\n%s",
                     testsuite.name, error)
        testsuite.runstatus("Not_Run", "Command execution failed")
        return
    logger.info('')
    result_link = "%s/job.log" % testsuite.jobdir()
    testsuite.runstatus("Run", "Successfully executed", result_link)
    return


def env_clean():
    """
    Clean/uninstall avocado and autotest
    """
    logger.info("Uninstalling avocado and autotest from environment")
    for package in ['avocado', 'avocado_plugins_vt', 'autotest']:
        cmd = "pip uninstall %s -y --disable-pip-version-check" % package
        err_str = "Error in removing package: %s" % package
        try:
            status, output = commands.getstatusoutput(cmd)
            if status != 0:
                logger.error("%s %s", err_str, output)
            logger.debug("%s", output)
        except Exception, error:
            logger.error("%s %s", err_str, error)
            sys.exit(1)


def edit_mux_file(test_config_name, mux_file_path, tmp_mux_path):
    """
    Edit the mux file with input given in  input config file.
    """
    INPUTFILE.read(args.inputfile)
    if INPUTFILE.has_section(test_config_name):
        input_dic = {}
        for input_line in INPUTFILE.items(test_config_name):
            input_dic[input_line[0]] = input_line[1]
    else:
        logger.debug("Section %s not found in input file", test_config_name)
        shutil.copyfile(mux_file_path, tmp_mux_path)
        return

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

    with open(tmp_mux_path, 'w') as mux_fp:
        mux_fp.write(str("\n".join(mux_str_edited)))


def parse_test_config(test_config_file, avocado_bin):
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
        env_type = get_env_type()
        if NORUNTESTFILE.has_section('norun_%s' % env_type):
            norun_tests = NORUNTESTFILE.get('norun_%s' % env_type, 'tests').split(',')
        with open(test_config_file, 'r') as fp:
            test_config_contents = fp.read()
        test_list = []
        mux_flag = 0
        for line in test_config_contents.splitlines():
            test_dic = {}
            if line in norun_tests:
                continue
            if line.startswith("#") or not line:
                continue
            line = line.split()
            test_dic['test'] = line[0].strip('$')
            test_dic['name'] = test_dic['test'].split("/")[-1]
            if ":" in test_dic['test'].split("/")[-1]:
                test_dic['name'] = "%s_%s" % (test_dic['name'].split(".")[0],
                                              test_dic['name'].split(":")[-1].replace(".", "_"))
                test_dic['test'] = "%s$" % test_dic['test']
            else:
                test_dic['name'] = test_dic['name'].split(".")[0]
            cmd = "%s list %s 2> /dev/null" % (avocado_bin, test_dic['test'])
            (status, output) = commands.getstatusoutput(cmd)
            logger.debug("%s does not exist", test_dic['test'])
            if status != 0:
                continue
            if len(line) > 1:
                test_dic['mux'] = line[1]
                mux_flag = 1
                test_dic['name'] = "%s_%s" % (test_dic['name'], test_dic['mux'].split("/")[-1].split(".")[0])
                if args.inputfile:
                    mux_file = os.path.join(TEST_DIR, test_dic['mux'])
                    if not os.path.isfile(mux_file):
                        logger.debug("%s does not exist", mux_file)
                        continue
                    tmp_mux_path = os.path.join('/tmp/mux/', "%s_%s.yaml" % (test_config_name, test_dic['name']))
                    edit_mux_file(test_config_name, mux_file, tmp_mux_path)
                    test_dic['mux'] = tmp_mux_path
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
                        help='Prepare the environment for test')
    parser.add_argument('--run-suite', dest='run_suite',
                        action='store', default=None,
                        help='Indicate which test suite(s) to run')
    parser.add_argument('--output-dir', dest='outputdir',
                        action='store', default=None,
                        help='Specify the custom test results directory')
    parser.add_argument('--input-file', dest='inputfile',
                        action='store', default=None,
                        help='Specify input file for custom mux values for host tests')
    parser.add_argument('--interval-time', dest='interval',
                        action='store', default=None,
                        help='Specify the interval time between tests')
    parser.add_argument('--verbose', dest='verbose',
                        action='store_true', default=False,
                        help='Enable verbose output on the console')
    parser.add_argument('--only-filter', dest='only_filter',
                        action='store', default="",
                        help='Add filters to include specific avocado tests,'
                        'features from the guest test suite')
    parser.add_argument('--no-filter', dest='no_filter',
                        action='store', default="",
                        help='Add filters to exclude specific avocado tests,'
                        'features from the guest test suite')
    parser.add_argument('--additional-args', dest='add_args',
                        action='store', default="",
                        help='Pass additional arguments to the command')
    parser.add_argument('--guest-os', dest='guest_os',
                        action='store', default='JeOS.27.ppc64le',
                        help='Provide Guest os: Default: JeOS.27.ppc64le')
    parser.add_argument('--vt', dest='vt_type',
                        action='store', choices=['qemu', 'libvirt'],
                        default='libvirt',
                        help='Provide VT: qemu or libvirt Default: libvirt')
    parser.add_argument('--install', dest='install_guest',
                        action='store_true', default=False,
                        help='Install the Guest VM, if needed.')
    parser.add_argument('--no-download', dest='no_guest_download',
                        action='store_true', default=False,
                        help='To download the preinstalled guest image')
    parser.add_argument('--no-deps-check', dest="no_deps_check",
                        action='store_true', default=False,
                        help='To force wrapper not to check for dependancy packages')
    parser.add_argument('--clean', dest="clean",
                        action='store_true', default=False,
                        help='To remove/uninstall autotest, avocado from system')

    args = parser.parse_args()
    env_check()
    additional_args = args.add_args
    if args.verbose:
        additional_args += ' --show-job-log'
    if args.outputdir:
        # Check if it valid path
        if not os.path.isdir(os.path.abspath(args.outputdir)):
            raise ValueError("No output dir")
        outputdir = os.path.join(args.outputdir, 'results')
    else:
        outputdir = os.path.join(BASE_PATH, 'results')

    additional_args += ' --job-results-dir %s' % outputdir
    bootstraped = False
    if (args.bootstrap or need_bootstrap()):
        create_config(outputdir)
        bootstrap()
        bootstraped = True
        if args.guest_os and not args.no_guest_download:
            vt_bootstrap(args.guest_os)
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
        if "guest_" in args.run_suite:
            # Make sure we download guest image once
            if not args.no_guest_download and not bootstraped:
                vt_bootstrap(args.guest_os)
            only_filter = args.only_filter
            if only_filter:
                only_filter += ' %s' % args.guest_os
            else:
                only_filter = args.guest_os
            if only_filter:
                TestSuite.guest_add_args += ' --vt-only-filter \
                                            "%s"' % only_filter
            if args.no_filter:
                TestSuite.guest_add_args += ' --vt-no-filter \
                                            "%s"' % args.no_filter
            if additional_args:
                TestSuite.guest_add_args += additional_args
        if "host_" in args.run_suite:
            TestSuite.host_add_args = additional_args
        test_suites = args.run_suite.split(',')
        if args.install_guest:
            test_suites.insert(0, 'guest_install')
        avocado_bin = get_avocado_bin()
        Testsuites = {}
        # Validate if given test suite is available
        # and init TestSuite object for each test suite
        Testsuites_list = []
        for test_suite in test_suites:
            if 'host' in test_suite:
                test_list = parse_test_config(test_suite, avocado_bin)
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
                guest_additional_args = ""
                Testsuites[test_suite] = TestSuite(str(test_suite),
                                                   outputdir, args.vt_type)
                Testsuites_list.append(str(test_suite))
                if not Testsuites[test_suite].config():
                    Testsuites[test_suite].runstatus("Cant_Run",
                                                     "Config file not present")
                    continue
        # Run Tests
        for test_suite in Testsuites_list:
            if not Testsuites[test_suite].run == "Cant_Run":
                run_test(Testsuites[test_suite], avocado_bin)
                if args.interval:
                    time.sleep(int(args.interval))

        # List the final output
        summary_output = ["Summary of test results can be found below:\n%-75s %-10s %-20s" % ('TestSuite', 'TestRun', 'Summary')]
        for test_suite in Testsuites_list:
            summary_output.append(' ')
            summary_output.append('%-75s %-10s %-20s' % (Testsuites[test_suite].name,
                                                         Testsuites[test_suite].run,
                                                         Testsuites[test_suite].runsummary))
            summary_output.append(Testsuites[test_suite].runlink)
        logger.info("\n".join(summary_output))

    if os.path.isdir("/tmp/mux/"):
        logger.info("Removing temporary mux dir")
        shutil.rmtree("/tmp/mux/")

    if args.clean:
        env_clean()
