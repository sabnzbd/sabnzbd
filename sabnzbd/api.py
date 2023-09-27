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

"""
sabnzbd.api - api
"""

import os
import logging
import re
import gc
import time
import getpass
import cherrypy
from threading import Thread
from typing import Tuple, Optional, List, Dict, Any

# For json.dumps, orjson is magnitudes faster than ujson, but it is harder to
# compile due to Rust dependency. Since the output is the same, we support all modules.
try:
    import orjson as json
except ImportError:
    try:
        import ujson as json
    except ImportError:
        import json

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
    AddNzbFileResult,
)
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.skintext import SKIN_TEXT
from sabnzbd.utils.diskspeed import diskspeedmeasure
from sabnzbd.utils.internetspeed import internetspeed
from sabnzbd.utils.pathbrowser import folders_at_path
from sabnzbd.utils.getperformance import getpystone
from sabnzbd.misc import (
    loadavg,
    to_units,
    int_conv,
    create_https_certificates,
    calc_age,
    opts_to_pp,
    format_time_left,
)
from sabnzbd.filesystem import diskspace, get_ext, clip_path, remove_all, list_scripts, purge_log_files
from sabnzbd.encoding import xml_name, utob
from sabnzbd.utils.servertests import test_nntp_server_dict
from sabnzbd.getipaddress import localipv4, publicipv4, ipv6, dnslookup, active_socks5_proxy
from sabnzbd.database import build_history_info, unpack_history_info, HistoryDB
from sabnzbd.lang import is_rtl
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


def api_handler(kwargs: Dict[str, Any]):
    """API Dispatcher"""
    # Clean-up the arguments
    for vr in ("mode", "name", "value", "value2", "value3", "start", "limit", "search"):
        if vr in kwargs and isinstance(kwargs[vr], list):
            kwargs[vr] = kwargs[vr][0]

    mode = kwargs.get("mode", "")
    name = kwargs.get("name", "")

    response = _api_table.get(mode, (_api_undefined, 2))[0](name, kwargs)
    return response


def _api_get_config(name, kwargs):
    """API: accepts keyword, section"""
    _, data = config.get_dconfig(kwargs.get("section"), kwargs.get("keyword"))
    return report(keyword="config", data=data)


def _api_set_config(name, kwargs):
    """API: accepts keyword, section"""
    if cfg.configlock():
        return report(_MSG_CONFIG_LOCKED)
    if kwargs.get("section") == "servers":
        kwargs["keyword"] = handle_server_api(kwargs)
    elif kwargs.get("section") == "rss":
        kwargs["keyword"] = handle_rss_api(kwargs)
    elif kwargs.get("section") == "categories":
        kwargs["keyword"] = handle_cat_api(kwargs)
    elif kwargs.get("section") == "sorters":
        kwargs["keyword"] = handle_sorter_api(kwargs)
    else:
        res = config.set_config(kwargs)
        if not res:
            return report(_MSG_NO_SUCH_CONFIG)
    config.save_config()
    res, data = config.get_dconfig(kwargs.get("section"), kwargs.get("keyword"))
    return report(keyword="config", data=data)


def _api_set_config_default(name, kwargs):
    """API: Reset requested config variables back to defaults. Currently only for misc-section"""
    if cfg.configlock():
        return report(_MSG_CONFIG_LOCKED)
    keywords = kwargs.get("keyword", [])
    if not isinstance(keywords, list):
        keywords = [keywords]
    for keyword in keywords:
        item = config.get_config("misc", keyword)
        if item:
            item.set(item.default)
    config.save_config()
    return report()


def _api_del_config(name, kwargs):
    """API: accepts keyword, section"""
    if cfg.configlock():
        return report(_MSG_CONFIG_LOCKED)
    if del_from_section(kwargs):
        return report()
    else:
        return report(_MSG_NOT_IMPLEMENTED)


def _api_queue(name, kwargs):
    """API: Dispatcher for mode=queue"""
    value = kwargs.get("value", "")
    return _api_queue_table.get(name, (_api_queue_default, 2))[0](value, kwargs)


def _api_queue_delete(value, kwargs):
    """API: accepts value"""
    if value.lower() == "all":
        removed = sabnzbd.NzbQueue.remove_all(kwargs.get("search"))
        return report(keyword="", data={"status": bool(removed), "nzo_ids": removed})
    elif value:
        items = value.split(",")
        delete_all_data = int_conv(kwargs.get("del_files"))
        removed = sabnzbd.NzbQueue.remove_multiple(items, delete_all_data=delete_all_data)
        return report(keyword="", data={"status": bool(removed), "nzo_ids": removed})
    else:
        return report(_MSG_NO_VALUE)


def _api_queue_delete_nzf(value, kwargs):
    """API: accepts value(=nzo_id), value2(=nzf_ids)"""
    nzf_ids = kwargs.get("value2")
    if value and nzf_ids:
        nzf_ids = nzf_ids.split(",")
        removed = sabnzbd.NzbQueue.remove_nzfs(value, nzf_ids)
        return report(keyword="", data={"status": bool(removed), "nzf_ids": removed})
    else:
        return report(_MSG_NO_VALUE2)


def _api_queue_rename(value, kwargs):
    """API: accepts value(=old name), value2(=new name), value3(=password)"""
    value2 = kwargs.get("value2")
    value3 = kwargs.get("value3")
    if value and value2:
        ret = sabnzbd.NzbQueue.change_name(value, value2, value3)
        return report(keyword="", data={"status": ret})
    else:
        return report(_MSG_NO_VALUE2)


def _api_queue_change_complete_action(value, kwargs):
    """API: accepts value(=action)"""
    sabnzbd.misc.change_queue_complete_action(value)
    return report()


def _api_queue_purge(value, kwargs):
    removed = sabnzbd.NzbQueue.remove_all(kwargs.get("search"))
    return report(keyword="", data={"status": bool(removed), "nzo_ids": removed})


def _api_queue_pause(value, kwargs):
    """API: accepts value(=list of nzo_id)"""
    if value:
        items = value.split(",")
        handled = sabnzbd.NzbQueue.pause_multiple_nzo(items)
    else:
        handled = False
    return report(keyword="", data={"status": bool(handled), "nzo_ids": handled})


