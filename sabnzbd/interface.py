#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
sabnzbd.interface - webinterface
"""

import os
import time
from datetime import datetime
import cherrypy
import logging
import urllib.request, urllib.parse, urllib.error
import re
import hashlib
import socket
import ssl
import functools
from random import randint
from xml.sax.saxutils import escape
from Cheetah.Template import Template
from typing import Optional, Callable, Union
from guessit.api import properties as guessit_properties

import sabnzbd
import sabnzbd.rss
from sabnzbd.misc import (
    to_units,
    from_units,
    time_format,
    calc_age,
    int_conv,
    get_base_url,
    is_ipv4_addr,
    is_ipv6_addr,
    get_server_addrinfo,
    is_lan_addr,
    is_loopback_addr,
    ip_in_subnet,
)
from sabnzbd.filesystem import (
    real_path,
    globber,
    globber_full,
    clip_path,
    same_file,
    setname_from_path,
)
from sabnzbd.encoding import xml_name, utob
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.notifier as notifier
import sabnzbd.newsunpack
from sabnzbd.utils.servertests import test_nntp_server_dict
import sabnzbd.utils.ssdp
from sabnzbd.constants import DEF_STDCONFIG, DEFAULT_PRIORITY, CHEETAH_DIRECTIVES, EXCLUDED_GUESSIT_PROPERTIES
from sabnzbd.lang import list_languages
from sabnzbd.api import (
    list_scripts,
    list_cats,
    del_from_section,
    api_handler,
    build_header,
    Ttemplate,
)

##############################################################################
# Security functions
##############################################################################
_MSG_ACCESS_DENIED = "External internet access denied - https://sabnzbd.org/access-denied"
_MSG_ACCESS_DENIED_CONFIG_LOCK = "Access denied - Configuration locked"
_MSG_ACCESS_DENIED_HOSTNAME = "Access denied - Hostname verification failed: https://sabnzbd.org/hostname-check"
_MSG_MISSING_AUTH = "Missing authentication"
_MSG_APIKEY_REQUIRED = "API Key Required"
_MSG_APIKEY_INCORRECT = "API Key Incorrect"


def secured_expose(
    wrap_func: Optional[Callable] = None,
    check_configlock: bool = False,
    check_for_login: bool = True,
    check_api_key: bool = False,
    access_type: int = 4,
) -> Union[Callable, str]:
    """Wrapper for both cherrypy.expose and login/access check"""
    if not wrap_func:
        return functools.partial(
            secured_expose,
            check_configlock=check_configlock,
            check_for_login=check_for_login,
            check_api_key=check_api_key,
            access_type=access_type,
        )

    # Expose to cherrypy
    wrap_func.exposed = True

    @functools.wraps(wrap_func)
    def internal_wrap(*args, **kwargs):
        # Label for logging in this and other functions, handling X-Forwarded-For
        # The cherrypy.request object allows adding custom attributes
        if cherrypy.request.headers.get("X-Forwarded-For"):
            cherrypy.request.remote_label = "%s (X-Forwarded-For: %s) [%s]" % (
                cherrypy.request.remote.ip,
                cherrypy.request.headers.get("X-Forwarded-For"),
                cherrypy.request.headers.get("User-Agent"),
            )
        else:
            cherrypy.request.remote_label = "%s [%s]" % (
                cherrypy.request.remote.ip,
                cherrypy.request.headers.get("User-Agent"),
            )

        # Log all requests
        if cfg.api_logging():
            logging.debug(
                "Request %s %s from %s %s",
                cherrypy.request.method,
                cherrypy.request.path_info,
                cherrypy.request.remote_label,
                kwargs,
            )

        # Add X-Frame-Headers headers to page-requests
        if cfg.x_frame_options():
            cherrypy.response.headers["X-Frame-Options"] = "SameOrigin"

        # Check if config is locked
        if check_configlock and cfg.configlock():
            cherrypy.response.status = 403
            return _MSG_ACCESS_DENIED_CONFIG_LOCK

        # Check if external access and if it's allowed
        if not check_access(access_type=access_type, warn_user=True):
            cherrypy.response.status = 403
            return _MSG_ACCESS_DENIED

        # Verify login status, only for non-key pages
        if check_for_login and not check_api_key and not check_login():
            raise Raiser("/login/")

        # Verify host used for the visit
        if not check_hostname():
            cherrypy.response.status = 403
            return _MSG_ACCESS_DENIED_HOSTNAME

        # Some pages need correct API key
        if check_api_key:
            msg = check_apikey(kwargs)
            if msg:
                cherrypy.response.status = 403
                return msg

        # All good, cool!
        return wrap_func(*args, **kwargs)

    return internal_wrap


def check_access(access_type: int = 4, warn_user: bool = False) -> bool:
    """Check if external address is allowed given access_type:
    1=nzb
    2=api
    3=full_api
    4=webui
    5=webui with login for external
    """
    # Easy, it's allowed
    if access_type <= cfg.inet_exposure():
        return True

    remote_ip = cherrypy.request.remote.ip

    # Check for localhost
    if is_loopback_addr(remote_ip):
        return True

    if not cfg.local_ranges():
        # No local ranges defined, allow all private addresses by default
        is_allowed = is_lan_addr(remote_ip)
    else:
        is_allowed = any(ip_in_subnet(remote_ip, r) for r in cfg.local_ranges())

    if not is_allowed and warn_user:
        log_warning_and_ip(T("Refused connection from:"))
    return is_allowed


def check_hostname():
    """Check if hostname is allowed, to mitigate DNS-rebinding attack.
    Similar to CVE-2019-5702, we need to add protection even
    if only allowed to be accessed via localhost.
    """
    # If login is enabled, no API-key can be deducted
    if cfg.username() and cfg.password():
        return True

    # Don't allow requests without Host
    host = cherrypy.request.headers.get("Host")
    if not host:
        return False

    # Remove the port-part (like ':8080'), if it is there, always on the right hand side.
    # Not to be confused with IPv6 colons (within square brackets)
    host = re.sub(":[0123456789]+$", "", host).lower()

    # Fine if localhost or IP
    if host == "localhost" or is_ipv4_addr(host) or is_ipv6_addr(host):
        return True

    # Check on the whitelist
    if host in cfg.host_whitelist():
        return True

    # Fine if ends with ".local" or ".local.", aka mDNS name
    # See rfc6762 Multicast DNS
    if host.endswith((".local", ".local.")):
        return True

    # Ohoh, bad
    log_warning_and_ip(T('Refused connection with hostname "%s" from:') % host)
    return False


# Create a more unique ID for each instance
COOKIE_SECRET = str(randint(1000, 100000) * os.getpid())


def set_login_cookie(remove=False, remember_me=False):
    """We try to set a cookie as unique as possible
    to the current user. Based on it's IP and the
    current process ID of the SAB instance and a random
    number, so cookies cannot be re-used
    """
    salt = randint(1, 1000)
    cookie_str = utob(str(salt) + cherrypy.request.remote.ip + COOKIE_SECRET)
    cherrypy.response.cookie["login_cookie"] = hashlib.sha1(cookie_str).hexdigest()
    cherrypy.response.cookie["login_cookie"]["path"] = "/"
    cherrypy.response.cookie["login_cookie"]["httponly"] = 1
    cherrypy.response.cookie["login_salt"] = salt
    cherrypy.response.cookie["login_salt"]["path"] = "/"
    cherrypy.response.cookie["login_salt"]["httponly"] = 1

    # If we want to be remembered
    if remember_me:
        cherrypy.response.cookie["login_cookie"]["max-age"] = 3600 * 24 * 14
        cherrypy.response.cookie["login_salt"]["max-age"] = 3600 * 24 * 14

    # To remove
    if remove:
        cherrypy.response.cookie["login_cookie"]["expires"] = 0
        cherrypy.response.cookie["login_salt"]["expires"] = 0
    else:
        # Notify about new login
        notifier.send_notification(T("User logged in"), T("User logged in to the web interface"), "new_login")


def check_login_cookie():
    # Do we have everything?
    if "login_cookie" not in cherrypy.request.cookie or "login_salt" not in cherrypy.request.cookie:
        return False

    cookie_str = utob(str(cherrypy.request.cookie["login_salt"].value) + cherrypy.request.remote.ip + COOKIE_SECRET)
    return cherrypy.request.cookie["login_cookie"].value == hashlib.sha1(cookie_str).hexdigest()


def check_login():
    # Not when no authentication required or basic-auth is on
    if not cfg.html_login() or not cfg.username() or not cfg.password():
        return True

    # If we show login for external IP, by using access_type=6 we can check if IP match
    if cfg.inet_exposure() == 5 and check_access(access_type=6):
        return True

    # Check the cookie
    return check_login_cookie()


def check_basic_auth(_, username, password):
    """CherryPy basic authentication validation"""
    return username == cfg.username() and password == cfg.password()


def set_auth(conf):
    """Set the authentication for CherryPy"""
    if cfg.username() and cfg.password() and not cfg.html_login():
        conf.update(
            {
                "tools.auth_basic.on": True,
                "tools.auth_basic.realm": "SABnzbd",
                "tools.auth_basic.checkpassword": check_basic_auth,
            }
        )
        conf.update(
            {
                "/api": {"tools.auth_basic.on": False},
                "%s/api" % cfg.url_base(): {"tools.auth_basic.on": False},
            }
        )
    else:
        conf.update({"tools.auth_basic.on": False})


def check_apikey(kwargs):
    """Check API-key or NZB-key
    Return None when OK, otherwise an error message
    """
    mode = kwargs.get("mode", "")
    name = kwargs.get("name", "")

    # Lookup required access level for the specific api-call
    req_access = sabnzbd.api.api_level(mode, name)
    if not check_access(req_access, warn_user=True):
        return _MSG_ACCESS_DENIED

    # Skip for auth and version calls
    if mode in ("version", "auth"):
        return None

    # First check API-key, if OK that's sufficient
    if not cfg.disable_key():
        key = kwargs.get("apikey")
        if not key:
            log_warning_and_ip(
                T("API Key missing, please enter the api key from Config->General into your 3rd party program:")
            )
            return _MSG_APIKEY_REQUIRED
        elif req_access == 1 and key == cfg.nzb_key():
            return None
        elif key == cfg.api_key():
            return None
        else:
            log_warning_and_ip(T("API Key incorrect, Use the api key from Config->General in your 3rd party program:"))
            return _MSG_APIKEY_INCORRECT

    # No active API-key, check web credentials instead
    if cfg.username() and cfg.password():
        if check_login() or (
            kwargs.get("ma_username") == cfg.username() and kwargs.get("ma_password") == cfg.password()
        ):
            pass
        else:
            log_warning_and_ip(
                T(
                    "Authentication missing, please enter username/password from Config->General into your 3rd party program:"
                )
            )
            return _MSG_MISSING_AUTH
    return None


def log_warning_and_ip(txt):
    """Include the IP and the Proxy-IP for warnings"""
    if cfg.api_warnings():
        logging.warning("%s %s", txt, cherrypy.request.remote_label)


##############################################################################
# Helper raiser functions
##############################################################################
def Raiser(root: str = "", **kwargs):
    # Add extras
    if kwargs:
        root = "%s?%s" % (root, urllib.parse.urlencode(kwargs))

    # Optionally add the leading /sabnzbd/ (or what the user set)
    if not root.startswith(cfg.url_base()):
        root = cherrypy.request.script_name + root

    # Log the redirect
    if cfg.api_logging():
        logging.debug("Request %s %s redirected to %s", cherrypy.request.method, cherrypy.request.path_info, root)

    # Send the redirect
    return cherrypy.HTTPRedirect(root)


def rssRaiser(root, kwargs):
    return Raiser(root, feed=kwargs.get("feed"))


##############################################################################
# Page definitions
##############################################################################
class MainPage:
    def __init__(self):
        self.__root = "/"

        # Add all sub-pages
        self.login = LoginPage()
        self.config = ConfigPage("/config/")
        self.wizard = Wizard("/wizard/")

    @secured_expose
    def index(self, **kwargs):
        # Redirect to wizard if no servers are set
        if kwargs.get("skip_wizard") or config.get_servers():
            info = build_header()

            info["have_rss_defined"] = bool(config.get_rss())
            info["have_watched_dir"] = bool(cfg.dirscan_dir())

            # Have logout only with HTML and if inet=5, only when we are external
            info["have_logout"] = (
                cfg.username()
                and cfg.password()
                and (
                    cfg.html_login()
                    and (cfg.inet_exposure() < 5 or (cfg.inet_exposure() == 5 and not check_access(access_type=6)))
                )
            )

            bytespersec_list = sabnzbd.BPSMeter.get_bps_list()
            info["bytespersec_list"] = ",".join([str(bps) for bps in bytespersec_list])

            template = Template(
                file=os.path.join(sabnzbd.WEB_DIR, "main.tmpl"), searchList=[info], compilerSettings=CHEETAH_DIRECTIVES
            )
            return template.respond()
        else:
            # Redirect to the setup wizard
            raise cherrypy.HTTPRedirect("%s/wizard/" % cfg.url_base())

    @secured_expose(check_api_key=True)
    def shutdown(self, **kwargs):
        # Check for PID
        pid_in = kwargs.get("pid")
        if pid_in and int(pid_in) != os.getpid():
            return "Incorrect PID for this instance, remove PID from URL to initiate shutdown."

        sabnzbd.shutdown_program()
        return T("SABnzbd shutdown finished")

    @secured_expose(check_api_key=True, access_type=1)
    def api(self, **kwargs):
        """Redirect to API-handler, we check the access_type in the API-handler"""
        return api_handler(kwargs)

    @secured_expose
    def scriptlog(self, **kwargs):
        """Needed for all skins, URL is fixed due to postproc"""
        # No session key check, due to fixed URLs
        name = kwargs.get("name")
        if name:
            history_db = sabnzbd.get_db_connection()
            return ShowString(history_db.get_name(name), history_db.get_script_log(name))
        else:
            raise Raiser(self.__root)

    @secured_expose
    def robots_txt(self, **kwargs):
        """Keep web crawlers out"""
        cherrypy.response.headers["Content-Type"] = "text/plain"
        return "User-agent: *\nDisallow: /\n"

    @secured_expose
    def description_xml(self, **kwargs):
        """Provide the description.xml which was broadcast via SSDP"""
        if is_lan_addr(cherrypy.request.remote.ip):
            cherrypy.response.headers["Content-Type"] = "application/xml"
            return utob(sabnzbd.utils.ssdp.server_ssdp_xml())
        else:
            return None


##############################################################################
class Wizard:
    def __init__(self, root):
        self.__root = root

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):
        """Show the language selection page"""
        if sabnzbd.WIN32:
            from sabnzbd.utils.apireg import get_install_lng

            cfg.language.set(get_install_lng())
            logging.debug('Installer language code "%s"', cfg.language())

        info = build_header(sabnzbd.WIZARD_DIR)
        info["languages"] = list_languages()
        template = Template(
            file=os.path.join(sabnzbd.WIZARD_DIR, "index.html"), searchList=[info], compilerSettings=CHEETAH_DIRECTIVES
        )
        return template.respond()

    @secured_expose(check_configlock=True)
    def one(self, **kwargs):
        """Accept language and show server page"""
        if kwargs.get("lang"):
            cfg.language.set(kwargs.get("lang"))

        # Always setup Glitter
        change_web_dir("Glitter - Auto")

        info = build_header(sabnzbd.WIZARD_DIR)
        info["certificate_validation"] = sabnzbd.CERTIFICATE_VALIDATION

        # Just in case, add server
        servers = config.get_servers()
        if not servers:
            info["host"] = ""
            info["port"] = ""
            info["username"] = ""
            info["password"] = ""
            info["connections"] = ""
            info["ssl"] = 0
            info["ssl_verify"] = 2
        else:
            # Sort servers to get the first enabled one
            server_names = sorted(
                servers,
                key=lambda svr: "%d%02d%s"
                % (int(not servers[svr].enable()), servers[svr].priority(), servers[svr].displayname().lower()),
            )
            for server in server_names:
                # If there are multiple servers, just use the first enabled one
                s = servers[server]
                info["host"] = s.host()
                info["port"] = s.port()
                info["username"] = s.username()
                info["password"] = s.password.get_stars()
                info["connections"] = s.connections()
                info["ssl"] = s.ssl()
                info["ssl_verify"] = s.ssl_verify()
                if s.enable():
                    break
        template = Template(
            file=os.path.join(sabnzbd.WIZARD_DIR, "one.html"), searchList=[info], compilerSettings=CHEETAH_DIRECTIVES
        )
        return template.respond()

    @secured_expose(check_configlock=True)
    def two(self, **kwargs):
        """Accept server and show the final page for restart"""
        # Save server details
        if kwargs:
            kwargs["enable"] = 1
            handle_server(kwargs)

        config.save_config()

        # Show Restart screen
        info = build_header(sabnzbd.WIZARD_DIR)

        info["access_url"], info["urls"] = get_access_info()
        info["download_dir"] = cfg.download_dir.get_clipped_path()
        info["complete_dir"] = cfg.complete_dir.get_clipped_path()

        template = Template(
            file=os.path.join(sabnzbd.WIZARD_DIR, "two.html"), searchList=[info], compilerSettings=CHEETAH_DIRECTIVES
        )
        return template.respond()


def get_access_info():
    """Build up a list of url's that sabnzbd can be accessed from"""
    # Access_url is used to provide the user a link to SABnzbd depending on the host
    cherryhost = cfg.cherryhost()
    host = socket.gethostname().lower()
    socks = [host]

    if cherryhost == "0.0.0.0":
        # Grab a list of all ips for the hostname
        try:
            addresses = socket.getaddrinfo(host, None)
        except:
            addresses = []
        for addr in addresses:
            address = addr[4][0]
            # Filter out ipv6 addresses (should not be allowed)
            if ":" not in address and address not in socks:
                socks.append(address)
        socks.insert(0, "localhost")
    elif cherryhost == "::":
        # Grab a list of all ips for the hostname
        addresses = socket.getaddrinfo(host, None)
        for addr in addresses:
            address = addr[4][0]
            # Only ipv6 addresses will work
            if ":" in address:
                address = "[%s]" % address
                if address not in socks:
                    socks.append(address)
        socks.insert(0, "localhost")
    elif cherryhost:
        socks = [cherryhost]

    # Add the current requested URL as the base
    access_url = urllib.parse.urljoin(cherrypy.request.base, cfg.url_base())

    urls = [access_url]
    for sock in socks:
        if sock:
            if cfg.enable_https() and cfg.https_port():
                url = "https://%s:%s%s" % (sock, cfg.https_port(), cfg.url_base())
            elif cfg.enable_https():
                url = "https://%s:%s%s" % (sock, cfg.cherryport(), cfg.url_base())
            else:
                url = "http://%s:%s%s" % (sock, cfg.cherryport(), cfg.url_base())
            urls.append(url)

    # Return a unique list
    return access_url, set(urls)


