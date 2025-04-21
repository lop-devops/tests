#!/usr/bin/env python3
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
import json
import sys
import shlex
import argparse
import configparser
import binascii
from enum import Enum
from lib.logger import logger_init
from lib import helper

AVOCADO_CONFIG_DIR = "%s/.config/avocado" % os.environ['HOME']
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = "%s/config/wrapper/env.conf" % BASE_PATH
prescript = "%s/config/prescript" % BASE_PATH
postscript = "%s/config/postscript" % BASE_PATH
NORUNTEST_PATH = "%s/config/wrapper/no_run_tests.conf" % BASE_PATH
TEST_CONF_PATH = "%s/config/tests/" % BASE_PATH
CONFIGFILE = configparser.ConfigParser()
CONFIGFILE.read(CONFIG_PATH)
NORUNTESTFILE = configparser.ConfigParser()
NORUNTESTFILE.read(NORUNTEST_PATH)
INPUTFILE = configparser.ConfigParser()
INPUTFILE.optionxform = str
BASE_FRAMEWORK = eval(CONFIGFILE.get('framework', 'base'))
KVM_FRAMEWORK = eval(CONFIGFILE.get('framework', 'kvm'))
OPTIONAL_FRAMEWORK = eval(CONFIGFILE.get('framework', 'optional'))
TEST_REPOS = eval(CONFIGFILE.get('tests', 'name'))
TEST_DIR = "%s/tests" % BASE_PATH
DATA_DIR = "%s/data" % BASE_PATH
LOG_DIR = "%s/results" % BASE_PATH
logger = logger_init(filepath=BASE_PATH).getlogger()
prescript_dir = CONFIGFILE.get('script-dir', 'prescriptdir')
postscript_dir = CONFIGFILE.get('script-dir', 'postscriptdir')
args = None
outputdir = ''
pipManager = None


class Result(Enum):
    Testcount = "Total"
    Pass = "pass"
    Cancel = "cancel"
    Error = "errors"
    Failures = "failures"
    Skip = "skip"
    Warn = "warn"
    Interrupt ="interrupt"

class Testsuite_status(Enum):
    Total = "Total"
    Run = "Run"
    Not_Run = "Not_Run"
    Cant_Run = "Cant_Run"

count_result = { _.value : 0 for _ in Result}
count_testsuites_status = { _.value : 0 for _ in Testsuite_status}

class TestSuite():
    """
        Class for Testsuite
    """
    guest_add_args = ""
    host_add_args = ""

    def __init__(self, name, resultdir, vt_type, test=None, mux=None, args=None,
                 use_test_dir=False):
        self.jobid = binascii.b2a_hex(os.urandom(20)).decode()
        self.name = str(name)
        self.shortname = "_".join(self.name.split('_')[1:])
        self.job_dir = None
        self.type = str(name.split('_')[0])
        self.resultdir = resultdir
        self.conf = None
        self.test = test
        self.mux = mux
        self.args = args
        self.run = Testsuite_status.Not_Run.value
        self.runsummary = None
        self.runlink = None
        if use_test_dir:
            self.resultdir = os.path.join(self.resultdir, self.name)
        if self.type == 'guest':
            self.vt_type = vt_type
        else:
            self.vt_type = None

    def jobdir(self):
        cmd = 'grep %s %s/*/id|grep job-' % (self.jobid, self.resultdir)
        status, self.job_dir = helper.runcmd(cmd, ignore_status=True)
        if status != 0:
            return ''
        self.job_dir = self.job_dir.split(':')[0]
        return os.path.dirname(self.job_dir)

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