def _api_queue_resume(value, kwargs):
    """API: accepts value(=list of nzo_id)"""
    if value:
        items = value.split(",")
        handled = sabnzbd.NzbQueue.resume_multiple_nzo(items)
    else:
        handled = False
    return report(keyword="", data={"status": bool(handled), "nzo_ids": handled})


def _api_queue_priority(value, kwargs):
    """API: accepts value(=nzo_id), value2(=priority)"""
    value2 = kwargs.get("value2")
    if value and value2:
        try:
            try:
                priority = int(value2)
            except:
                return report(_MSG_INT_VALUE)
            pos = sabnzbd.NzbQueue.set_priority(value, priority)
            # Returns the position in the queue, -1 is incorrect job-id
            return report(keyword="position", data=pos)
        except:
            return report(_MSG_NO_VALUE2)
    else:
        return report(_MSG_NO_VALUE2)


def _api_queue_sort(value, kwargs):
    """API: accepts sort, dir"""
    sort = kwargs.get("sort", "")
    direction = kwargs.get("dir", "")
    if sort:
        sabnzbd.NzbQueue.sort_queue(sort, direction)
        return report()
    else:
        return report(_MSG_NO_VALUE2)


def _api_queue_default(value, kwargs):
    """API: accepts sort, dir, start, limit and search terms"""
    start = int_conv(kwargs.get("start"))
    limit = int_conv(kwargs.get("limit"))
    search = kwargs.get("search")
    categories = kwargs.get("cat") or kwargs.get("category")
    priorities = kwargs.get("priority")
    nzo_ids = kwargs.get("nzo_ids")

    if categories and not isinstance(categories, list):
        categories = categories.split(",")
    if priorities and not isinstance(priorities, list):
        # Make sure it's an integer
        priorities = [int_conv(prio) for prio in priorities.split(",")]
    if nzo_ids and not isinstance(nzo_ids, list):
        nzo_ids = nzo_ids.split(",")

    return report(
        keyword="queue",
        data=build_queue(
            start=start, limit=limit, search=search, categories=categories, priorities=priorities, nzo_ids=nzo_ids
        ),
    )


def _api_translate(name, kwargs):
    """API: accepts value(=acronym)"""
    return report(keyword="value", data=T(kwargs.get("value", "")))


def _api_addfile(name, kwargs):
    """API: accepts name, pp, script, cat, priority, nzbname"""
    # Normal upload will send the nzb in a kw arg called name or nzbfile
    if not name or isinstance(name, str):
        name = kwargs.get("nzbfile", None)
    if hasattr(name, "file") and hasattr(name, "filename") and name.filename:
        # Add the NZB-file
        res, nzo_ids = sabnzbd.nzbparser.add_nzbfile(
            name,
            pp=kwargs.get("pp"),
            script=kwargs.get("script"),
            cat=kwargs.get("cat"),
            priority=kwargs.get("priority"),
            nzbname=kwargs.get("nzbname"),
            password=kwargs.get("password"),
        )
        return report(keyword="", data={"status": res is AddNzbFileResult.OK, "nzo_ids": nzo_ids})
    else:
        return report(_MSG_NO_VALUE)


def _api_retry(name, kwargs):
    """API: accepts name, value(=nzo_id), nzbfile(=optional NZB), password (optional)"""
    value = kwargs.get("value")
    # Normal upload will send the nzb in a kw arg called nzbfile
    if name is None or isinstance(name, str):
        name = kwargs.get("nzbfile")
    password = kwargs.get("password")
    password = password[0] if isinstance(password, list) else password

    nzo_id = retry_job(value, name, password)
    if nzo_id:
        return report(keyword="", data={"status": True, "nzo_id": nzo_id})
    else:
        return report(_MSG_NO_ITEM)


def _api_cancel_pp(name, kwargs):
    """API: accepts name, value(=nzo_id)"""
    nzo_id = kwargs.get("value")
    if sabnzbd.PostProcessor.cancel_pp(nzo_id):
        return report(keyword="", data={"status": True, "nzo_id": nzo_id})
    else:
        return report(_MSG_NO_ITEM)


def _api_addlocalfile(name, kwargs):
    """API: accepts name, pp, script, cat, priority, nzbname"""
    if name:
        if os.path.exists(name):
            if get_ext(name) in VALID_ARCHIVES + VALID_NZB_FILES:
                res, nzo_ids = sabnzbd.nzbparser.add_nzbfile(
                    name,
                    pp=kwargs.get("pp"),
                    script=kwargs.get("script"),
                    cat=kwargs.get("cat"),
                    priority=kwargs.get("priority"),
                    keep=True,
                    nzbname=kwargs.get("nzbname"),
                    password=kwargs.get("password"),
                )
                return report(keyword="", data={"status": res is AddNzbFileResult.OK, "nzo_ids": nzo_ids})
            else:
                logging.info('API-call addlocalfile: "%s" is not a supported file', name)
                return report(_MSG_NO_FILE)
        else:
            logging.info('API-call addlocalfile: file "%s" not found', name)
            return report(_MSG_NO_PATH)
    else:
        logging.info("API-call addlocalfile: no file name given")
        return report(_MSG_NO_VALUE)


def _api_switch(name, kwargs):
    """API: accepts value(=first id), value2(=second id)"""
    value = kwargs.get("value")
    value2 = kwargs.get("value2")
    if value and value2:
        pos, prio = sabnzbd.NzbQueue.switch(value, value2)
        # Returns the new position and new priority (if different)
        return report(keyword="result", data={"position": pos, "priority": prio})
    else:
        return report(_MSG_NO_VALUE2)


def _api_change_cat(name, kwargs):
    """API: accepts value(=nzo_id), value2(=category)"""
    value = kwargs.get("value")
    value2 = kwargs.get("value2")
    if value and value2:
        nzo_id = value
        cat = value2
        if cat == "None":
            cat = None
        result = sabnzbd.NzbQueue.change_cat(nzo_id, cat)
        return report(keyword="status", data=bool(result > 0))
    else:
        return report(_MSG_NO_VALUE)


def _api_change_script(name, kwargs):
    """API: accepts value(=nzo_id), value2(=script)"""
    value = kwargs.get("value")
    value2 = kwargs.get("value2")
    if value and value2:
        nzo_id = value
        script = value2
        if script.lower() == "none":
            script = None
        result = sabnzbd.NzbQueue.change_script(nzo_id, script)
        return report(keyword="status", data=bool(result > 0))
    else:
        return report(_MSG_NO_VALUE)


