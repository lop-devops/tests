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
# Copyright: 2024 IBM
# Author: Shaik Abdulla <abdulla1@linux.vnet.ibm.com>

"""
HMC CLI helper module.

Connects to an IBM HMC over SSH (using sshpass) and runs HMC CLI commands
to discover managed systems and LPAR details.

Typical usage
-------------
    from lib.hmc import HMCClient

    with HMCClient(hmc_ip='192.168.1.100', username='hscroot', password='abc123') as hmc:
        # List all managed systems on this HMC
        systems = hmc.list_managed_systems()
        print(systems)
        # ['Server-9009-42A-SN12345', 'Server-9009-42A-SN67890']

        # Find which managed system a given LPAR name belongs to
        managed_system = hmc.get_managed_system_for_lpar('my-lpar-01')
        print(managed_system)
        # 'Server-9009-42A-SN12345'

        # Get full details of a specific LPAR
        info = hmc.get_lpar_info('my-lpar-01', managed_system)
        print(info)
"""

import os
import re
import subprocess
import shlex

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

from lib.logger import logger_init

BASE_PATH = os.path.dirname(os.path.abspath(os.path.join(__file__, os.pardir)))
logger = logger_init(filepath=BASE_PATH).getlogger()

# SSH options that suppress host-key prompts and banners — same as RemoteRunner
_SSH_OPTS = (
    "-o StrictHostKeyChecking=no "
    "-o UserKnownHostsFile=/dev/null "
    "-o BatchMode=no "
    "-o LogLevel=ERROR"
)


def get_hmc_ip_from_lsrsrc():
    """
    Detect the HMC IP address from the local RSCT resource class ``IBM.MCP``.

    Runs ``lsrsrc IBM.MCP IPAddresses`` and extracts the first IP address
    from the ``IPAddresses`` attribute, which holds the HMC management IP(s).

    :return: HMC IP string, or None if not found / RSCT not available.
    """
    status, output = subprocess.getstatusoutput(
        "lsrsrc IBM.MCP IPAddresses 2>/dev/null"
    )
    if status != 0 or not output.strip():
        logger.warning("lsrsrc IBM.MCP IPAddresses returned no output (RSCT not available?)")
        return None

    # Output looks like:
    #   resource 1:
    #     IPAddresses = {"192.168.1.100","192.168.1.101"}
    # Extract the first IP inside the braces / quotes
    match = re.search(r'IPAddresses\s*=\s*\{?"?(\d{1,3}(?:\.\d{1,3}){3})', output)
    if match:
        hmc_ip = match.group(1)
        logger.info("HMC IP detected via lsrsrc IBM.MCP: %s", hmc_ip)
        return hmc_ip

    logger.warning("Could not parse IPAddresses from lsrsrc IBM.MCP output:\n%s", output)
    return None