##############################################################################
class LoginPage:
    @secured_expose(check_for_login=False)
    def index(self, **kwargs):
        # Base output var
        info = build_header(sabnzbd.WEB_DIR_CONFIG)
        info["error"] = ""

        # Logout?
        if kwargs.get("logout"):
            set_login_cookie(remove=True)
            raise Raiser()

        # Check if there's even a username/password set
        if check_login():
            raise Raiser(cherrypy.request.script_name + "/")

        # Check login info
        if kwargs.get("username") == cfg.username() and kwargs.get("password") == cfg.password():
            # Save login cookie
            set_login_cookie(remember_me=kwargs.get("remember_me", False))
            # Log the success
            logging.info("Successful login from %s", cherrypy.request.remote_label)
            # Redirect
            raise Raiser(cherrypy.request.script_name + "/")
        elif kwargs.get("username") or kwargs.get("password"):
            info["error"] = T("Authentication failed, check username/password.")
            # Warn about the potential security problem
            logging.warning(T("Unsuccessful login attempt from %s"), cherrypy.request.remote_label)

        # Show login
        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "login", "main.tmpl"),
            searchList=[info],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()


##############################################################################
class ConfigPage:
    def __init__(self, root):
        self.__root = root
        self.folders = ConfigFolders("/config/folders/")
        self.notify = ConfigNotify("/config/notify/")
        self.general = ConfigGeneral("/config/general/")
        self.rss = ConfigRss("/config/rss/")
        self.scheduling = ConfigScheduling("/config/scheduling/")
        self.server = ConfigServer("/config/server/")
        self.switches = ConfigSwitches("/config/switches/")
        self.categories = ConfigCats("/config/categories/")
        self.sorting = ConfigSorting("/config/sorting/")
        self.special = ConfigSpecial("/config/special/")

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):
        conf = build_header(sabnzbd.WEB_DIR_CONFIG)
        conf["configfn"] = clip_path(config.get_filename())
        conf["cmdline"] = sabnzbd.CMDLINE
        conf["build"] = sabnzbd.__baseline__[:7]

        conf["have_unzip"] = bool(sabnzbd.newsunpack.ZIP_COMMAND)
        conf["have_7zip"] = bool(sabnzbd.newsunpack.SEVEN_COMMAND)
        conf["have_sabyenc"] = sabnzbd.decoder.SABYENC_ENABLED
        conf["have_mt_par2"] = sabnzbd.newsunpack.PAR2_MT

        conf["certificate_validation"] = sabnzbd.CERTIFICATE_VALIDATION
        conf["ssl_version"] = ssl.OPENSSL_VERSION

        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "config.tmpl"),
            searchList=[conf],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()