def _api_change_opts(name, kwargs):
    """API: accepts value(=nzo_id), value2(=pp)"""
    value = kwargs.get("value")
    value2 = kwargs.get("value2")
    result = 0
    if value and value2 and value2.isdigit():
        result = sabnzbd.NzbQueue.change_opts(value, int(value2))
    return report(keyword="status", data=bool(result > 0))


def _api_fullstatus(name, kwargs):
    """API: full history status"""
    status = build_status(
        calculate_performance=kwargs.get("calculate_performance", 0), skip_dashboard=kwargs.get("skip_dashboard", 1)
    )
    return report(keyword="status", data=status)


def _api_status(name, kwargs):
    """API: Dispatcher for mode=status, passing on the value"""
    value = kwargs.get("value", "")
    return _api_status_table.get(name, (_api_fullstatus, 2))[0](value, kwargs)


def _api_unblock_server(value, kwargs):
    """Unblock a blocked server"""
    sabnzbd.Downloader.unblock(value)
    return report()


def _api_delete_orphan(path, kwargs):
    """Remove orphaned job"""
    if path:
        path = os.path.join(cfg.download_dir.get_path(), path)
        logging.info("Removing orphaned job %s", path)
        remove_all(path, recursive=True)
        return report()
    else:
        return report(_MSG_NO_ITEM)


def _api_delete_all_orphan(value, kwargs):
    """Remove all orphaned jobs"""
    paths = sabnzbd.NzbQueue.scan_jobs(all_jobs=False, action=False)
    for path in paths:
        _api_delete_orphan(path, kwargs)
    return report()


def _api_add_orphan(path, kwargs):
    """Add orphaned job"""
    if path:
        path = os.path.join(cfg.download_dir.get_path(), path)
        logging.info("Re-adding orphaned job %s", path)
        sabnzbd.NzbQueue.repair_job(path, None, None)
        return report()
    else:
        return report(_MSG_NO_ITEM)


def _api_add_all_orphan(value, kwargs):
    """Add all orphaned jobs"""
    paths = sabnzbd.NzbQueue.scan_jobs(all_jobs=False, action=False)
    for path in paths:
        _api_add_orphan(path, kwargs)
    return report()


def _api_history(name, kwargs):
    """API: accepts value(=nzo_id), start, limit, search, nzo_ids"""
    value = kwargs.get("value", "")
    start = int_conv(kwargs.get("start"))
    limit = int_conv(kwargs.get("limit"))
    last_history_update = int_conv(kwargs.get("last_history_update", 0))
    search = kwargs.get("search")
    failed_only = int_conv(kwargs.get("failed_only"))
    categories = kwargs.get("cat") or kwargs.get("category")
    nzo_ids = kwargs.get("nzo_ids")

    # Do we need to send anything?
    if last_history_update == sabnzbd.LAST_HISTORY_UPDATE:
        return report(keyword="history", data=False)

    if categories and not isinstance(categories, list):
        categories = categories.split(",")

    if nzo_ids and not isinstance(nzo_ids, list):
        nzo_ids = nzo_ids.split(",")

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
            sabnzbd.misc.history_updated()
            return report()
        elif value:
            jobs = value.split(",")
            for job in jobs:
                path = sabnzbd.PostProcessor.get_path(job)
                if path:
                    sabnzbd.PostProcessor.delete(job, del_files=del_files)
                else:
                    history_db = sabnzbd.get_db_connection()
                    remove_all(history_db.get_path(job), recursive=True)
                    history_db.remove_history(job)
            sabnzbd.misc.history_updated()
            return report()
        else:
            return report(_MSG_NO_VALUE)
    elif not name:
        history = {}
        grand, month, week, day = sabnzbd.BPSMeter.get_sums()
        history["total_size"], history["month_size"], history["week_size"], history["day_size"] = (
            to_units(grand),
            to_units(month),
            to_units(week),
            to_units(day),
        )
        history["slots"], history["ppslots"], history["noofslots"] = build_history(
            start=start, limit=limit, search=search, failed_only=failed_only, categories=categories, nzo_ids=nzo_ids
        )
        history["last_history_update"] = sabnzbd.LAST_HISTORY_UPDATE
        history["version"] = sabnzbd.__version__
        return report(keyword="history", data=history)
    else:
        return report(_MSG_NOT_IMPLEMENTED)


def _api_get_files(name, kwargs):
    """API: accepts value(=nzo_id)"""
    value = kwargs.get("value")
    if value:
        return report(keyword="files", data=build_file_list(value))
    else:
        return report(_MSG_NO_VALUE)


def _api_move_nzf_bulk(name, kwargs):
    """API: accepts name(=top/up/down/bottom), value=(=nzo_id), nzf_ids, size (optional)"""
    nzo_id = kwargs.get("value")
    nzf_ids = kwargs.get("nzf_ids")
    size = int_conv(kwargs.get("size"))

    if nzo_id and nzf_ids and name:
        name = name.lower()
        nzf_ids = nzf_ids.split(",")
        nzf_moved = False
        if name == "up" and size:
            sabnzbd.NzbQueue.move_nzf_up_bulk(nzo_id, nzf_ids, size)
            nzf_moved = True
        elif name == "top":
            sabnzbd.NzbQueue.move_nzf_top_bulk(nzo_id, nzf_ids)
            nzf_moved = True
        elif name == "down" and size:
            sabnzbd.NzbQueue.move_nzf_down_bulk(nzo_id, nzf_ids, size)
            nzf_moved = True
        elif name == "bottom":
            sabnzbd.NzbQueue.move_nzf_bottom_bulk(nzo_id, nzf_ids)
            nzf_moved = True
        if nzf_moved:
            return report(keyword="", data={"status": True, "nzf_ids": nzf_ids})
    return report(_MSG_NO_VALUE)