def get_hmc_password_from_secrets_manager(url='https://web.stg-secrets-manager.dal.app.cirrus.ibm.com/'):
    """
    Fetch the current HMC/lab password from the IBM Cirrus Secrets Manager web page.

    The page is a JavaScript SPA; this function attempts to retrieve the
    rendered content by:
      1. Fetching the SPA shell to extract the API base URL / auth token hints.
      2. Trying common REST API endpoints that SPAs typically expose.
      3. Parsing the response for a "Lab Password History" section and
         returning the first (most recent) password entry.

    If the page cannot be fetched or parsed, returns None and logs a warning
    so the caller can fall back to a manually supplied password.

    :param url: Base URL of the secrets manager (default: IBM Cirrus staging).
    :return: Password string, or None if unavailable.
    """
    if not _REQUESTS_AVAILABLE:
        logger.warning(
            "requests library not installed. Install with: pip3 install requests\n"
            "Cannot auto-fetch HMC password from secrets manager."
        )
        return None

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (compatible; pci_info/1.0)',
        'Accept': 'application/json, text/html, */*',
    })

    # ---- Step 1: fetch the SPA shell ----
    try:
        resp = session.get(url, timeout=15, verify=False)
        resp.raise_for_status()
    except Exception as err:
        logger.warning("Could not reach secrets manager at %s: %s", url, err)
        return None

    html = resp.text

    # ---- Step 2: try to find an embedded API base or JS bundle with password data ----
    # Some SPAs embed their API base URL in the HTML or in a config JS file.
    api_base_match = re.search(r'(https?://[^\s"\']+/api)', html)
    api_base = api_base_match.group(1) if api_base_match else url.rstrip('/') + '/api'

    # Common REST endpoints for lab/password resources
    candidate_paths = [
        '/lab-passwords',
        '/passwords',
        '/lab/passwords',
        '/secrets',
        '/lab-password-history',
    ]

    for path in candidate_paths:
        try:
            api_url = api_base.rstrip('/') + path
            api_resp = session.get(api_url, timeout=10, verify=False)
            if api_resp.status_code == 200:
                data = api_resp.json()
                # Handle list response — take first entry
                if isinstance(data, list) and data:
                    entry = data[0]
                    # Common field names for the password value
                    for field in ('password', 'passwd', 'value', 'secret', 'lab_password'):
                        if field in entry:
                            logger.info("HMC password retrieved from %s", api_url)
                            return str(entry[field])
                # Handle dict response with a list inside
                if isinstance(data, dict):
                    for key in ('results', 'data', 'passwords', 'items'):
                        if key in data and isinstance(data[key], list) and data[key]:
                            entry = data[key][0]
                            for field in ('password', 'passwd', 'value', 'secret', 'lab_password'):
                                if field in entry:
                                    logger.info("HMC password retrieved from %s (key=%s)", api_url, key)
                                    return str(entry[field])
        except Exception:
            continue

    # ---- Step 3: last resort — regex scan the raw HTML for password-like values
    # near "Lab Password History"
    lab_section = re.search(
        r'Lab Password History.*?([A-Za-z0-9!@#$%^&*()_+\-=]{8,})',
        html, re.DOTALL | re.IGNORECASE
    )
    if lab_section:
        password = lab_section.group(1).strip()
        logger.info("HMC password extracted from HTML near 'Lab Password History'")
        return password

    logger.warning(
        "Could not extract HMC password from %s. "
        "The page may require browser-based JavaScript rendering. "
        "Please supply the password manually via --hmc-password.",
        url
    )
    return None