def env_check(enable_kvm):
    """
    Check if the environment is proper
    """
    logger.info("Check for environment")
    not_found = []
    (env_ver, env_type, cmd_pat) = helper.get_env_type(enable_kvm)
    # try to check base packages using major version numbers
    env_ver = env_ver.split('.')[0]
    env_deps = []
    if not CONFIGFILE.has_section('deps_%s' % env_ver):
        # Fallback to base name if specific version is not found
        dist = helper.get_dist()
        env_ver = dist[0]

    if CONFIGFILE.has_section('deps_%s' % env_ver):
        packages = CONFIGFILE.get('deps_%s' % env_ver, 'packages')
        if packages != '':
            env_deps = packages.split(',')
    for dep in env_deps:
        if helper.runcmd(cmd_pat % dep, ignore_status=True)[0] != 0:
            not_found.append(dep)

    env_deps = []
    # try to check env specific packages
    if CONFIGFILE.has_section('deps_%s_%s' % (env_ver, env_type)):
        packages = CONFIGFILE.get('deps_%s_%s' %
                                  (env_ver, env_type), 'packages')
        if packages != '':
            env_deps = packages.split(',')
    for dep in env_deps:
        if helper.runcmd(cmd_pat % dep, ignore_status=True)[0] != 0:
            not_found.append(dep)
    if not_found:
        if args.install_deps:
            logger.warning("Installing missing packages %s",
                           " ".join(not_found))
            if helper.install_packages(not_found):
                logger.error("Some packages not installed")
                sys.exit(1)
        else:
            logger.error("Please install following "
                         "dependancy packages %s", " ".join(not_found))
            sys.exit(1)


def is_avocado_plugin_avl(plugin):
    """
    Check if the given avocado plugin installed
    """
    cmd = 'avocado plugins|grep %s' % plugin
    if helper.runcmd(cmd, ignore_status=True)[0] != 0:
        logger.warning("Avocado %s plugin not installed", plugin)
        return False
    return True


def need_bootstrap(enable_kvm=False):
    """
    Check if bootstrap required
    :return: True if bootstrap is needed
    """
    logger.debug("Check if bootstrap required")
    needs_bootstrap = False
    # Check for avocado
    if 'no avocado ' in helper.get_avocado_bin(ignore_status=True):
        logger.debug("Avocado needs to be installed")
        needs_bootstrap = True
    if enable_kvm:
        # Check for avocado-vt
        for plugin in ['vt', 'vt-list', 'vt-bootstrap']:
            if not is_avocado_plugin_avl(plugin):
                logger.debug("Avocado %s plugin needs to installed", plugin)
                needs_bootstrap = True
    # Check for avocado-tests
    for repo in TEST_REPOS:
        repo_name = repo[0].split('/')[-1].split('.')[0]
        if not os.path.isdir(os.path.join(TEST_DIR, repo_name)):
            logger.debug("Test needs to be downloaded/updated")
            needs_bootstrap = True
    return needs_bootstrap


def get_repo(repo, basepath):
    """
    To get given repo cloned/updated and install
    :param repo: tuple of repo link and branch(optional)
    :param basepath: base path where the repository has to be downloaded
    """
    if not isinstance(repo, tuple):
        repo = (repo, '')

    if repo[1] == '':
        branch = "master"
    else:
        branch = repo[1]
    cmd_update = "b=%s;git reset --hard && git checkout master && git remote update && (git branch | grep -w $b && (git switch $b && git pull origin $b --rebase) || (git fetch origin && git switch -c $b origin/$b) || echo \"Error: Could not sync with origin/$b\")" % branch
    repo_name = repo[0].split('/')[-1].split('.git')[0]
    repo_path = os.path.join(basepath, repo_name)
    cmd_clone = "git clone %s %s" % (repo[0], repo_path)

    logger.info("\t3. Cloning/Updating the repo: %s with branch %s under %s" % (
                      repo_name, branch, repo_path))
    if not os.path.isdir(repo_path):
        cmd = "%s && cd %s" % (cmd_clone, repo_path)
    else:
        cmd = "cd %s && [ %s = \"$(git remote get-url origin)\" ] && echo \"Repo matches\" && exit 0 \" \
               || echo \"Repo does not match\" && exit 1 \"" % (repo_path, repo[0])

    helper.runcmd(cmd, err_str="Failed to clone %s repository:, Please clean environment" % repo_name)

    cmd = "cd %s && %s" % (repo_path, cmd_update)
    helper.runcmd(cmd, err_str="Failed to update %s repository:" % repo_name)