def _api_addurl(name, kwargs):
    """API: accepts name, output, pp, script, cat, priority, nzbname"""
    pp = kwargs.get("pp")
    script = kwargs.get("script")
    cat = kwargs.get("cat")
    priority = kwargs.get("priority")
    nzbname = kwargs.get("nzbname", "")
    password = kwargs.get("password", "")

    if name:
        nzo_id = sabnzbd.urlgrabber.add_url(name, pp, script, cat, priority, nzbname, password)
        # Reporting a list of NZO's, for compatibility with other add-methods
        return report(keyword="", data={"status": True, "nzo_ids": [nzo_id]})
    else:
        logging.info("API-call addurl: no URLs received")
        return report(_MSG_NO_VALUE)


def _api_pause(name, kwargs):
    sabnzbd.Scheduler.plan_resume(0)
    sabnzbd.Downloader.pause()
    return report()


def _api_resume(name, kwargs):
    sabnzbd.Scheduler.plan_resume(0)
    sabnzbd.downloader.unpause_all()
    return report()


def _api_shutdown(name, kwargs):
    sabnzbd.shutdown_program()
    return report()


def _api_warnings(name, kwargs):
    """API: accepts name, output"""
    if name == "clear":
        return report(keyword="warnings", data=sabnzbd.GUIHANDLER.clear())
    elif name == "show":
        return report(keyword="warnings", data=sabnzbd.GUIHANDLER.content())
    elif name:
        return report(_MSG_NOT_IMPLEMENTED)
    return report(keyword="warnings", data=sabnzbd.GUIHANDLER.content())


LOG_JSON_RE = re.compile(rb"'(apikey|api|username|password)': '(.*?)'", re.I)
LOG_INI_HIDE_RE = re.compile(
    rb"(apikey|api|user|username|password|email_pwd|email_account|email_to|email_from|pushover_token|pushover_userkey"
    rb"|pushbullet_apikey|prowl_apikey|growl_password|growl_server|IPv[4|6] address)\s?=.*",
    re.I,
)
LOG_HASH_RE = re.compile(rb"([a-zA-Z\d]{25})", re.I)


def _api_showlog(name, kwargs):
    """Fetch the INI and the log-data and add a message at the top"""
    log_data = b"--------------------------------\n\n"
    log_data += b"The log includes a copy of your sabnzbd.ini with\nall usernames, passwords and API-keys removed."
    log_data += b"\n\n--------------------------------\n"

    with open(sabnzbd.LOGFILE, "rb") as f:
        log_data += f.read()

    with open(config.get_filename(), "rb") as f:
        log_data += f.read()

    # We need to remove all passwords/usernames/api-keys
    log_data = LOG_JSON_RE.sub(b"'REMOVED': '<REMOVED>'", log_data)
    log_data = LOG_INI_HIDE_RE.sub(b"\\1 = <REMOVED>", log_data)
    log_data = LOG_HASH_RE.sub(b"<HASH>", log_data)

    # Try to replace the username
    try:
        if cur_user := getpass.getuser():
            log_data = log_data.replace(utob(cur_user), b"<USERNAME>")
    except:
        pass

    # Set headers
    cherrypy.response.headers["Content-Type"] = "application/x-download;charset=utf-8"
    cherrypy.response.headers["Content-Disposition"] = 'attachment;filename="sabnzbd.log"'
    return log_data


def _api_get_cats(name, kwargs):
    return report(keyword="categories", data=list_cats(False))


def _api_get_scripts(name, kwargs):
    return report(keyword="scripts", data=list_scripts())


def _api_version(name, kwargs):
    return report(keyword="version", data=sabnzbd.__version__)


def _api_auth(name, kwargs):
    key = kwargs.get("key", "")
    if not key:
        auth = "apikey"
    else:
        auth = "badkey"
        if key == cfg.nzb_key():
            auth = "nzbkey"
        if key == cfg.api_key():
            auth = "apikey"
    return report(keyword="auth", data=auth)


def _api_restart(name, kwargs):
    logging.info("Restart requested by API")
    # Do the shutdown async to still send goodbye to browser
    Thread(target=sabnzbd.trigger_restart, kwargs={"timeout": 1}).start()
    return report()


def _api_restart_repair(name, kwargs):
    logging.info("Queue repair requested by API")
    sabnzbd.misc.request_repair()
    # Do the shutdown async to still send goodbye to browser
    Thread(target=sabnzbd.trigger_restart, kwargs={"timeout": 1}).start()
    return report()


def _api_disconnect(name, kwargs):
    sabnzbd.Downloader.disconnect()
    return report()


def _api_eval_sort(name, kwargs):
    """API: evaluate sorting expression"""
    sort_string = kwargs.get("sort_string", "")
    job_name = kwargs.get("job_name", "")
    multipart_label = kwargs.get("multipart_label", "")
    path = sabnzbd.sorting.eval_sort(sort_string, job_name, multipart_label)
    if path is None:
        return report(_MSG_NOT_IMPLEMENTED)
    else:
        return report(keyword="result", data=path)


def _api_watched_now(name, kwargs):
    sabnzbd.DirScanner.scan()
    return report()


def _api_resume_pp(name, kwargs):
    sabnzbd.PostProcessor.paused = False
    return report()


def _api_pause_pp(name, kwargs):
    sabnzbd.PostProcessor.paused = True
    return report()


def _api_rss_now(name, kwargs):
    # Run RSS scan async, because it can take a long time
    sabnzbd.Scheduler.force_rss()
    return report()


def _api_retry_all(name, kwargs):
    """API: Retry all failed items in History"""
    items = sabnzbd.api.build_history()[0]
    nzo_ids = []
    for item in items:
        if item["retry"]:
            nzo_ids.append(retry_job(item["nzo_id"]))
    return report(keyword="status", data=nzo_ids)


def _api_reset_quota(name, kwargs):
    """Reset quota left"""
    sabnzbd.BPSMeter.reset_quota(force=True)
    return report()


def _api_test_email(name, kwargs):
    """API: send a test email, return result"""
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
        return report()
    return report(error=res)


def _api_test_windows(name, kwargs):
    """API: send a test to Windows, return result"""
    logging.info("Sending test notification")
    res = sabnzbd.notifier.send_windows("SABnzbd", T("Test Notification"), "other")
    return report(error=res)


def _api_test_notif(name, kwargs):
    """API: send a test to Notification Center, return result"""
    logging.info("Sending test notification")
    res = sabnzbd.notifier.send_notification_center("SABnzbd", T("Test Notification"), "other")
    return report(error=res)


