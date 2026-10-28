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

import itertools
import subprocess
import os
import re
import sys
import shlex
import shutil
import stat
import time
import platform
import importlib.metadata

from .logger import logger_init

LOG_PATH = os.path.dirname(os.path.abspath(os.path.join(__file__, os.pardir)))
DEFAULT_VENV_DIR = os.path.join(LOG_PATH, '.venv')

logger = logger_init(filepath=LOG_PATH).getlogger()


def use_venv():
    """
    Return True when the isolated virtual-environment path is enabled.
    Controlled by AVOCADO_USE_VENV=1 (or 'true'/'yes'/'on').
    """
    val = os.environ.get("AVOCADO_USE_VENV", "").lower()
    return val in ("1", "true", "yes", "on")


def get_venv_dir():
    """Return the path of the optional Avocado virtual environment."""
    return os.environ.get("AVOCADO_VENV", DEFAULT_VENV_DIR)


def prepend_venv_to_path():
    """Prepend the venv bin directory to PATH when venv mode is enabled."""
    if use_venv():
        venv_bin = os.path.join(get_venv_dir(), 'bin')
        os.environ['PATH'] = venv_bin + os.pathsep + os.environ.get('PATH', '')
        logger.debug("Prepended %s to PATH (venv mode)", venv_bin)


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
    if use_venv():
        venv_avocado = os.path.join(get_venv_dir(), 'bin', 'avocado')
        if os.path.isfile(venv_avocado) and os.access(venv_avocado, os.X_OK):
            return venv_avocado
        if not ignore_status:
            logger.error("avocado command not installed or not found in venv at %s",
                         get_venv_dir())
            sys.exit(1)
        return ""
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
    def __init__(self, base_fw=[], opt_fw=[], kvm_fw=[], pip_packages=[], enable_kvm=False):
        """
        helper class to parse, install, uninstall pip package from user config
        """
        if sys.version_info[:2] < (3, 6):
            logger.error("System installed python version(%s) not supported, make sure python3.6 or above is installed to proceed" % sys.version_info[:2])
            sys.exit(1)
        self.use_venv = use_venv()
        self.venv_dir = get_venv_dir()

        if self.use_venv:
            self.python = os.path.join(self.venv_dir, 'bin', 'python')
            self.pip_cmd = os.path.join(self.venv_dir, 'bin', 'pip')
            logger.info("Using isolated virtual environment: %s", self.venv_dir)
        else:
            self.pip_cmd = "pip%s" % sys.version_info[0]
            cmd = "%s --help >/dev/null 2>&1||(curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && python%s ./get-pip.py)" % (self.pip_cmd, sys.version_info[0])
            runcmd(cmd, err_str='Unable to install pip3')
            pip_version_split = importlib.metadata.version("pip").split(".")
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

    def _ensure_venv(self):
        ready_marker = os.path.join(self.venv_dir, '.bootstrap_ok')
        if (os.path.isdir(self.venv_dir) and os.path.isfile(self.python)
                and os.path.isfile(ready_marker)):
            logger.debug("Reusing existing virtual environment at %s", self.venv_dir)
            return
        if os.path.isdir(self.venv_dir):
            logger.info("Removing incomplete virtual environment at %s", self.venv_dir)
            shutil.rmtree(self.venv_dir, ignore_errors=True)
        logger.info("Creating isolated virtual environment at %s", self.venv_dir)
        runcmd('%s -m venv %s' % (sys.executable, self.venv_dir),
               err_str='Failed to create virtual environment')
        runcmd('%s -m pip install --upgrade pip "setuptools<82" wheel' % self.python,
               err_str='Failed to upgrade pip inside venv')
        with open(ready_marker, 'w') as marker_file:
            marker_file.write('ok\n')

    def install(self):
        if self.use_venv:
            self._ensure_venv()
            pip_installcmd = '%s install -U' % self.pip_cmd
            for package in self.install_packages:
                cmd = '%s %s' % (pip_installcmd, package)
                runcmd(cmd,
                       err_str='Package installation via pip failed: package  %s' % package,
                       debug_str='Installing python package %s using pip' % package)
            return
        if os.geteuid() != 0:
            pip_installcmd = '%s install --user -U' % self.pip_cmd
        else:
            pip_installcmd = '%s install -U' % self.pip_cmd
        for package in self.install_packages:
            cmd = '%s %s' % (pip_installcmd, package)
            if (self.pip_vmajor > 23) or (self.pip_vmajor == 23 and self.pip_vminor >= 1):
                cmd = cmd + ' --break-system-packages'  # --break-system-packages introduced in pip 23.1
            runcmd(cmd,
                   err_str='Package installation via pip failed: package  %s' % package,
                   debug_str='Installing python package %s using pip' % package)

    def uninstall(self):
        if self.use_venv:
            return
        self._pip_uninstall(self.pip_cmd, self.pip_vmajor, self.pip_vminor)

    def uninstall_system_wide(self):
        venv_bin = os.path.join(self.venv_dir, 'bin')
        path_entries = os.environ.get('PATH', '').split(os.pathsep)
        system_path = os.pathsep.join(p for p in path_entries if p and p != venv_bin)
        pip_cmd = shutil.which('pip%s' % sys.version_info[0], path=system_path)
        if not pip_cmd:
            logger.debug("System pip not found, skipping system-wide Avocado cleanup")
            return
        status, output = subprocess.getstatusoutput('%s --version' % pip_cmd)
        match = re.search(r'pip (\d+)\.(\d+)', output)
        if status != 0 or not match:
            logger.debug("Could not determine system pip version, skipping system-wide Avocado cleanup")
            return
        pip_vmajor, pip_vminor = int(match.group(1)), int(match.group(2))
        logger.info("Removing system-wide Avocado packages")
        self._pip_uninstall(pip_cmd, pip_vmajor, pip_vminor)

    def _pip_uninstall(self, pip_cmd, pip_vmajor, pip_vminor):
        for package in self.uninstall_packages:
            cmd = '%s uninstall %s -y --disable-pip-version-check' % (pip_cmd, package)
            if (pip_vmajor > 23) or (pip_vmajor == 23 and pip_vminor >= 1):
                cmd = cmd + ' --break-system-packages'  # --break-system-packages introduced in pip 23.1
            runcmd(cmd, ignore_status=True,
                   err_str="Error in removing package: %s" % package,
                   debug_str="Uninstalling %s" % package)

    def remove_venv(self):
        if os.path.isdir(self.venv_dir):
            logger.info("Cleaning up any previously existing virtual environment at %s",
                        self.venv_dir)
            shutil.rmtree(self.venv_dir, ignore_errors=True)