def create_config(logdir):
    """
    Create the local avocado config file
    :param logdir: Log directory
    """
    logger.info("\t1. Creating Avocado Config")
    config = configparser.ConfigParser()
    os.makedirs(AVOCADO_CONFIG_DIR, exist_ok=True)
    avocado_conf = os.path.join(AVOCADO_CONFIG_DIR, "avocado.conf")
    config.add_section('datadir.paths')
    config.set('datadir.paths', 'base_dir', BASE_PATH)
    config.set('datadir.paths', 'test_dir', TEST_DIR)
    config.set('datadir.paths', 'data_dir', DATA_DIR)
    config.set('datadir.paths', 'logs_dir', logdir)

    config.add_section('sysinfo.collect')
    config.set('sysinfo.collect', 'enabled', 'on')
    config.set('sysinfo.collect', 'profiler', 'True')
    config.set('sysinfo.collect', 'per_test', 'True')
    config.set('sysinfo.collect', 'optimize', 'True')

    config.add_section('sysinfo.collectibles')
    config.set('sysinfo.collectibles', 'commands',
               os.path.join(BASE_PATH, "config/sysinfo/commands"))
    config.set('sysinfo.collectibles', 'fail_commands',
               os.path.join(BASE_PATH, "config/sysinfo/fail_commands"))
    config.set('sysinfo.collectibles', 'files',
               os.path.join(BASE_PATH, "config/sysinfo/files"))
    config.set('sysinfo.collectibles', 'fail_files',
               os.path.join(BASE_PATH, "config/sysinfo/fail_files"))
    config.set('sysinfo.collectibles', 'profilers',
               os.path.join(BASE_PATH, "config/sysinfo/profilers"))

    with open(avocado_conf, 'w+') as conf:
        config.write(conf)


def guest_download(guestos):
    """
    Guest image downloading
    """
    avocado_bin = helper.get_avocado_bin()
    cmd = '%s vt-bootstrap --vt-guest-os %s --yes-to-all' % (avocado_bin,
                                                             guestos)
    helper.runcmd(cmd, err_str="Failed to Download Guest OS. Error:",
                  info_str="Downloading the guest OS(%s) image" % guestos)


def kvm_bootstrap(guest_os):
    """
    Prepare KVM Test environment
    """
    avocado_bin = helper.get_avocado_bin()
    libvirt_cmd = '%s vt-bootstrap --vt-type libvirt \
                  --vt-update-providers --vt-skip-verify-download-assets \
                  --yes-to-all' % avocado_bin
    helper.runcmd(libvirt_cmd, err_str="Failed to bootstrap vt libvirt. Error:",
                  info_str="\t\ti) Bootstrapping VT libvirt")
    qemu_cmd = '%s vt-bootstrap --vt-type qemu --vt-update-providers \
               --vt-skip-verify-download-assets --yes-to-all' % avocado_bin
    helper.runcmd(qemu_cmd, err_str="Failed to bootstrap vt qemu. Error:",
                  info_str="\t\tii) Bootstrapping VT qemu")
    if guest_os:
        guestos_cmd = '%s vt-bootstrap --vt-guest-os %s --yes-to-all' % (avocado_bin,
                                                                         guest_os)
        helper.runcmd(guestos_cmd, err_str="Failed to Download Guest OS. Error:",
                      info_str="\t\tiii) Downloading guest OS(%s) image" % guest_os)


def bootstrap(enable_kvm=False, guest_os=None):
    """
    Prepare the environment for execution

    :params enable_kvm: Flag to enable kvm environment bootstrap
    """
    env_clean()
    logger.info("Bootstrapping Framework")
    create_config(outputdir)
    if enable_kvm:
        install_str = "\t2. Installing Avocado and Avocado-VT(KVM) Framework"
    else:
        install_str = "\t2. Installing Avocado Framework"
    logger.info(install_str)
    pipManager.install()
    if enable_kvm:
        logger.info("\t2a.Bootstrapping Avocado-VT(KVM) Framework")
        # Copy if any isos present in the local folder
        dst_iso_path = "%s/avocado-vt/isos/linux/" % DATA_DIR
        os.makedirs(dst_iso_path, exist_ok=True)
        for fle in os.listdir("%s/isos" % BASE_PATH):
            if fle.endswith(".iso"):
                file_path = os.path.join(BASE_PATH, 'isos', fle)
                dst_file = os.path.join(dst_iso_path, fle)
                shutil.copyfile(file_path, dst_file)
        kvm_bootstrap(guest_os)
    helper.runcmd('mkdir -p %s' % TEST_DIR,
                  debug_str="Creating test repo dir %s" % TEST_DIR,
                  err_str="Failed to create test repo dir. Error: ")
    for repo in TEST_REPOS:
        get_repo(repo, TEST_DIR)

    if os.path.isdir(prescript):
        if len(os.listdir(prescript)):
            if not os.path.exists(prescript_dir):
                os.makedirs(prescript_dir)
            helper.copy_dir_file(prescript, prescript_dir)
    if os.path.isdir(postscript):
        if len(os.listdir(postscript)):
            if not os.path.exists(postscript_dir):
                os.makedirs(postscript_dir)
            helper.copy_dir_file(postscript, postscript_dir)