def _api_test_osd(name, kwargs):
    """API: send a test OSD notification, return result"""
    logging.info("Sending OSD notification")
    res = sabnzbd.notifier.send_notify_osd("SABnzbd", T("Test Notification"))
    return report(error=res)


def _api_test_prowl(name, kwargs):
    """API: send a test Prowl notification, return result"""
    logging.info("Sending Prowl notification")
    res = sabnzbd.notifier.send_prowl("SABnzbd", T("Test Notification"), "other", force=True, test=kwargs)
    return report(error=res)


def _api_test_pushover(name, kwargs):
    """API: send a test Pushover notification, return result"""
    logging.info("Sending Pushover notification")
    res = sabnzbd.notifier.send_pushover("SABnzbd", T("Test Notification"), "other", force=True, test=kwargs)
    return report(error=res)


def _api_test_pushbullet(name, kwargs):
    """API: send a test Pushbullet notification, return result"""
    logging.info("Sending Pushbullet notification")
    res = sabnzbd.notifier.send_pushbullet("SABnzbd", T("Test Notification"), "other", force=True, test=kwargs)
    return report(error=res)


def _api_test_nscript(name, kwargs):
    """API: execute a test notification script, return result"""
    logging.info("Executing notification script")
    res = sabnzbd.notifier.send_nscript("SABnzbd", T("Test Notification"), "other", force=True, test=kwargs)
    return report(error=res)


def _api_undefined(name, kwargs):
    return report(_MSG_NOT_IMPLEMENTED)


def _api_browse(name, kwargs):
    """Return tree of local path"""
    compact = kwargs.get("compact")

    if compact and compact == "1":
        name = kwargs.get("term", "")
        paths = [entry["path"] for entry in folders_at_path(os.path.dirname(name)) if "path" in entry]
        return report(keyword="", data=paths)
    else:
        show_hidden = kwargs.get("show_hidden_folders")
        paths = folders_at_path(name, True, show_hidden)
        return report(keyword="paths", data=paths)


def _api_config(name, kwargs):
    """API: Dispatcher for "config" """
    if cfg.configlock():
        return report(_MSG_CONFIG_LOCKED)
    return _api_config_table.get(name, (_api_config_undefined, 2))[0](kwargs)


def _api_config_speedlimit(kwargs):
    """API: accepts value(=speed)"""
    value = kwargs.get("value")
    if not value:
        value = "0"
    sabnzbd.Downloader.limit_speed(value)
    return report()


def _api_config_set_pause(kwargs):
    """API: accepts value(=pause interval)"""
    value = kwargs.get("value")
    sabnzbd.Scheduler.plan_resume(int_conv(value))
    return report()


def _api_config_set_apikey(kwargs):
    cfg.api_key.set(config.create_api_key())
    config.save_config()
    return report(keyword="apikey", data=cfg.api_key())


def _api_config_set_nzbkey(kwargs):
    cfg.nzb_key.set(config.create_api_key())
    config.save_config()
    return report(keyword="nzbkey", data=cfg.nzb_key())


def _api_config_regenerate_certs(kwargs):
    # Make sure we only over-write default locations
    result = False
    if (
        sabnzbd.cfg.https_cert() is sabnzbd.cfg.https_cert.default
        and sabnzbd.cfg.https_key() is sabnzbd.cfg.https_key.default
    ):
        https_cert = sabnzbd.cfg.https_cert.get_path()
        https_key = sabnzbd.cfg.https_key.get_path()
        result = create_https_certificates(https_cert, https_key)
        sabnzbd.RESTART_REQ = True
    return report(data=result)


def _api_config_test_server(kwargs):
    """API: accepts server-params"""
    result, msg = test_nntp_server_dict(kwargs)
    return report(data={"result": result, "message": msg})


def _api_config_create_backup(kwargs):
    backup_file = config.create_config_backup()
    return report(data={"result": bool(backup_file), "message": backup_file})


def _api_config_purge_log_files(kwargs):
    purge_log_files()
    return report()


def _api_config_undefined(kwargs):
    return report(_MSG_NOT_IMPLEMENTED)


def _api_server_stats(name, kwargs):
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

    return report(keyword="", data=stats)


def _api_gc_stats(name, kwargs):
    """Function only intended for internal testing of the memory handling"""
    # Collect before we check
    gc.collect()
    # We cannot create any lists/dicts, as they would create a reference
    return report(data=[str(obj) for obj in gc.get_objects() if isinstance(obj, sabnzbd.nzbstuff.TryList)])


##############################################################################
_api_table = {
    "server_stats": (_api_server_stats, 2),
    "get_config": (_api_get_config, 3),
    "set_config": (_api_set_config, 3),
    "set_config_default": (_api_set_config_default, 3),
    "del_config": (_api_del_config, 3),
    "queue": (_api_queue, 2),
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
    "status": (_api_status, 2),
    "history": (_api_history, 2),
    "get_files": (_api_get_files, 2),
    "move_nzf_bulk": (_api_move_nzf_bulk, 2),
    "addurl": (_api_addurl, 1),
    "pause": (_api_pause, 2),
    "resume": (_api_resume, 2),
    "shutdown": (_api_shutdown, 3),
    "warnings": (_api_warnings, 2),
    "showlog": (_api_showlog, 3),
    "config": (_api_config, 2),
    "get_cats": (_api_get_cats, 2),
    "get_scripts": (_api_get_scripts, 2),
    "version": (_api_version, 1),
    "auth": (_api_auth, 1),
    "restart": (_api_restart, 3),
    "restart_repair": (_api_restart_repair, 3),
    "disconnect": (_api_disconnect, 2),
    "gc_stats": (_api_gc_stats, 3),
    "eval_sort": (_api_eval_sort, 3),
    "watched_now": (_api_watched_now, 2),
    "resume_pp": (_api_resume_pp, 2),
    "pause_pp": (_api_pause_pp, 2),
    "rss_now": (_api_rss_now, 2),
    "browse": (_api_browse, 3),
    "retry_all": (_api_retry_all, 2),
    "reset_quota": (_api_reset_quota, 3),
    "test_email": (_api_test_email, 3),
    "test_windows": (_api_test_windows, 3),
    "test_notif": (_api_test_notif, 3),
    "test_osd": (_api_test_osd, 3),
    "test_pushover": (_api_test_pushover, 3),
    "test_pushbullet": (_api_test_pushbullet, 3),
    "test_prowl": (_api_test_prowl, 3),
    "test_nscript": (_api_test_nscript, 3),
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
}