##############################################################################
LIST_DIRPAGE = (
    "download_dir",
    "download_free",
    "complete_dir",
    "complete_free",
    "admin_dir",
    "nzb_backup_dir",
    "dirscan_dir",
    "dirscan_speed",
    "script_dir",
    "email_dir",
    "permissions",
    "log_dir",
    "password_file",
)

LIST_BOOL_DIRPAGE = ("fulldisk_autoresume",)


class ConfigFolders:
    def __init__(self, root):
        self.__root = root

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):
        conf = build_header(sabnzbd.WEB_DIR_CONFIG)

        for kw in LIST_DIRPAGE + LIST_BOOL_DIRPAGE:
            conf[kw] = config.get_config("misc", kw)()

        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "config_folders.tmpl"),
            searchList=[conf],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()

    @secured_expose(check_api_key=True, check_configlock=True)
    def saveDirectories(self, **kwargs):
        for kw in LIST_DIRPAGE + LIST_BOOL_DIRPAGE:
            value = kwargs.get(kw)
            if value is not None or kw in LIST_BOOL_DIRPAGE:
                if kw in ("complete_dir", "dirscan_dir"):
                    msg = config.get_config("misc", kw).set(value, create=True)
                else:
                    msg = config.get_config("misc", kw).set(value)
                if msg:
                    # return sabnzbd.api.report('json', error=msg)
                    return badParameterResponse(msg, kwargs.get("ajax"))

        if not sabnzbd.check_incomplete_vs_complete():
            return badParameterResponse(
                T("The Completed Download Folder cannot be the same or a subfolder of the Temporary Download Folder"),
                kwargs.get("ajax"),
            )
        config.save_config()
        if kwargs.get("ajax"):
            return sabnzbd.api.report()
        else:
            raise Raiser(self.__root)


##############################################################################
SWITCH_LIST = (
    "par_option",
    "top_only",
    "direct_unpack",
    "enable_meta",
    "win_process_prio",
    "auto_sort",
    "propagation_delay",
    "auto_disconnect",
    "flat_unpack",
    "safe_postproc",
    "no_dupes",
    "replace_spaces",
    "replace_dots",
    "ignore_samples",
    "pause_on_post_processing",
    "nice",
    "ionice",
    "pre_script",
    "pause_on_pwrar",
    "sfv_check",
    "deobfuscate_final_filenames",
    "folder_rename",
    "load_balancing",
    "quota_size",
    "quota_day",
    "quota_resume",
    "quota_period",
    "history_retention",
    "pre_check",
    "max_art_tries",
    "fail_hopeless_jobs",
    "enable_all_par",
    "enable_recursive",
    "no_series_dupes",
    "series_propercheck",
    "script_can_fail",
    "new_nzb_on_failure",
    "unwanted_extensions",
    "action_on_unwanted_extensions",
    "unwanted_extensions_mode",
    "sanitize_safe",
    "rating_enable",
    "rating_api_key",
    "rating_filter_enable",
    "rating_filter_abort_audio",
    "rating_filter_abort_video",
    "rating_filter_abort_encrypted",
    "rating_filter_abort_encrypted_confirm",
    "rating_filter_abort_spam",
    "rating_filter_abort_spam_confirm",
    "rating_filter_abort_downvoted",
    "rating_filter_abort_keywords",
    "rating_filter_pause_audio",
    "rating_filter_pause_video",
    "rating_filter_pause_encrypted",
    "rating_filter_pause_encrypted_confirm",
    "rating_filter_pause_spam",
    "rating_filter_pause_spam_confirm",
    "rating_filter_pause_downvoted",
    "rating_filter_pause_keywords",
)