def run_test(testsuite, avocado_bin, nrunner):
    """
    To run given testsuite
    :param testsuite: Testsuite object which has details about the tests
    :param avocado_bin: Executable path of avocado
    """

    if not nrunner:
        nrunner = '--test-runner runner'
    else:
        nrunner = ''

    logger.info('')
    if 'guest' in testsuite.type:
        guest_args = TestSuite.guest_add_args
        logger.info("Running Guest Tests Suite %s", testsuite.shortname)
        if "sanity" in testsuite.shortname:
            guest_args = " --vt-only-filter %s " % args.guest_os
        cmd = "%s run --vt-type %s --vt-config %s \
                --force-job-id %s \
                --job-results-dir %s %s" % (avocado_bin, testsuite.vt_type,
                                            testsuite.config(),
                                            testsuite.jobid,
                                            testsuite.resultdir, guest_args)
    if 'host' in testsuite.type:
        logger.info("Running Host Tests Suite %s", testsuite.shortname)
        cmd = "%s run %s %s" % (avocado_bin, nrunner, testsuite.test)
        if testsuite.mux:
            cmd += " -m %s" % os.path.join(TEST_DIR, testsuite.mux)
        cmd += " --force-job-id %s \
                 --job-results-dir %s %s" % (testsuite.jobid,
                                             testsuite.resultdir,
                                             TestSuite.host_add_args)
        if testsuite.args:
            cmd += testsuite.args

    try:
        logger.info("Running: %s", cmd)
        status = os.system(cmd)
        status = int(bin(int(status))[2:].zfill(16)[:-8], 2)
        if status >= 2:
            testsuite.runstatus(Testsuite_status.Not_Run.value, "Command execution failed")
            count_testsuites_status[Testsuite_status.Not_Run.value] += 1
            return
    except Exception as error:
        logger.error("Running testsuite %s failed with error\n%s",
                     testsuite.name, error)
        testsuite.runstatus(Testsuite_status.Not_Run.value, "Command execution failed")
        count_testsuites_status[Testsuite_status.Not_Run.value] += 1
        return
    logger.info('')
    result_link = testsuite.jobdir()
    if result_link:
        result_json = result_link + "/results.json"
        result_link += "/job.log\n"
        with open(result_json, encoding="utf-8") as filep:
            result_state = json.load(filep)
        for state in count_result:
            if state in result_state.keys():
                count_result[Result.Testcount.value] += int(result_state[state])
                count_result[state] += int(result_state[state])
                result_link += "| %s %s |" % (state.upper(),
                                              str(result_state[state]))
        testsuite.runstatus(Testsuite_status.Run.value, "Successfully executed", result_link)
        count_testsuites_status[Testsuite_status.Run.value] += 1
    else:
        testsuite.runstatus(Testsuite_status.Not_Run.value, "Unable to find job log file")
        count_testsuites_status[Testsuite_status.Not_Run.value] += 1
    return