_api_status_table = {
    "unblock_server": (_api_unblock_server, 2),
    "delete_orphan": (_api_delete_orphan, 2),
    "delete_all_orphan": (_api_delete_all_orphan, 2),
    "add_orphan": (_api_add_orphan, 2),
    "add_all_orphan": (_api_add_all_orphan, 2),
}

_api_config_table = {
    "speedlimit": (_api_config_speedlimit, 2),
    "set_pause": (_api_config_set_pause, 2),
    "set_apikey": (_api_config_set_apikey, 3),
    "set_nzbkey": (_api_config_set_nzbkey, 3),
    "regenerate_certs": (_api_config_regenerate_certs, 3),
    "test_server": (_api_config_test_server, 3),
    "create_backup": (_api_config_create_backup, 3),
    "purge_log_files": (_api_config_purge_log_files, 3),
}


def api_level(mode: str, name: str) -> int:
    """Return access level required for this API call"""
    if mode == "queue" and name in _api_queue_table:
        return _api_queue_table[name][1]
    if mode == "status" and name in _api_status_table:
        return _api_status_table[name][1]
    if mode == "config" and name in _api_config_table:
        return _api_config_table[name][1]
    if mode in _api_table:
        return _api_table[mode][1]
    # It is invalid if it's none of these, but that's is handled somewhere else
    return 4


def report(error: Optional[str] = None, keyword: str = "value", data: Any = None) -> bytes:
    """Report message in json, xml or plain text
    If error is set, only an status/error report is made.
    If no error and no data, only a status report is made.
    Else, a data report is made (optional 'keyword' for outer XML section).
    """
    output = cherrypy.request.params.get("output")
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

        response = utob(json.dumps(info))

    elif output == "xml":
        if not keyword:
            # xml always needs an outer keyword, even when json doesn't
            keyword = "result"
        content = "text/xml"
        xmlmaker = XmlOutputFactory()
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


class XmlOutputFactory:
    """Recursive xml string maker. Feed it a mixed tuple/dict/item object and will output into an xml string
    Current limitations:
        In Two tiered lists hard-coded name of "item": <cat_list><item> </item></cat_list>
        In Three tiered lists hard-coded name of "slot": <tier1><slot><tier2> </tier2></slot></tier1>
    """

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


def handle_server_api(kwargs):
    """Special handler for API-call 'set_config' [servers]"""
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


def handle_sorter_api(kwargs):
    """Special handler for API-call 'set_config' [sorters]"""
    name = kwargs.get("keyword")
    if not name:
        name = kwargs.get("name")
    if not name:
        return None

    sorter = config.get_config("sorters", name)
    if sorter:
        sorter.set_dict(kwargs)
    else:
        config.ConfigSorter(name, kwargs)
    return name


def handle_rss_api(kwargs):
    """Special handler for API-call 'set_config' [rss]"""
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


def handle_cat_api(kwargs):
    """Special handler for API-call 'set_config' [categories]"""
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


def build_status(calculate_performance: bool = False, skip_dashboard: bool = False) -> Dict[str, Any]:
    # build up header full of basic information
    info = build_header(trans_functions=False)

    info["logfile"] = clip_path(sabnzbd.LOGFILE)
    info["weblogfile"] = clip_path(sabnzbd.WEBLOGFILE)
    info["webdir"] = clip_path(info["webdir"])
    info["loglevel"] = str(cfg.log_level())
    info["folders"] = sabnzbd.NzbQueue.scan_jobs(all_jobs=False, action=False)
    info["configfn"] = clip_path(config.get_filename())
    info["warnings"] = sabnzbd.GUIHANDLER.content()

    # Calculate performance measures, if requested
    if int_conv(calculate_performance):
        # Perform the internetspeed measure in separate thread
        internetspeed_future = sabnzbd.THREAD_POOL.submit(internetspeed)

        # PyStone
        sabnzbd.PYSTONE_SCORE = getpystone()

        # Diskspeed of download (aka incomplete) and complete directory:
        sabnzbd.DOWNLOAD_DIR_SPEED = round(diskspeedmeasure(sabnzbd.cfg.download_dir.get_path()), 1)
        sabnzbd.COMPLETE_DIR_SPEED = round(diskspeedmeasure(sabnzbd.cfg.complete_dir.get_path()), 1)

        # Internet bandwidth
        sabnzbd.INTERNET_BANDWIDTH = round(internetspeed_future.result(), 1)

    # How often did we delay?
    info["delayed_assembler"] = sabnzbd.BPSMeter.delayed_assembler

    # Dashboard: Speed and load of System
    info["loadavg"] = loadavg()
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
        info["active_socks5_proxy"] = active_socks5_proxy()
        info["localipv4"] = localipv4()
        info["publicipv4"] = publicipv4()
        info["ipv6"] = ipv6()
        info["dnslookup"] = dnslookup()

    info["servers"] = []
    # Servers-list could be modified during iteration, so we need a copy
    for server in sabnzbd.Downloader.servers[:]:
        connected = sum(nw.connected for nw in server.idle_threads.copy())
        serverconnections = []
        for nw in server.busy_threads.copy():
            if nw.connected:
                connected += 1
            if nw.article:
                serverconnections.append(
                    {
                        "thrdnum": nw.thrdnum,
                        "art_name": nw.article.article,
                        "nzf_name": nw.article.nzf.filename,
                        "nzo_name": nw.article.nzf.nzo.final_name,
                    }
                )

        if server.warning and not (connected or server.errormsg):
            connected = server.warning

        if server.request and not server.info:
            connected = T("&nbsp;Resolving address").replace("&nbsp;", "")

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

    return info