class ConfigSwitches:
    def __init__(self, root):
        self.__root = root

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):
        conf = build_header(sabnzbd.WEB_DIR_CONFIG)

        conf["certificate_validation"] = sabnzbd.CERTIFICATE_VALIDATION
        conf["have_nice"] = bool(sabnzbd.newsunpack.NICE_COMMAND)
        conf["have_ionice"] = bool(sabnzbd.newsunpack.IONICE_COMMAND)
        conf["cleanup_list"] = cfg.cleanup_list.get_string()

        for kw in SWITCH_LIST:
            conf[kw] = config.get_config("misc", kw)()
        conf["unwanted_extensions"] = cfg.unwanted_extensions.get_string()

        conf["scripts"] = list_scripts() or ["None"]

        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "config_switches.tmpl"),
            searchList=[conf],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()

    @secured_expose(check_api_key=True, check_configlock=True)
    def saveSwitches(self, **kwargs):
        for kw in SWITCH_LIST:
            item = config.get_config("misc", kw)
            value = kwargs.get(kw)
            if kw == "unwanted_extensions" and value:
                value = value.lower().replace(".", "")
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg, kwargs.get("ajax"))

        cleanup_list = kwargs.get("cleanup_list")
        if cleanup_list and sabnzbd.WIN32:
            cleanup_list = cleanup_list.lower()
        cfg.cleanup_list.set(cleanup_list)

        config.save_config()
        if kwargs.get("ajax"):
            return sabnzbd.api.report()
        else:
            raise Raiser(self.__root)


##############################################################################
SPECIAL_BOOL_LIST = (
    "start_paused",
    "no_penalties",
    "fast_fail",
    "overwrite_files",
    "enable_par_cleanup",
    "process_unpacked_par2",
    "queue_complete_pers",
    "api_warnings",
    "helpfull_warnings",
    "ampm",
    "enable_unrar",
    "enable_unzip",
    "enable_7zip",
    "enable_filejoin",
    "enable_tsjoin",
    "ignore_unrar_dates",
    "osx_menu",
    "osx_speed",
    "win_menu",
    "allow_incomplete_nzb",
    "rss_filenames",
    "ipv6_hosting",
    "keep_awake",
    "empty_postproc",
    "html_login",
    "wait_for_dfolder",
    "enable_broadcast",
    "warn_dupl_jobs",
    "replace_illegal",
    "backup_for_duplicates",
    "disable_api_key",
    "api_logging",
    "x_frame_options",
    "require_modern_tls",
)
SPECIAL_VALUE_LIST = (
    "downloader_sleep_time",
    "size_limit",
    "movie_rename_limit",
    "episode_rename_limit",
    "nomedia_marker",
    "max_url_retries",
    "req_completion_rate",
    "wait_ext_drive",
    "max_foldername_length",
    "show_sysload",
    "url_base",
    "num_decoders",
    "direct_unpack_threads",
    "ipv6_servers",
    "selftest_host",
    "rating_host",
    "ssdp_broadcast_interval",
)
SPECIAL_LIST_LIST = (
    "rss_odd_titles",
    "quick_check_ext_ignore",
    "host_whitelist",
    "local_ranges",
)


class ConfigSpecial:
    def __init__(self, root):
        self.__root = root

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):
        conf = build_header(sabnzbd.WEB_DIR_CONFIG)
        conf["switches"] = [
            (kw, config.get_config("misc", kw)(), config.get_config("misc", kw).default()) for kw in SPECIAL_BOOL_LIST
        ]
        conf["entries"] = [
            (kw, config.get_config("misc", kw)(), config.get_config("misc", kw).default()) for kw in SPECIAL_VALUE_LIST
        ]
        conf["entries"].extend(
            [
                (kw, config.get_config("misc", kw).get_string(), config.get_config("misc", kw).default_string())
                for kw in SPECIAL_LIST_LIST
            ]
        )

        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "config_special.tmpl"),
            searchList=[conf],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()

    @secured_expose(check_api_key=True, check_configlock=True)
    def saveSpecial(self, **kwargs):
        for kw in SPECIAL_BOOL_LIST + SPECIAL_VALUE_LIST + SPECIAL_LIST_LIST:
            item = config.get_config("misc", kw)
            value = kwargs.get(kw)
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg)

        config.save_config()
        raise Raiser(self.__root)


##############################################################################
GENERAL_LIST = (
    "host",
    "port",
    "username",
    "refresh_rate",
    "language",
    "cache_limit",
    "inet_exposure",
    "enable_https",
    "https_port",
    "https_cert",
    "https_key",
    "https_chain",
    "enable_https_verification",
    "auto_browser",
    "check_new_rel",
)


class ConfigGeneral:
    def __init__(self, root):
        self.__root = root

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):

        conf = build_header(sabnzbd.WEB_DIR_CONFIG)

        conf["configfn"] = config.get_filename()
        conf["certificate_validation"] = sabnzbd.CERTIFICATE_VALIDATION

        web_list = []
        for interface_dir in globber_full(sabnzbd.DIR_INTERFACES):
            # Ignore the config
            if not interface_dir.endswith(DEF_STDCONFIG):
                # Check the available templates
                for colorscheme in globber(
                    os.path.join(interface_dir, "templates", "static", "stylesheets", "colorschemes")
                ):
                    web_list.append("%s - %s" % (setname_from_path(interface_dir), setname_from_path(colorscheme)))

        conf["web_list"] = web_list
        conf["web_dir"] = "%s - %s" % (cfg.web_dir(), cfg.web_color())
        conf["password"] = cfg.password.get_stars()

        conf["language"] = cfg.language()
        conf["lang_list"] = list_languages()

        for kw in GENERAL_LIST:
            conf[kw] = config.get_config("misc", kw)()

        conf["bandwidth_max"] = cfg.bandwidth_max()
        conf["bandwidth_perc"] = cfg.bandwidth_perc()
        conf["nzb_key"] = cfg.nzb_key()
        conf["caller_url"] = cherrypy.request.base + cfg.url_base()

        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "config_general.tmpl"),
            searchList=[conf],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()

    @secured_expose(check_api_key=True, check_configlock=True)
    def saveGeneral(self, **kwargs):
        # Handle general options
        for kw in GENERAL_LIST:
            item = config.get_config("misc", kw)
            value = kwargs.get(kw)
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg)

        # Handle special options
        cfg.password.set(kwargs.get("password"))

        web_dir = kwargs.get("web_dir")
        change_web_dir(web_dir)

        bandwidth_max = kwargs.get("bandwidth_max")
        if bandwidth_max is not None:
            cfg.bandwidth_max.set(bandwidth_max)
        bandwidth_perc = kwargs.get("bandwidth_perc")
        if bandwidth_perc is not None:
            cfg.bandwidth_perc.set(bandwidth_perc)
        bandwidth_perc = cfg.bandwidth_perc()
        if bandwidth_perc and not bandwidth_max:
            logging.warning_helpful(T("You must set a maximum bandwidth before you can set a bandwidth limit"))

        config.save_config()

        # Update CherryPy authentication
        set_auth(cherrypy.config)
        if kwargs.get("ajax"):
            return sabnzbd.api.report(data={"success": True, "restart_req": sabnzbd.RESTART_REQ})
        else:
            raise Raiser(self.__root)


def change_web_dir(web_dir):
    web_dir, web_color = web_dir.split(" - ")
    web_dir_path = real_path(sabnzbd.DIR_INTERFACES, web_dir)

    if not os.path.exists(web_dir_path):
        return badParameterResponse("Cannot find web template: %s" % web_dir_path)
    else:
        cfg.web_dir.set(web_dir)
        cfg.web_color.set(web_color)