class RemoteRunner:
    """
    SSH-based remote command runner using ``sshpass`` + the system ``ssh``
    binary.  No Python C-extension dependencies (no paramiko/bcrypt/pynacl)
    are required — only the ``sshpass`` package must be installed on the
    *local* machine (``yum install sshpass`` / ``apt-get install sshpass``).

    Provides the same ``runcmd()`` interface as the local helper so it can be
    used as a drop-in replacement for remote machines.

    Usage::

        runner = RemoteRunner(host='192.168.1.10', username='root', password='secret')
        status, output = runner.runcmd('ip a s dev eth0')
        runner.close()   # no-op for this implementation, kept for API compat

    Context-manager usage::

        with RemoteRunner(host='192.168.1.10', username='root', password='secret') as r:
            status, output = r.runcmd('lsdevinfo -c')
    """

    # Common SSH options that suppress host-key prompts and banners.
    _SSH_OPTS = (
        "-o StrictHostKeyChecking=no "
        "-o UserKnownHostsFile=/dev/null "
        "-o BatchMode=no "
        "-o LogLevel=ERROR"
    )

    def __init__(self, host, username, password, port=22, timeout=30):
        """
        Store connection parameters and verify that ``sshpass`` is available.

        :param host: Hostname or IP address of the remote machine.
        :param username: SSH login username.
        :param password: SSH login password.
        :param port: SSH port (default 22).
        :param timeout: Per-command connect timeout in seconds (default 30).
        """
        # Verify sshpass is on PATH
        chk_status, _ = subprocess.getstatusoutput("which sshpass")
        if chk_status != 0:
            logger.error(
                "sshpass is not installed. Install it with: "
                "yum install sshpass  OR  apt-get install sshpass"
            )
            sys.exit(1)

        self.host = host
        self.username = username
        self._password = password
        self.port = port
        self.timeout = timeout
        logger.info("RemoteRunner ready for %s@%s:%s (sshpass mode)", username, host, port)

    def runcmd(self, cmd, ignore_status=False, err_str="", info_str="", debug_str=""):
        """
        Run *cmd* on the remote host via ``sshpass``/``ssh``.

        :param cmd: Shell command string to execute remotely.
        :param ignore_status: If False (default), calls sys.exit(1) on non-zero exit.
        :param err_str: Message to log at ERROR level on failure.
        :param info_str: Message to log at INFO level before running.
        :param debug_str: Message to log at DEBUG level before running.
        :return: (status, output) tuple — identical contract to local runcmd().
        """
        if info_str:
            logger.info(info_str)
        if debug_str:
            logger.debug(debug_str)

        # Build: sshpass -p <pwd> ssh <opts> -p <port> -o ConnectTimeout=<t> user@host '<cmd>'
        remote_cmd = (
            "sshpass -p {pwd} ssh {opts} -p {port} "
            "-o ConnectTimeout={timeout} "
            "{user}@{host} {quoted_cmd}"
        ).format(
            pwd=shlex.quote(self._password),
            opts=self._SSH_OPTS,
            port=self.port,
            timeout=self.timeout,
            user=self.username,
            host=self.host,
            quoted_cmd=shlex.quote(cmd),
        )

        logger.debug("Remote(%s) running: %s", self.host, cmd)
        try:
            status, output = subprocess.getstatusoutput(remote_cmd)
            if status != 0 and not ignore_status:
                if err_str:
                    logger.error("%s %s", err_str, output)
                sys.exit(1)
            logger.debug(output)
            return (status, output)
        except Exception as error:
            if err_str:
                logger.error("%s %s", err_str, error)
            sys.exit(1)

    def close(self):
        """No persistent connection to close; kept for API compatibility."""
        logger.debug("RemoteRunner.close() called for %s (no-op)", self.host)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


