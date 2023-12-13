#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team (sabnzbd.org)
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
#

"""
sabnzbd.notifier - Send notifications to any notification services
"""


import os.path
import logging
import urllib.request
import urllib.parse
import http.client
import json
from threading import Thread
from typing import Optional, Dict

import sabnzbd
import sabnzbd.cfg
from sabnzbd.encoding import utob
from sabnzbd.filesystem import make_script_path
from sabnzbd.misc import build_and_run_command
from sabnzbd.newsunpack import create_env

if sabnzbd.WIN32:
    try:
        from win32comext.shell import shell
        from windows_toasts import InteractableWindowsToaster, Toast, ToastActivatedEventArgs, ToastButton

        # Set a custom AUMID to display the right icon, it is written to the registry by the installer
        shell.SetCurrentProcessExplicitAppUserModelID("SABnzbd")
        _HAVE_WINDOWS_TOASTER = True
    except:
        # Only supported on Windows 10 and above
        _HAVE_WINDOWS_TOASTER = False

try:
    import notify2

    _HAVE_NTFOSD = True

    # Check for working version, not all pynotify are the same
    # Without DISPLAY, notify2 cannot autolaunch a dbus-daemon
    if not hasattr(notify2, "init") or "DISPLAY" not in os.environ:
        _HAVE_NTFOSD = False
except:
    _HAVE_NTFOSD = False


##############################################################################
# Define translatable message table
##############################################################################
TT = lambda x: x
NOTIFICATION_TYPES = {
    "startup": TT("Startup/Shutdown"),  #: Notification
    "pause_resume": TT("Pause") + "/" + TT("Resume"),  #: Notification
    "download": TT("Added NZB"),  #: Notification
    "pp": TT("Post-processing started"),  # : Notification
    "complete": TT("Job finished"),  #: Notification
    "failed": TT("Job failed"),  #: Notification
    "warning": TT("Warning"),  #: Notification
    "error": TT("Error"),  #: Notification
    "disk_full": TT("Disk full"),  #: Notification
    "queue_done": TT("Queue finished"),  #: Notification
    "new_login": TT("User logged in"),  #: Notification
    "other": TT("Other Messages"),  #: Notification
}

NOTIFICATION_ACTIONS = {
    "open_folder": TT("Open folder"),  #: Notification action
    "open_complete": TT("Open complete folder"),  #: Notification action
}


def have_ntfosd() -> bool:
    """Return if any PyNotify (notify2) support is present"""
    return bool(_HAVE_NTFOSD)


def check_classes(notification_type: str, section: str) -> bool:
    """Check if `notification_type` is enabled in `section`"""
    try:
        return sabnzbd.config.get_config(section, "%s_prio_%s" % (section, notification_type))() > 0
    except TypeError:
        logging.debug("Incorrect Notify option %s:%s_prio_%s", section, section, notification_type)
        return False


def get_prio(notification_type: str, section: str) -> int:
    """Check prio of `notification_type` in `section`"""
    try:
        return sabnzbd.config.get_config(section, "%s_prio_%s" % (section, notification_type))()
    except TypeError:
        logging.debug("Incorrect Notify option %s:%s_prio_%s", section, section, notification_type)
        return -1000


def check_cat(section: str, job_cat: str, keyword: Optional[str] = None) -> bool:
    """Check if `job_cat` is enabled in `section`.
    * = All, if no other categories selected.
    """
    if not job_cat:
        return True
    try:
        if not keyword:
            keyword = section
        section_cats = sabnzbd.config.get_config(section, "%s_cats" % keyword)()
        return ["*"] == section_cats or job_cat in section_cats
    except TypeError:
        logging.debug("Incorrect Notify option %s:%s_cats", section, section)
        return True