##############################################################################
class ConfigServer:
    def __init__(self, root):
        self.__root = root

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):
        conf = build_header(sabnzbd.WEB_DIR_CONFIG)
        new = []
        servers = config.get_servers()
        server_names = sorted(
            servers,
            key=lambda svr: "%d%02d%s"
            % (int(not servers[svr].enable()), servers[svr].priority(), servers[svr].displayname().lower()),
        )
        for svr in server_names:
            new.append(servers[svr].get_dict(safe=True))
            t, m, w, d, daily, articles_tried, articles_success = sabnzbd.BPSMeter.amounts(svr)
            if t:
                new[-1]["amounts"] = (
                    to_units(t),
                    to_units(m),
                    to_units(w),
                    to_units(d),
                    daily,
                    articles_tried,
                    articles_success,
                )
            new[-1]["quota_left"] = to_units(
                servers[svr].quota.get_int() - sabnzbd.BPSMeter.grand_total.get(svr, 0) + servers[svr].usage_at_start()
            )

        conf["servers"] = new
        conf["cats"] = list_cats(default=True)
        conf["certificate_validation"] = sabnzbd.CERTIFICATE_VALIDATION

        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "config_server.tmpl"),
            searchList=[conf],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()

    @secured_expose(check_api_key=True, check_configlock=True)
    def addServer(self, **kwargs):
        return handle_server(kwargs, self.__root, True)

    @secured_expose(check_api_key=True, check_configlock=True)
    def saveServer(self, **kwargs):
        return handle_server(kwargs, self.__root)

    @secured_expose(check_api_key=True, check_configlock=True)
    def testServer(self, **kwargs):
        _, msg = test_nntp_server_dict(kwargs)
        return msg

    @secured_expose(check_api_key=True, check_configlock=True)
    def delServer(self, **kwargs):
        kwargs["section"] = "servers"
        kwargs["keyword"] = kwargs.get("server")
        del_from_section(kwargs)
        raise Raiser(self.__root)

    @secured_expose(check_api_key=True, check_configlock=True)
    def clrServer(self, **kwargs):
        server = kwargs.get("server")
        if server:
            sabnzbd.BPSMeter.clear_server(server)
        raise Raiser(self.__root)

    @secured_expose(check_api_key=True, check_configlock=True)
    def toggleServer(self, **kwargs):
        server = kwargs.get("server")
        if server:
            svr = config.get_config("servers", server)
            if svr:
                svr.enable.set(not svr.enable())
                config.save_config()
                sabnzbd.Downloader.update_server(server, server)
        raise Raiser(self.__root)


def unique_svr_name(server):
    """Return a unique variant on given server name"""
    num = 0
    svr = 1
    new_name = server
    while svr:
        if num:
            new_name = "%s@%d" % (server, num)
        else:
            new_name = "%s" % server
        svr = config.get_config("servers", new_name)
        num += 1
    return new_name


def check_server(host, port, ajax):
    """Check if server address resolves properly"""
    if host.lower() == "localhost" and sabnzbd.AMBI_LOCALHOST:
        return badParameterResponse(T("Warning: LOCALHOST is ambiguous, use numerical IP-address."), ajax)

    if get_server_addrinfo(host, int_conv(port)):
        return ""
    else:
        return badParameterResponse(T('Server address "%s:%s" is not valid.') % (host, port), ajax)


def handle_server(kwargs, root=None, new_svr=False):
    """Internal server handler"""
    ajax = kwargs.get("ajax")
    host = kwargs.get("host", "").strip()
    if not host:
        return badParameterResponse(T("Server address required"), ajax)

    port = kwargs.get("port", "").strip()
    if not port:
        if not kwargs.get("ssl", "").strip():
            port = "119"
        else:
            port = "563"
        kwargs["port"] = port

    if kwargs.get("connections", "").strip() == "":
        kwargs["connections"] = "1"

    if kwargs.get("enable") == "1":
        msg = check_server(host, port, ajax)
        if msg:
            return msg

    # Default server name is just the host name
    server = host

    svr = None
    old_server = kwargs.get("server")
    if old_server:
        svr = config.get_config("servers", old_server)
    if svr:
        server = old_server
    else:
        svr = config.get_config("servers", server)

    if new_svr:
        server = unique_svr_name(server)

    for kw in ("ssl", "send_group", "enable", "optional"):
        if kw not in kwargs.keys():
            kwargs[kw] = None
    if svr and not new_svr:
        svr.set_dict(kwargs)
    else:
        old_server = None
        config.ConfigServer(server, kwargs)

    config.save_config()
    sabnzbd.Downloader.update_server(old_server, server)
    if root:
        if ajax:
            return sabnzbd.api.report()
        else:
            raise Raiser(root)