class HMCClient:
    """
    Thin SSH wrapper around the HMC CLI.

    All HMC CLI commands are executed via ``sshpass`` + ``ssh`` so no
    Python C-extension dependencies are required.  Only ``sshpass`` must
    be installed on the local machine::

        yum install sshpass   # RHEL/CentOS/Fedora
        apt-get install sshpass  # Ubuntu/Debian

    Parameters
    ----------
    hmc_ip : str
        Hostname or IP address of the HMC.
    username : str
        HMC login username (default HMC admin user is ``hscroot``).
    password : str
        HMC login password.
    port : int
        SSH port on the HMC (default 22).
    timeout : int
        Per-command connect timeout in seconds (default 30).
    """

    def __init__(self, hmc_ip, username='hscroot', password='', port=22, timeout=30):
        # Verify sshpass is available
        chk, _ = subprocess.getstatusoutput("which sshpass")
        if chk != 0:
            logger.error(
                "sshpass is not installed. Install it with: "
                "yum install sshpass  OR  apt-get install sshpass"
            )
            raise RuntimeError("sshpass not found in PATH")

        self.hmc_ip = hmc_ip
        self.username = username
        self._password = password
        self.port = port
        self.timeout = timeout
        logger.info("HMCClient ready for %s@%s:%s", username, hmc_ip, port)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _run(self, hmc_cmd, ignore_status=False):
        """
        Execute *hmc_cmd* on the HMC via sshpass/ssh.

        :param hmc_cmd: HMC CLI command string (e.g. ``lssyscfg -r sys -F name``).
        :param ignore_status: When True, non-zero exit does not raise/exit.
        :return: (status, output) tuple.
        """
        remote_cmd = (
            "sshpass -p {pwd} ssh {opts} -p {port} "
            "-o ConnectTimeout={timeout} "
            "{user}@{host} {quoted_cmd}"
        ).format(
            pwd=shlex.quote(self._password),
            opts=_SSH_OPTS,
            port=self.port,
            timeout=self.timeout,
            user=self.username,
            host=self.hmc_ip,
            quoted_cmd=shlex.quote(hmc_cmd),
        )
        logger.debug("HMC(%s) running: %s", self.hmc_ip, hmc_cmd)
        status, output = subprocess.getstatusoutput(remote_cmd)
        if status != 0 and not ignore_status:
            logger.error("HMC command failed (exit %s): %s\n%s", status, hmc_cmd, output)
        logger.debug(output)
        return (status, output)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def list_managed_systems(self):
        """
        Return a list of all managed system names visible from this HMC.

        Uses: ``lssyscfg -r sys -F name``

        :return: list of str, e.g. ``['Server-9009-42A-SN12345', ...]``
        """
        status, output = self._run("lssyscfg -r sys -F name", ignore_status=True)
        logger.debug("list_managed_systems raw output (exit=%s): %r", status, output)
        if status != 0 or not output.strip():
            logger.warning(
                "No managed systems found on HMC %s (exit=%s). "
                "Check HMC credentials, user permissions, and that the HMC manages at least one system. "
                "Raw output: %r",
                self.hmc_ip, status, output,
            )
            return []
        systems = [s.strip() for s in output.splitlines() if s.strip()]
        logger.info("Managed systems on %s: %s", self.hmc_ip, systems)
        return systems

    def list_lpars(self, managed_system):
        """
        Return a list of LPAR names on *managed_system*.

        Uses: ``lssyscfg -r lpar -m <managed_system> -F name``

        :param managed_system: Managed system name as returned by
                               :meth:`list_managed_systems`.
        :return: list of str LPAR names.
        """
        cmd = "lssyscfg -r lpar -m %s -F name" % shlex.quote(managed_system)
        status, output = self._run(cmd)
        if status != 0 or not output.strip():
            logger.warning("No LPARs found on managed system %s", managed_system)
            return []
        lpars = [l.strip() for l in output.splitlines() if l.strip()]
        logger.info("LPARs on %s: %s", managed_system, lpars)
        return lpars

    def get_managed_system_for_lpar(self, lpar_name):
        """
        Find which managed system a given LPAR belongs to by iterating
        over all managed systems and checking their LPAR lists.

        :param lpar_name: LPAR name to search for.
        :return: managed system name (str) or None if not found.
        """
        for system in self.list_managed_systems():
            if lpar_name in self.list_lpars(system):
                logger.info("LPAR '%s' found on managed system '%s'", lpar_name, system)
                return system
        logger.warning("LPAR '%s' not found on any managed system of HMC %s",
                       lpar_name, self.hmc_ip)
        return None

    def get_lpar_info(self, lpar_name, managed_system):
        """
        Return a dict of key LPAR attributes for *lpar_name* on
        *managed_system*.

        Uses: ``lssyscfg -r lpar -m <ms> --filter lpar_names=<name>``

        :param lpar_name: LPAR name.
        :param managed_system: Managed system name.
        :return: dict with keys such as ``name``, ``lpar_id``, ``state``,
                 ``lpar_env``, ``default_profile``, ``os_version``.
        """
        fields = "name,lpar_id,state,lpar_env,default_profile,os_version"
        cmd = (
            "lssyscfg -r lpar -m {ms} --filter lpar_names={lpar} -F {fields}"
        ).format(
            ms=shlex.quote(managed_system),
            lpar=shlex.quote(lpar_name),
            fields=fields,
        )
        status, output = self._run(cmd)
        if status != 0 or not output.strip():
            logger.warning("Could not retrieve info for LPAR '%s'", lpar_name)
            return {}
        values = output.strip().split(',')
        keys = fields.split(',')
        info = dict(zip(keys, values))
        logger.info("LPAR info for '%s': %s", lpar_name, info)
        return info

    def get_vios_info(self, managed_system):
        """
        Return VIOS names and their RMC IP addresses on *managed_system*.

        Step 1: ``lssyscfg -r lpar -m <ms> -F name,lpar_env --filter lpar_env=vioserver``
                to get VIOS partition names (confirmed working format: "ltcden7-vios1,vioserver").
        Step 2: For each VIOS name, fetch its RMC IP via a separate
                ``lssyscfg -r lpar -m <ms> --filter lpar_names=<name> -F rmc_ipaddr`` call.

        :param managed_system: Managed system name.
        :return: dict with keys:
                 - ``vios_names`` — space-separated VIOS partition names
                 - ``vios_ip``    — space-separated VIOS RMC IP addresses
                 - ``vios_list``  — list of dicts, each with ``name`` and ``ip``
        """
        # Step 1: fetch ALL LPARs with name + lpar_env, then filter in Python.
        # The HMC --filter flag can be unreliable across firmware versions;
        # Python-side filtering on lpar_env containing "vio" (case-insensitive)
        # or partition name containing "vios" is more robust.
        cmd = (
            "lssyscfg -r lpar -m {ms} -F name,lpar_env"
        ).format(ms=shlex.quote(managed_system))
        status, output = self._run(cmd, ignore_status=True)
        if status != 0 or not output.strip():
            logger.warning("lssyscfg returned no output for managed system '%s'", managed_system)
            return {'vios_names': '', 'vios_ip': '', 'vios_list': []}

        vios_list = []
        for line in output.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            # Format: "ltcden7-vios1,vioserver"
            parts = line.split(',')
            name = parts[0].strip()
            lpar_env = parts[1].strip() if len(parts) > 1 else ''
            # Match on lpar_env containing "vio" OR partition name containing "vios"
            if ('vio' in lpar_env.lower() or 'vios' in name.lower()) and name:
                vios_list.append({'name': name, 'ip': ''})

        if not vios_list:
            logger.warning("No VIOS partitions identified on managed system '%s'", managed_system)
            return {'vios_names': '', 'vios_ip': '', 'vios_list': []}

        # Step 2: fetch RMC IP for each VIOS
        for vios in vios_list:
            ip_cmd = (
                "lssyscfg -r lpar -m {ms} --filter lpar_names={name} -F rmc_ipaddr"
            ).format(
                ms=shlex.quote(managed_system),
                name=shlex.quote(vios['name']),
            )
            ip_status, ip_output = self._run(ip_cmd, ignore_status=True)
            if ip_status == 0 and ip_output.strip():
                vios['ip'] = ip_output.strip().split('\n')[0].strip()

        names = [v['name'] for v in vios_list]
        # If only one VIOS, repeat it twice so callers always get two entries
        if len(names) == 1:
            names = names * 2
        vios_names = ' '.join(names)
        vios_ip = ' '.join(v['ip'] for v in vios_list if v['ip'])
        logger.info("VIOS on '%s': names=%s ips=%s", managed_system, vios_names, vios_ip)
        return {'vios_names': vios_names, 'vios_ip': vios_ip, 'vios_list': vios_list}

    def get_managed_system_details(self, managed_system):
        """
        Return a dict of key attributes for *managed_system*.

        Uses: ``lssyscfg -r sys -m <ms> -F name,serial_num,type_model,state``

        :param managed_system: Managed system name.
        :return: dict with keys ``name``, ``serial_num``, ``type_model``, ``state``.
        """
        fields = "name,serial_num,type_model,state"
        cmd = "lssyscfg -r sys -m {ms} -F {fields}".format(
            ms=shlex.quote(managed_system),
            fields=fields,
        )
        status, output = self._run(cmd)
        if status != 0 or not output.strip():
            logger.warning("Could not retrieve details for managed system '%s'", managed_system)
            return {}
        values = output.strip().split(',')
        keys = fields.split(',')
        details = dict(zip(keys, values))
        logger.info("Managed system details for '%s': %s", managed_system, details)
        return details

    # ------------------------------------------------------------------ #
    # Context manager support
    # ------------------------------------------------------------------ #

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # No persistent SSH connection to close (sshpass spawns per-command)
        logger.debug("HMCClient context exited for %s", self.hmc_ip)
        return False
