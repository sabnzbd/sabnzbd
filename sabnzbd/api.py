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
sabnzbd.api - api
"""

import os
import logging
import re
import gc
import datetime
import time
import json
import cherrypy
import locale
from threading import Thread
from typing import List, Tuple

import sabnzbd
from sabnzbd.constants import (
    VALID_ARCHIVES,
    VALID_NZB_FILES,
    Status,
    FORCE_PRIORITY,
    NORMAL_PRIORITY,
    INTERFACE_PRIORITIES,
    KIBI,
    MEBI,
    GIGI,
)
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.skintext import SKIN_TEXT
from sabnzbd.utils.pathbrowser import folders_at_path
from sabnzbd.utils.getperformance import getcpu
from sabnzbd.misc import (
    loadavg,
    to_units,
    int_conv,
    time_format,
    cat_convert,
    create_https_certificates,
    calc_age,
    opts_to_pp,
)
from sabnzbd.filesystem import diskspace, get_ext, clip_path, remove_all, list_scripts
from sabnzbd.encoding import xml_name
from sabnzbd.utils.servertests import test_nntp_server_dict
from sabnzbd.getipaddress import localipv4, publicipv4, ipv6, addresslookup
from sabnzbd.database import build_history_info, unpack_history_info, HistoryDB
import sabnzbd.notifier
import sabnzbd.rss
import sabnzbd.emailer
import sabnzbd.sorting

##############################################################################
# API error messages
##############################################################################
_MSG_NO_VALUE = "expects one parameter"
_MSG_NO_VALUE2 = "expects two parameters"
_MSG_INT_VALUE = "expects integer value"
_MSG_NO_ITEM = "item does not exist"
_MSG_NOT_IMPLEMENTED = "not implemented"
_MSG_NO_FILE = "no file given"
_MSG_NO_PATH = "file does not exist"
_MSG_OUTPUT_FORMAT = "Format not supported"
_MSG_NO_SUCH_CONFIG = "Config item does not exist"
_MSG_CONFIG_LOCKED = "Configuration locked"
_MSG_BAD_SERVER_PARMS = "Incorrect server settings"


def api_handler(kwargs):
    """ API Dispatcher """
    if cfg.api_logging():
        # Was it proxy forwarded?
        xff = cherrypy.request.headers.get("X-Forwarded-For")
        if xff:
            logging.debug(
                "API-call from %s (X-Forwarded-For: %s) [%s] %s",
                cherrypy.request.remote.ip,
                xff,
                cherrypy.request.headers.get("User-Agent", "??"),
                kwargs,
            )
        else:
            logging.debug(
                "API-call from %s [%s] %s",
                cherrypy.request.remote.ip,
                cherrypy.request.headers.get("User-Agent", "??"),
                kwargs,
            )

    # Clean-up the arguments
    for vr in ("mode", "output", "name"):
        if vr in kwargs and isinstance(kwargs[vr], list):
            kwargs[vr] = kwargs[vr][0]

    mode = kwargs.get("mode", "")
    output = kwargs.get("output", "")
    name = kwargs.get("name", "")

    if mode not in ("version", "auth"):
        msg = sabnzbd.interface.check_apikey(kwargs)
        if msg:
            return report(output, msg)

    response = _api_table.get(mode, (_api_undefined, 2))[0](name, output, kwargs)
    return response


def _api_get_config(name, output, kwargs):
    """ API: accepts output, keyword, section """
    _, data = config.get_dconfig(kwargs.get("section"), kwargs.get("keyword"))
    return report(output, keyword="config", data=data)


def _api_set_config(name, output, kwargs):
    """ API: accepts output, keyword, section """
    if cfg.configlock():
        return report(output, _MSG_CONFIG_LOCKED)
    if kwargs.get("section") == "servers":
        kwargs["keyword"] = handle_server_api(output, kwargs)
    elif kwargs.get("section") == "rss":
        kwargs["keyword"] = handle_rss_api(output, kwargs)
    elif kwargs.get("section") == "categories":
        kwargs["keyword"] = handle_cat_api(output, kwargs)
    else:
        res = config.set_config(kwargs)
        if not res:
            return report(output, _MSG_NO_SUCH_CONFIG)
    config.save_config()
    res, data = config.get_dconfig(kwargs.get("section"), kwargs.get("keyword"))
    return report(output, keyword="config", data=data)


def _api_set_config_default(name, output, kwargs):
    """ API: Reset requested config variables back to defaults. Currently only for misc-section """
    if cfg.configlock():
        return report(output, _MSG_CONFIG_LOCKED)
    keywords = kwargs.get("keyword", [])
    if not isinstance(keywords, list):
        keywords = [keywords]
    for keyword in keywords:
        item = config.get_config("misc", keyword)
        if item:
            item.set(item.default())
    config.save_config()
    return report(output)


def _api_del_config(name, output, kwargs):
    """ API: accepts output, keyword, section """
    if cfg.configlock():
        return report(output, _MSG_CONFIG_LOCKED)
    if del_from_section(kwargs):
        return report(output)
    else:
        return report(output, _MSG_NOT_IMPLEMENTED)


def _api_queue(name, output, kwargs):
    """ API: Dispatcher for mode=queue """
    value = kwargs.get("value", "")
    return _api_queue_table.get(name, (_api_queue_default, 2))[0](output, value, kwargs)


def _api_queue_delete(output, value, kwargs):
    """ API: accepts output, value """
    if value.lower() == "all":
        removed = sabnzbd.NzbQueue.remove_all(kwargs.get("search"))
        return report(output, keyword="", data={"status": bool(removed), "nzo_ids": removed})
    elif value:
        items = value.split(",")
        delete_all_data = int_conv(kwargs.get("del_files"))
        removed = sabnzbd.NzbQueue.remove_multiple(items, delete_all_data=delete_all_data)
        return report(output, keyword="", data={"status": bool(removed), "nzo_ids": removed})
    else:
        return report(output, _MSG_NO_VALUE)


def _api_queue_delete_nzf(output, value, kwargs):
    """ API: accepts value(=nzo_id), value2(=nzf_id) """
    value2 = kwargs.get("value2")
    if value and value2:
        removed = sabnzbd.NzbQueue.remove_nzf(value, value2, force_delete=True)
        return report(output, keyword="", data={"status": bool(removed), "nzf_ids": removed})
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_rename(output, value, kwargs):
    """ API: accepts output, value(=old name), value2(=new name), value3(=password) """
    value2 = kwargs.get("value2")
    value3 = kwargs.get("value3")
    if value and value2:
        ret = sabnzbd.NzbQueue.change_name(value, value2, value3)
        return report(output, keyword="", data={"status": ret})
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_change_complete_action(output, value, kwargs):
    """ API: accepts output, value(=action) """
    sabnzbd.change_queue_complete_action(value)
    return report(output)


def _api_queue_purge(output, value, kwargs):
    """ API: accepts output """
    removed = sabnzbd.NzbQueue.remove_all(kwargs.get("search"))
    return report(output, keyword="", data={"status": bool(removed), "nzo_ids": removed})


def _api_queue_pause(output, value, kwargs):
    """ API: accepts output, value(=list of nzo_id) """
    if value:
        items = value.split(",")
        handled = sabnzbd.NzbQueue.pause_multiple_nzo(items)
    else:
        handled = False
    return report(output, keyword="", data={"status": bool(handled), "nzo_ids": handled})


def _api_queue_resume(output, value, kwargs):
    """ API: accepts output, value(=list of nzo_id) """
    if value:
        items = value.split(",")
        handled = sabnzbd.NzbQueue.resume_multiple_nzo(items)
    else:
        handled = False
    return report(output, keyword="", data={"status": bool(handled), "nzo_ids": handled})


def _api_queue_priority(output, value, kwargs):
    """ API: accepts output, value(=nzo_id), value2(=priority) """
    value2 = kwargs.get("value2")
    if value and value2:
        try:
            try:
                priority = int(value2)
            except:
                return report(output, _MSG_INT_VALUE)
            pos = sabnzbd.NzbQueue.set_priority(value, priority)
            # Returns the position in the queue, -1 is incorrect job-id
            return report(output, keyword="position", data=pos)
        except:
            return report(output, _MSG_NO_VALUE2)
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_sort(output, value, kwargs):
    """ API: accepts output, sort, dir """
    sort = kwargs.get("sort")
    direction = kwargs.get("dir", "")
    if sort:
        sabnzbd.NzbQueue.sort_queue(sort, direction)
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_default(output, value, kwargs):
    """ API: accepts output, sort, dir, start, limit """
    start = int_conv(kwargs.get("start"))
    limit = int_conv(kwargs.get("limit"))
    search = kwargs.get("search")
    nzo_ids = kwargs.get("nzo_ids")

    info, pnfo_list, bytespersec = build_queue(start=start, limit=limit, output=output, search=search, nzo_ids=nzo_ids)
    return report(output, keyword="queue", data=info)


def _api_queue_rating(output, value, kwargs):
    """ API: accepts output, value(=nzo_id), type, setting, detail """
    vote_map = {"up": sabnzbd.Rating.VOTE_UP, "down": sabnzbd.Rating.VOTE_DOWN}
    flag_map = {
        "spam": sabnzbd.Rating.FLAG_SPAM,
        "encrypted": sabnzbd.Rating.FLAG_ENCRYPTED,
        "expired": sabnzbd.Rating.FLAG_EXPIRED,
        "other": sabnzbd.Rating.FLAG_OTHER,
        "comment": sabnzbd.Rating.FLAG_COMMENT,
    }
    content_type = kwargs.get("type")
    setting = kwargs.get("setting")
    if value:
        try:
            video = audio = vote = flag = None
            if content_type == "video" and setting != "-":
                video = setting
            if content_type == "audio" and setting != "-":
                audio = setting
            if content_type == "vote":
                vote = vote_map[setting]
            if content_type == "flag":
                flag = flag_map[setting]
            if cfg.rating_enable():
                sabnzbd.Rating.update_user_rating(value, video, audio, vote, flag, kwargs.get("detail"))
            return report(output)
        except:
            return report(output, _MSG_BAD_SERVER_PARMS)
    else:
        return report(output, _MSG_NO_VALUE)


def _api_options(name, output, kwargs):
    """ API: accepts output """
    return options_list(output)


def _api_translate(name, output, kwargs):
    """ API: accepts output, value(=acronym) """
    return report(output, keyword="value", data=T(kwargs.get("value", "")))


def _api_addfile(name, output, kwargs):
    """ API: accepts name, output, pp, script, cat, priority, nzbname """
    # Normal upload will send the nzb in a kw arg called name or nzbfile
    if not name or isinstance(name, str):
        name = kwargs.get("nzbfile", None)
    if hasattr(name, "file") and hasattr(name, "filename") and name.filename:
        cat = kwargs.get("cat")
        xcat = kwargs.get("xcat")
        if not cat and xcat:
            # Indexer category, so do mapping
            cat = cat_convert(xcat)
        # Add the NZB-file
        res, nzo_ids = sabnzbd.add_nzbfile(
            name,
            pp=kwargs.get("pp"),
            script=kwargs.get("script"),
            cat=cat,
            priority=kwargs.get("priority"),
            nzbname=kwargs.get("nzbname"),
            password=kwargs.get("password"),
        )
        return report(output, keyword="", data={"status": res == 0, "nzo_ids": nzo_ids})
    else:
        return report(output, _MSG_NO_VALUE)


def _api_retry(name, output, kwargs):
    """ API: accepts name, output, value(=nzo_id), nzbfile(=optional NZB), password (optional) """
    value = kwargs.get("value")
    # Normal upload will send the nzb in a kw arg called nzbfile
    if name is None or isinstance(name, str):
        name = kwargs.get("nzbfile")
    password = kwargs.get("password")
    password = password[0] if isinstance(password, list) else password

    nzo_id = retry_job(value, name, password)
    if nzo_id:
        return report(output, keyword="", data={"status": True, "nzo_id": nzo_id})
    else:
        return report(output, _MSG_NO_ITEM)


def _api_cancel_pp(name, output, kwargs):
    """ API: accepts name, output, value(=nzo_id) """
    nzo_id = kwargs.get("value")
    if sabnzbd.PostProcessor.cancel_pp(nzo_id):
        return report(output, keyword="", data={"status": True, "nzo_id": nzo_id})
    else:
        return report(output, _MSG_NO_ITEM)


def _api_addlocalfile(name, output, kwargs):
    """ API: accepts name, output, pp, script, cat, priority, nzbname """
    if name:
        if os.path.exists(name):
            pp = kwargs.get("pp")
            script = kwargs.get("script")
            cat = kwargs.get("cat")
            xcat = kwargs.get("xcat")
            if not cat and xcat:
                # Indexer category, so do mapping
                cat = cat_convert(xcat)
            priority = kwargs.get("priority")
            nzbname = kwargs.get("nzbname")
            password = kwargs.get("password")

            if get_ext(name) in VALID_ARCHIVES + VALID_NZB_FILES:
                res, nzo_ids = sabnzbd.add_nzbfile(
                    name,
                    pp=pp,
                    script=script,
                    cat=cat,
                    priority=priority,
                    keep=True,
                    nzbname=nzbname,
                    password=password,
                )
                return report(output, keyword="", data={"status": res == 0, "nzo_ids": nzo_ids})
            else:
                logging.info('API-call addlocalfile: "%s" is not a supported file', name)
                return report(output, _MSG_NO_FILE)
        else:
            logging.info('API-call addlocalfile: file "%s" not found', name)
            return report(output, _MSG_NO_PATH)
    else:
        logging.info("API-call addlocalfile: no file name given")
        return report(output, _MSG_NO_VALUE)


def _api_switch(name, output, kwargs):
    """ API: accepts output, value(=first id), value2(=second id) """
    value = kwargs.get("value")
    value2 = kwargs.get("value2")
    if value and value2:
        pos, prio = sabnzbd.NzbQueue.switch(value, value2)
        # Returns the new position and new priority (if different)
        return report(output, keyword="result", data={"position": pos, "priority": prio})
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_change_cat(name, output, kwargs):
    """ API: accepts output, value(=nzo_id), value2(=category) """
    value = kwargs.get("value")
    value2 = kwargs.get("value2")
    if value and value2:
        nzo_id = value
        cat = value2
        if cat == "None":
            cat = None
        result = sabnzbd.NzbQueue.change_cat(nzo_id, cat)
        return report(output, keyword="status", data=bool(result > 0))
    else:
        return report(output, _MSG_NO_VALUE)


def _api_change_script(name, output, kwargs):
    """ API: accepts output, value(=nzo_id), value2(=script) """
    value = kwargs.get("value")
    value2 = kwargs.get("value2")
    if value and value2:
        nzo_id = value
        script = value2
        if script.lower() == "none":
            script = None
        result = sabnzbd.NzbQueue.change_script(nzo_id, script)
        return report(output, keyword="status", data=bool(result > 0))
    else:
        return report(output, _MSG_NO_VALUE)


def _api_change_opts(name, output, kwargs):
    """ API: accepts output, value(=nzo_id), value2(=pp) """
    value = kwargs.get("value")
    value2 = kwargs.get("value2")
    result = 0
    if value and value2 and value2.isdigit():
        result = sabnzbd.NzbQueue.change_opts(value, int(value2))
    return report(output, keyword="status", data=bool(result > 0))


def _api_fullstatus(name, output, kwargs):
    """ API: full history status"""
    status = build_status(skip_dashboard=kwargs.get("skip_dashboard", 1), output=output)
    return report(output, keyword="status", data=status)


def _api_history(name, output, kwargs):
    """ API: accepts output, value(=nzo_id), start, limit, search, nzo_ids """
    value = kwargs.get("value", "")
    start = int_conv(kwargs.get("start"))
    limit = int_conv(kwargs.get("limit"))
    last_history_update = int_conv(kwargs.get("last_history_update", 0))
    search = kwargs.get("search")
    failed_only = int_conv(kwargs.get("failed_only"))
    categories = kwargs.get("category")
    nzo_ids = kwargs.get("nzo_ids")

    # Do we need to send anything?
    if last_history_update == sabnzbd.LAST_HISTORY_UPDATE:
        return report(output, keyword="history", data=False)

    if categories and not isinstance(categories, list):
        categories = [categories]

    if not limit:
        limit = cfg.history_limit()

    if name == "delete":
        special = value.lower()
        del_files = bool(int_conv(kwargs.get("del_files")))
        if special in ("all", "failed", "completed"):
            history_db = sabnzbd.get_db_connection()
            if special in ("all", "failed"):
                if del_files:
                    del_job_files(history_db.get_failed_paths(search))
                history_db.remove_failed(search)
            if special in ("all", "completed"):
                history_db.remove_completed(search)
            sabnzbd.history_updated()
            return report(output)
        elif value:
            jobs = value.split(",")
            for job in jobs:
                del_hist_job(job, del_files)
            sabnzbd.history_updated()
            return report(output)
        else:
            return report(output, _MSG_NO_VALUE)
    elif not name:
        history = {}
        grand, month, week, day = sabnzbd.BPSMeter.get_sums()
        history["total_size"], history["month_size"], history["week_size"], history["day_size"] = (
            to_units(grand),
            to_units(month),
            to_units(week),
            to_units(day),
        )
        history["slots"], fetched_items, history["noofslots"] = build_history(
            start=start, limit=limit, search=search, failed_only=failed_only, categories=categories, nzo_ids=nzo_ids
        )
        history["last_history_update"] = sabnzbd.LAST_HISTORY_UPDATE
        history["version"] = sabnzbd.__version__
        return report(output, keyword="history", data=history)
    else:
        return report(output, _MSG_NOT_IMPLEMENTED)


def _api_get_files(name, output, kwargs):
    """ API: accepts output, value(=nzo_id) """
    value = kwargs.get("value")
    if value:
        return report(output, keyword="files", data=build_file_list(value))
    else:
        return report(output, _MSG_NO_VALUE)


def _api_addurl(name, output, kwargs):
    """ API: accepts name, output, pp, script, cat, priority, nzbname """
    pp = kwargs.get("pp")
    script = kwargs.get("script")
    cat = kwargs.get("cat")
    priority = kwargs.get("priority")
    nzbname = kwargs.get("nzbname", "")
    password = kwargs.get("password", "")

    if name:
        nzo_id = sabnzbd.add_url(name, pp, script, cat, priority, nzbname, password)
        # Reporting a list of NZO's, for compatibility with other add-methods
        return report(output, keyword="", data={"status": True, "nzo_ids": [nzo_id]})
    else:
        logging.info("API-call addurl: no URLs recieved")
        return report(output, _MSG_NO_VALUE)


def _api_pause(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.Scheduler.plan_resume(0)
    sabnzbd.Downloader.pause()
    return report(output)


def _api_resume(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.Scheduler.plan_resume(0)
    sabnzbd.unpause_all()
    return report(output)


def _api_shutdown(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.shutdown_program()
    return report(output)


def _api_warnings(name, output, kwargs):
    """ API: accepts name, output """
    if name == "clear":
        return report(output, keyword="warnings", data=sabnzbd.GUIHANDLER.clear())
    elif name == "show":
        return report(output, keyword="warnings", data=sabnzbd.GUIHANDLER.content())
    elif name:
        return report(output, _MSG_NOT_IMPLEMENTED)
    return report(output, keyword="warnings", data=sabnzbd.GUIHANDLER.content())


def _api_get_cats(name, output, kwargs):
    """ API: accepts output """
    return report(output, keyword="categories", data=list_cats(False))


def _api_get_scripts(name, output, kwargs):
    """ API: accepts output """
    return report(output, keyword="scripts", data=list_scripts())


def _api_version(name, output, kwargs):
    """ API: accepts output """
    return report(output, keyword="version", data=sabnzbd.__version__)


def _api_auth(name, output, kwargs):
    """ API: accepts output """
    auth = "None"
    if not cfg.disable_key():
        auth = "badkey"
        key = kwargs.get("key", "")
        if not key:
            auth = "apikey"
        else:
            if key == cfg.nzb_key():
                auth = "nzbkey"
            if key == cfg.api_key():
                auth = "apikey"
    elif cfg.username() and cfg.password():
        auth = "login"
    return report(output, keyword="auth", data=auth)


def _api_restart(name, output, kwargs):
    """ API: accepts output """
    logging.info("Restart requested by API")
    # Do the shutdown async to still send goodbye to browser
    Thread(target=sabnzbd.trigger_restart, kwargs={"timeout": 1}).start()
    return report(output)


def _api_restart_repair(name, output, kwargs):
    """ API: accepts output """
    logging.info("Queue repair requested by API")
    sabnzbd.request_repair()
    # Do the shutdown async to still send goodbye to browser
    Thread(target=sabnzbd.trigger_restart, kwargs={"timeout": 1}).start()
    return report(output)


def _api_disconnect(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.Downloader.disconnect()
    return report(output)


def _api_osx_icon(name, output, kwargs):
    """ API: accepts output, value """
    value = kwargs.get("value", "1").strip()
    cfg.osx_menu.set(value != "0")
    return report(output)


def _api_rescan(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.NzbQueue.scan_jobs(all_jobs=False, action=True)
    return report(output)


def _api_eval_sort(name, output, kwargs):
    """ API: evaluate sorting expression """
    name = kwargs.get("name", "")
    value = kwargs.get("value", "")
    title = kwargs.get("title")
    multipart = kwargs.get("movieextra", "")
    path = sabnzbd.sorting.eval_sort(value, title, name, multipart)
    if path is None:
        return report(output, _MSG_NOT_IMPLEMENTED)
    else:
        return report(output, keyword="result", data=path)


def _api_watched_now(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.DirScanner.scan()
    return report(output)


def _api_resume_pp(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.PostProcessor.paused = False
    return report(output)


def _api_pause_pp(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.PostProcessor.paused = True
    return report(output)


def _api_rss_now(name, output, kwargs):
    """ API: accepts output """
    # Run RSS scan async, because it can take a long time
    sabnzbd.Scheduler.force_rss()
    return report(output)


def _api_retry_all(name, output, kwargs):
    """ API: Retry all failed items in History """
    return report(output, keyword="status", data=retry_all_jobs())


def _api_reset_quota(name, output, kwargs):
    """ Reset quota left """
    sabnzbd.BPSMeter.reset_quota(force=True)
    return report(output)


def _api_test_email(name, output, kwargs):
    """ API: send a test email, return result """
    logging.info("Sending test email")
    pack = {"download": ["action 1", "action 2"], "unpack": ["action 1", "action 2"]}
    res = sabnzbd.emailer.endjob(
        "I had a d\xe8ja vu",
        "unknown",
        True,
        os.path.normpath(os.path.join(cfg.complete_dir.get_path(), "/unknown/I had a d\xe8ja vu")),
        123 * MEBI,
        None,
        pack,
        "my_script",
        "Line 1\nLine 2\nLine 3\nd\xe8ja vu\n",
        0,
        test=kwargs,
    )
    if res == T("Email succeeded"):
        return report(output)
    return report(output, error=res)


def _api_test_windows(name, output, kwargs):
    """ API: send a test to Windows, return result """
    logging.info("Sending test notification")
    res = sabnzbd.notifier.send_windows("SABnzbd", T("Test Notification"), "other")
    return report(output, error=res)


def _api_test_notif(name, output, kwargs):
    """ API: send a test to Notification Center, return result """
    logging.info("Sending test notification")
    res = sabnzbd.notifier.send_notification_center("SABnzbd", T("Test Notification"), "other")
    return report(output, error=res)


def _api_test_osd(name, output, kwargs):
    """ API: send a test OSD notification, return result """
    logging.info("Sending OSD notification")
    res = sabnzbd.notifier.send_notify_osd("SABnzbd", T("Test Notification"))
    return report(output, error=res)


def _api_test_prowl(name, output, kwargs):
    """ API: send a test Prowl notification, return result """
    logging.info("Sending Prowl notification")
    res = sabnzbd.notifier.send_prowl("SABnzbd", T("Test Notification"), "other", force=True, test=kwargs)
    return report(output, error=res)


def _api_test_pushover(name, output, kwargs):
    """ API: send a test Pushover notification, return result """
    logging.info("Sending Pushover notification")
    res = sabnzbd.notifier.send_pushover("SABnzbd", T("Test Notification"), "other", force=True, test=kwargs)
    return report(output, error=res)


def _api_test_pushbullet(name, output, kwargs):
    """ API: send a test Pushbullet notification, return result """
    logging.info("Sending Pushbullet notification")
    res = sabnzbd.notifier.send_pushbullet("SABnzbd", T("Test Notification"), "other", force=True, test=kwargs)
    return report(output, error=res)


def _api_test_nscript(name, output, kwargs):
    """ API: execute a test notification script, return result """
    logging.info("Executing notification script")
    res = sabnzbd.notifier.send_nscript("SABnzbd", T("Test Notification"), "other", force=True, test=kwargs)
    return report(output, error=res)


def _api_undefined(name, output, kwargs):
    """ API: accepts output """
    return report(output, _MSG_NOT_IMPLEMENTED)


def _api_browse(name, output, kwargs):
    """ Return tree of local path """
    compact = kwargs.get("compact")

    if compact and compact == "1":
        name = kwargs.get("term", "")
        paths = [entry["path"] for entry in folders_at_path(os.path.dirname(name)) if "path" in entry]
        return report(output, keyword="", data=paths)
    else:
        show_hidden = kwargs.get("show_hidden_folders")
        paths = folders_at_path(name, True, show_hidden)
        return report(output, keyword="paths", data=paths)


def _api_config(name, output, kwargs):
    """ API: Dispatcher for "config" """
    if cfg.configlock():
        return report(output, _MSG_CONFIG_LOCKED)
    return _api_config_table.get(name, (_api_config_undefined, 2))[0](output, kwargs)


def _api_config_speedlimit(output, kwargs):
    """ API: accepts output, value(=speed) """
    value = kwargs.get("value")
    if not value:
        value = "0"
    sabnzbd.Downloader.limit_speed(value)
    return report(output)


def _api_config_get_speedlimit(output, kwargs):
    """ API: accepts output """
    return report(output, keyword="speedlimit", data=sabnzbd.Downloader.get_limit())


def _api_config_set_colorscheme(output, kwargs):
    """ API: accepts output"""
    value = kwargs.get("value")
    if value:
        cfg.web_color.set(value)
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE)


def _api_config_set_pause(output, kwargs):
    """ API: accepts output, value(=pause interval) """
    value = kwargs.get("value")
    sabnzbd.Scheduler.plan_resume(int_conv(value))
    return report(output)


def _api_config_set_apikey(output, kwargs):
    """ API: accepts output """
    cfg.api_key.set(config.create_api_key())
    config.save_config()
    return report(output, keyword="apikey", data=cfg.api_key())


def _api_config_set_nzbkey(output, kwargs):
    """ API: accepts output """
    cfg.nzb_key.set(config.create_api_key())
    config.save_config()
    return report(output, keyword="nzbkey", data=cfg.nzb_key())


def _api_config_regenerate_certs(output, kwargs):
    # Make sure we only over-write default locations
    result = False
    if (
        sabnzbd.cfg.https_cert() is sabnzbd.cfg.https_cert.default()
        and sabnzbd.cfg.https_key() is sabnzbd.cfg.https_key.default()
    ):
        https_cert = sabnzbd.cfg.https_cert.get_path()
        https_key = sabnzbd.cfg.https_key.get_path()
        result = create_https_certificates(https_cert, https_key)
        sabnzbd.RESTART_REQ = True
    return report(output, data=result)


def _api_config_test_server(output, kwargs):
    """ API: accepts output, server-params """
    result, msg = test_nntp_server_dict(kwargs)
    response = {"result": result, "message": msg}
    if output:
        return report(output, data=response)
    else:
        return msg


def _api_config_undefined(output, kwargs):
    """ API: accepts output """
    return report(output, _MSG_NOT_IMPLEMENTED)


def _api_server_stats(name, output, kwargs):
    """ API: accepts output """
    sum_t, sum_m, sum_w, sum_d = sabnzbd.BPSMeter.get_sums()
    stats = {"total": sum_t, "month": sum_m, "week": sum_w, "day": sum_d, "servers": {}}

    for svr in config.get_servers():
        t, m, w, d, daily, articles_tried, articles_success = sabnzbd.BPSMeter.amounts(svr)
        stats["servers"][svr] = {
            "total": t,
            "month": m,
            "week": w,
            "day": d,
            "daily": daily,
            "articles_tried": articles_tried,
            "articles_success": articles_success,
        }

    return report(output, keyword="", data=stats)


def _api_gc_stats(name, output, kwargs):
    """Function only intended for internal testing of the memory handling"""
    # Collect before we check
    gc.collect()
    # We cannot create any lists/dicts, as they would create a reference
    return report(output, data=[str(obj) for obj in gc.get_objects() if isinstance(obj, sabnzbd.nzbstuff.TryList)])


##############################################################################
_api_table = {
    "server_stats": (_api_server_stats, 2),
    "get_config": (_api_get_config, 3),
    "set_config": (_api_set_config, 3),
    "set_config_default": (_api_set_config_default, 3),
    "del_config": (_api_del_config, 3),
    "queue": (_api_queue, 2),
    "options": (_api_options, 2),
    "translate": (_api_translate, 2),
    "addfile": (_api_addfile, 1),
    "retry": (_api_retry, 2),
    "cancel_pp": (_api_cancel_pp, 2),
    "addlocalfile": (_api_addlocalfile, 1),
    "switch": (_api_switch, 2),
    "change_cat": (_api_change_cat, 2),
    "change_script": (_api_change_script, 2),
    "change_opts": (_api_change_opts, 2),
    "fullstatus": (_api_fullstatus, 2),
    "history": (_api_history, 2),
    "get_files": (_api_get_files, 2),
    "addurl": (_api_addurl, 1),
    "addid": (_api_addurl, 1),
    "pause": (_api_pause, 2),
    "resume": (_api_resume, 2),
    "shutdown": (_api_shutdown, 3),
    "warnings": (_api_warnings, 2),
    "config": (_api_config, 2),
    "get_cats": (_api_get_cats, 2),
    "get_scripts": (_api_get_scripts, 2),
    "version": (_api_version, 1),
    "auth": (_api_auth, 1),
    "restart": (_api_restart, 3),
    "restart_repair": (_api_restart_repair, 2),
    "disconnect": (_api_disconnect, 2),
    "osx_icon": (_api_osx_icon, 3),
    "gc_stats": (_api_gc_stats, 3),
    "rescan": (_api_rescan, 2),
    "eval_sort": (_api_eval_sort, 2),
    "watched_now": (_api_watched_now, 2),
    "resume_pp": (_api_resume_pp, 2),
    "pause_pp": (_api_pause_pp, 2),
    "rss_now": (_api_rss_now, 2),
    "browse": (_api_browse, 2),
    "retry_all": (_api_retry_all, 2),
    "reset_quota": (_api_reset_quota, 2),
    "test_email": (_api_test_email, 2),
    "test_windows": (_api_test_windows, 2),
    "test_notif": (_api_test_notif, 2),
    "test_osd": (_api_test_osd, 2),
    "test_pushover": (_api_test_pushover, 2),
    "test_pushbullet": (_api_test_pushbullet, 2),
    "test_prowl": (_api_test_prowl, 2),
    "test_nscript": (_api_test_nscript, 2),
}

_api_queue_table = {
    "delete": (_api_queue_delete, 2),
    "delete_nzf": (_api_queue_delete_nzf, 2),
    "rename": (_api_queue_rename, 2),
    "change_complete_action": (_api_queue_change_complete_action, 2),
    "purge": (_api_queue_purge, 2),
    "pause": (_api_queue_pause, 2),
    "resume": (_api_queue_resume, 2),
    "priority": (_api_queue_priority, 2),
    "sort": (_api_queue_sort, 2),
    "rating": (_api_queue_rating, 2),
}

_api_config_table = {
    "speedlimit": (_api_config_speedlimit, 2),
    "set_speedlimit": (_api_config_speedlimit, 2),
    "get_speedlimit": (_api_config_get_speedlimit, 2),
    "set_colorscheme": (_api_config_set_colorscheme, 2),
    "set_pause": (_api_config_set_pause, 2),
    "set_apikey": (_api_config_set_apikey, 3),
    "set_nzbkey": (_api_config_set_nzbkey, 3),
    "regenerate_certs": (_api_config_regenerate_certs, 3),
    "test_server": (_api_config_test_server, 2),
}


def api_level(cmd, name):
    """ Return access level required for this API call """
    if cmd in _api_table:
        return _api_table[cmd][1]
    if name == "queue" and cmd in _api_queue_table:
        return _api_queue_table[cmd][1]
    if name == "config" and cmd in _api_config_table:
        return _api_config_table[cmd][1]
    return 4


def report(output, error=None, keyword="value", data=None):
    """Report message in json, xml or plain text
    If error is set, only an status/error report is made.
    If no error and no data, only a status report is made.
    Else, a data report is made (optional 'keyword' for outer XML section).
    """
    if output == "json":
        content = "application/json;charset=UTF-8"
        if error:
            info = {"status": False, "error": error}
        elif data is None:
            info = {"status": True}
        else:
            if hasattr(data, "__iter__") and not keyword:
                info = data
            else:
                info = {keyword: data}
        response = json.dumps(info).encode("utf-8")

    elif output == "xml":
        if not keyword:
            # xml always needs an outer keyword, even when json doesn't
            keyword = "result"
        content = "text/xml"
        xmlmaker = xml_factory()
        if error:
            status_str = xmlmaker.run("result", {"status": False, "error": error})
        elif data is None:
            status_str = xmlmaker.run("result", {"status": True})
        else:
            status_str = xmlmaker.run(keyword, data)
        response = '<?xml version="1.0" encoding="UTF-8" ?>\n%s\n' % status_str

    else:
        content = "text/plain"
        if error:
            response = "error: %s\n" % error
        elif not data:
            response = "ok\n"
        else:
            response = "%s\n" % str(data)

    cherrypy.response.headers["Content-Type"] = content
    cherrypy.response.headers["Pragma"] = "no-cache"
    return response


class xml_factory:
    """Recursive xml string maker. Feed it a mixed tuple/dict/item object and will output into an xml string
    Current limitations:
        In Two tiered lists hard-coded name of "item": <cat_list><item> </item></cat_list>
        In Three tiered lists hard-coded name of "slot": <tier1><slot><tier2> </tier2></slot></tier1>
    """

    def __init__(self):
        self.__text = ""

    def _tuple(self, keyw, lst):
        text = []
        for item in lst:
            text.append(self.run(keyw, item))
        return "".join(text)

    def _dict(self, keyw, lst):
        text = []
        for key in lst.keys():
            text.append(self.run(key, lst[key]))
        if keyw:
            return "<%s>%s</%s>\n" % (keyw, "".join(text), keyw)
        else:
            return ""

    def _list(self, keyw, lst):
        text = []
        for cat in lst:
            if isinstance(cat, dict):
                text.append(self._dict(plural_to_single(keyw, "slot"), cat))
            elif isinstance(cat, list):
                text.append(self._list(plural_to_single(keyw, "list"), cat))
            elif isinstance(cat, tuple):
                text.append(self._tuple(plural_to_single(keyw, "tuple"), cat))
            else:
                if not isinstance(cat, str):
                    cat = str(cat)
                name = plural_to_single(keyw, "item")
                text.append("<%s>%s</%s>\n" % (name, xml_name(cat), name))
        if keyw:
            return "<%s>%s</%s>\n" % (keyw, "".join(text), keyw)
        else:
            return ""

    def run(self, keyw, lst):
        if isinstance(lst, dict):
            text = self._dict(keyw, lst)
        elif isinstance(lst, list):
            text = self._list(keyw, lst)
        elif isinstance(lst, tuple):
            text = self._tuple(keyw, lst)
        elif keyw:
            text = "<%s>%s</%s>\n" % (keyw, xml_name(lst), keyw)
        else:
            text = ""
        return text


def handle_server_api(output, kwargs):
    """ Special handler for API-call 'set_config' [servers] """
    name = kwargs.get("keyword")
    if not name:
        name = kwargs.get("name")

    if name:
        server = config.get_config("servers", name)
        if server:
            server.set_dict(kwargs)
            old_name = name
        else:
            config.ConfigServer(name, kwargs)
            old_name = None
        sabnzbd.Downloader.update_server(old_name, name)
    return name


def handle_rss_api(output, kwargs):
    """ Special handler for API-call 'set_config' [rss] """
    name = kwargs.get("keyword")
    if not name:
        name = kwargs.get("name")
    if not name:
        return None

    feed = config.get_config("rss", name)
    if feed:
        feed.set_dict(kwargs)
    else:
        config.ConfigRSS(name, kwargs)

    action = kwargs.get("filter_action")
    if action in ("add", "update"):
        # Use the general function, but catch the redirect-raise
        try:
            kwargs["feed"] = name
            sabnzbd.interface.ConfigRss("/").internal_upd_rss_filter(**kwargs)
        except cherrypy.HTTPRedirect:
            pass

    elif action == "delete":
        # Use the general function, but catch the redirect-raise
        try:
            kwargs["feed"] = name
            sabnzbd.interface.ConfigRss("/").internal_del_rss_filter(**kwargs)
        except cherrypy.HTTPRedirect:
            pass

    return name


def handle_cat_api(output, kwargs):
    """ Special handler for API-call 'set_config' [categories] """
    name = kwargs.get("keyword")
    if not name:
        name = kwargs.get("name")
    if not name:
        return None
    name = name.lower()

    cat = config.get_config("categories", name)
    if cat:
        cat.set_dict(kwargs)
    else:
        config.ConfigCat(name, kwargs)
    return name


def build_status(skip_dashboard=False, output=None):
    # build up header full of basic information
    info = build_header(trans_functions=not output)

    info["logfile"] = sabnzbd.LOGFILE
    info["weblogfile"] = sabnzbd.WEBLOGFILE
    info["loglevel"] = str(cfg.log_level())
    info["folders"] = sabnzbd.NzbQueue.scan_jobs(all_jobs=False, action=False)
    info["configfn"] = config.get_filename()

    # Dashboard: Speed of System
    info["cpumodel"] = getcpu()
    info["pystone"] = sabnzbd.PYSTONE_SCORE

    # Dashboard: Speed of Download directory:
    info["downloaddir"] = cfg.download_dir.get_clipped_path()
    info["downloaddirspeed"] = sabnzbd.DOWNLOAD_DIR_SPEED

    # Dashboard: Speed of Complete directory:
    info["completedir"] = cfg.complete_dir.get_clipped_path()
    info["completedirspeed"] = sabnzbd.COMPLETE_DIR_SPEED

    # Dashboard: Measured download-speed
    info["internetbandwidth"] = sabnzbd.INTERNET_BANDWIDTH

    # Dashboard: Connection information
    if not int_conv(skip_dashboard):
        info["localipv4"] = localipv4()
        info["publicipv4"] = publicipv4()
        info["ipv6"] = ipv6()
        # Dashboard: DNS-check
        try:
            addresslookup(cfg.selftest_host())
            info["dnslookup"] = "OK"
        except:
            info["dnslookup"] = None

    info["servers"] = []
    servers = sorted(sabnzbd.Downloader.servers[:], key=lambda svr: "%02d%s" % (svr.priority, svr.displayname.lower()))
    for server in servers:
        serverconnections = []
        connected = 0

        for nw in server.idle_threads[:]:
            if nw.connected:
                connected += 1

        for nw in server.busy_threads[:]:
            article = nw.article
            art_name = ""
            nzf_name = ""
            nzo_name = ""

            if article:
                nzf = article.nzf
                nzo = nzf.nzo

                art_name = article.article
                # filename field is not always present
                try:
                    nzf_name = nzf.filename
                except:  # attribute error
                    nzf_name = nzf.subject
                nzo_name = nzo.final_name

            # For the templates or for JSON
            if output:
                thread_info = {"thrdnum": nw.thrdnum, "art_name": art_name, "nzf_name": nzf_name, "nzo_name": nzo_name}
                serverconnections.append(thread_info)
            else:
                serverconnections.append((nw.thrdnum, art_name, nzf_name, nzo_name))

            if nw.connected:
                connected += 1

        if server.warning and not (connected or server.errormsg):
            connected = server.warning

        if server.request and not server.info:
            connected = T("&nbsp;Resolving address").replace("&nbsp;", "")

        # For the templates or for JSON
        if output:
            server_info = {
                "servername": server.displayname,
                "serveractiveconn": connected,
                "servertotalconn": server.threads,
                "serverconnections": serverconnections,
                "serverssl": server.ssl,
                "serversslinfo": server.ssl_info,
                "serveractive": server.active,
                "servererror": server.errormsg,
                "serverpriority": server.priority,
                "serveroptional": server.optional,
                "serverbps": to_units(sabnzbd.BPSMeter.server_bps.get(server.id, 0)),
            }
            info["servers"].append(server_info)
        else:
            info["servers"].append(
                (
                    server.displayname,
                    "",
                    connected,
                    serverconnections,
                    server.ssl,
                    server.active,
                    server.errormsg,
                    server.priority,
                    server.optional,
                )
            )

    info["warnings"] = sabnzbd.GUIHANDLER.content()

    return info


def build_queue(start=0, limit=0, trans=False, output=None, search=None, nzo_ids=None):
    # build up header full of basic information
    info, pnfo_list, bytespersec, q_size, bytes_left_previous_page = build_queue_header(
        search=search, start=start, limit=limit, output=output, nzo_ids=nzo_ids
    )

    datestart = datetime.datetime.now()
    limit = int_conv(limit)
    start = int_conv(start)

    info["refresh_rate"] = str(cfg.refresh_rate()) if cfg.refresh_rate() > 0 else ""
    info["interface_settings"] = cfg.interface_settings()
    info["scripts"] = list_scripts()
    info["categories"] = list_cats(output is None)
    info["rating_enable"] = bool(cfg.rating_enable())
    info["noofslots"] = q_size
    info["start"] = start
    info["limit"] = limit
    info["finish"] = info["start"] + info["limit"]

    n = start
    running_bytes = bytes_left_previous_page
    slotinfo = []
    for pnfo in pnfo_list:
        nzo_id = pnfo.nzo_id
        bytesleft = pnfo.bytes_left
        bytes_total = pnfo.bytes
        average_date = pnfo.avg_date
        is_propagating = (pnfo.avg_stamp + float(cfg.propagation_delay() * 60)) > time.time()
        status = pnfo.status
        priority = pnfo.priority
        mbleft = bytesleft / MEBI
        mb = bytes_total / MEBI

        slot = {}
        slot["index"] = n
        slot["nzo_id"] = str(nzo_id)
        slot["unpackopts"] = str(opts_to_pp(pnfo.repair, pnfo.unpack, pnfo.delete))
        slot["priority"] = INTERFACE_PRIORITIES.get(priority, NORMAL_PRIORITY)
        slot["script"] = pnfo.script if pnfo.script else "None"
        slot["filename"] = pnfo.filename
        slot["labels"] = pnfo.labels
        slot["password"] = pnfo.password if pnfo.password else ""
        slot["cat"] = pnfo.category if pnfo.category else "None"
        slot["mbleft"] = "%.2f" % mbleft
        slot["mb"] = "%.2f" % mb
        slot["size"] = to_units(bytes_total, "B")
        slot["sizeleft"] = to_units(bytesleft, "B")
        slot["percentage"] = "%s" % (int(((mb - mbleft) / mb) * 100)) if mb != mbleft else "0"
        slot["mbmissing"] = "%.2f" % (pnfo.bytes_missing / MEBI)
        slot["direct_unpack"] = pnfo.direct_unpack
        if not output:
            slot["mb_fmt"] = locale.format_string("%d", int(mb), True)
            slot["mbdone_fmt"] = locale.format_string("%d", int(mb - mbleft), True)

        if not sabnzbd.Downloader.paused and status not in (Status.PAUSED, Status.FETCHING, Status.GRABBING):
            if is_propagating:
                slot["status"] = Status.PROP
            elif status == Status.CHECKING:
                slot["status"] = Status.CHECKING
            else:
                slot["status"] = Status.DOWNLOADING
        else:
            # Ensure compatibility of API status
            if status == Status.DELETED or priority == FORCE_PRIORITY:
                status = Status.DOWNLOADING
            slot["status"] = "%s" % status

        if (
            sabnzbd.Downloader.paused
            or sabnzbd.Downloader.paused_for_postproc
            or is_propagating
            or status not in (Status.DOWNLOADING, Status.FETCHING, Status.QUEUED)
        ) and priority != FORCE_PRIORITY:
            slot["timeleft"] = "0:00:00"
            slot["eta"] = "unknown"
        else:
            running_bytes += bytesleft
            slot["timeleft"] = calc_timeleft(running_bytes, bytespersec)
            try:
                datestart = datestart + datetime.timedelta(seconds=bytesleft / bytespersec)
                # new eta format: 16:00 Fri 07 Feb
                slot["eta"] = datestart.strftime(time_format("%H:%M %a %d %b"))
            except:
                datestart = datetime.datetime.now()
                slot["eta"] = "unknown"

        # Do not show age when it's not known
        if average_date.year < 2000:
            slot["avg_age"] = "-"
        else:
            slot["avg_age"] = calc_age(average_date, bool(trans))

        rating = sabnzbd.Rating.get_rating_by_nzo(nzo_id)
        slot["has_rating"] = rating is not None
        if rating:
            slot["rating_avg_video"] = rating.avg_video
            slot["rating_avg_audio"] = rating.avg_audio

        slotinfo.append(slot)
        n += 1

    if slotinfo:
        info["slots"] = slotinfo
    else:
        info["slots"] = []

    return info, pnfo_list, bytespersec


def fast_queue() -> Tuple[bool, int, float, str]:
    """ Return paused, bytes_left, bpsnow, time_left """
    bytes_left = sabnzbd.sabnzbd.NzbQueue.remaining()
    paused = sabnzbd.Downloader.paused
    bpsnow = sabnzbd.BPSMeter.bps
    time_left = calc_timeleft(bytes_left, bpsnow)
    return paused, bytes_left, bpsnow, time_left


def build_file_list(nzo_id: str):
    """Build file lists for specified job"""
    jobs = []
    nzo = sabnzbd.sabnzbd.NzbQueue.get_nzo(nzo_id)
    if nzo:
        pnfo = nzo.gather_info(full=True)

        finished_files = pnfo.finished_files
        active_files = pnfo.active_files
        queued_files = pnfo.queued_files

        for nzf in finished_files:
            jobs.append(
                {
                    "filename": nzf.filename if nzf.filename else nzf.subject,
                    "mbleft": "%.2f" % (nzf.bytes_left / MEBI),
                    "mb": "%.2f" % (nzf.bytes / MEBI),
                    "bytes": "%.2f" % nzf.bytes,
                    "age": calc_age(nzf.date),
                    "nzf_id": nzf.nzf_id,
                    "status": "finished",
                }
            )

        for nzf in active_files:
            jobs.append(
                {
                    "filename": nzf.filename if nzf.filename else nzf.subject,
                    "mbleft": "%.2f" % (nzf.bytes_left / MEBI),
                    "mb": "%.2f" % (nzf.bytes / MEBI),
                    "bytes": "%.2f" % nzf.bytes,
                    "age": calc_age(nzf.date),
                    "nzf_id": nzf.nzf_id,
                    "status": "active",
                }
            )

        for nzf in queued_files:
            jobs.append(
                {
                    "filename": nzf.filename if nzf.filename else nzf.subject,
                    "set": nzf.setname,
                    "mbleft": "%.2f" % (nzf.bytes_left / MEBI),
                    "mb": "%.2f" % (nzf.bytes / MEBI),
                    "bytes": "%.2f" % nzf.bytes,
                    "age": calc_age(nzf.date),
                    "nzf_id": nzf.nzf_id,
                    "status": "queued",
                }
            )

    return jobs


def options_list(output):
    return report(
        output,
        keyword="options",
        data={
            "sabyenc": sabnzbd.decoder.SABYENC_ENABLED,
            "par2": sabnzbd.newsunpack.PAR2_COMMAND,
            "multipar": sabnzbd.newsunpack.MULTIPAR_COMMAND,
            "rar": sabnzbd.newsunpack.RAR_COMMAND,
            "zip": sabnzbd.newsunpack.ZIP_COMMAND,
            "7zip": sabnzbd.newsunpack.SEVEN_COMMAND,
            "nice": sabnzbd.newsunpack.NICE_COMMAND,
            "ionice": sabnzbd.newsunpack.IONICE_COMMAND,
        },
    )


def retry_job(job, new_nzb=None, password=None):
    """ Re enter failed job in the download queue """
    if job:
        history_db = sabnzbd.get_db_connection()
        futuretype, url, pp, script, cat = history_db.get_other(job)
        if futuretype:
            nzo_id = sabnzbd.add_url(url, pp, script, cat)
        else:
            path = history_db.get_path(job)
            nzo_id = sabnzbd.NzbQueue.repair_job(path, new_nzb, password)
        if nzo_id:
            # Only remove from history if we repaired something
            history_db.remove_history(job)
            return nzo_id
    return None


def retry_all_jobs():
    """ Re enter all failed jobs in the download queue """
    # Fetch all retryable folders from History
    items = sabnzbd.api.build_history()[0]
    nzo_ids = []
    for item in items:
        if item["retry"]:
            nzo_ids.append(retry_job(item["nzo_id"]))
    return nzo_ids


def del_job_files(job_paths):
    """ Remove files of each path in the list """
    for path in job_paths:
        if path and clip_path(path).lower().startswith(cfg.download_dir.get_clipped_path().lower()):
            remove_all(path, recursive=True)


def del_hist_job(job, del_files):
    """ Remove history element """
    if job:
        path = sabnzbd.PostProcessor.get_path(job)
        if path:
            sabnzbd.PostProcessor.delete(job, del_files=del_files)
        else:
            history_db = sabnzbd.get_db_connection()
            remove_all(history_db.get_path(job), recursive=True)
            history_db.remove_history(job)


def Tspec(txt):
    """ Translate special terms """
    if txt == "None":
        return T("None")
    elif txt in ("Default", "*"):
        return T("Default")
    else:
        return txt


_SKIN_CACHE = {}  # Stores pre-translated acronyms


def Ttemplate(txt):
    """Translation function for Skin texts
    This special is to be used in interface.py for template processing
    to be passed for the $T function: so { ..., 'T' : Ttemplate, ...}
    """
    global _SKIN_CACHE
    if txt in _SKIN_CACHE:
        return _SKIN_CACHE[txt]
    else:
        # We need to remove the " and ' to be JS/JSON-string-safe
        # Saving it in dictionary is 20x faster on next look-up
        tra = T(SKIN_TEXT.get(txt, txt)).replace('"', "&quot;").replace("'", "&apos;")
        _SKIN_CACHE[txt] = tra
        return tra


def clear_trans_cache():
    """ Clean cache for skin translations """
    global _SKIN_CACHE
    _SKIN_CACHE = {}
    sabnzbd.WEBUI_READY = True


def build_header(webdir="", output=None, trans_functions=True):
    """ Build the basic header """
    try:
        uptime = calc_age(sabnzbd.START)
    except:
        uptime = "-"

    speed_limit = sabnzbd.Downloader.get_limit()
    if speed_limit <= 0:
        speed_limit = 100
    speed_limit_abs = sabnzbd.Downloader.get_limit_abs()
    if speed_limit_abs <= 0:
        speed_limit_abs = ""

    diskspace_info = diskspace()

    header = {}

    # We don't output everything for API
    if not output:
        # These are functions, and cause problems for JSON
        if trans_functions:
            header["T"] = Ttemplate
            header["Tspec"] = Tspec

        header["uptime"] = uptime
        header["color_scheme"] = sabnzbd.WEB_COLOR or ""
        header["helpuri"] = "https://sabnzbd.org/wiki/"

        header["restart_req"] = sabnzbd.RESTART_REQ
        header["pid"] = os.getpid()
        header["active_lang"] = cfg.language()

        header["my_lcldata"] = clip_path(sabnzbd.DIR_LCLDATA)
        header["my_home"] = clip_path(sabnzbd.DIR_HOME)
        header["webdir"] = webdir or sabnzbd.WEB_DIR
        header["url_base"] = cfg.url_base()

        header["nt"] = sabnzbd.WIN32
        header["darwin"] = sabnzbd.DARWIN

        header["power_options"] = sabnzbd.WIN32 or sabnzbd.DARWIN or sabnzbd.LINUX_POWER
        header["pp_pause_event"] = sabnzbd.Scheduler.pp_pause_event

        header["apikey"] = cfg.api_key()
        header["new_release"], header["new_rel_url"] = sabnzbd.NEW_VERSION

    header["version"] = sabnzbd.__version__
    header["paused"] = bool(sabnzbd.Downloader.paused or sabnzbd.Downloader.paused_for_postproc)
    header["pause_int"] = sabnzbd.Scheduler.pause_int()
    header["paused_all"] = sabnzbd.PAUSED_ALL

    header["diskspace1"] = "%.2f" % diskspace_info["download_dir"][1]
    header["diskspace2"] = "%.2f" % diskspace_info["complete_dir"][1]
    header["diskspace1_norm"] = to_units(diskspace_info["download_dir"][1] * GIGI)
    header["diskspace2_norm"] = to_units(diskspace_info["complete_dir"][1] * GIGI)
    header["diskspacetotal1"] = "%.2f" % diskspace_info["download_dir"][0]
    header["diskspacetotal2"] = "%.2f" % diskspace_info["complete_dir"][0]
    header["loadavg"] = loadavg()
    header["speedlimit"] = "{1:0.{0}f}".format(int(speed_limit % 1 > 0), speed_limit)
    header["speedlimit_abs"] = "%s" % speed_limit_abs

    header["have_warnings"] = str(sabnzbd.GUIHANDLER.count())
    header["finishaction"] = sabnzbd.QUEUECOMPLETE

    header["quota"] = to_units(sabnzbd.BPSMeter.quota)
    header["have_quota"] = bool(sabnzbd.BPSMeter.quota > 0.0)
    header["left_quota"] = to_units(sabnzbd.BPSMeter.left)

    anfo = sabnzbd.ArticleCache.cache_info()
    header["cache_art"] = str(anfo.article_sum)
    header["cache_size"] = to_units(anfo.cache_size, "B")
    header["cache_max"] = str(anfo.cache_limit)

    return header


def build_queue_header(search=None, nzo_ids=None, start=0, limit=0, output=None):
    """ Build full queue header """

    header = build_header(output=output)

    bytespersec = sabnzbd.BPSMeter.bps
    qnfo = sabnzbd.NzbQueue.queue_info(search=search, nzo_ids=nzo_ids, start=start, limit=limit)

    bytesleft = qnfo.bytes_left
    bytes_total = qnfo.bytes

    header["kbpersec"] = "%.2f" % (bytespersec / KIBI)
    header["speed"] = to_units(bytespersec)
    header["mbleft"] = "%.2f" % (bytesleft / MEBI)
    header["mb"] = "%.2f" % (bytes_total / MEBI)
    header["sizeleft"] = to_units(bytesleft, "B")
    header["size"] = to_units(bytes_total, "B")
    header["noofslots_total"] = qnfo.q_fullsize

    if sabnzbd.Downloader.paused or sabnzbd.Downloader.paused_for_postproc:
        status = Status.PAUSED
    elif bytespersec > 0:
        status = Status.DOWNLOADING
    else:
        status = "Idle"
    header["status"] = status
    header["timeleft"] = calc_timeleft(bytesleft, bytespersec)

    try:
        datestart = datetime.datetime.now() + datetime.timedelta(seconds=bytesleft / bytespersec)
        # new eta format: 16:00 Fri 07 Feb
        header["eta"] = datestart.strftime(time_format("%H:%M %a %d %b"))
    except:
        header["eta"] = T("unknown")

    return header, qnfo.list, bytespersec, qnfo.q_fullsize, qnfo.bytes_left_previous_page


def build_history(start=0, limit=0, search=None, failed_only=0, categories=None, nzo_ids=None):
    """Combine the jobs still in post-processing and the database history"""
    if not limit:
        limit = 1000000

    # Grab any items that are active or queued in postproc
    postproc_queue = sabnzbd.PostProcessor.get_queue()

    # Filter out any items that don't match the search term or category
    if postproc_queue:
        # It would be more efficient to iterate only once, but we accept the penalty for code clarity
        if isinstance(search, list):
            postproc_queue = [nzo for nzo in postproc_queue if nzo.cat in categories]

        if isinstance(search, str):
            # Replace * with .* and ' ' with .
            search_text = search.strip().replace("*", ".*").replace(" ", ".*") + ".*?"
            try:
                re_search = re.compile(search_text, re.I)
                postproc_queue = [nzo for nzo in postproc_queue if re_search.search(nzo.final_name)]
            except:
                logging.error(T("Failed to compile regex for search term: %s"), search_text)

    # Multi-page support for postproc items
    postproc_queue_size = len(postproc_queue)
    if start > postproc_queue_size:
        # On a page where we shouldn't show postproc items
        postproc_queue = []
        database_history_limit = limit
    else:
        try:
            if limit:
                postproc_queue = postproc_queue[start : start + limit]
            else:
                postproc_queue = postproc_queue[start:]
        except:
            pass
        # Remove the amount of postproc items from the db request for history items
        database_history_limit = max(limit - len(postproc_queue), 0)
    database_history_start = max(start - postproc_queue_size, 0)

    # Acquire the db instance
    try:
        history_db = sabnzbd.get_db_connection()
        close_db = False
    except:
        # Required for repairs at startup because Cherrypy isn't active yet
        history_db = HistoryDB()
        close_db = True

    # Fetch history items
    if not database_history_limit:
        items, fetched_items, total_items = history_db.fetch_history(
            database_history_start, 1, search, failed_only, categories, nzo_ids
        )
        items = []
    else:
        items, fetched_items, total_items = history_db.fetch_history(
            database_history_start, database_history_limit, search, failed_only, categories, nzo_ids
        )

    # Reverse the queue to add items to the top (faster than insert)
    items.reverse()

    # Add the postproc items to the top of the history
    items = get_active_history(postproc_queue, items)

    # Un-reverse the queue
    items.reverse()

    # Global check if rating is enabled
    rating_enabled = cfg.rating_enable()

    for item in items:
        item["size"] = to_units(item["bytes"], "B")

        if "loaded" not in item:
            item["loaded"] = False

        path = item.get("path", "")
        item["retry"] = int_conv(item.get("status") == Status.FAILED and path and os.path.exists(path))
        # Retry of failed URL-fetch
        if item["report"] == "future":
            item["retry"] = True

        if rating_enabled:
            rating = sabnzbd.Rating.get_rating_by_nzo(item["nzo_id"])
            item["has_rating"] = rating is not None
            if rating:
                item["rating_avg_video"] = rating.avg_video
                item["rating_avg_audio"] = rating.avg_audio
                item["rating_avg_vote_up"] = rating.avg_vote_up
                item["rating_avg_vote_down"] = rating.avg_vote_down
                item["rating_user_video"] = rating.user_video
                item["rating_user_audio"] = rating.user_audio
                item["rating_user_vote"] = rating.user_vote

    total_items += postproc_queue_size
    fetched_items = len(items)

    if close_db:
        history_db.close()

    return items, fetched_items, total_items


def get_active_history(queue, items):
    """ Get the currently in progress and active history queue. """
    for nzo in queue:
        item = {}
        (
            item["completed"],
            item["name"],
            item["nzb_name"],
            item["category"],
            item["pp"],
            item["script"],
            item["report"],
            item["url"],
            item["status"],
            item["nzo_id"],
            item["storage"],
            item["path"],
            item["script_log"],
            item["script_line"],
            item["download_time"],
            item["postproc_time"],
            item["stage_log"],
            item["downloaded"],
            item["fail_message"],
            item["url_info"],
            item["bytes"],
            _,
            _,
            item["password"],
        ) = build_history_info(nzo)
        item["action_line"] = nzo.action_line
        item = unpack_history_info(item)

        item["loaded"] = nzo.pp_active
        if item["bytes"]:
            item["size"] = to_units(item["bytes"], "B")
        else:
            item["size"] = ""
        items.append(item)

    return items


def calc_timeleft(bytesleft, bps):
    """ Calculate the time left in the format HH:MM:SS """
    try:
        if bytesleft <= 0:
            return "0:00:00"
        totalseconds = int(bytesleft / bps)
        minutes, seconds = divmod(totalseconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        if minutes < 10:
            minutes = "0%s" % minutes
        if seconds < 10:
            seconds = "0%s" % seconds
        if days > 0:
            if hours < 10:
                hours = "0%s" % hours
            return "%s:%s:%s:%s" % (days, hours, minutes, seconds)
        else:
            return "%s:%s:%s" % (hours, minutes, seconds)
    except:
        return "0:00:00"


def list_cats(default=True):
    """Return list of (ordered) categories,
    when default==False use '*' for Default category
    """
    lst = [cat["name"] for cat in config.get_ordered_categories()]
    if default:
        lst.remove("*")
        lst.insert(0, "Default")
    return lst


_PLURAL_TO_SINGLE = {
    "categories": "category",
    "servers": "server",
    "rss": "feed",
    "scripts": "script",
    "warnings": "warning",
    "files": "file",
    "jobs": "job",
}


def plural_to_single(kw, def_kw=""):
    try:
        return _PLURAL_TO_SINGLE[kw]
    except KeyError:
        return def_kw


def del_from_section(kwargs):
    """ Remove keyword in section """
    section = kwargs.get("section", "")
    if section in ("servers", "rss", "categories"):
        keyword = kwargs.get("keyword")
        if keyword:
            item = config.get_config(section, keyword)
            if item:
                item.delete()
                del item
                config.save_config()
                if section == "servers":
                    sabnzbd.Downloader.update_server(keyword, None)
        return True
    else:
        return False


def history_remove_failed():
    """ Remove all failed jobs from history, including files """
    logging.info("Scheduled removal of all failed jobs")
    with HistoryDB() as history_db:
        del_job_files(history_db.get_failed_paths())
        history_db.remove_failed()


def history_remove_completed():
    """ Remove all completed jobs from history """
    logging.info("Scheduled removal of all completed jobs")
    with HistoryDB() as history_db:
        history_db.remove_completed()