##############################################################################
class ConfigRss:
    def __init__(self, root):
        self.__root = root
        self.__refresh_readout = None  # Set to URL when new readout is needed
        self.__refresh_download = False  # True when feed needs to be read
        self.__refresh_force = False  # True if forced download of all matches is required
        self.__refresh_ignore = False  # True if first batch of new feed must be ignored
        self.__evaluate = False  # True if feed needs to be re-filtered
        self.__show_eval_button = False  # True if the "Apply filers" button should be shown
        self.__last_msg = ""  # Last error message from RSS reader

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):
        conf = build_header(sabnzbd.WEB_DIR_CONFIG)

        conf["scripts"] = list_scripts(default=True)
        pick_script = conf["scripts"] != []

        conf["categories"] = list_cats(default=True)
        pick_cat = conf["categories"] != []

        conf["rss_rate"] = cfg.rss_rate()

        rss = {}
        feeds = config.get_rss()
        for feed in feeds:
            rss[feed] = feeds[feed].get_dict()
            filters = feeds[feed].filters()
            rss[feed]["filters"] = filters
            rss[feed]["filter_states"] = [bool(sabnzbd.rss.convert_filter(f[4])) for f in filters]
            rss[feed]["filtercount"] = len(filters)

            rss[feed]["pick_cat"] = pick_cat
            rss[feed]["pick_script"] = pick_script
            rss[feed]["link"] = urllib.parse.quote_plus(feed)
            rss[feed]["baselink"] = [get_base_url(uri) for uri in rss[feed]["uri"]]
            rss[feed]["uris"] = feeds[feed].uri.get_string()

        active_feed = kwargs.get("feed", "")
        conf["active_feed"] = active_feed
        conf["rss"] = rss
        conf["rss_next"] = time.strftime(time_format("%H:%M"), time.localtime(sabnzbd.RSSReader.next_run))

        if active_feed:
            readout = bool(self.__refresh_readout)
            logging.debug("RSS READOUT = %s", readout)
            if not readout:
                self.__refresh_download = False
                self.__refresh_force = False
                self.__refresh_ignore = False
            if self.__evaluate:
                msg = sabnzbd.RSSReader.run_feed(
                    active_feed,
                    download=self.__refresh_download,
                    force=self.__refresh_force,
                    ignoreFirst=self.__refresh_ignore,
                    readout=readout,
                )
            else:
                msg = ""
            self.__evaluate = False
            if readout:
                sabnzbd.RSSReader.save()
                self.__last_msg = msg
            else:
                msg = self.__last_msg
            self.__refresh_readout = None
            conf["evalButton"] = self.__show_eval_button
            conf["error"] = msg

            conf["downloaded"], conf["matched"], conf["unmatched"] = GetRssLog(active_feed)
        else:
            self.__last_msg = ""

        # Find a unique new Feed name
        unum = 1
        txt = T("Feed")  # : Used as default Feed name in Config->RSS
        while txt + str(unum) in feeds:
            unum += 1
        conf["feed"] = txt + str(unum)

        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "config_rss.tmpl"),
            searchList=[conf],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()

    @secured_expose(check_api_key=True, check_configlock=True)
    def save_rss_rate(self, **kwargs):
        """Save changed RSS automatic readout rate"""
        cfg.rss_rate.set(kwargs.get("rss_rate"))
        config.save_config()
        sabnzbd.Scheduler.restart()
        raise Raiser(self.__root)

    @secured_expose(check_api_key=True, check_configlock=True)
    def upd_rss_feed(self, **kwargs):
        """Update Feed level attributes,
        legacy version: ignores 'enable' parameter
        """
        if kwargs.get("enable") is not None:
            del kwargs["enable"]
        try:
            cf = config.get_rss()[kwargs.get("feed")]
        except KeyError:
            cf = None
        uri = Strip(kwargs.get("uri"))
        if cf and uri:
            kwargs["uri"] = uri
            cf.set_dict(kwargs)
            config.save_config()

        self.__evaluate = False
        self.__show_eval_button = True
        raise rssRaiser(self.__root, kwargs)

    @secured_expose(check_api_key=True, check_configlock=True)
    def save_rss_feed(self, **kwargs):
        """Update Feed level attributes"""
        feed_name = kwargs.get("feed")
        try:
            cf = config.get_rss()[feed_name]
        except KeyError:
            cf = None
        if "enable" not in kwargs:
            kwargs["enable"] = 0
        uri = Strip(kwargs.get("uri"))
        if cf and uri:
            kwargs["uri"] = uri
            cf.set_dict(kwargs)

            # Did we get a new name for this feed?
            new_name = kwargs.get("feed_new_name")
            if new_name and new_name != feed_name:
                cf.rename(new_name)
                # Update the feed name for the redirect
                kwargs["feed"] = new_name

            config.save_config()

        raise rssRaiser(self.__root, kwargs)

    @secured_expose(check_api_key=True, check_configlock=True)
    def toggle_rss_feed(self, **kwargs):
        """Toggle automatic read-out flag of Feed"""
        try:
            item = config.get_rss()[kwargs.get("feed")]
        except KeyError:
            item = None
        if cfg:
            item.enable.set(not item.enable())
            config.save_config()
        if kwargs.get("table"):
            raise Raiser(self.__root)
        else:
            raise rssRaiser(self.__root, kwargs)

    @secured_expose(check_api_key=True, check_configlock=True)
    def add_rss_feed(self, **kwargs):
        """Add one new RSS feed definition"""
        feed = Strip(kwargs.get("feed")).strip("[]")
        uri = Strip(kwargs.get("uri"))
        if feed and uri:
            try:
                rss_cfg = config.get_rss()[feed]
            except KeyError:
                rss_cfg = None
            if not rss_cfg and uri:
                kwargs["feed"] = feed
                kwargs["uri"] = uri
                config.ConfigRSS(feed, kwargs)
                # Clear out any existing reference to this feed name
                # Otherwise first-run detection can fail
                sabnzbd.RSSReader.clear_feed(feed)
                config.save_config()
                self.__refresh_readout = feed
                self.__refresh_download = False
                self.__refresh_force = False
                self.__refresh_ignore = True
                self.__evaluate = True
                raise rssRaiser(self.__root, kwargs)
            else:
                raise Raiser(self.__root)
        else:
            raise Raiser(self.__root)

    @secured_expose(check_api_key=True, check_configlock=True)
    def upd_rss_filter(self, **kwargs):
        """Wrapper, so we can call from api.py"""
        self.internal_upd_rss_filter(**kwargs)

    def internal_upd_rss_filter(self, **kwargs):
        """Save updated filter definition"""
        try:
            feed_cfg = config.get_rss()[kwargs.get("feed")]
        except KeyError:
            raise rssRaiser(self.__root, kwargs)

        pp = kwargs.get("pp", "")
        if pp.lower() == "none":
            pp = ""
        script = ConvertSpecials(kwargs.get("script"))
        cat = ConvertSpecials(kwargs.get("cat"))
        prio = ConvertSpecials(kwargs.get("priority"))
        filt = kwargs.get("filter_text")
        enabled = kwargs.get("enabled", "0")

        if filt:
            feed_cfg.filters.update(
                int(kwargs.get("index", 0)), (cat, pp, script, kwargs.get("filter_type"), filt, prio, enabled)
            )

            # Move filter if requested
            index = int_conv(kwargs.get("index", ""))
            new_index = kwargs.get("new_index", "")
            if new_index and int_conv(new_index) != index:
                feed_cfg.filters.move(int(index), int_conv(new_index))

            config.save_config()
        self.__evaluate = False
        self.__show_eval_button = True
        raise rssRaiser(self.__root, kwargs)

    @secured_expose(check_api_key=True, check_configlock=True)
    def del_rss_feed(self, *args, **kwargs):
        """Remove complete RSS feed"""
        kwargs["section"] = "rss"
        kwargs["keyword"] = kwargs.get("feed")
        del_from_section(kwargs)
        sabnzbd.RSSReader.clear_feed(kwargs.get("feed"))
        raise Raiser(self.__root)

    @secured_expose(check_api_key=True, check_configlock=True)
    def del_rss_filter(self, **kwargs):
        """Wrapper, so we can call from api.py"""
        self.internal_del_rss_filter(**kwargs)

    def internal_del_rss_filter(self, **kwargs):
        """Remove one RSS filter"""
        try:
            feed_cfg = config.get_rss()[kwargs.get("feed")]
        except KeyError:
            raise rssRaiser(self.__root, kwargs)

        feed_cfg.filters.delete(int(kwargs.get("index", 0)))
        config.save_config()
        self.__evaluate = False
        self.__show_eval_button = True
        raise rssRaiser(self.__root, kwargs)

    @secured_expose(check_api_key=True, check_configlock=True)
    def download_rss_feed(self, *args, **kwargs):
        """Force download of all matching jobs in a feed"""
        if "feed" in kwargs:
            feed = kwargs["feed"]
            self.__refresh_readout = feed
            self.__refresh_download = True
            self.__refresh_force = True
            self.__refresh_ignore = False
            self.__evaluate = True
        raise rssRaiser(self.__root, kwargs)

    @secured_expose(check_api_key=True, check_configlock=True)
    def clean_rss_jobs(self, *args, **kwargs):
        """Remove processed RSS jobs from UI"""
        sabnzbd.RSSReader.clear_downloaded(kwargs["feed"])
        self.__evaluate = True
        raise rssRaiser(self.__root, kwargs)

    @secured_expose(check_api_key=True, check_configlock=True)
    def test_rss_feed(self, *args, **kwargs):
        """Read the feed content again and show results"""
        if "feed" in kwargs:
            feed = kwargs["feed"]
            self.__refresh_readout = feed
            self.__refresh_download = False
            self.__refresh_force = False
            self.__refresh_ignore = True
            self.__evaluate = True
            self.__show_eval_button = False
        raise rssRaiser(self.__root, kwargs)

    @secured_expose(check_api_key=True, check_configlock=True)
    def eval_rss_feed(self, *args, **kwargs):
        """Re-apply the filters to the feed"""
        if "feed" in kwargs:
            self.__refresh_download = False
            self.__refresh_force = False
            self.__refresh_ignore = False
            self.__show_eval_button = False
            self.__evaluate = True

        raise rssRaiser(self.__root, kwargs)

    @secured_expose(check_api_key=True, check_configlock=True)
    def download(self, **kwargs):
        """Download NZB from provider (Download button)"""
        feed = kwargs.get("feed")
        url = kwargs.get("url")
        nzbname = kwargs.get("nzbname")
        att = sabnzbd.RSSReader.lookup_url(feed, url)
        if att:
            pp = att.get("pp")
            cat = att.get("cat")
            script = att.get("script")
            prio = att.get("prio")

            if url:
                sabnzbd.add_url(url, pp, script, cat, prio, nzbname)
            # Need to pass the title instead
            sabnzbd.RSSReader.flag_downloaded(feed, url)
        raise rssRaiser(self.__root, kwargs)

    @secured_expose(check_api_key=True, check_configlock=True)
    def rss_now(self, *args, **kwargs):
        """Run an automatic RSS run now"""
        sabnzbd.Scheduler.force_rss()
        raise Raiser(self.__root)


def ConvertSpecials(p):
    """Convert None to 'None' and 'Default' to ''"""
    if p is None:
        p = "None"
    elif p.lower() == T("Default").lower():
        p = ""
    return p


def Strip(txt):
    """Return stripped string, can handle None"""
    try:
        return txt.strip()
    except:
        return None


##############################################################################
_SCHED_ACTIONS = (
    "resume",
    "pause",
    "pause_all",
    "shutdown",
    "restart",
    "speedlimit",
    "pause_post",
    "resume_post",
    "scan_folder",
    "rss_scan",
    "remove_failed",
    "remove_completed",
    "pause_all_low",
    "pause_all_normal",
    "pause_all_high",
    "resume_all_low",
    "resume_all_normal",
    "resume_all_high",
    "enable_quota",
    "disable_quota",
)


