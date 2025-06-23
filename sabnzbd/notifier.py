#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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


import sys
import os.path
import logging
import platform
import urllib.request
import urllib.parse
import http.client
import json
import apprise
from threading import Thread
from typing import Optional, Dict, Union

import sabnzbd
import sabnzbd.cfg
from sabnzbd.encoding import utob
from sabnzbd.filesystem import make_script_path
from sabnzbd.misc import build_and_run_command, int_conv
from sabnzbd.newsunpack import create_env

if sabnzbd.WINDOWS:
    try:
        from win32comext.shell import shell
        from windows_toasts import InteractableWindowsToaster, Toast, ToastActivatedEventArgs, ToastButton

        # Only Windows 10 and above are supported
        if int_conv(platform.release()) < 10:
            raise OSError

        # Set a custom AUMID to display the right icon, it is written to the registry by the installer
        shell.SetCurrentProcessExplicitAppUserModelID("SABnzbd")
        _HAVE_WINDOWS_TOASTER = True
    except Exception:
        # Sending toasts on non-supported platforms results in segfaults
        _HAVE_WINDOWS_TOASTER = False

try:
    import notify2

    _HAVE_NTFOSD = True

    # Check for working version, not all pynotify are the same
    # Without DISPLAY, notify2 cannot autolaunch a dbus-daemon
    if not hasattr(notify2, "init") or "DISPLAY" not in os.environ:
        _HAVE_NTFOSD = False
except Exception:
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
    "open_update_page": TT("Download"),
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


def get_targets(notification_type: str, section: str) -> Union[str, bool, None]:
    """Check target of `notification_type` in `section` if enabled is set"""
    try:
        if sabnzbd.config.get_config(section, "%s_target_%s_enable" % (section, notification_type))() > 0:
            if result := sabnzbd.config.get_config(section, "%s_target_%s" % (section, notification_type))():
                return result
            # Use Default
            return True
    except TypeError:
        logging.debug("Incorrect Notify option %s:%s_target_%s", section, section, notification_type)
        return False
    return False


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
    if sabnzbd.WINDOWS and sabnzbd.cfg.acenter_enable():
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

    # Apprise
    if sabnzbd.cfg.apprise_enable() and check_cat("apprise", job_cat):
        # it is possible to not define global apprise_urls() but only URLs for a specific type
        # such as complete or disk_full.
        if get_targets(notification_type, "apprise"):
            Thread(target=send_apprise, args=(title, msg, notification_type)).start()

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
    except Exception:
        _NTFOSD = False

    if _NTFOSD:
        logging.info("Send to NotifyOSD: %s / %s", title, message)
        try:
            note = notify2.Notification(title, message, icon)
            note.show()
        except Exception:
            # Apparently not implemented on this system
            logging.info(error)
            return error
        return None
    else:
        return error


def send_notification_center(title: str, msg: str, notification_type: str, actions: Optional[Dict[str, str]] = None):
    """Send message to macOS Notification Center.
    Only 1 button is possible on macOS!"""
    logging.debug("Sending macOS notification")
    try:
        subtitle = T(NOTIFICATION_TYPES.get(notification_type, "other"))
        button_text = button_action = None
        if actions:
            for action in actions:
                button_text = NOTIFICATION_ACTIONS[action]
                button_action = actions[action]
                break

        sabnzbd.MACOSTRAY.send_notification(title, subtitle, msg, button_text, button_action)
    except Exception:
        logging.info(T("Failed to send macOS notification"))
        logging.debug("Traceback: ", exc_info=True)
        return T("Failed to send macOS notification")


def send_prowl(title, msg, notification_type, force=False, test=None):
    """Send message to Prowl"""
    logging.debug("Sending Prowl notification")
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
        except Exception:
            logging.warning(T("Failed to send Prowl message"))
            logging.info("Traceback: ", exc_info=True)
            return T("Failed to send Prowl message")
    return ""