def build_queue(
    start: int = 0,
    limit: int = 0,
    search: Optional[str] = None,
    categories: Optional[List[str]] = None,
    priorities: Optional[List[str]] = None,
    nzo_ids: Optional[List[str]] = None,
):
    info = build_header(for_template=False)
    (
        queue_bytes_total,
        queue_bytes_left,
        bytes_left_previous_page,
        nzo_list,
        queue_fullsize,
        nzos_matched,
    ) = sabnzbd.NzbQueue.queue_info(
        search=search, categories=categories, priorities=priorities, nzo_ids=nzo_ids, start=start, limit=limit
    )

    info["kbpersec"] = "%.2f" % (sabnzbd.BPSMeter.bps / KIBI)
    info["speed"] = to_units(sabnzbd.BPSMeter.bps)
    info["mbleft"] = "%.2f" % (queue_bytes_left / MEBI)
    info["mb"] = "%.2f" % (queue_bytes_total / MEBI)
    info["sizeleft"] = to_units(queue_bytes_left, "B")
    info["size"] = to_units(queue_bytes_total, "B")
    info["noofslots_total"] = queue_fullsize
    info["noofslots"] = nzos_matched
    info["start"] = start
    info["limit"] = limit
    info["finish"] = start + limit

    if sabnzbd.Downloader.paused or sabnzbd.Downloader.paused_for_postproc:
        status = Status.PAUSED
    elif sabnzbd.BPSMeter.bps > 0:
        status = Status.DOWNLOADING
    else:
        status = Status.IDLE
    info["status"] = status
    info["timeleft"] = calc_timeleft(queue_bytes_left, sabnzbd.BPSMeter.bps)

    n = start
    running_bytes = bytes_left_previous_page
    slotinfo = []
    for nzo in nzo_list:
        mbleft = nzo.remaining / MEBI
        mb = nzo.bytes / MEBI
        is_propagating = (nzo.avg_stamp + float(cfg.propagation_delay() * 60)) > time.time()

        slot = {}
        slot["index"] = n
        slot["nzo_id"] = str(nzo.nzo_id)
        slot["unpackopts"] = str(opts_to_pp(nzo.repair, nzo.unpack, nzo.delete))
        slot["priority"] = INTERFACE_PRIORITIES.get(nzo.priority, NORMAL_PRIORITY)
        slot["script"] = nzo.script if nzo.script else "None"
        slot["filename"] = nzo.final_name
        slot["labels"] = nzo.labels
        slot["password"] = nzo.password if nzo.password else ""
        slot["cat"] = nzo.cat if nzo.cat else "None"
        slot["mbleft"] = "%.2f" % mbleft
        slot["mb"] = "%.2f" % mb
        slot["size"] = to_units(nzo.bytes, "B")
        slot["sizeleft"] = to_units(nzo.remaining, "B")
        slot["percentage"] = "%s" % (int(((mb - mbleft) / mb) * 100)) if mb != mbleft else "0"
        slot["mbmissing"] = "%.2f" % (nzo.bytes_missing / MEBI)
        slot["direct_unpack"] = nzo.direct_unpack_progress

        if not sabnzbd.Downloader.paused and nzo.status not in (Status.PAUSED, Status.FETCHING, Status.GRABBING):
            if is_propagating:
                slot["status"] = Status.PROP
            elif nzo.status == Status.CHECKING:
                slot["status"] = Status.CHECKING
            else:
                slot["status"] = Status.DOWNLOADING
        else:
            # Ensure compatibility of API status
            if nzo.status == Status.DELETED or nzo.priority == FORCE_PRIORITY:
                nzo.status = Status.DOWNLOADING
            slot["status"] = nzo.status

        if (
            sabnzbd.Downloader.paused
            or sabnzbd.Downloader.paused_for_postproc
            or is_propagating
            or nzo.status not in (Status.DOWNLOADING, Status.FETCHING, Status.QUEUED)
        ) and nzo.priority != FORCE_PRIORITY:
            slot["timeleft"] = "0:00:00"
        else:
            running_bytes += nzo.remaining
            slot["timeleft"] = calc_timeleft(running_bytes, sabnzbd.BPSMeter.bps)

        # Do not show age when it's not known
        if nzo.avg_date.year < 2000:
            slot["avg_age"] = "-"
        else:
            slot["avg_age"] = calc_age(nzo.avg_date)

        slotinfo.append(slot)
        n += 1

    if slotinfo:
        info["slots"] = slotinfo
    else:
        info["slots"] = []

    return info


