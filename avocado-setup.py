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
#

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
AVOCADO_REPO = CONFIGFILE.get('repo', 'avocado')
AVOCADO_VT_REPO = CONFIGFILE.get('repo', 'avocado_vt')
TEST_REPOS = CONFIGFILE.get('repo', 'tests').split(',')
REPOS = [AVOCADO_REPO, AVOCADO_VT_REPO]
ENV_DEPS = CONFIGFILE.get('deps', 'packages').split(',')
TEST_DIR = "%s/tests" % BASE_PATH
DATA_DIR = "%s/data" % BASE_PATH
LOG_DIR = "%s/results" % BASE_PATH
AVOCADO_BIN = "/usr/bin/avocado"

logger = logger_init(filepath=BASE_PATH).getlogger()


class TestSuite():

    def __init__(self, name, resultdir, vt_type):
        self.id = binascii.b2a_hex(os.urandom(20))
        self.name = str(name)
        self.shortname = "_".join(self.name.split('_')[1:])
        self.job_dir = None
        self.type = str(name.split('_')[0])
        self.resultdir = resultdir
        self.conf = None
        self.run = "Not Run"
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


def is_present(package, package_list):
    """
    Check if the given package is installed in the system
    :param package: Name of the package
    """
    result = re.findall('^%s-[0-9].*' % package, package_list, re.M)
    if result:
        return True
    else:
        return False


def env_check():
    """
    Check if the environment is proper
    """
    logger.info("Check for environment")
    # :TODO: Check expects rpm to be available in system
    # this is not true in all distributions
    status, pack_list = commands.getstatusoutput("rpm -qa")
    if status != 0:
        logger.error("rpm command failed, please ensure "
                     "the deps are installed manually and "
                     "proceed\n List of deps: %s", ' '.join(ENV_DEPS))
        # We are not exiting here as we might not know at this place
        # the env deps are satisfied or not,above :TODO: to be addressed
    else:
        not_found = []
        for dep in ENV_DEPS:
            if not is_present(dep, pack_list):
                not_found.append(dep)
        if not_found:
            logger.info("Please install following "
                        "dependancy packages %s", " ".join(not_found))
            sys.exit(1)


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
        cmd = 'avocado plugins|grep %s' % plugin
        status, output = commands.getstatusoutput(cmd)
        if status != 0:
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
            logger.error("Error while installing: %s\n%s",
                         path.split('/')[-1], status)
            sys.exit(1)
        else:
            logger.debug("%s", output)
    except Exception, error:
        logger.error("Failed with exception during installing %s\n%s",
                     path.split('/')[-1], error)
        sys.exit(1)


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


def bootstrap():
    """
    Prepare the environment for execution
    """
    logger.info("Bootstraping")
    # Check if the avocado and avocado-vt installed in the system
    for repo in REPOS:
        get_repo(repo, BASE_PATH, True)
    # bootstrap_vt
    libvirt_cmd = '%s vt-bootstrap --vt-type libvirt \
                    --vt-no-downloads --yes-to-all' % AVOCADO_BIN
    os.system(libvirt_cmd)
    qemu_cmd = '%s vt-bootstrap --vt-type qemu --vt-no-downloads' % AVOCADO_BIN
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
    conf = testsuite.config()
    test_type = testsuite.type
    vt_type = testsuite.vt_type
    if 'guest' in test_type:
        logger.info("Running Guest Tests Suite %s", testsuite.shortname)
        cmd = "%s run --vt-type %s --vt-config %s \
                --force-job-id %s" % (AVOCADO_BIN, vt_type, conf, testsuite.id)
    if 'host' in test_type:
        logger.info("Running Host Tests Suite %s", testsuite.shortname)
        cmd = "%s run  --force-job-id %s \
                $(cat %s|grep -v '^#')" % (AVOCADO_BIN, testsuite.id, conf)
    if args:
        cmd += " %s" % args
    try:
        logger.debug("Running: %s", cmd)
        os.system(cmd)
    except Exception, error:
        logger.info("Running testsuite %s failed with error\n%s",
                    testsuite.name, error)
        testsuite.runstatus("Not Run", "command execution failed")
        return
    result_link = "%s/html/results.html" % testsuite.jobdir()
    testsuite.runstatus("Run", "Sucussfully executed", result_link)
    return


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
    parser.add_argument('--verbose', dest='verbose',
                        action='store_true', default=False,
                        help='Enable verbose output on the console')
    parser.add_argument('--only-filter', dest='only_filter',
                        action='store', default=None,
                        help='Add filters to include specific avocado tests,'
                        'features from the guest test suite')
    parser.add_argument('--no-filter', dest='no_filter',
                        action='store', default=None,
                        help='Add filters to exclude specific avocado tests,'
                        'features from the guest test suite')
    parser.add_argument('--additional-args', dest='add_args',
                        action='store', default=None,
                        help='Pass additional arguments to the command')
    parser.add_argument('--guest-os', dest='guest_os',
                        action='store', default='Fedora.23.ppc64le',
                        help='Provide Guest os: Default: Fedora.23.ppc64le')
    parser.add_argument('--vt', dest='vt_type',
                        action='store', choices=['qemu', 'libvirt'],
                        default='libvirt',
                        help='Provide VT: qemu or libvirt Default: libvirt')
    parser.add_argument('--install', dest='install_guest',
                        action='store_true', default=False,
                        help='Install the Guest VM, if needed.')

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

    if args.bootstrap or need_bootstrap():
        create_config(outputdir)
        bootstrap()
        # Copy if any isos present in the local folder
        dst_iso_path = "%s/avocado-vt/isos/linux/" % DATA_DIR
        if not os.path.isdir(dst_iso_path):
            os.system('mkdir -p %s' % dst_iso_path)
        for fle in os.listdir("%s/isos" % BASE_PATH):
            if fle.endswith(".iso"):
                file_path = os.path.join(BASE_PATH, 'isos', fle)
                dst_file = os.path.join(dst_iso_path, fle)
                copyfile(file_path, dst_file)

    if args.run_suite:
        test_suites = args.run_suite.split(',')
        if args.install_guest:
            test_suites.insert(0, 'guest_install')
        Testsuites = {}
        # Validate if given test suite is available
        # run Guest tests
        for test_suite in test_suites:
            Testsuites[test_suite] = TestSuite(str(test_suite),
                                               outputdir, args.vt_type)
            if not Testsuites[test_suite].config():
                Testsuites[test_suite].runstatus("Not Run",
                                                 "Config file not present")
                continue
            if 'guest' in Testsuites[test_suite].type:
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
                                        %s' % only_filter
                if args.no_filter:
                    additional_args += ' --vt-no-filter %s' % args.no_filter
            if args.add_args:
                additional_args += " %s" % args.add_args
            run_test(Testsuites[test_suite], additional_args)
        # List the final output
        logger.info("Summary of test results can be found below: "
                    "\nTestSuite\tTestrun\tResultLink\t\t\tSummary\n\n")
        for test_suite in test_suites:
            print '%s\t%s\t%s\t%s\n' % (Testsuites[test_suite].name,
                                        Testsuites[test_suite].run,
                                        Testsuites[test_suite].runlink,
                                        Testsuites[test_suite].runsummary)