def send_notification(
    title: str,
    msg: str,
    notification_type: str,
    job_cat: Optional[str] = None,
    actions: Optional[Dict[str, str]] = None,
):
    """Send Notification message"""
    logging.info("Sending notification: %s - %s (type=%s, job_cat=%s)", title, msg, notification_type, job_cat)
    # Notification Center
    if sabnzbd.MACOS and sabnzbd.cfg.ncenter_enable():
        if check_classes(notification_type, "ncenter") and check_cat("ncenter", job_cat):
            send_notification_center(title, msg, notification_type, actions)

    # Windows
    if sabnzbd.WIN32 and sabnzbd.cfg.acenter_enable():
        if check_classes(notification_type, "acenter") and check_cat("acenter", job_cat):
            send_windows(title, msg, notification_type, actions)

    # Prowl
    if sabnzbd.cfg.prowl_enable() and check_cat("prowl", job_cat):
        if sabnzbd.cfg.prowl_apikey():
            Thread(target=send_prowl, args=(title, msg, notification_type)).start()

    # Pushover
    if sabnzbd.cfg.pushover_enable() and check_cat("pushover", job_cat):
        if sabnzbd.cfg.pushover_token():
            Thread(target=send_pushover, args=(title, msg, notification_type)).start()

    # Pushbullet
    if sabnzbd.cfg.pushbullet_enable() and check_cat("pushbullet", job_cat):
        if sabnzbd.cfg.pushbullet_apikey() and check_classes(notification_type, "pushbullet"):
            Thread(target=send_pushbullet, args=(title, msg, notification_type)).start()

    # Notification script.
    if sabnzbd.cfg.nscript_enable() and check_cat("nscript", job_cat):
        if sabnzbd.cfg.nscript_script():
            Thread(target=send_nscript, args=(title, msg, notification_type)).start()

    # NTFOSD
    if have_ntfosd() and sabnzbd.cfg.ntfosd_enable():
        if check_classes(notification_type, "ntfosd") and check_cat("ntfosd", job_cat):
            send_notify_osd(title, msg)


##############################################################################
# Ubuntu NotifyOSD Support
##############################################################################
_NTFOSD = False


def send_notify_osd(title, message):
    """Send a message to NotifyOSD"""
    global _NTFOSD
    if not _HAVE_NTFOSD:
        return T("Not available")  # : Function is not available on this OS

    error = "NotifyOSD not working"
    icon = os.path.join(sabnzbd.DIR_PROG, "interfaces/Config/templates/staticcfg/images/logo-arrow.svg")

    # Wrap notify2.init to prevent blocking in dbus
    # when there's no active notification daemon
    try:
        _NTFOSD = _NTFOSD or notify2.init("SABnzbd")
    except:
        _NTFOSD = False

    if _NTFOSD:
        logging.info("Send to NotifyOSD: %s / %s", title, message)
        try:
            note = notify2.Notification(title, message, icon)
            note.show()
        except:
            # Apparently not implemented on this system
            logging.info(error)
            return error
        return None
    else:
        return error


def send_notification_center(title: str, msg: str, notification_type: str, actions: Optional[Dict[str, str]] = None):
    """Send message to macOS Notification Center.
    Only 1 button is possible on macOS!"""
    try:
        subtitle = T(NOTIFICATION_TYPES.get(notification_type, "other"))
        button_text = button_action = None
        if actions:
            for action in actions:
                button_text = NOTIFICATION_ACTIONS[action]
                button_action = actions[action]
                break

        sabnzbd.MACOSTRAY.send_notification(title, subtitle, msg, button_text, button_action)
    except:
        logging.info(T("Failed to send macOS notification"))
        logging.debug("Traceback: ", exc_info=True)
        return T("Failed to send macOS notification")


def send_prowl(title, msg, notification_type, force=False, test=None):
    """Send message to Prowl"""

    if test:
        apikey = test.get("prowl_apikey")
    else:
        apikey = sabnzbd.cfg.prowl_apikey()
    if not apikey:
        return T("Cannot send, missing required data")

    title = T(NOTIFICATION_TYPES.get(notification_type, "other"))
    title = urllib.parse.quote(utob(title))
    msg = urllib.parse.quote(utob(msg))
    prio = get_prio(notification_type, "prowl")

    if force:
        prio = 0

    if prio > -3:
        url = (
            "https://api.prowlapp.com/publicapi/add?apikey=%s&application=SABnzbd"
            "&event=%s&description=%s&priority=%d" % (apikey, title, msg, prio)
        )
        try:
            urllib.request.urlopen(url)
            return ""
        except:
            logging.warning(T("Failed to send Prowl message"))
            logging.info("Traceback: ", exc_info=True)
            return T("Failed to send Prowl message")
    return ""


def send_pushover(title, msg, notification_type, force=False, test=None):
    """Send message to pushover"""

    if test:
        apikey = test.get("pushover_token")
        userkey = test.get("pushover_userkey")
        device = test.get("pushover_device")
    else:
        apikey = sabnzbd.cfg.pushover_token()
        userkey = sabnzbd.cfg.pushover_userkey()
        device = sabnzbd.cfg.pushover_device()
        emergency_retry = sabnzbd.cfg.pushover_emergency_retry()
        emergency_expire = sabnzbd.cfg.pushover_emergency_expire()
    if not apikey or not userkey:
        return T("Cannot send, missing required data")

    title = T(NOTIFICATION_TYPES.get(notification_type, "other"))
    prio = get_prio(notification_type, "pushover")

    if force:
        prio = 1

    if prio == 2:
        body = {
            "token": apikey,
            "user": userkey,
            "device": device,
            "title": title,
            "message": msg,
            "priority": prio,
            "retry": emergency_retry,
            "expire": emergency_expire,
        }
        return do_send_pushover(body)
    if -3 < prio < 2:
        body = {
            "token": apikey,
            "user": userkey,
            "device": device,
            "title": title,
            "message": msg,
            "priority": prio,
        }
        return do_send_pushover(body)


