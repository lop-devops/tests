# Copyright (C) IBM Corp. 2019.
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
# Helper methods
# Author: Satheesh Rajendran<sathnaga@linux.vnet.ibm.com>

import subprocess
import os
import re
import sys
import shutil
import stat
import platform
import importlib.metadata

from .logger import logger_init

LOG_PATH = os.path.dirname(os.path.abspath(os.path.join(__file__, os.pardir)))

logger = logger_init(filepath=LOG_PATH).getlogger()


def runcmd(cmd, ignore_status=False, err_str="", info_str="", debug_str=""):
    """
    Running command and get the results

    :param cmd: Command to run
    :param ignore_status: Whether to exit program on failure
    :param err_str: String to be printed in case of command error
    :param info_str: Info string to be printed, default None
    :param debug_str: Debug string to be printed, default None
    :param log: log handle

    :return: Status and output of the command
    """
    if info_str:
        logger.info(info_str)
    if debug_str:
        logger.debug(debug_str)
    try:
        logger.debug("Running %s", cmd)
        status, output = subprocess.getstatusoutput(cmd)
        if status != 0 and not ignore_status:
            if err_str:
                logger.error("%s %s", err_str, output)
            sys.exit(1)
        logger.debug(output)
    except Exception as error:
        if err_str:
            logger.error("%s %s ", err_str, error)
        sys.exit(1)
    return (status, output)


def get_dist():
    """
    Return the distribution
    """
    dist = None
    dist_ver = None
    if os.path.isfile('/etc/os-release'):
        fd = open('/etc/os-release', 'r')
        for line in fd.readlines():
            if line.startswith("ID="):
                try:
                    line = line.replace('"', '')
                    dist = re.findall("ID=(\\S+)", line)[0]
                except:
                    pass
            elif line.__contains__("VERSION="):
                try:
                    line = line.replace('"', '')
                    dist_ver = re.findall("VERSION=(\\S+)", line)[0].lower().replace("-", ".")
                except:
                    pass
        fd.close()
    if os.uname()[-1] == 'ppc64':
        dist += 'be'
    return (dist, dist_ver)


def get_machine_type():
    """
    Return What kind of machine example: pHypLpar/PowerNV/qemu
    """
    machine_type = None
    cpuinfo = '/proc/cpuinfo'
    if not os.path.isfile(cpuinfo):
        return machine_type
    with open(cpuinfo, 'r') as fd:
        for line in fd.readlines():
            if line.startswith("machine"):
                if 'PowerNV' in line:
                    machine_type = 'NV'
                    break
                elif 'pSeries' in line:
                    if 'qemu' in line:
                        machine_type = 'qemu'
                    else:
                        machine_type = 'pHyp'
                    break
    return machine_type


def get_env_type(enable_kvm=False):
    """
    Return what environment the system is: Distro, Version, Type
    """
    (dist, dist_ver) = get_dist()
    env_ver = dist
    env_ver += dist_ver
    env_type = get_machine_type()
    if env_type == "NV" and enable_kvm:
        env_type = "kvm"
    if 'ubuntu' in dist:
        cmd_pat = "apt list --installed | grep -i '%s'"
    else:
        cmd_pat = "rpm -q %s"
    return (env_ver, env_type, cmd_pat)


def get_avocado_bin(ignore_status=False):
    """
    Get the avocado executable path
    """
    return runcmd('which avocado', ignore_status=ignore_status,
                  err_str="avocado command not installed or not found in path")[1]


def get_install_cmd():
    """
    Get the command to install, based on the distro
    """
    (dist, _) = get_dist()
    if 'ubuntu' in dist:
        cmd = "echo y | apt-get install"
    elif 'sles' in dist:
        cmd = "zypper install -y"
    else:
        cmd = "yum -y install"
    return cmd


def install_packages(package_list):
    """
    Install packages, given list of packages
    """
    install_cmd = get_install_cmd()
    not_installed = False
    for pkg in package_list:
        (status, output) = runcmd("%s %s" % (install_cmd, pkg), ignore_status=True)
        if status != 0:
            logger.error("%s not installed" % pkg)
            logger.debug(output)
            not_installed = True
    return not_installed