def send_apprise(title, msg, notification_type, force=False, test=None):
    """send apprise message"""
    logging.debug("Sending Apprise notification")
    if test:
        urls = test.get("apprise_urls")
    else:
        urls = sabnzbd.cfg.apprise_urls()

    # Notification mapper
    n_map = {
        # Startup/Shutdown
        "startup": apprise.common.NotifyType.INFO,
        # Pause/Resume
        "pause_resume": apprise.common.NotifyType.INFO,
        # Added NZB
        "download": apprise.common.NotifyType.INFO,
        # Post-processing started
        "pp": apprise.common.NotifyType.INFO,
        # Job finished
        "complete": apprise.common.NotifyType.SUCCESS,
        # Job failed
        "failed": apprise.common.NotifyType.FAILURE,
        # Warning
        "warning": apprise.common.NotifyType.WARNING,
        # Error
        "error": apprise.common.NotifyType.FAILURE,
        # Disk full
        "disk_full": apprise.common.NotifyType.WARNING,
        # Queue finished
        "queue_done": apprise.common.NotifyType.INFO,
        # User logged in
        "new_login": apprise.common.NotifyType.INFO,
        # Other Messages
        "other": apprise.common.NotifyType.INFO,
    }

    # Prepare our Asset Object
    asset = apprise.AppriseAsset(
        app_id="SABnzbd",
        app_desc="SABnzbd Notification",
        app_url="https://sabnzbd.org/",
        image_url_logo="https://sabnzbd.org/images/icons/apple-touch-icon-180x180-precomposed.png",
    )

    # Initialize our Apprise Instance
    apobj = apprise.Apprise(asset=asset)

    if not test:
        # Get a list of tags that are set to use the common list
        if target := get_targets(notification_type, "apprise"):
            if target is True:
                if not urls:
                    # Nothing to notify
                    logging.warning(T("Failed to send Apprise message - no URLs defined"))
                    return ""
                # Use default list
                apobj.add(urls)
            elif not apobj.add(target):
                # Target is string of URLs to over-ride with
                # Store our URL and assign our key
                logging.warning("%s - %s", notification_type, T("One or more Apprise URLs could not be loaded."))
        else:
            # Nothing to notify
            return ""
    else:
        # Use default list
        apobj.add(urls)

    try:
        # The below notifies anything added to our list
        if not apobj.notify(
            body=msg,
            title=title,
            notify_type=n_map[notification_type],
            body_format=apprise.NotifyFormat.TEXT,
        ):
            return T("Failed to send one or more Apprise Notifications")

    except Exception:
        logging.warning(T("Failed to send Apprise message"))
        logging.info("Traceback: ", exc_info=True)
        return T("Failed to send Apprise message")

    return ""


def send_pushover(title, msg, notification_type, force=False, test=None):
    """Send message to pushover"""
    logging.debug("Sending Pushover notification")
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
    except Exception:
        logging.warning(T("Failed to send pushover message"))
        logging.info("Traceback: ", exc_info=True)
        return T("Failed to send pushover message")


def send_pushbullet(title, msg, notification_type, force=False, test=None):
    """Send message to Pushbullet"""
    logging.debug("Sending Pushbullet notification")
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

    except Exception:
        logging.warning(T("Failed to send pushbullet message"))
        logging.info("Traceback: ", exc_info=True)
        return T("Failed to send pushbullet message")
    return ""


def send_nscript(title, msg, notification_type, force=False, test=None):
    """Run user's notification script"""
    logging.debug("Sending notification script notification")
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
            except Exception:
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
    """Send Windows notifications, either fancy with buttons (Windows 10+) or basic ones"""
    # Skip any notifications if ran as a Windows Service, it can result in crashes
    if sabnzbd.WIN_SERVICE:
        return None

    logging.debug("Sending Windows notification")
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
    except Exception:
        logging.info(T("Failed to send Windows notification"))
        logging.debug("Traceback: ", exc_info=True)
        return T("Failed to send Windows notification")
    return None