def do_send_pushover(body):
    try:
        conn = http.client.HTTPSConnection("api.pushover.net:443")
        conn.request(
            "POST",
            "/1/messages.json",
            urllib.parse.urlencode(body),
            {"Content-type": "application/x-www-form-urlencoded"},
        )
        res = conn.getresponse()
        if res.status != 200:
            logging.error(T("Bad response from Pushover (%s): %s"), res.status, res.read())
            return T("Failed to send pushover message")
        else:
            return ""
    except:
        logging.warning(T("Failed to send pushover message"))
        logging.info("Traceback: ", exc_info=True)
        return T("Failed to send pushover message")


def send_pushbullet(title, msg, notification_type, force=False, test=None):
    """Send message to Pushbullet"""

    if test:
        apikey = test.get("pushbullet_apikey")
        device = test.get("pushbullet_device")
    else:
        apikey = sabnzbd.cfg.pushbullet_apikey()
        device = sabnzbd.cfg.pushbullet_device()
    if not apikey:
        return T("Cannot send, missing required data")

    title = "SABnzbd: " + T(NOTIFICATION_TYPES.get(notification_type, "other"))

    try:
        conn = http.client.HTTPSConnection("api.pushbullet.com:443")
        conn.request(
            "POST",
            "/v2/pushes",
            json.dumps({"type": "note", "device": device, "title": title, "body": msg}),
            headers={"Authorization": "Bearer " + apikey, "Content-type": "application/json"},
        )
        res = conn.getresponse()
        if res.status != 200:
            logging.error(T("Bad response from Pushbullet (%s): %s"), res.status, res.read())
        else:
            logging.info("Successfully sent to Pushbullet")

    except:
        logging.warning(T("Failed to send pushbullet message"))
        logging.info("Traceback: ", exc_info=True)
        return T("Failed to send pushbullet message")
    return ""


def send_nscript(title, msg, notification_type, force=False, test=None):
    """Run user's notification script"""
    if test:
        script = test.get("nscript_script")
        env_params = {"notification_parameters": test.get("nscript_parameters")}
    else:
        script = sabnzbd.cfg.nscript_script()
        env_params = {"notification_parameters": sabnzbd.cfg.nscript_parameters()}

    if not script:
        return T("Cannot send, missing required data")
    title = "SABnzbd: " + T(NOTIFICATION_TYPES.get(notification_type, "other"))

    if force or check_classes(notification_type, "nscript"):
        script_path = make_script_path(script)
        if script_path:
            ret = -1
            output = None
            try:
                p = build_and_run_command(
                    [
                        script_path,
                        notification_type,
                        title,
                        msg,
                    ],
                    env=create_env(extra_env_fields=env_params),
                )
                output = p.stdout.read()
                ret = p.wait()
            except:
                logging.info("Failed to run script %s", script, exc_info=True)

            if ret:
                logging.error(T('Script returned exit code %s and output "%s"'), ret, output)
                return T('Script returned exit code %s and output "%s"') % (ret, output)
            else:
                logging.info("Successfully executed notification script %s", script_path)
                logging.debug("Script output: %s", output)
        else:
            return T('Notification script "%s" does not exist') % script_path
    return ""


def send_windows(title: str, msg: str, notification_type: str, actions: Optional[Dict[str, str]] = None):
    try:
        if _HAVE_WINDOWS_TOASTER:
            notification_sender = InteractableWindowsToaster("SABnzbd", notifierAUMID="SABnzbd")
            toast_notification = Toast([title, msg], group=notification_type, launch_action=sabnzbd.BROWSER_URL)

            # Add any buttons
            if actions:
                for action in actions:
                    toast_notification.AddAction(ToastButton(NOTIFICATION_ACTIONS[action], launch=actions[action]))

            notification_sender.show_toast(toast_notification)
        elif sabnzbd.WINTRAY and not sabnzbd.WINTRAY.terminate:
            sabnzbd.WINTRAY.sendnotification(title, msg)
    except:
        logging.info(T("Failed to send Windows notification"))
        logging.debug("Traceback: ", exc_info=True)
        return T("Failed to send Windows notification")
    return None