def gcov_reset():
    """
    Resets the gcov to zero
    """
    gcov_cmd = "echo 1 > /sys/kernel/debug/gcov/reset"
    if runcmd(gcov_cmd, ignore_status=False):
        logger.info("Gcov reset successful")
    else:
        logger.info("Gcov reset fails")


def gcov_code_coverage(basedir_name, test_name, driver_name=None):
    """
    Capture the gcov code coverage
    """
    if not basedir_name.endswith("/"):
        basedir_name = basedir_name + "/"
    linux_src_gcov = f"/sys/kernel/debug/gcov{basedir_name}"

    # copying all the c files into c_files.txt
    os.chdir(basedir_name)
    if os.path.exists("c_files.txt"):
        os.remove("c_files.txt")
    cmd = f"find {linux_src_gcov} -maxdepth 6 -name '*.gcno' > c_files.txt"
    runcmd(cmd, ignore_status=False)
    cmd = "sed -i 's/gcno/c/g' c_files.txt"
    runcmd(cmd, ignore_status=False)
    if os.path.exists("object_directory"):
        shutil.rmtree("object_directory")
    time.sleep(3)
    os.mkdir("object_directory")
    os.chdir(linux_src_gcov)
    gcno_cmd = "find -maxdepth 15 -name '*.gcno' -exec cp {} %sobject_directory \\;" % basedir_name
    gcda_cmd = "find -maxdepth 15 -name '*.gcda' -exec cp {} %sobject_directory \\;" % basedir_name
    runcmd(gcno_cmd, ignore_status=False)
    runcmd(gcda_cmd, ignore_status=False)
    os.chdir(basedir_name)
    with open('c_files.txt', 'r+') as f:
        for line in f.readlines():
            line = line.strip()
            cmd = f"gcov -n -f {line} -o {basedir_name}object_directory > coverage.txt"
            runcmd(cmd, ignore_status=False)
            runcmd("sed -n -i '/Function/{N;p}' coverage.txt", ignore_status=True)
            covrg_percentage = 0
            with open('coverage.txt', 'r+') as fs1:
                for line1, line2 in itertools.zip_longest(*[fs1] * 2):
                    if not line2.startswith("Line"):
                        continue
                    out = line2.split(":")[-1]
                    covrg_percentage = float(out.split("%")[0])
                    if covrg_percentage > 0:
                        line1 = line1.split(" ")[-1]
                        line1 = line1.replace("'", "")
                        line = line.split("gcov")[-1]
                        if driver_name:
                            final_line = line + ":" + line1.strip() + "::" + test_name + "::" + str(covrg_percentage) + "::" + driver_name
                        else:
                            final_line = line + ":" + line1.strip() + "::" + test_name + "::" + str(covrg_percentage)
                        runcmd(f"echo '{final_line}' >> final_files.txt", ignore_status=False)