def copy_dir_file(src, dest):
    """
    Copy all files from one dir to other dir
    """
    for item in os.listdir(src):
        s_file = os.path.join(src, item)
        d_file = os.path.join(dest, item)
        if os.path.exists(d_file):
            logger.info("file already exist in %s it will going to overwrite with new file" % dest)
        shutil.copy2(s_file, d_file)
        # changing permission to 744
        os.chmod(d_file, stat.S_IRWXU | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    logger.info("copied all files from  %s to %s" % (src, dest))


def is_rhel8():
    """
    Check the OS version

    :return: True if it is rhel8 False otherwise
    """
    system_info = platform.system()
    release_info = platform.release()

    if system_info == "Linux" and "el8" in release_info:
        return True
    else:
        return False


def remove_file(src, dest):
    """
    Remove Files from Destination Folder  which is common in Source  and Destination
    """
    for item in os.listdir(src):
        d_file = os.path.join(dest, item)
        if os.path.exists(d_file):
            os.remove(d_file)
        logger.debug("%s file deleted" % d_file)


class PipMagager:
    def __init__(self, base_fw=[], opt_fw=[], kvm_fw=[],pip_packages=[], enable_kvm=False):
        """
        helper class to parse, install, uninstall pip package from user config
        """
        if sys.version_info[:2] < (3, 6):
            logger.error("System installed python version(%s) not supported, make sure python3.6 or above is installed to proceed" % sys.version_info[:2])
            sys.exit(1)
        self.pip_cmd = "pip%s" % sys.version_info[0]
        # Check for pip if not attempt install and proceed
        cmd = "%s --help >/dev/null 2>&1||(curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && python%s ./get-pip.py)" % (self.pip_cmd, sys.version_info[0])
        runcmd(cmd, err_str='Unable to install pip3')

        # Get pip version
        pip_version_split = importlib.metadata.version(f"pip").split(".")
        self.pip_vmajor, self.pip_vminor = int(pip_version_split[0]), int(pip_version_split[1])

        self.uninstallitems = base_fw + opt_fw + kvm_fw + pip_packages
        if enable_kvm:
            self.installitems = self.uninstallitems
        else:
            self.installitems = base_fw + opt_fw + pip_packages

        self.install_packages = []
        self.uninstall_packages = []
        for item in self.uninstallitems:
            self.uninstall_packages.append(item[0])
        for item in self.installitems:
            if item[1]:
                if item[1].startswith('git'):
                    self.install_packages.append(item[1])
                else:
                    self.install_packages.append("%s==%s" % (item[0], item[1]))
            else:
                self.install_packages.append(item[0])

    def install(self):
        if os.geteuid() != 0:
            pip_installcmd = '%s install --user -U' % self.pip_cmd
        else:
            pip_installcmd = '%s install -U' % self.pip_cmd
        for package in self.install_packages:
            cmd = '%s %s' % (pip_installcmd, package)
            if (self.pip_vmajor > 23) or (self.pip_vmajor == 23 and self.pip_vminor >= 1):
                cmd = cmd + ' --break-system-packages' # --break-system-packages introduced in pip 23.1
            runcmd(cmd,
                   err_str='Package installation via pip failed: package  %s' % package,
                   debug_str='Installing python package %s using pip' % package)

    def uninstall(self):
        for package in self.uninstall_packages:
            cmd = '%s uninstall %s -y --disable-pip-version-check' % (self.pip_cmd, package)
            if (self.pip_vmajor > 23) or (self.pip_vmajor == 23 and self.pip_vminor >= 1):
                cmd = cmd + ' --break-system-packages' # --break-system-packages introduced in pip 23.1
            runcmd(cmd, ignore_status=True,
                   err_str="Error in removing package: %s" % package,
                   debug_str="Uninstalling %s" % package)
