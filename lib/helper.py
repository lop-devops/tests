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

import commands
import os
import re
import sys

from logger import logger_init

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
        status, output = commands.getstatusoutput(cmd)
        if status != 0 and not ignore_status:
            if err_str:
                logger.error("%s %s", err_str, output)
            sys.exit(1)
        logger.debug(output)
    except Exception, error:
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
                    dist = re.findall("ID=(\S+)", line)[0]
                except:
                    pass
            elif line.startswith("VERSION="):
                try:
                    line = line.replace('"', '')
                    dist_ver = re.findall("VERSION=(\S+)", line)[0].lower().replace("-",".")
                except:
                    pass
        fd.close()
    if os.uname()[-1] == 'ppc64':
        dist += 'be'
    return (dist, dist_ver)


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
                machine_type = 'NV'
            elif 'pSeries' in line:
                machine_type = 'pHyp'
        fd.close()
    return machine_type


def get_env_type(disable_kvm=False):
    """
    Return what environment the system is: Distro, Version, Type
    """
    (dist, dist_ver) = get_dist()
    env_ver = dist
    env_ver += dist_ver
    env_type = get_machine_type()
    if env_type == "NV" and not disable_kvm:
        env_type = "kvm"
    if 'ubuntu' in dist:
        cmd_pat = "dpkg -l|grep  ' %s'"
    else:
        cmd_pat = "rpm -q %s"
    return (env_ver, env_type, cmd_pat)


def get_avocado_bin(ignore_status=False):
    """
    Get the avocado executable path
    """
    return runcmd('which avocado', ignore_status=ignore_status,
                  err_str="avocado command not installed or not found in path")[1]