class ConfigScheduling:
    def __init__(self, root):
        self.__root = root

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):
        def get_days():
            days = {
                "*": T("Daily"),
                "1": T("Monday"),
                "2": T("Tuesday"),
                "3": T("Wednesday"),
                "4": T("Thursday"),
                "5": T("Friday"),
                "6": T("Saturday"),
                "7": T("Sunday"),
            }
            return days

        conf = build_header(sabnzbd.WEB_DIR_CONFIG)

        actions = []
        actions.extend(_SCHED_ACTIONS)
        day_names = get_days()
        categories = list_cats(False)
        snum = 1
        conf["schedlines"] = []
        conf["taskinfo"] = []
        for ev in sabnzbd.scheduler.sort_schedules(all_events=False):
            line = ev[3]
            conf["schedlines"].append(line)
            try:
                enabled, m, h, day_numbers, action = line.split(" ", 4)
            except:
                continue
            action = action.strip()
            try:
                action, value = action.split(" ", 1)
            except:
                value = ""
            value = value.strip()
            if value and not value.lower().strip("0123456789kmgtp%."):
                if "%" not in value and from_units(value) < 1.0:
                    value = T("off")  # : "Off" value for speedlimit in scheduler
                else:
                    if "%" not in value and 1 < int_conv(value) < 101:
                        value += "%"
                    value = value.upper()
            if action in actions:
                action = Ttemplate("sch-" + action)
            else:
                if action in ("enable_server", "disable_server"):
                    try:
                        value = '"%s"' % config.get_servers()[value].displayname()
                    except KeyError:
                        value = '"%s" <<< %s' % (value, T("Undefined server!"))
                    action = Ttemplate("sch-" + action)
                if action in ("pause_cat", "resume_cat"):
                    action = Ttemplate("sch-" + action)
                    if value not in categories:
                        # Category name change
                        value = '"%s" <<< %s' % (value, T("Incorrect parameter"))
                    else:
                        value = '"%s"' % value

            if day_numbers == "1234567":
                days_of_week = "Daily"
            elif day_numbers == "12345":
                days_of_week = "Weekdays"
            elif day_numbers == "67":
                days_of_week = "Weekends"
            else:
                days_of_week = ", ".join([day_names.get(i, "**") for i in day_numbers])

            item = (snum, "%02d" % int(h), "%02d" % int(m), days_of_week, "%s %s" % (action, value), enabled)

            conf["taskinfo"].append(item)
            snum += 1

        actions_lng = {}
        for action in actions:
            actions_lng[action] = Ttemplate("sch-" + action)

        actions_servers = {}
        servers = config.get_servers()
        for srv in servers:
            actions_servers[srv] = servers[srv].displayname()

        conf["actions_servers"] = actions_servers
        conf["actions"] = actions
        conf["actions_lng"] = actions_lng
        conf["categories"] = categories

        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "config_scheduling.tmpl"),
            searchList=[conf],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()

    @secured_expose(check_api_key=True, check_configlock=True)
    def addSchedule(self, **kwargs):
        servers = config.get_servers()
        minute = kwargs.get("minute")
        hour = kwargs.get("hour")
        days_of_week = "".join([str(x) for x in kwargs.get("daysofweek", "")])
        if not days_of_week:
            days_of_week = "1234567"
        action = kwargs.get("action")
        arguments = kwargs.get("arguments")

        arguments = arguments.strip().lower()
        if arguments in ("on", "enable"):
            arguments = "1"
        elif arguments in ("off", "disable"):
            arguments = "0"

        if minute and hour and days_of_week and action:
            if action == "speedlimit":
                if not arguments or arguments.strip("0123456789kmgtp%."):
                    arguments = 0
            elif action in _SCHED_ACTIONS:
                arguments = ""
            elif action in servers:
                if arguments == "1":
                    arguments = action
                    action = "enable_server"
                else:
                    arguments = action
                    action = "disable_server"

            elif action in ("pause_cat", "resume_cat"):
                # Need original category name, not lowercased
                arguments = arguments.strip()
            else:
                # Something else, leave empty
                action = None

            if action:
                sched = cfg.schedules()
                sched.append("%s %s %s %s %s %s" % (1, minute, hour, days_of_week, action, arguments))
                cfg.schedules.set(sched)

        config.save_config()
        sabnzbd.Scheduler.restart()
        raise Raiser(self.__root)

    @secured_expose(check_api_key=True, check_configlock=True)
    def delSchedule(self, **kwargs):
        schedules = cfg.schedules()
        line = kwargs.get("line")
        if line and line in schedules:
            schedules.remove(line)
            cfg.schedules.set(schedules)
            config.save_config()
            sabnzbd.Scheduler.restart()
        raise Raiser(self.__root)

    @secured_expose(check_api_key=True, check_configlock=True)
    def toggleSchedule(self, **kwargs):
        schedules = cfg.schedules()
        line = kwargs.get("line")
        if line:
            for i, schedule in enumerate(schedules):
                if schedule == line:
                    # Toggle the schedule
                    schedule_split = schedule.split()
                    schedule_split[0] = "%d" % (schedule_split[0] == "0")
                    schedules[i] = " ".join(schedule_split)
                    break
            cfg.schedules.set(schedules)
            config.save_config()
            sabnzbd.Scheduler.restart()
        raise Raiser(self.__root)


##############################################################################
class ConfigCats:
    def __init__(self, root):
        self.__root = root

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):
        conf = build_header(sabnzbd.WEB_DIR_CONFIG)

        conf["scripts"] = list_scripts(default=True)
        conf["defdir"] = cfg.complete_dir.get_clipped_path()

        categories = config.get_ordered_categories()
        conf["have_cats"] = len(categories) > 1

        slotinfo = []
        for cat in categories:
            cat["newzbin"] = cat["newzbin"].replace('"', "&quot;")
            slotinfo.append(cat)

        # Add empty line
        empty = {
            "name": "",
            "order": "0",
            "pp": "-1",
            "script": "",
            "dir": "",
            "newzbin": "",
            "priority": DEFAULT_PRIORITY,
        }
        slotinfo.insert(1, empty)
        conf["slotinfo"] = slotinfo

        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "config_cat.tmpl"),
            searchList=[conf],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()

    @secured_expose(check_api_key=True, check_configlock=True)
    def delete(self, **kwargs):
        kwargs["section"] = "categories"
        kwargs["keyword"] = kwargs.get("name")
        del_from_section(kwargs)
        raise Raiser(self.__root)

    @secured_expose(check_api_key=True, check_configlock=True)
    def save(self, **kwargs):
        name = kwargs.get("name", "*")
        if name == "*":
            newname = name
        else:
            newname = re.sub('"', "", kwargs.get("newname", ""))
        if newname:
            # Check if this cat-dir is not sub-folder of incomplete
            if same_file(cfg.download_dir.get_path(), real_path(cfg.complete_dir.get_path(), kwargs["dir"])):
                return T("Category folder cannot be a subfolder of the Temporary Download Folder.")

            # Delete current one and replace with new one
            if name:
                config.delete("categories", name)
            config.ConfigCat(newname.lower(), kwargs)

        config.save_config()
        raise Raiser(self.__root)


##############################################################################
SORT_LIST = (
    "enable_tv_sorting",
    "tv_sort_string",
    "tv_categories",
    "enable_movie_sorting",
    "movie_sort_string",
    "movie_sort_extra",
    "movie_extra_folder",
    "enable_date_sorting",
    "date_sort_string",
    "movie_categories",
    "date_categories",
)


class ConfigSorting:
    def __init__(self, root):
        self.__root = root

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):
        conf = build_header(sabnzbd.WEB_DIR_CONFIG)
        conf["complete_dir"] = cfg.complete_dir.get_clipped_path()

        for kw in SORT_LIST:
            conf[kw] = config.get_config("misc", kw)()
        conf["categories"] = list_cats(False)
        conf["guessit_properties"] = tuple(
            prop for prop in guessit_properties().keys() if prop not in EXCLUDED_GUESSIT_PROPERTIES
        )

        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "config_sorting.tmpl"),
            searchList=[conf],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()

    @secured_expose(check_api_key=True, check_configlock=True)
    def saveSorting(self, **kwargs):
        for kw in SORT_LIST:
            item = config.get_config("misc", kw)
            value = kwargs.get(kw)
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg)

        config.save_config()
        raise Raiser(self.__root)


def badParameterResponse(msg, ajax=None):
    """Return a html page with error message and a 'back' button"""
    if ajax:
        return sabnzbd.api.report(error=msg)
    else:
        return """
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
<head>
           <title>SABnzbd %s - %s</title>
</head>
<body>
<h3>%s</h3>
%s
<br><br>
<FORM><INPUT TYPE="BUTTON" VALUE="%s" ONCLICK="history.go(-1)"></FORM>
</body>
</html>
""" % (
            sabnzbd.__version__,
            T("ERROR:"),
            T("Incorrect parameter"),
            msg,
            T("Back"),
        )