def env_clean(deep=False):
    """
    Clean/uninstall avocado and autotest
    """
    logger.info("Cleaning the Environment")
    pipManager.uninstall()
    if os.path.isdir(prescript):
        helper.remove_file(prescript, prescript_dir)

    if os.path.isdir(postscript):
        helper.remove_file(postscript, postscript_dir)
    if deep:
        # Remove Data dir if present
        if os.path.isdir(DATA_DIR):
            shutil.rmtree(DATA_DIR)
        # Remove local avocado config if present
        if os.path.isdir(AVOCADO_CONFIG_DIR):
            shutil.rmtree(AVOCADO_CONFIG_DIR)
        # Remove tests folder
        if os.path.isdir(TEST_DIR):
            shutil.rmtree(TEST_DIR)


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
        for key, value in input_dic.items():
            temp_line = line.split(":")
            mux_key = temp_line[0]
            mux_value = temp_line[1]
            if key == mux_key.strip():
                line = line.replace('%s' % line.strip(),
                                    '%s: %s' % (key, value))
        mux_str_edited.append(line)

    with open(tmp_mux_path, 'w') as mux_fp:
        mux_fp.write(str("\n".join(mux_str_edited)))


def parse_test_config(test_config_file, avocado_bin, enable_kvm):
    """
    Parses Test Config file and returns list of indivual tests dictionaries,
    with test path and yaml file path.
    """
    test_config_type = test_config_file[:test_config_file.find("_")]
    test_config_name = test_config_file[test_config_file.find("_") + 1:]
    test_config_file = "%s/%s/%s.cfg" % (TEST_CONF_PATH, test_config_type,
                                         test_config_name)
    if os.path.isfile(test_config_file):
        (env_ver, env_type, _) = helper.get_env_type(enable_kvm)
        norun_tests = []
        # Get common set of not needed tests
        env = 'norun_%s' % env_type
        dist = 'norun_%s' % helper.get_dist()[0]
        major = 'norun_%s' % env_ver.split('.')[0]
        minor = 'norun_%s' % env_ver
        minor_env = 'norun_%s_%s' % (env_ver, env_type)
        for section in [env, dist, major, minor, minor_env]:
            if NORUNTESTFILE.has_section(section):
                norun_tests.extend(NORUNTESTFILE.get(
                    section, 'tests').split(','))
        norun_tests = list(filter(None, norun_tests))

        with open(test_config_file, 'r') as filep:
            test_config_contents = filep.read()
        test_list = []
        mux_flag = 0
        arg_flag = 0
        for line in test_config_contents.splitlines():
            norun_flag = False
            test_dic = {}
            # Comment line or Empty line filtering
            if line.startswith("#") or not line:
                norun_flag = True
            # Filtering <test yaml> combination
            elif line in norun_tests:
                norun_flag = True
            # Filtering <string*> pattern
            else:
                for norun_test in norun_tests:
                    if norun_test.endswith('*') and line.startswith(norun_test[:-1]):
                        norun_flag = True
                        break
            if norun_flag:
                continue
            # split line ignoring quotes used for additional args
            line = shlex.split(line)
            test_dic['test'] = os.path.join(TEST_DIR, line[0].strip('$'))
            test_dic['name'] = test_dic['test'].split("/")[-1]
            if ":" in test_dic['test'].split("/")[-1]:
                test_dic['name'] = "%s_%s" % (test_dic['name'].split(".")[0],
                                              test_dic['name'].split(":")[-1].replace(".", "_"))
                test_dic['test'] = "%s$" % test_dic['test']
            else:
                test_dic['name'] = test_dic['name'].split(".")[0]
            cmd = "%s list %s 2> /dev/null" % (avocado_bin, test_dic['test'])
            if helper.runcmd(cmd, ignore_status=True)[0] != 0:
                logger.debug("%s does not exist", test_dic['test'])
                continue
            # Handling parameters after test from cfg
            if len(line) > 1:
                # Handling yaml file from second param
                if '.yaml' in line[1]:
                    test_dic['mux'] = line[1]
                    mux_flag = 1
                    test_dic['name'] = "%s_%s" % (test_dic['name'],
                                                  test_dic['mux'].split("/")[-1].split(".")[0])
                    if args.inputfile:
                        mux_file = os.path.join(TEST_DIR, test_dic['mux'])
                        if not os.path.isfile(mux_file):
                            logger.debug("%s does not exist", mux_file)
                            continue
                        tmp_mux_path = os.path.join('/tmp/mux/', "%s_%s.yaml" % (test_config_name,
                                                                                 test_dic['name']))
                        edit_mux_file(test_config_name, mux_file, tmp_mux_path)
                        test_dic['mux'] = tmp_mux_path
                # Handling additional args from second param
                else:
                    arg_flag = 1
                    test_dic['args'] = " %s" % line[1]
            count = 0
            for list_dic in test_list:
                if test_dic['name'] == list_dic['name'].split('.')[0]:
                    count += 1
            if count:
                test_dic['name'] += ".%d" % (count + 1)
            # Handle additional args after yaml(second arg) from third param
            if len(line) > 2:
                arg_flag = 1
                test_dic['args'] = " %s" % line[2]
            test_list.append(test_dic)
        if mux_flag == 0 and arg_flag == 0:
            single_test_dic = {}
            single_test_dic['name'] = test_config_name
            single_test_dic['test'] = ''
            for test in test_list:
                single_test_dic['test'] += " %s" % test['test']
            return [single_test_dic]
        return test_list
    logger.error("Test Config %s not present", test_config_file)
    return []


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
    parser.add_argument('--use-test-dir', dest='testdir',
                        action='store_true', default=False,
                        help='Use corresponding test-name dir for storing job results')
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
    parser.add_argument('--install-deps', dest="install_deps",
                        action='store_true', default=False,
                        help="To force wrapper to install dependancy packages "
                             "(Only for Ubuntu, SLES and yum based OS)")
    parser.add_argument('--clean', dest="clean",
                        action='store_true', default=False,
                        help='To remove/uninstall autotest, avocado from system')
    parser.add_argument('--enable-kvm', dest="enable_kvm", action='store_true',
                        default=False, help='enable bootstrap kvm tests')
    parser.add_argument('--nrunner', dest="nrunner", action='store_true',
                        default=False, help='enable Parallel run')

    parser.add_argument('--run-tests', dest="run_tests", action='store',
                        default=None,
                        help="To run the host tests provided in the option and publish result [Note: test names(full path) and separated by comma]")

    args = parser.parse_args()
    if helper.get_machine_type() == 'pHyp':
        args.enable_kvm = False
        if args.run_suite:
            if "guest_" in args.run_suite:
                logger.error("Not suitable platform to run kvm tests, "
                             "please check the commandline, exiting...")
                sys.exit(-1)
    else:
        if args.run_suite:
            if "guest_" in args.run_suite:
                logger.warning("Overriding user setting and enabling kvm bootstrap "
                               "as guest tests are requested")
                args.enable_kvm = True
    pipManager = helper.PipMagager(BASE_FRAMEWORK, OPTIONAL_FRAMEWORK,
                                   KVM_FRAMEWORK, args.enable_kvm)
    if not (args.run_suite and args.install_deps
            and args.bootstrap and args.install) and args.clean:
        # honor the spl condition, just to deep clean the environment incase needed
        env_clean(deep=True)
        sys.exit(0)
    if not args.no_deps_check:
        env_check(args.enable_kvm)
    additional_args = " %s" % args.add_args
    if args.verbose:
        additional_args += ' --show-job-log'
    if args.outputdir:
        # Check if it valid path
        if not os.path.isdir(os.path.abspath(args.outputdir)):
            raise ValueError("No output dir")
        outputdir = os.path.join(args.outputdir, 'results')
    else:
        outputdir = os.path.join(BASE_PATH, 'results')

    bootstraped = False
    if (args.bootstrap or need_bootstrap(args.enable_kvm)):
        if not args.no_guest_download and args.enable_kvm:
            bootstrap(args.enable_kvm, args.guest_os)
        else:
            bootstrap(args.enable_kvm)
        bootstraped = True

    if args.run_tests:
        with open("%s/host/dynamic_test_suite" % TEST_CONF_PATH+".cfg", "w+") as fp:
            fp.write('\n'.join(args.run_tests.split(",")))
        args.run_suite = str(args.run_suite)+","+"host_dynamic_test_suite"

    if args.inputfile:
        if not os.path.isfile(args.inputfile):
            logger.debug(
                "Input file %s not found. Continuing without input file", args.inputfile)
            args.inputfile = None

    if args.run_suite:
        # create a folder to store all edited multiplexer files
        if not os.path.isdir("/tmp/mux/"):
            logger.info("Creating temporary mux dir")
            os.makedirs("/tmp/mux/")
        if "guest_" in args.run_suite:
            # Make sure we download guest image once
            if not args.no_guest_download and not bootstraped:
                guest_download(args.guest_os)
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
        avocado_bin = helper.get_avocado_bin()
        Testsuites = {}
        # Validate if given test suite is available
        # and init TestSuite object for each test suite
        Testsuites_list = []
        for test_suite in test_suites:
            if 'host' in test_suite:
                test_list = parse_test_config(
                    test_suite, avocado_bin, args.enable_kvm)
                if not test_list:
                    Testsuites[test_suite] = TestSuite(test_suite, outputdir,
                                                       args.vt_type,
                                                       use_test_dir=args.testdir)
                    Testsuites[test_suite].runstatus(Testsuite_status.Cant_Run.value,
                                                     "Config file not present")
                    count_testsuites_status[Testsuite_status.Cant_Run.value] += 1
                    Testsuites_list.append(test_suite)
                    continue
                for test in test_list:
                    for l_key in ['mux', 'args']:
                        if l_key not in test:
                            test[l_key] = ''
                    test_suite_name = "%s_%s" % (test_suite, test['name'])
                    Testsuites[test_suite_name] = TestSuite(test_suite_name,
                                                            outputdir, args.vt_type,
                                                            test['test'], test['mux'],
                                                            test['args'],
                                                            use_test_dir=args.testdir)
                    Testsuites_list.append(test_suite_name)

            if 'guest' in test_suite:
                guest_additional_args = ""
                Testsuites[test_suite] = TestSuite(str(test_suite),
                                                   outputdir, args.vt_type,
                                                   use_test_dir=args.testdir)
                Testsuites_list.append(str(test_suite))
                if not Testsuites[test_suite].config():
                    Testsuites[test_suite].runstatus(Testsuite_status.Cant_Run.value,
                                                     "Config file not present")
                    count_testsuites_status[Testsuite_status.Cant_Run.value] += 1
                    continue
        # Run Tests
        count_testsuites_status[Testsuite_status.Total.value] = len(Testsuites_list)
        for test_suite in Testsuites_list:
            if not Testsuites[test_suite].run == Testsuite_status.Cant_Run.value:
                run_test(Testsuites[test_suite], avocado_bin, args.nrunner)
                if args.interval:
                    time.sleep(int(args.interval))

        # Finding the space needed for formatting result summary
        test_name_list = []
        for test_suite in Testsuites_list:
            test_name_list.append(Testsuites[test_suite].name)
            if Testsuites[test_suite].runlink:
                test_name_list.extend(
                    Testsuites[test_suite].runlink.split('\n'))
        if test_name_list:
            lg_name_len = len((sorted(test_name_list, key=len)[-1])) + 5
        else:
            lg_name_len = 10

        # List the final output
        output_str = "Summary of test results can be found below:"
        output_str += "\n%s %s %s" % ('TestSuite'.ljust(lg_name_len),
                                      'TestRun'.ljust(10), 'Summary')
        summary_output = [output_str]
        for test_suite in Testsuites_list:
            summary_output.append(' ')
            summary_output.append('%s %s %s' % (Testsuites[test_suite].name.ljust(lg_name_len),
                                                Testsuites[test_suite].run.ljust(
                                                    10),
                                                Testsuites[test_suite].runsummary))
            summary_output.append(Testsuites[test_suite].runlink)

        summary_output.append("\nTest suites status:\n")
        for k, val in count_testsuites_status.items():
            summary_output.append('%s %s' % (k.upper().ljust(20), val))

        summary_output.append("\nFinal count summary for tests run:\n")
        for k, val in count_result.items():
            summary_output.append('%s %s' % (k.upper().ljust(20), val))

        logger.info("\n".join(summary_output))

    if os.path.isdir("/tmp/mux/"):
        logger.info("Removing temporary mux dir")
        shutil.rmtree("/tmp/mux/")

    if args.clean:
        env_clean()