def fast_queue() -> Tuple[bool, int, float, str]:
    """Return paused, bytes_left, bpsnow, time_left"""
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
        for nzf in nzo.finished_files:
            jobs.append(
                {
                    "filename": nzf.filename,
                    "mbleft": "%.2f" % (nzf.bytes_left / MEBI),
                    "mb": "%.2f" % (nzf.bytes / MEBI),
                    "bytes": "%.2f" % nzf.bytes,
                    "age": calc_age(nzf.date),
                    "nzf_id": nzf.nzf_id,
                    "status": "finished",
                }
            )

        for nzf in nzo.files:
            jobs.append(
                {
                    "filename": nzf.filename,
                    "mbleft": "%.2f" % (nzf.bytes_left / MEBI),
                    "mb": "%.2f" % (nzf.bytes / MEBI),
                    "bytes": "%.2f" % nzf.bytes,
                    "age": calc_age(nzf.date),
                    "nzf_id": nzf.nzf_id,
                    "status": "active",
                }
            )

        # extrapars can change during iteration
        for parset in nzo.extrapars.keys():
            extrapar_set = nzo.extrapars.get(parset, [])
            for nzf in extrapar_set[:]:
                # Prevent listing files twice
                if nzf not in nzo.files and nzf not in nzo.finished_files:
                    jobs.append(
                        {
                            "filename": nzf.filename,
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


def retry_job(job, new_nzb=None, password=None):
    """Re enter failed job in the download queue"""
    if job:
        history_db = sabnzbd.get_db_connection()
        futuretype, url, pp, script, cat = history_db.get_other(job)
        if futuretype:
            nzo_id = sabnzbd.urlgrabber.add_url(url, pp, script, cat)
        else:
            path = history_db.get_path(job)
            nzo_id = sabnzbd.NzbQueue.repair_job(path, new_nzb, password)
        if nzo_id:
            # Only remove from history if we repaired something
            history_db.remove_history(job)
            return nzo_id
    return None


def del_job_files(job_paths):
    """Remove files of each path in the list"""
    for path in job_paths:
        if path and clip_path(path).lower().startswith(cfg.download_dir.get_clipped_path().lower()):
            remove_all(path, recursive=True)


def Tspec(txt):
    """Translate special terms"""
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
    """Clean cache for skin translations"""
    global _SKIN_CACHE
    _SKIN_CACHE = {}
    sabnzbd.WEBUI_READY = True


def build_header(webdir: str = "", for_template: bool = True, trans_functions: bool = True) -> Dict:
    """Build the basic header"""
    header = {}

    # We don't output everything for API
    if for_template:
        # These are functions, and cause problems for JSON
        if trans_functions:
            header["T"] = Ttemplate
            header["Tspec"] = Tspec

        header["uptime"] = calc_age(sabnzbd.START)
        header["color_scheme"] = sabnzbd.WEB_COLOR or ""
        header["web_config_override"] = cfg.web_config_override()
        header["confighelpuri"] = f"https://sabnzbd.org/wiki/configuration/{sabnzbd.__version__[:3]}/"

        header["pid"] = os.getpid()
        header["active_lang"] = cfg.language()
        header["rtl"] = is_rtl(header["active_lang"])

        header["my_lcldata"] = clip_path(sabnzbd.DIR_LCLDATA)
        header["my_home"] = clip_path(sabnzbd.DIR_HOME)
        header["webdir"] = webdir or sabnzbd.WEB_DIR
        header["url_base"] = cfg.url_base()

        header["windows"] = sabnzbd.WIN32
        header["macos"] = sabnzbd.MACOS

        header["power_options"] = sabnzbd.WIN32 or sabnzbd.MACOS or sabnzbd.LINUX_POWER
        header["pp_pause_event"] = sabnzbd.Scheduler.pp_pause_event

        header["apikey"] = cfg.api_key()
        header["new_release"], header["new_rel_url"] = sabnzbd.NEW_VERSION

    header["version"] = sabnzbd.__version__
    header["paused"] = bool(sabnzbd.Downloader.paused or sabnzbd.Downloader.paused_for_postproc)
    header["pause_int"] = sabnzbd.Scheduler.pause_int()
    header["paused_all"] = sabnzbd.PAUSED_ALL

    diskspace_info = diskspace()
    header["diskspace1"] = "%.2f" % diskspace_info["download_dir"][1]
    header["diskspace2"] = "%.2f" % diskspace_info["complete_dir"][1]
    header["diskspace1_norm"] = to_units(diskspace_info["download_dir"][1] * GIGI)
    header["diskspace2_norm"] = to_units(diskspace_info["complete_dir"][1] * GIGI)
    header["diskspacetotal1"] = "%.2f" % diskspace_info["download_dir"][0]
    header["diskspacetotal2"] = "%.2f" % diskspace_info["complete_dir"][0]
    header["speedlimit"] = str(sabnzbd.Downloader.bandwidth_perc)
    header["speedlimit_abs"] = str(sabnzbd.Downloader.bandwidth_limit)

    header["have_warnings"] = str(sabnzbd.GUIHANDLER.count())
    header["finishaction"] = sabnzbd.QUEUECOMPLETE

    header["quota"] = to_units(sabnzbd.BPSMeter.quota)
    header["have_quota"] = bool(sabnzbd.BPSMeter.quota > 0.0)
    header["left_quota"] = to_units(sabnzbd.BPSMeter.left)

    anfo = sabnzbd.ArticleCache.cache_info()
    header["cache_art"] = str(anfo.article_sum)
    header["cache_size"] = to_units(anfo.cache_size, "B")

    return header


def build_history(
    start: int = 0,
    limit: int = 0,
    search: Optional[str] = None,
    failed_only: int = 0,
    categories: Optional[List[str]] = None,
    nzo_ids: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], int, int]:
    """Combine the jobs still in post-processing and the database history"""
    if not limit:
        limit = 1000000

    # Grab any items that are active or queued in postproc
    postproc_queue = sabnzbd.PostProcessor.get_queue()

    # Filter out any items that don't match the search term or category
    if postproc_queue:
        # It would be more efficient to iterate only once, but we accept the penalty for code clarity
        if isinstance(categories, list):
            postproc_queue = [nzo for nzo in postproc_queue if nzo.cat in categories]

        if isinstance(search, str):
            # Replace * with .* and ' ' with .
            search_text = search.strip().replace("*", ".*").replace(" ", ".*") + ".*?"
            try:
                re_search = re.compile(search_text, re.I)
                postproc_queue = [nzo for nzo in postproc_queue if re_search.search(nzo.final_name)]
            except:
                logging.error(T("Failed to compile regex for search term: %s"), search_text)

        if nzo_ids:
            postproc_queue = [nzo for nzo in postproc_queue if nzo.nzo_id in nzo_ids]

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
        items, total_items = history_db.fetch_history(
            database_history_start, 1, search, failed_only, categories, nzo_ids
        )
        items = []
    else:
        items, total_items = history_db.fetch_history(
            database_history_start, database_history_limit, search, failed_only, categories, nzo_ids
        )

    # Reverse the queue to add items to the top (faster than insert)
    items.reverse()

    # Add the postproc items to the top of the history
    items = get_active_history(postproc_queue, items)

    # Un-reverse the queue
    items.reverse()

    for item in items:
        item["size"] = to_units(item["bytes"], "B")

        if "loaded" not in item:
            item["loaded"] = False

        path = item.get("path", "")
        item["retry"] = int_conv(item.get("status") == Status.FAILED and path and os.path.exists(path))
        # Retry of failed URL-fetch
        if item["report"] == "future":
            item["retry"] = True

    total_items += postproc_queue_size

    if close_db:
        history_db.close()

    return items, postproc_queue_size, total_items


def get_active_history(queue, items):
    """Get the jobs currently in progress and active history queue."""
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
    """Based on bytesleft and bps calculate the time left in the format HH:MM:SS"""
    if bytesleft <= 0 or bps <= 0:
        return "0:00:00"
    return format_time_left(int(bytesleft / bps))


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
    """Remove keyword in section"""
    section = kwargs.get("section", "")
    if section in ("sorters", "servers", "rss", "categories"):
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
    """Remove all failed jobs from history, including files"""
    logging.info("Scheduled removal of all failed jobs")
    with HistoryDB() as history_db:
        del_job_files(history_db.get_failed_paths())
        history_db.remove_failed()


def history_remove_completed():
    """Remove all completed jobs from history"""
    logging.info("Scheduled removal of all completed jobs")
    with HistoryDB() as history_db:
        history_db.remove_completed()