def ShowString(name, msg):
    """Return a html page listing a file and a 'back' button"""
    return """
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
<head>
           <title>%s</title>
</head>
<body>
           <FORM><INPUT TYPE="BUTTON" VALUE="%s" ONCLICK="history.go(-1)"></FORM>
           <h3>%s</h3>
           <code><pre>%s</pre></code>
</body>
</html>
""" % (
        xml_name(name),
        T("Back"),
        xml_name(name),
        escape(msg),
    )


def GetRssLog(feed):
    def make_item(job):
        # Make a copy
        job = job.copy()

        # Now we apply some formatting
        job["title"] = job["title"]
        job["skip"] = "*" * int(job.get("status", "").endswith("*"))
        # These fields could be empty
        job["cat"] = job.get("cat", "")
        job["size"] = job.get("size", "")
        job["infourl"] = job.get("infourl", "")

        # Auto-fetched jobs didn't have these fields set
        if job.get("url"):
            job["baselink"] = get_base_url(job.get("url"))
            if sabnzbd.rss.special_rss_site(job.get("url")):
                job["nzbname"] = ""
            else:
                job["nzbname"] = job["title"]
        else:
            job["baselink"] = ""
            job["nzbname"] = job["title"]

        if job.get("size", 0):
            job["size_units"] = to_units(job["size"])
        else:
            job["size_units"] = "-"

        # And we add extra fields for sorting
        if job.get("age", 0):
            job["age_ms"] = (job["age"] - datetime.utcfromtimestamp(0)).total_seconds()
            job["age"] = calc_age(job["age"], True)
        else:
            job["age_ms"] = ""
            job["age"] = ""

        if job.get("time_downloaded"):
            job["time_downloaded_ms"] = time.mktime(job["time_downloaded"])
            job["time_downloaded"] = time.strftime(time_format("%H:%M %a %d %b"), job["time_downloaded"])
        else:
            job["time_downloaded_ms"] = ""
            job["time_downloaded"] = ""

        return job

    jobs = sabnzbd.RSSReader.show_result(feed).values()
    good, bad, done = ([], [], [])
    for job in jobs:
        if job["status"][0] == "G":
            good.append(make_item(job))
        elif job["status"][0] == "B":
            bad.append(make_item(job))
        elif job["status"] == "D":
            done.append(make_item(job))

    try:
        # Sort based on actual age, in try-catch just to be sure
        good.sort(key=lambda job: job["age_ms"], reverse=True)
        bad.sort(key=lambda job: job["age_ms"], reverse=True)
        done.sort(key=lambda job: job["time_downloaded_ms"], reverse=True)
    except:
        # Let the javascript do it then..
        pass

    return done, good, bad


##############################################################################
NOTIFY_OPTIONS = {
    "misc": (
        "email_endjob",
        "email_cats",
        "email_full",
        "email_server",
        "email_to",
        "email_from",
        "email_account",
        "email_pwd",
        "email_rss",
    ),
    "ncenter": (
        "ncenter_enable",
        "ncenter_cats",
        "ncenter_prio_startup",
        "ncenter_prio_download",
        "ncenter_prio_pause_resume",
        "ncenter_prio_pp",
        "ncenter_prio_pp",
        "ncenter_prio_complete",
        "ncenter_prio_failed",
        "ncenter_prio_disk_full",
        "ncenter_prio_warning",
        "ncenter_prio_error",
        "ncenter_prio_queue_done",
        "ncenter_prio_other",
        "ncenter_prio_new_login",
    ),
    "acenter": (
        "acenter_enable",
        "acenter_cats",
        "acenter_prio_startup",
        "acenter_prio_download",
        "acenter_prio_pause_resume",
        "acenter_prio_pp",
        "acenter_prio_complete",
        "acenter_prio_failed",
        "acenter_prio_disk_full",
        "acenter_prio_warning",
        "acenter_prio_error",
        "acenter_prio_queue_done",
        "acenter_prio_other",
        "acenter_prio_new_login",
    ),
    "ntfosd": (
        "ntfosd_enable",
        "ntfosd_cats",
        "ntfosd_prio_startup",
        "ntfosd_prio_download",
        "ntfosd_prio_pause_resume",
        "ntfosd_prio_pp",
        "ntfosd_prio_complete",
        "ntfosd_prio_failed",
        "ntfosd_prio_disk_full",
        "ntfosd_prio_warning",
        "ntfosd_prio_error",
        "ntfosd_prio_queue_done",
        "ntfosd_prio_other",
        "ntfosd_prio_new_login",
    ),
    "prowl": (
        "prowl_enable",
        "prowl_cats",
        "prowl_apikey",
        "prowl_prio_startup",
        "prowl_prio_download",
        "prowl_prio_pause_resume",
        "prowl_prio_pp",
        "prowl_prio_complete",
        "prowl_prio_failed",
        "prowl_prio_disk_full",
        "prowl_prio_warning",
        "prowl_prio_error",
        "prowl_prio_queue_done",
        "prowl_prio_other",
        "prowl_prio_new_login",
    ),
    "pushover": (
        "pushover_enable",
        "pushover_cats",
        "pushover_token",
        "pushover_userkey",
        "pushover_device",
        "pushover_prio_startup",
        "pushover_prio_download",
        "pushover_prio_pause_resume",
        "pushover_prio_pp",
        "pushover_prio_complete",
        "pushover_prio_failed",
        "pushover_prio_disk_full",
        "pushover_prio_warning",
        "pushover_prio_error",
        "pushover_prio_queue_done",
        "pushover_prio_other",
        "pushover_prio_new_login",
        "pushover_emergency_retry",
        "pushover_emergency_expire",
    ),
    "pushbullet": (
        "pushbullet_enable",
        "pushbullet_cats",
        "pushbullet_apikey",
        "pushbullet_device",
        "pushbullet_prio_startup",
        "pushbullet_prio_download",
        "pushbullet_prio_pause_resume",
        "pushbullet_prio_pp",
        "pushbullet_prio_complete",
        "pushbullet_prio_failed",
        "pushbullet_prio_disk_full",
        "pushbullet_prio_warning",
        "pushbullet_prio_error",
        "pushbullet_prio_queue_done",
        "pushbullet_prio_other",
        "pushbullet_prio_new_login",
    ),
    "nscript": (
        "nscript_enable",
        "nscript_cats",
        "nscript_script",
        "nscript_parameters",
        "nscript_prio_startup",
        "nscript_prio_download",
        "nscript_prio_pause_resume",
        "nscript_prio_pp",
        "nscript_prio_complete",
        "nscript_prio_failed",
        "nscript_prio_disk_full",
        "nscript_prio_warning",
        "nscript_prio_error",
        "nscript_prio_queue_done",
        "nscript_prio_other",
        "nscript_prio_new_login",
    ),
}


class ConfigNotify:
    def __init__(self, root):
        self.__root = root

    @secured_expose(check_configlock=True)
    def index(self, **kwargs):
        conf = build_header(sabnzbd.WEB_DIR_CONFIG)
        conf["notify_types"] = sabnzbd.notifier.NOTIFICATION
        conf["categories"] = list_cats(False)
        conf["have_ntfosd"] = sabnzbd.notifier.have_ntfosd()
        conf["have_ncenter"] = sabnzbd.DARWIN and sabnzbd.FOUNDATION
        conf["scripts"] = list_scripts(default=False, none=True)

        for section in NOTIFY_OPTIONS:
            for option in NOTIFY_OPTIONS[section]:
                # Use get_string to make sure lists are displayed correctly
                conf[option] = config.get_config(section, option).get_string()

        template = Template(
            file=os.path.join(sabnzbd.WEB_DIR_CONFIG, "config_notify.tmpl"),
            searchList=[conf],
            compilerSettings=CHEETAH_DIRECTIVES,
        )
        return template.respond()

    @secured_expose(check_api_key=True, check_configlock=True)
    def saveNotify(self, **kwargs):
        for section in NOTIFY_OPTIONS:
            for option in NOTIFY_OPTIONS[section]:
                config.get_config(section, option).set(kwargs.get(option))
        config.save_config()
        if kwargs.get("ajax"):
            return sabnzbd.api.report()
        else:
            raise Raiser(self.__root)
