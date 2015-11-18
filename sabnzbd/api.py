#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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
import datetime
import time
import json
import cherrypy
import locale
try:
    locale.setlocale(locale.LC_ALL, "")
except:
    # Work-around for Python-ports with bad "locale" support
    pass
try:
    import win32api
    import win32file
except ImportError:
    pass


import sabnzbd
from sabnzbd.constants import *
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.downloader import Downloader
from sabnzbd.nzbqueue import NzbQueue, set_priority, sort_queue, scan_jobs, repair_job
import sabnzbd.nzbstuff as nzbstuff
import sabnzbd.scheduler as scheduler
from sabnzbd.skintext import SKIN_TEXT

from sabnzbd.utils.rsslib import RSS, Item
from sabnzbd.utils.pathbrowser import folders_at_path
from sabnzbd.misc import loadavg, to_units, diskfree, disktotal, get_ext, \
    get_filename, int_conv, globber, globber_full, time_format, remove_all, \
    starts_with_path, cat_convert, clip_path
from sabnzbd.encoding import xml_name, unicoder, special_fixer, platform_encode, html_escape
from sabnzbd.postproc import PostProcessor
from sabnzbd.articlecache import ArticleCache
from sabnzbd.utils.servertests import test_nntp_server_dict
from sabnzbd.bpsmeter import BPSMeter
from sabnzbd.rating import Rating
from sabnzbd.database import build_history_info, unpack_history_info, get_history_handle
import sabnzbd.growler
import sabnzbd.rss
import sabnzbd.emailer


##############################################################################
# API error messages
##############################################################################
_MSG_NO_VALUE = 'expect one parameter'
_MSG_NO_VALUE2 = 'expect two parameters'
_MSG_INT_VALUE = 'expect integer value'
_MSG_NO_ITEM = 'item does not exist'
_MSG_NOT_IMPLEMENTED = 'not implemented'
_MSG_NO_FILE = 'no file given'
_MSG_NO_PATH = 'file does not exist'
_MSG_OUTPUT_FORMAT = 'Format not supported'
_MSG_NO_SUCH_CONFIG = 'Config item does not exist'
_MSG_BAD_SERVER_PARMS = 'Incorrect server settings'


# For Windows: determine executable extensions
if os.name == 'nt':
    PATHEXT = os.environ.get('PATHEXT', '').lower().split(';')
else:
    PATHEXT = []


def api_handler(kwargs):
    """ API Dispatcher """
    mode = kwargs.get('mode', '')
    output = kwargs.get('output')
    name = kwargs.get('name', '')
    callback = kwargs.get('callback', '')

    if isinstance(mode, list):
        mode = mode[0]
    if isinstance(output, list):
        output = output[0]
    response = _api_table.get(mode, (_api_undefined, 2))[0](name, output, kwargs)
    if output == 'json' and callback:
        response = '%s(%s)' % (callback, response)
    return response


def _api_get_config(name, output, kwargs):
    """ API: accepts output, keyword, section """
    unused, data = config.get_dconfig(kwargs.get('section'), kwargs.get('keyword'))
    return report(output, keyword='config', data=data)


def _api_set_config(name, output, kwargs):
    """ API: accepts output, keyword, section """
    if kwargs.get('section') == 'servers':
        kwargs['keyword'] = handle_server_api(output, kwargs)
    elif kwargs.get('section') == 'rss':
        kwargs['keyword'] = handle_rss_api(output, kwargs)
    elif kwargs.get('section') == 'categories':
        kwargs['keyword'] = handle_cat_api(output, kwargs)
    else:
        res = config.set_config(kwargs)
        if not res:
            return report(output, _MSG_NO_SUCH_CONFIG)
    config.save_config()
    res, data = config.get_dconfig(kwargs.get('section'), kwargs.get('keyword'))
    return report(output, keyword='config', data=data)


def _api_del_config(name, output, kwargs):
    """ API: accepts output, keyword, section """
    if del_from_section(kwargs):
        return report(output)
    else:
        return report(output, _MSG_NOT_IMPLEMENTED)


def _api_qstatus(name, output, kwargs):
    """ API: accepts output """
    if output == 'json':
        # Compatibility Fix:
        # Old qstatus did not have a keyword, so do not use one now.
        keyword = ''
    else:
        keyword = 'queue'
    return report(output, keyword=keyword, data=qstatus_data())


def _api_queue(name, output, kwargs):
    """ API: Dispatcher for mode=queue """
    value = kwargs.get('value', '')
    return _api_queue_table.get(name, (_api_queue_default, 2))[0](output, value, kwargs)


def _api_queue_delete(output, value, kwargs):
    """ API: accepts output, value """
    if value.lower() == 'all':
        removed = NzbQueue.do.remove_all(kwargs.get('search'))
        return report(output, keyword='', data={'status': bool(removed), 'nzo_ids': removed})
    elif value:
        items = value.split(',')
        del_files = int_conv(kwargs.get('del_files'))
        removed = NzbQueue.do.remove_multiple(items, del_files)
        return report(output, keyword='', data={'status': bool(removed), 'nzo_ids': removed})
    else:
        return report(output, _MSG_NO_VALUE)


def _api_queue_delete_nzf(output, value, kwargs):
    """ API: accepts value(=nzo_id), value2(=nzf_id) """
    value2 = kwargs.get('value2')
    if value and value2:
        removed = NzbQueue.do.remove_nzf(value, value2)
        return report(output, keyword='', data={'status': bool(removed), 'nzf_ids': removed})
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_rename(output, value, kwargs):
    """ API: accepts output, value(=old name), value2(=new name), value3(=password) """
    value2 = kwargs.get('value2')
    value3 = kwargs.get('value3')
    if value and value2:
        ret = NzbQueue.do.change_name(value, special_fixer(value2), special_fixer(value3))
        return report(output, keyword='', data={'status': ret})
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_change_complete_action(output, value, kwargs):
    """ API: accepts output, value(=action) """
    sabnzbd.change_queue_complete_action(value)
    return report(output)


def _api_queue_purge(output, value, kwargs):
    """ API: accepts output """
    removed = NzbQueue.do.remove_all(kwargs.get('search'))
    return report(output, keyword='', data={'status': bool(removed), 'nzo_ids': removed})


def _api_queue_pause(output, value, kwargs):
    """ API: accepts output, value(=list of nzo_id) """
    if value:
        items = value.split(',')
        handled = NzbQueue.do.pause_multiple_nzo(items)
    return report(output, keyword='', data={'status': bool(handled), 'nzo_ids': handled})


def _api_queue_resume(output, value, kwargs):
    """ API: accepts output, value(=list of nzo_id) """
    if value:
        items = value.split(',')
        handled = NzbQueue.do.resume_multiple_nzo(items)
    return report(output, keyword='', data={'status': bool(handled), 'nzo_ids': handled})


def _api_queue_priority(output, value, kwargs):
    """ API: accepts output, value(=nzo_id), value2(=priority) """
    value2 = kwargs.get('value2')
    if value and value2:
        try:
            try:
                priority = int(value2)
            except:
                return report(output, _MSG_INT_VALUE)
            pos = set_priority(value, priority)
            # Returns the position in the queue, -1 is incorrect job-id
            return report(output, keyword='position', data=pos)
        except:
            return report(output, _MSG_NO_VALUE2)
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_sort(output, value, kwargs):
    """ API: accepts output, sort, dir """
    sort = kwargs.get('sort')
    direction = kwargs.get('dir', '')
    if sort:
        sort_queue(sort, direction)
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_default(output, value, kwargs):
    """ API: accepts output, sort, dir, start, limit """
    sort = kwargs.get('sort')
    direction = kwargs.get('dir', '')
    start = kwargs.get('start')
    limit = kwargs.get('limit')
    trans = kwargs.get('trans')
    search = kwargs.get('search')

    if output in ('xml', 'json'):
        if sort and sort != 'index':
            reverse = direction.lower() == 'desc'
            sort_queue(sort, reverse)

        # &history=1 will show unprocessed items in the history
        history = bool(kwargs.get('history'))

        info, pnfo_list, bytespersec, verbose_list, dictn = \
            build_queue(history=history, start=start, limit=limit, output=output, trans=trans, search=search)
        info['categories'] = info.pop('cat_list')
        info['scripts'] = info.pop('script_list')
        return report(output, keyword='queue', data=remove_callable(info))
    elif output == 'rss':
        return rss_qstatus()
    else:
        return report(output, _MSG_NOT_IMPLEMENTED)


def _api_queue_rating(output, value, kwargs):
    """ API: accepts output, value(=nzo_id), type, setting, detail """
    vote_map = {'up': Rating.VOTE_UP, 'down': Rating.VOTE_DOWN}
    flag_map = {'spam': Rating.FLAG_SPAM, 'encrypted': Rating.FLAG_ENCRYPTED, 'expired': Rating.FLAG_EXPIRED, 'other': Rating.FLAG_OTHER, 'comment': Rating.FLAG_COMMENT}
    content_type = kwargs.get('type')
    setting = kwargs.get('setting')
    if value:
        try:
            video = audio = vote = flag = None
            if content_type == 'video' and setting != "-":
                video = setting
            if content_type == 'audio' and setting != "-":
                audio = setting
            if content_type == 'vote':
                vote = vote_map[setting]
            if content_type == 'flag':
                flag = flag_map[setting]
            if cfg.rating_enable():
                Rating.do.update_user_rating(value, video, audio, vote, flag, kwargs.get('detail'))
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
    return report(output, keyword='value', data=Tx(kwargs.get('value', '')))


def _api_addfile(name, output, kwargs):
    """ API: accepts name, output, pp, script, cat, priority, nzbname """
    # When uploading via flash it will send the nzb in a kw arg called Filedata
    if name is None or isinstance(name, basestring):
        name = kwargs.get('Filedata')
    # Normal upload will send the nzb in a kw arg called nzbfile
    if name is None or isinstance(name, basestring):
        name = kwargs.get('nzbfile')
    if hasattr(name, 'getvalue'):
        # Side effect of next line is that attribute .value is created
        # which is needed to make add_nzbfile() work
        size = name.length
    elif hasattr(name, 'file') and hasattr(name, 'filename') and name.filename:
        # CherryPy 3.2.2 object
        if hasattr(name.file, 'file'):
            name.value = name.file.file.read()
        else:
            name.value = name.file.read()
        size = len(name.value)
    elif hasattr(name, 'value'):
        size = len(name.value)
    else:
        size = 0
    if name is not None and size and name.filename:
        cat = kwargs.get('cat')
        xcat = kwargs.get('xcat')
        if not cat and xcat:
            # Indexer category, so do mapping
            cat = cat_convert(xcat)
        res = sabnzbd.add_nzbfile(name, kwargs.get('pp'), kwargs.get('script'), cat,
                            kwargs.get('priority'), kwargs.get('nzbname'))
        return report(output, keyword='', data={'status': res[0] == 0, 'nzo_ids': res[1]}, compat=True)
    else:
        return report(output, _MSG_NO_VALUE)


def _api_retry(name, output, kwargs):
    """ API: accepts name, output, value(=nzo_id), nzbfile(=optional NZB), password (optional) """
    value = kwargs.get('value')
    # When uploading via flash it will send the nzb in a kw arg called Filedata
    if name is None or isinstance(name, basestring):
        name = kwargs.get('Filedata')
    # Normal upload will send the nzb in a kw arg called nzbfile
    if name is None or isinstance(name, basestring):
        name = kwargs.get('nzbfile')
    password = kwargs.get('password')
    password = password[0] if isinstance(password, list) else password

    nzo_id = retry_job(value, name, password)
    if nzo_id:
        if isinstance(nzo_id, list):
            nzo_id = nzo_id[0]
        return report(output, keyword='', data={'status': True, 'nzo_id': nzo_id})
    else:
        return report(output, _MSG_NO_ITEM)


def _api_addlocalfile(name, output, kwargs):
    """ API: accepts name, output, pp, script, cat, priority, nzbname """
    if name and isinstance(name, list):
        name = name[0]
    if name:
        if os.path.exists(name):
            fn = get_filename(name)
            if fn:
                pp = kwargs.get('pp')
                script = kwargs.get('script')
                cat = kwargs.get('cat')
                xcat = kwargs.get('xcat')
                if not cat and xcat:
                    # Indexer category, so do mapping
                    cat = cat_convert(xcat)
                priority = kwargs.get('priority')
                nzbname = kwargs.get('nzbname')

                if get_ext(name) in VALID_ARCHIVES:
                    res = sabnzbd.dirscanner.ProcessArchiveFile(
                        fn, name, pp=pp, script=script, cat=cat, priority=priority, keep=True, nzbname=nzbname)
                elif get_ext(name) in ('.nzb', '.gz', '.bz2'):
                    res = sabnzbd.dirscanner.ProcessSingleFile(
                        fn, name, pp=pp, script=script, cat=cat, priority=priority, keep=True, nzbname=nzbname)
            else:
                logging.info('API-call addlocalfile: "%s" not a proper file name', name)
                return report(output, _MSG_NO_FILE)
        else:
            logging.info('API-call addlocalfile: file "%s" not found', name)
            return report(output, _MSG_NO_PATH)
        return report(output, keyword='', data={'status': res[0] == 0, 'nzo_ids': res[1]}, compat=True)
    else:
        logging.info('API-call addlocalfile: no file name given')
        return report(output, _MSG_NO_VALUE)


def _api_switch(name, output, kwargs):
    """ API: accepts output, value(=first id), value2(=second id) """
    value = kwargs.get('value')
    value2 = kwargs.get('value2')
    if value and value2:
        pos, prio = NzbQueue.do.switch(value, value2)
        # Returns the new position and new priority (if different)
        if output not in ('xml', 'json'):
            return report(output, data=(pos, prio))
        else:
            return report(output, keyword='result', data={'position': pos, 'priority': prio})
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_change_cat(name, output, kwargs):
    """ API: accepts output, value(=nzo_id), value2(=category) """
    value = kwargs.get('value')
    value2 = kwargs.get('value2')
    if value and value2:
        nzo_id = value
        cat = value2
        if cat == 'None':
            cat = None
        result = NzbQueue.do.change_cat(nzo_id, cat)
        return report(output, keyword='status', data=bool(result > 0))
    else:
        return report(output, _MSG_NO_VALUE)


def _api_change_script(name, output, kwargs):
    """ API: accepts output, value(=nzo_id), value2(=script) """
    value = kwargs.get('value')
    value2 = kwargs.get('value2')
    if value and value2:
        nzo_id = value
        script = value2
        if script.lower() == 'none':
            script = None
        result = NzbQueue.do.change_script(nzo_id, script)
        return report(output, keyword='status', data=bool(result > 0))
    else:
        return report(output, _MSG_NO_VALUE)


def _api_change_opts(name, output, kwargs):
    """ API: accepts output, value(=nzo_id), value2(=pp) """
    value = kwargs.get('value')
    value2 = kwargs.get('value2')
    if value and value2 and value2.isdigit():
        result = NzbQueue.do.change_opts(value, int(value2))
    return report(output, keyword='status', data=bool(result > 0))


def _api_fullstatus(name, output, kwargs):
    """ API: not implemented """
    return report(output, _MSG_NOT_IMPLEMENTED + ' YET')  # xml_full()


def _api_history(name, output, kwargs):
    """ API: accepts output, value(=nzo_id), start, limit, search """
    value = kwargs.get('value', '')
    start = kwargs.get('start')
    limit = kwargs.get('limit')
    search = kwargs.get('search')
    failed_only = kwargs.get('failed_only')
    categories = kwargs.get('category')
    if categories and not isinstance(categories, list):
        categories = [categories]

    if not limit:
        limit = cfg.history_limit()

    if name == 'delete':
        special = value.lower()
        del_files = bool(int_conv(kwargs.get('del_files')))
        if special in ('all', 'failed', 'completed'):
            history_db = cherrypy.thread_data.history_db
            if special in ('all', 'failed'):
                if del_files:
                    del_job_files(history_db.get_failed_paths(search))
                history_db.remove_failed(search)
            if special in ('all', 'completed'):
                history_db.remove_completed(search)
            return report(output)
        elif value:
            jobs = value.split(',')
            for job in jobs:
                del_hist_job(job, del_files)
            return report(output)
        else:
            return report(output, _MSG_NO_VALUE)
    elif not name:
        history, pnfo_list, bytespersec = build_header(True)
        if 'noofslots_total' in history:
            del history['noofslots_total']
        grand, month, week, day = BPSMeter.do.get_sums()
        history['total_size'], history['month_size'], history['week_size'], history['day_size'] = \
               to_units(grand), to_units(month), to_units(week), to_units(day)
        history['slots'], fetched_items, history['noofslots'] = build_history(start=start,
                                                                              limit=limit, verbose=True,
                                                                              search=search, failed_only=failed_only,
                                                                              categories=categories,
                                                                              output=output)
        return report(output, keyword='history', data=remove_callable(history))
    else:
        return report(output, _MSG_NOT_IMPLEMENTED)


def _api_get_files(name, output, kwargs):
    """ API: accepts output, value(=nzo_id) """
    value = kwargs.get('value')
    if value:
        return report(output, keyword='files', data=build_file_list(value))
    else:
        return report(output, _MSG_NO_VALUE)


def _api_addurl(names, output, kwargs):
    """ API: accepts name, output, pp, script, cat, priority, nzbname """
    pp = kwargs.get('pp')
    script = kwargs.get('script')
    cat = kwargs.get('cat')
    priority = kwargs.get('priority')
    nzbnames = kwargs.get('nzbname')
    if not isinstance(names, list):
        names = [names]
    if not isinstance(nzbnames, list):
        nzbnames = [nzbnames]

    nzo_ids = []
    for n in xrange(len(names)):
        name = names[n]
        if n < len(nzbnames):
            nzbname = nzbnames[n]
        else:
            nzbname = ''

        if name:
            name = name.strip()
        if name:
            nzo_ids.append(sabnzbd.add_url(name, pp, script, cat, priority, nzbname))

    if len(names) > 0:
        return report(output, keyword='', data={'status': True, 'nzo_ids': nzo_ids}, compat=True)
    else:
        logging.info('API-call addurl: no files retrieved from %s', names)
        return report(output, _MSG_NO_VALUE)


def _api_pause(name, output, kwargs):
    """ API: accepts output """
    scheduler.plan_resume(0)
    Downloader.do.pause()
    return report(output)


def _api_resume(name, output, kwargs):
    """ API: accepts output """
    scheduler.plan_resume(0)
    sabnzbd.unpause_all()
    return report(output)


def _api_shutdown(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.halt()
    cherrypy.engine.exit()
    sabnzbd.SABSTOP = True
    return report(output)


def _api_warnings(name, output, kwargs):
    """ API: accepts name, output """
    if name == 'clear':
        return report(output, keyword="warnings", data=sabnzbd.GUIHANDLER.clear())
    elif name == 'show':
        return report(output, keyword="warnings", data=sabnzbd.GUIHANDLER.content())
    elif name:
        return report(output, _MSG_NOT_IMPLEMENTED)
    return report(output, keyword="warnings", data=sabnzbd.GUIHANDLER.content())


def _api_get_cats(name, output, kwargs):
    """ API: accepts output """
    return report(output, keyword="categories", data=list_cats(False))


def _api_get_scripts(name, output, kwargs):
    """ API: accepts output """
    data = [unicoder(val) for val in list_scripts()]
    return report(output, keyword="scripts", data=data)


def _api_version(name, output, kwargs):
    """ API: accepts output """
    return report(output, keyword='version', data=sabnzbd.__version__)


def _api_auth(name, output, kwargs):
    """ API: accepts output """
    auth = 'None'
    if not cfg.disable_key():
        auth = 'badkey'
        key = kwargs.get('key', '')
        if not key:
            auth = 'apikey'
        else:
            if key == cfg.nzb_key():
                auth = 'nzbkey'
            if key == cfg.api_key():
                auth = 'apikey'
    elif cfg.username() and cfg.password():
        auth = 'login'
    return report(output, keyword='auth', data=auth)


def _api_restart(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.halt()
    cherrypy.engine.restart()
    return report(output)


def _api_restart_repair(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.request_repair()
    sabnzbd.halt()
    cherrypy.engine.restart()
    return report(output)


def _api_disconnect(name, output, kwargs):
    """ API: accepts output """
    Downloader.do.disconnect()
    return report(output)


def _api_osx_icon(name, output, kwargs):
    """ API: accepts output, value """
    value = kwargs.get('value', '1').strip()
    cfg.osx_menu.set(value != '0')
    return report(output)


def _api_rescan(name, output, kwargs):
    """ API: accepts output """
    scan_jobs(all=False, action=True)
    return report(output)


def _api_eval_sort(name, output, kwargs):
    """ API: evaluate sorting expression """
    import sabnzbd.tvsort
    name = kwargs.get('name', '')
    value = kwargs.get('value', '')
    title = kwargs.get('title')
    multipart = kwargs.get('movieextra', '')
    path = sabnzbd.tvsort.eval_sort(value, title, name, multipart)
    if path is None:
        return report(output, _MSG_NOT_IMPLEMENTED)
    else:
        return report(output, keyword='result', data=path)


def _api_watched_now(name, output, kwargs):
    """ API: accepts output """
    sabnzbd.dirscanner.dirscan()
    return report(output)


def _api_resume_pp(name, output, kwargs):
    """ API: accepts output """
    PostProcessor.do.paused = False
    return report(output)


def _api_pause_pp(name, output, kwargs):
    """ API: accepts output """
    PostProcessor.do.paused = True
    return report(output)


def _api_rss_now(name, output, kwargs):
    """ API: accepts output """
    # Run RSS scan async, because it can take a long time
    scheduler.force_rss()
    return report(output)


def _api_retry_all(name, output, kwargs):
    """ API: Retry all failed items in History """
    return report(output, keyword='status', data=retry_all_jobs)


def _api_reset_quota(name, output, kwargs):
    """ Reset quota left """
    BPSMeter.do.reset_quota(force=True)


def _api_test_email(name, output, kwargs):
    """ API: send a test email, return result """
    logging.info("Sending test email")
    pack = {}
    pack['download'] = ['action 1', 'action 2']
    pack['unpack'] = ['action 1', 'action 2']
    res = sabnzbd.emailer.endjob(u'I had a d\xe8ja vu', 'unknown', True,
                                 os.path.normpath(os.path.join(cfg.complete_dir.get_path(), u'/unknown/I had a d\xe8ja vu')),
                                 123 * MEBI, None, pack, 'my_script', u'Line 1\nLine 2\nLine 3\nd\xe8ja vu\n', 0,
                                 test=kwargs)
    if res == 'Email succeeded':
        res = None
    return report(output, error=res)


def _api_test_notif(name, output, kwargs):
    """ API: send a test to Notification Center, return result """
    logging.info("Sending test notification")
    res = sabnzbd.growler.send_notification_center('SABnzbd', T('Test Notification'), 'other')
    return report(output, error=res)


def _api_test_growl(name, output, kwargs):
    """ API: send a test Growl notification, return result """
    logging.info("Sending Growl notification")
    res = sabnzbd.growler.send_growl('SABnzbd', T('Test Notification'), 'other', test=kwargs)
    return report(output, error=res)


def _api_test_osd(name, output, kwargs):
    """ API: send a test OSD notification, return result """
    logging.info("Sending OSD notification")
    res = sabnzbd.growler.send_notify_osd('SABnzbd', T('Test Notification'))
    return report(output, error=res)


def _api_test_prowl(name, output, kwargs):
    """ API: send a test Prowl notification, return result """
    logging.info("Sending Prowl notification")
    res = sabnzbd.growler.send_prowl('SABnzbd', T('Test Notification'), 'other', force=True, test=kwargs)
    return report(output, error=res)


def _api_test_pushover(name, output, kwargs):
    """ API: send a test Pushover notification, return result """
    logging.info("Sending Pushover notification")
    res = sabnzbd.growler.send_pushover('SABnzbd', T('Test Notification'), 'other', force=True, test=kwargs)
    return report(output, error=res)


def _api_test_pushbullet(name, output, kwargs):
    """ API: send a test Pushbullet notification, return result """
    logging.info("Sending Pushbullet notification")
    res = sabnzbd.growler.send_pushbullet('SABnzbd', T('Test Notification'), 'other', force=True, test=kwargs)
    return report(output, error=res)


def _api_undefined(name, output, kwargs):
    """ API: accepts output """
    return report(output, _MSG_NOT_IMPLEMENTED)


def _api_browse(name, output, kwargs):
    """ Return tree of local path """
    compact = kwargs.get('compact')
    if compact and compact == '1':
        paths = []
        name = platform_encode(kwargs.get('term', ''))
        paths = [entry['path'] for entry in folders_at_path(os.path.dirname(name)) if 'path' in entry]
        return report(output, keyword='', data=paths)
    else:
        name = platform_encode(name)
        paths = folders_at_path(name, True)
        return report(output, keyword='paths', data=paths)


def _api_config(name, output, kwargs):
    """ API: Dispatcher for "config" """
    return _api_config_table.get(name, (_api_config_undefined, 2))[0](output, kwargs)


def _api_config_speedlimit(output, kwargs):
    """ API: accepts output, value(=speed) """
    value = kwargs.get('value')
    if not value:
        value = '0'
    Downloader.do.limit_speed(value)
    return report(output)


def _api_config_get_speedlimit(output, kwargs):
    """ API: accepts output """
    return report(output, keyword='speedlimit', data=Downloader.do.get_limit())


def _api_config_set_colorscheme(output, kwargs):
    """ API: accepts output, value(=color for primary), value2(=color for secondary) """
    value = kwargs.get('value')
    value2 = kwargs.get('value2')
    if value:
        cfg.web_color.set(value)
    if value2:
        cfg.web_color2.set(value2)
    if value or value2:
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE)


def _api_config_set_pause(output, kwargs):
    """ API: accepts output, value(=pause interval) """
    value = kwargs.get('value')
    scheduler.plan_resume(int_conv(value))
    return report(output)


def _api_config_set_apikey(output, kwargs):
    """ API: accepts output """
    cfg.api_key.set(config.create_api_key())
    config.save_config()
    return report(output, keyword='apikey', data=cfg.api_key())


def _api_config_set_nzbkey(output, kwargs):
    """ API: accepts output """
    cfg.nzb_key.set(config.create_api_key())
    config.save_config()
    return report(output, keyword='nzbkey', data=cfg.nzb_key())


def _api_config_test_server(output, kwargs):
    """ API: accepts output, server-params """
    result, msg = test_nntp_server_dict(kwargs)
    response = {'result': result, 'message': msg}
    if output:
        return report(output, data=response)
    else:
        return msg


def _api_config_undefined(output, kwargs):
    """ API: accepts output """
    return report(output, _MSG_NOT_IMPLEMENTED)


def _api_server_stats(name, output, kwargs):
    """ API: accepts output """
    sum_t, sum_m, sum_w, sum_d = BPSMeter.do.get_sums()
    stats = {'total': sum_t, 'month': sum_m, 'week': sum_w, 'day': sum_d}

    stats['servers'] = {}
    for svr in config.get_servers():
        t, m, w, d = BPSMeter.do.amounts(svr)
        stats['servers'][svr] = {'total': t or 0, 'month': m or 0, 'week': w or 0, 'day': d or 0}

    return report(output, keyword='', data=stats)


##############################################################################
_api_table = {
    'server_stats': (_api_server_stats, 2),
    'get_config': (_api_get_config, 3),
    'set_config': (_api_set_config, 3),
    'del_config': (_api_del_config, 3),
    'qstatus': (_api_qstatus, 2),
    'queue': (_api_queue, 2),
    'options': (_api_options, 2),
    'translate': (_api_translate, 2),
    'addfile': (_api_addfile, 1),
    'retry': (_api_retry, 2),
    'addlocalfile': (_api_addlocalfile, 1),
    'switch': (_api_switch, 2),
    'change_cat': (_api_change_cat, 2),
    'change_script': (_api_change_script, 2),
    'change_opts': (_api_change_opts, 2),
    'fullstatus': (_api_fullstatus, 2),
    'history': (_api_history, 2),
    'get_files': (_api_get_files, 2),
    'addurl': (_api_addurl, 1),
    'addid': (_api_addurl, 1),
    'pause': (_api_pause, 2),
    'resume': (_api_resume, 2),
    'shutdown': (_api_shutdown, 3),
    'warnings': (_api_warnings, 2),
    'config': (_api_config, 2),
    'get_cats': (_api_get_cats, 2),
    'get_scripts': (_api_get_scripts, 2),
    'version': (_api_version, 1),
    'auth': (_api_auth, 1),
    'restart': (_api_restart, 3),
    'restart_repair': (_api_restart_repair, 2),
    'disconnect': (_api_disconnect, 2),
    'osx_icon': (_api_osx_icon, 3),
    'rescan': (_api_rescan, 2),
    'eval_sort': (_api_eval_sort, 2),
    'watched_now': (_api_watched_now, 2),
    'resume_pp': (_api_resume_pp, 2),
    'pause_pp': (_api_pause_pp, 2),
    'rss_now': (_api_rss_now, 2),
    'browse': (_api_browse, 2),
    'retry_all': (_api_retry_all, 2),
    'reset_quota': (_api_reset_quota, 2),
    'test_email': (_api_test_email, 2),
    'test_notif': (_api_test_notif, 2),
    'test_growl': (_api_test_growl, 2),
    'test_osd': (_api_test_osd, 2),
    'test_pushover': (_api_test_pushover, 2),
    'test_pushbullet': (_api_test_pushbullet, 2),
    'test_prowl': (_api_test_prowl, 2)
}

_api_queue_table = {
    'delete': (_api_queue_delete, 2),
    'delete_nzf': (_api_queue_delete_nzf, 2),
    'rename': (_api_queue_rename, 2),
    'change_complete_action': (_api_queue_change_complete_action, 2),
    'purge': (_api_queue_purge, 2),
    'pause': (_api_queue_pause, 2),
    'resume': (_api_queue_resume, 2),
    'priority': (_api_queue_priority, 2),
    'sort': (_api_queue_sort, 2),
    'rating': (_api_queue_rating, 2)
}

_api_config_table = {
    'speedlimit': (_api_config_speedlimit, 2),
    'set_speedlimit': (_api_config_speedlimit, 2),
    'get_speedlimit': (_api_config_get_speedlimit, 2),
    'set_colorscheme': (_api_config_set_colorscheme, 2),
    'set_pause': (_api_config_set_pause, 2),
    'set_apikey': (_api_config_set_apikey, 3),
    'set_nzbkey': (_api_config_set_nzbkey, 3),
    'test_server': (_api_config_test_server, 2)
}


def api_level(cmd, name):
    """ Return access level required for this API call """
    if cmd in _api_table:
        return _api_table[cmd][1]
    if name == 'queue' and cmd in _api_queue_table:
        return _api_queue_table[cmd][1]
    if name == 'config' and cmd in _api_config_table:
        return _api_config_table[cmd][1]
    return 4


def report(output, error=None, keyword='value', data=None, callback=None, compat=False):
    """ Report message in json, xml or plain text
        If error is set, only an status/error report is made.
        If no error and no data, only a status report is made.
        Else, a data report is made (optional 'keyword' for outer XML section).
        'compat' is a special case for compatibility for ascii ouput
    """
    if output == 'json':
        content = "application/json;charset=UTF-8"
        if error:
            info = {'status': False, 'error': error}
        elif data is None:
            info = {'status': True}
        else:
            if hasattr(data, '__iter__') and not keyword:
                info = data
            else:
                info = {keyword: data}
        response = json.dumps(info)
        if callback:
            response = '%s(%s)' % (callback, response)

    elif output == 'xml':
        if not keyword:
            # xml always needs an outer keyword, even when json doesn't
            keyword = 'result'
        content = "text/xml"
        xmlmaker = xml_factory()
        if error:
            status_str = xmlmaker.run('result', {'status': False, 'error': error})
        elif data is None:
            status_str = xmlmaker.run('result', {'status': True})
        else:
            status_str = xmlmaker.run(keyword, data)
        response = '<?xml version="1.0" encoding="UTF-8" ?>\n%s\n' % status_str

    else:
        content = "text/plain"
        if error:
            response = "error: %s\n" % error
        elif compat or data is None:
            response = 'ok\n'
        else:
            if type(data) in (list, tuple):
                # Special handling for list/tuple (backward compatibility)
                data = [str(val) for val in data]
                data = ' '.join(data)
            if isinstance(data, unicode):
                response = u'%s\n' % data
            else:
                response = '%s\n' % str(data)

    cherrypy.response.headers['Content-Type'] = content
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return response


class xml_factory(object):
    """ Recursive xml string maker. Feed it a mixed tuple/dict/item object and will output into an xml string
        Current limitations:
            In Two tiered lists hard-coded name of "item": <cat_list><item> </item></cat_list>
            In Three tiered lists hard-coded name of "slot": <tier1><slot><tier2> </tier2></slot></tier1>
    """

    def __init__(self):
        self.__text = ''

    def _tuple(self, keyw, lst):
        text = []
        for item in lst:
            text.append(self.run(keyw, item))
        return ''.join(text)

    def _dict(self, keyw, lst):
        text = []
        for key in lst.keys():
            text.append(self.run(key, lst[key]))
        if keyw:
            return '<%s>%s</%s>\n' % (keyw, ''.join(text), keyw)
        else:
            return ''

    def _list(self, keyw, lst):
        text = []
        for cat in lst:
            if isinstance(cat, dict):
                text.append(self._dict(plural_to_single(keyw, 'slot'), cat))
            elif isinstance(cat, list):
                text.append(self._list(plural_to_single(keyw, 'list'), cat))
            elif isinstance(cat, tuple):
                text.append(self._tuple(plural_to_single(keyw, 'tuple'), cat))
            else:
                if not isinstance(cat, basestring):
                    cat = str(cat)
                name = plural_to_single(keyw, 'item')
                text.append('<%s>%s</%s>\n' % (name, xml_name(cat, encoding='utf-8'), name))
        if keyw:
            return '<%s>%s</%s>\n' % (keyw, ''.join(text), keyw)
        else:
            return ''

    def run(self, keyw, lst):
        if isinstance(lst, dict):
            text = self._dict(keyw, lst)
        elif isinstance(lst, list):
            text = self._list(keyw, lst)
        elif isinstance(lst, tuple):
            text = self._tuple(keyw, lst)
        elif keyw:
            text = '<%s>%s</%s>\n' % (keyw, xml_name(lst, encoding='utf-8'), keyw)
        else:
            text = ''
        return text


def handle_server_api(output, kwargs):
    """ Special handler for API-call 'set_config' [servers] """
    name = kwargs.get('keyword')
    if not name:
        name = kwargs.get('name')

    if name:
        server = config.get_config('servers', name)
        if server:
            server.set_dict(kwargs)
            old_name = name
        else:
            config.ConfigServer(name, kwargs)
            old_name = None
        Downloader.do.update_server(old_name, name)
    return name


def handle_rss_api(output, kwargs):
    """ Special handler for API-call 'set_config' [rss] """
    name = kwargs.get('keyword')
    if not name:
        name = kwargs.get('name')
    if not name:
        return None

    feed = config.get_config('rss', name)
    if feed:
        feed.set_dict(kwargs)
    else:
        config.ConfigRSS(name, kwargs)
    return name


def handle_cat_api(output, kwargs):
    """ Special handler for API-call 'set_config' [categories] """
    name = kwargs.get('keyword')
    if not name:
        name = kwargs.get('name')
    if not name:
        return None

    feed = config.get_config('categories', name)
    if feed:
        feed.set_dict(kwargs)
    else:
        config.ConfigCat(name, kwargs)
    return name


def build_queue(web_dir=None, root=None, verbose=False, prim=True, webdir='', verbose_list=None,
                dictionary=None, history=False, start=None, limit=None, dummy2=None, trans=False, output=None,
                search=None):
    if output:
        converter = unicoder
    else:
        converter = xml_name

    if not verbose_list:
        verbose_list = []
    if dictionary:
        dictn = dictionary
    else:
        dictn = []
    # build up header full of basic information
    info, pnfo_list, bytespersec = build_header(prim, webdir, search=search)
    info['isverbose'] = verbose
    cookie = cherrypy.request.cookie
    if 'queue_details' in cookie:
        info['queue_details'] = str(int_conv(cookie['queue_details'].value))
    else:
        info['queue_details'] = '0'

    if cfg.refresh_rate() > 0:
        info['refresh_rate'] = str(cfg.refresh_rate())
    else:
        info['refresh_rate'] = ''

    datestart = datetime.datetime.now()

    info['script_list'] = list_scripts()
    info['cat_list'] = list_cats(output is None)

    info['rating_enable'] = bool(cfg.rating_enable())

    n = 0
    found_active = False
    running_bytes = 0
    slotinfo = []
    nzo_ids = []

    limit = int_conv(limit)
    start = int_conv(start)

    if history:
        # Collect nzo's from the history that are downloaded but not finished (repairing, extracting)
        slotinfo = format_history_for_queue()
        # if the specified start value is greater than the amount of history items, do no include the history (used for paging the queue)
        if len(slotinfo) < start:
            slotinfo = []
    else:
        slotinfo = []

    info['noofslots'] = len(pnfo_list) + len(slotinfo)

    info['start'] = start
    info['limit'] = limit
    info['finish'] = info['start'] + info['limit']
    if info['finish'] > info['noofslots']:
        info['finish'] = info['noofslots']

    for pnfo in pnfo_list:
        repair = pnfo[PNFO_REPAIR_FIELD]
        unpack = pnfo[PNFO_UNPACK_FIELD]
        delete = pnfo[PNFO_DELETE_FIELD]
        script = pnfo[PNFO_SCRIPT_FIELD]
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        cat = pnfo[PNFO_EXTRA_FIELD1]
        if not cat:
            cat = 'None'
        filename = pnfo[PNFO_FILENAME_FIELD]
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD]
        bytes = pnfo[PNFO_BYTES_FIELD]
        average_date = pnfo[PNFO_AVG_DATE_FIELD]
        status = pnfo[PNFO_STATUS_FIELD]
        priority = pnfo[PNFO_PRIORITY_FIELD]
        mbleft = (bytesleft / MEBI)
        mb = (bytes / MEBI)
        missing = pnfo[PNFO_MISSING_FIELD]
        if verbose or verbose_list:
            finished_files = pnfo[PNFO_FINISHED_FILES_FIELD]
            active_files = pnfo[PNFO_ACTIVE_FILES_FIELD]
            queued_files = pnfo[PNFO_QUEUED_FILES_FIELD]

        nzo_ids.append(nzo_id)

        slot = {'index': n, 'nzo_id': str(nzo_id)}
        unpackopts = sabnzbd.opts_to_pp(repair, unpack, delete)

        slot['unpackopts'] = str(unpackopts)
        if script:
            slot['script'] = script
        else:
            slot['script'] = 'None'
        slot['filename'] = converter(filename)
        slot['cat'] = cat
        slot['mbleft'] = "%.2f" % mbleft
        slot['mb'] = "%.2f" % mb
        if not output:
            slot['mb_fmt'] = locale.format('%d', int(mb), True)
            slot['mbdone_fmt'] = locale.format('%d', int(mb - mbleft), True)
        slot['size'] = format_bytes(bytes)
        slot['sizeleft'] = format_bytes(bytesleft)
        if not Downloader.do.paused and status not in (Status.PAUSED, Status.FETCHING) and not found_active:
            if status == Status.CHECKING:
                slot['status'] = Status.CHECKING
            else:
                slot['status'] = Status.DOWNLOADING
            found_active = True
        else:
            slot['status'] = "%s" % (status)
        if priority == TOP_PRIORITY:
            slot['priority'] = 'Force'
        elif priority == REPAIR_PRIORITY:
            slot['priority'] = 'Repair'
        elif priority == HIGH_PRIORITY:
            slot['priority'] = 'High'
        elif priority == LOW_PRIORITY:
            slot['priority'] = 'Low'
        else:
            slot['priority'] = 'Normal'
        if mb == mbleft:
            slot['percentage'] = "0"
        else:
            slot['percentage'] = "%s" % (int(((mb - mbleft) / mb) * 100))
        slot['missing'] = missing

        if (Downloader.do.paused or Downloader.do.postproc or status not in (Status.DOWNLOADING, Status.QUEUED)) \
           and priority != TOP_PRIORITY:
            slot['timeleft'] = '0:00:00'
            slot['eta'] = 'unknown'
        else:
            running_bytes += bytesleft
            slot['timeleft'] = calc_timeleft(running_bytes, bytespersec)
            try:
                datestart = datestart + datetime.timedelta(seconds=bytesleft / bytespersec)
                # new eta format: 16:00 Fri 07 Feb
                slot['eta'] = '%s' % datestart.strftime(time_format('%H:%M %a %d %b'))
            except:
                datestart = datetime.datetime.now()
                slot['eta'] = 'unknown'

        if status == Status.GRABBING:
            slot['avg_age'] = '---'
        else:
            slot['avg_age'] = calc_age(average_date, bool(trans))

        rating = Rating.do.get_rating_by_nzo(nzo_id)
        slot['has_rating'] = rating is not None
        if rating:
            slot['rating_avg_video'] = rating.avg_video
            slot['rating_avg_audio'] = rating.avg_audio

        slot['verbosity'] = ""
        if web_dir:
            finished = []
            active = []
            queued = []
            # this will list files in the xml output, wanted yes/no?
            if verbose or nzo_id in verbose_list:
                slot['verbosity'] = "True"
                for tup in finished_files:
                    bytes_left, bytes, fn, date = tup
                    fn = converter(fn)

                    age = calc_age(date)

                    line = {'filename': fn,
                            'mbleft': "%.2f" % (bytes_left / MEBI),
                            'mb': "%.2f" % (bytes / MEBI),
                            'size': format_bytes(bytes),
                            'sizeleft': format_bytes(bytes_left),
                            'age': age}
                    finished.append(line)

                for tup in active_files:
                    bytes_left, bytes, fn, date, nzf_id = tup
                    fn = converter(fn)

                    age = calc_age(date)

                    line = {'filename': fn,
                            'mbleft': "%.2f" % (bytes_left / MEBI),
                            'mb': "%.2f" % (bytes / MEBI),
                            'size': format_bytes(bytes),
                            'sizeleft': format_bytes(bytes_left),
                            'nzf_id': nzf_id,
                            'age': age}
                    active.append(line)

                for tup in queued_files:
                    _set, bytes_left, bytes, fn, date = tup
                    fn = converter(fn)
                    _set = converter(_set)

                    age = calc_age(date)

                    line = {'filename': fn, 'set': _set,
                            'mbleft': "%.2f" % (bytes_left / MEBI),
                            'mb': "%.2f" % (bytes / MEBI),
                            'size': format_bytes(bytes),
                            'sizeleft': format_bytes(bytes_left),
                            'age': age}
                    queued.append(line)

            slot['finished'] = finished
            slot['active'] = active
            slot['queued'] = queued

        if (start <= n and n < start + limit) or not limit:
            slotinfo.append(slot)
        n += 1

    if slotinfo:
        info['slots'] = slotinfo
    else:
        info['slots'] = []
        verbose_list = []

    # Paging of the queue using limit and/or start values
    if limit > 0:
        try:
            if start > 0:
                if start > len(pnfo_list):
                    pnfo_list = []
                else:
                    end = start + limit
                    if start + limit > len(pnfo_list):
                        end = len(pnfo_list)
                    pnfo_list = pnfo_list[start:end]
            else:
                if not limit > len(pnfo_list):
                    pnfo_list = pnfo_list[:limit]
        except:
            pass

    return info, pnfo_list, bytespersec, verbose_list, dictn


def fast_queue():
    """ Return paused, bytes_left, bpsnow, time_left """
    bytes_left = NzbQueue.do.remaining()
    paused = Downloader.do.paused
    bpsnow = BPSMeter.do.get_bps()
    time_left = calc_timeleft(bytes_left, bpsnow)
    return paused, bytes_left, bpsnow, time_left


def qstatus_data():
    """ Build up the queue status as a nested object and output as a JSON object """

    qnfo = NzbQueue.do.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    jobs = []
    bytesleftprogess = 0
    bpsnow = BPSMeter.do.get_bps()
    for pnfo in pnfo_list:
        filename = pnfo[PNFO_FILENAME_FIELD]
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
        bytesleftprogess += pnfo[PNFO_BYTES_LEFT_FIELD]
        bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        jobs.append({"id": nzo_id,
                        "mb": bytes,
                        "mbleft": bytesleft,
                        "filename": unicoder(filename),
                        "timeleft": calc_timeleft(bytesleftprogess, bpsnow)})

    state = "IDLE"
    if Downloader.do.paused:
        state = Status.PAUSED
    elif qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI > 0:
        state = Status.DOWNLOADING
    
    speed_limit = Downloader.do.get_limit()
    if speed_limit <= 0:
        speed_limit = 100

    status = {
        "state": state,
        "pp_active": not PostProcessor.do.empty(),
        "paused": Downloader.do.paused,
        "pause_int": scheduler.pause_int(),
        "kbpersec": bpsnow / KIBI,
        "speed": to_units(bpsnow, dec_limit=1),
        "mbleft": qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI,
        "mb": qnfo[QNFO_BYTES_FIELD] / MEBI,
        "noofslots": len(pnfo_list),
        "noofslots_total": qnfo[QNFO_Q_FULLSIZE_FIELD],
        "have_warnings": str(sabnzbd.GUIHANDLER.count()),
        "diskspace1": diskfree(cfg.download_dir.get_path()),
        "diskspace2": diskfree(cfg.complete_dir.get_path()),
        "timeleft": calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], bpsnow),
        "loadavg": loadavg(),
        "speedlimit": "{1:0.{0}f}".format(int(speed_limit % 1 > 0), speed_limit),
        "speedlimit_abs": str(Downloader.do.get_limit_abs() or ''),
        "jobs": jobs
    }
    return status


def build_file_list(id):
    qnfo = NzbQueue.do.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    jobs = []
    for pnfo in pnfo_list:
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        if nzo_id == id:
            finished_files = pnfo[PNFO_FINISHED_FILES_FIELD]
            active_files = pnfo[PNFO_ACTIVE_FILES_FIELD]
            queued_files = pnfo[PNFO_QUEUED_FILES_FIELD]

            n = 0
            for tup in finished_files:
                bytes_left, bytes, fn, date = tup
                fn = xml_name(fn)

                age = calc_age(date)

                line = {'filename': fn,
                        'mbleft': "%.2f" % (bytes_left / MEBI),
                        'mb': "%.2f" % (bytes / MEBI),
                        'bytes': "%.2f" % bytes,
                        'age': age, 'id': str(n), 'status': 'finished'}
                jobs.append(line)
                n += 1

            for tup in active_files:
                bytes_left, bytes, fn, date, nzf_id = tup
                fn = xml_name(fn)

                age = calc_age(date)

                line = {'filename': fn,
                        'mbleft': "%.2f" % (bytes_left / MEBI),
                        'mb': "%.2f" % (bytes / MEBI),
                        'bytes': "%.2f" % bytes,
                        'nzf_id': nzf_id,
                        'age': age, 'id': str(n), 'status': 'active'}
                jobs.append(line)
                n += 1

            for tup in queued_files:
                _set, bytes_left, bytes, fn, date = tup
                fn = xml_name(fn)
                _set = xml_name(_set)

                age = calc_age(date)

                line = {'filename': fn, 'set': _set,
                        'mbleft': "%.2f" % (bytes_left / MEBI),
                        'mb': "%.2f" % (bytes / MEBI),
                        'bytes': "%.2f" % bytes,
                        'age': age, 'id': str(n), 'status': 'queued'}
                jobs.append(line)
                n += 1

    return jobs


def rss_qstatus():
    """ Return a RSS feed with the queue status """
    qnfo = NzbQueue.do.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    rss = RSS()
    rss.channel.title = "SABnzbd Queue"
    rss.channel.description = "Overview of current downloads"
    rss.channel.link = "http://%s:%s/sabnzbd/queue" % (
        cfg.cherryhost(), cfg.cherryport())
    rss.channel.language = "en"

    item = Item()
    item.title = 'Total ETA: %s - Queued: %.2f MB - Speed: %.2f kB/s' % \
                 (
                     calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], BPSMeter.do.get_bps()),
                     qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI,
                     BPSMeter.do.get_bps() / KIBI
                 )
    rss.addItem(item)

    sum_bytesleft = 0
    for pnfo in pnfo_list:
        filename = pnfo[PNFO_FILENAME_FIELD]
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
        bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
        mbleft = (bytesleft / MEBI)
        mb = (bytes / MEBI)
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]

        if mb == mbleft:
            percentage = "0%"
        else:
            percentage = "%s%%" % (int(((mb - mbleft) / mb) * 100))

        filename = xml_name(filename)
        name = u'%s (%s)' % (filename, percentage)

        item = Item()
        item.title = name
        item.link = "http://%s:%s/sabnzbd/history" % (cfg.cherryhost(), cfg.cherryport())
        item.guid = nzo_id
        status_line = []
        status_line.append('<tr>')
        # Total MB/MB left
        status_line.append('<dt>Remain/Total: %.2f/%.2f MB</dt>' % (bytesleft, bytes))
        # ETA
        sum_bytesleft += pnfo[PNFO_BYTES_LEFT_FIELD]
        status_line.append("<dt>ETA: %s </dt>" % calc_timeleft(sum_bytesleft, BPSMeter.do.get_bps()))
        status_line.append("<dt>Age: %s</dt>" % calc_age(pnfo[PNFO_AVG_DATE_FIELD]))
        status_line.append("</tr>")
        item.description = ''.join(status_line)
        rss.addItem(item)

    rss.channel.lastBuildDate = std_time(time.time())
    rss.channel.pubDate = rss.channel.lastBuildDate
    rss.channel.ttl = "1"
    return rss.write()


def options_list(output):
    return report(output, keyword='options', data={
        'yenc': sabnzbd.decoder.HAVE_YENC,
        'par2': sabnzbd.newsunpack.PAR2_COMMAND,
        'par2c': sabnzbd.newsunpack.PAR2C_COMMAND,
        'rar': sabnzbd.newsunpack.RAR_COMMAND,
        'zip': sabnzbd.newsunpack.ZIP_COMMAND,
        '7zip': sabnzbd.newsunpack.SEVEN_COMMAND,
        'nice': sabnzbd.newsunpack.NICE_COMMAND,
        'ionice': sabnzbd.newsunpack.IONICE_COMMAND,
        'ssl': sabnzbd.newswrapper.HAVE_SSL
    })


def retry_job(job, new_nzb, password):
    """ Re enter failed job in the download queue """
    if job:
        history_db = cherrypy.thread_data.history_db
        futuretype, url, pp, script, cat = history_db.get_other(job)
        if futuretype:
            sabnzbd.add_url(url, pp, script, cat)
            history_db.remove_history(job)
        else:
            path = history_db.get_path(job)
            if path:
                nzo_id = repair_job(platform_encode(path), new_nzb, password)
                history_db.remove_history(job)
                return nzo_id
    return None


def retry_all_jobs():
    """ Re enter all failed jobs in the download queue """
    history_db = cherrypy.thread_data.history_db
    return NzbQueue.do.retry_all_jobs(history_db)


def del_job_files(job_paths):
    """ Remove files of each path in the list """
    for path in job_paths:
        if path and clip_path(path).lower().startswith(cfg.download_dir.get_path().lower()):
            remove_all(path, recursive=True)


def del_hist_job(job, del_files):
    """ Remove history element """
    if job:
        path = PostProcessor.do.get_path(job)
        if path:
            PostProcessor.do.delete(job, del_files=del_files)
        else:
            history_db = cherrypy.thread_data.history_db
            path = history_db.get_path(job)
            PostProcessor.do.delete(job, del_files=del_files)
            history_db.remove_history(job)

        if path and del_files and clip_path(path).lower().startswith(cfg.download_dir.get_path().lower()):
            remove_all(path, recursive=True)
    return True


def Tspec(txt):
    """ Translate special terms """
    if txt == 'None':
        return T('None')
    elif txt in ('Default', '*'):
        return T('Default')
    else:
        return txt

_SKIN_CACHE = {}    # Stores pre-translated acronyms
# This special is to be used in interface.py for template processing
# to be passed for the $T function: so { ..., 'T' : Ttemplate, ...}
def Ttemplate(txt):
    """ Translation function for Skin texts """
    global _SKIN_CACHE
    if txt in _SKIN_CACHE:
        return _SKIN_CACHE[txt]
    else:
        tra = html_escape(Tx(SKIN_TEXT.get(txt, txt)))
        _SKIN_CACHE[txt] = tra
        return tra


def clear_trans_cache():
    """ Clean cache for skin translations """
    global _SKIN_CACHE
    dummy = _SKIN_CACHE
    _SKIN_CACHE = {}
    del dummy
    sabnzbd.WEBUI_READY = True


def build_header(prim, webdir='', search=None):
    try:
        uptime = calc_age(sabnzbd.START)
    except:
        uptime = "-"

    if prim:
        color = sabnzbd.WEB_COLOR
    else:
        color = sabnzbd.WEB_COLOR2
    if not color:
        color = ''

    header = {'T': Ttemplate, 'Tspec': Tspec, 'Tx': Ttemplate, 'version': sabnzbd.__version__,
               'paused': Downloader.do.paused or Downloader.do.postproc,
               'pause_int': scheduler.pause_int(), 'paused_all': sabnzbd.PAUSED_ALL,
               'uptime': uptime, 'color_scheme': color}
    speed_limit = Downloader.do.get_limit()
    if speed_limit <= 0:
        speed_limit = 100
    speed_limit_abs = Downloader.do.get_limit_abs()
    if speed_limit_abs <= 0:
        speed_limit_abs = ''

    free1 = diskfree(cfg.download_dir.get_path())
    free2 = diskfree(cfg.complete_dir.get_path())

    header['helpuri'] = 'http://wiki.sabnzbd.org/'
    header['diskspace1'] = "%.2f" % free1
    header['diskspace2'] = "%.2f" % free2
    header['diskspace1_norm'] = to_units(free1 * GIGI)
    header['diskspace2_norm'] = to_units(free2 * GIGI)
    header['diskspacetotal1'] = "%.2f" % disktotal(cfg.download_dir.get_path())
    header['diskspacetotal2'] = "%.2f" % disktotal(cfg.complete_dir.get_path())
    header['loadavg'] = loadavg()
    # Special formatting so only decimal points when needed
    header['speedlimit'] = "{1:0.{0}f}".format(int(speed_limit % 1 > 0), speed_limit)
    header['speedlimit_abs'] = "%s" % speed_limit_abs
    header['restart_req'] = sabnzbd.RESTART_REQ
    header['have_warnings'] = str(sabnzbd.GUIHANDLER.count())
    header['last_warning'] = sabnzbd.GUIHANDLER.last().replace('WARNING', ('WARNING:')).replace('ERROR', T('ERROR:'))
    header['active_lang'] = cfg.language()
    header['my_lcldata'] = sabnzbd.DIR_LCLDATA
    header['my_home'] = sabnzbd.DIR_HOME

    header['webdir'] = webdir
    header['pid'] = os.getpid()

    header['finishaction'] = sabnzbd.QUEUECOMPLETE
    header['nt'] = sabnzbd.WIN32
    header['darwin'] = sabnzbd.DARWIN
    header['power_options'] = sabnzbd.WIN32 or sabnzbd.DARWIN or sabnzbd.LINUX_POWER

    header['session'] = cfg.api_key()

    bytespersec = BPSMeter.do.get_bps()
    qnfo = NzbQueue.do.queue_info(search=search)

    bytesleft = qnfo[QNFO_BYTES_LEFT_FIELD]
    bytes = qnfo[QNFO_BYTES_FIELD]

    header['kbpersec'] = "%.2f" % (bytespersec / KIBI)
    header['speed'] = to_units(bytespersec, spaces=1, dec_limit=1)
    header['mbleft'] = "%.2f" % (bytesleft / MEBI)
    header['mb'] = "%.2f" % (bytes / MEBI)
    header['sizeleft'] = format_bytes(bytesleft)
    header['size'] = format_bytes(bytes)
    header['noofslots_total'] = qnfo[QNFO_Q_FULLSIZE_FIELD]

    header['quota'] = to_units(BPSMeter.do.quota)
    header['have_quota'] = bool(BPSMeter.do.quota > 0.0)
    header['left_quota'] = to_units(BPSMeter.do.left)
    header['pp_pause_event'] = sabnzbd.scheduler.pp_pause_event()

    status = ''
    if Downloader.do.paused or Downloader.do.postproc:
        status = Status.PAUSED
    elif bytespersec > 0:
        status = Status.DOWNLOADING
    else:
        status = 'Idle'
    header['status'] = status

    anfo = ArticleCache.do.cache_info()

    header['cache_art'] = str(anfo[ANFO_ARTICLE_SUM_FIELD])
    header['cache_size'] = format_bytes(anfo[ANFO_CACHE_SIZE_FIELD])
    header['cache_max'] = str(anfo[ANFO_CACHE_LIMIT_FIELD])

    header['nzb_quota'] = ''

    if sabnzbd.NEW_VERSION:
        header['new_release'], header['new_rel_url'] = sabnzbd.NEW_VERSION.split(';')
    else:
        header['new_release'] = ''
        header['new_rel_url'] = ''

    header['timeleft'] = calc_timeleft(bytesleft, bytespersec)

    try:
        datestart = datetime.datetime.now() + datetime.timedelta(seconds=bytesleft / bytespersec)
        # new eta format: 16:00 Fri 07 Feb
        header['eta'] = '%s' % datestart.strftime(time_format('%H:%M %a %d %b'))
    except:
        datestart = datetime.datetime.now()
        header['eta'] = T('unknown')

    return (header, qnfo[QNFO_PNFO_LIST_FIELD], bytespersec)


def build_history(start=None, limit=None, verbose=False, verbose_list=None, search=None, failed_only=0,
                  categories=None, output=None):

    if output:
        converter = unicoder
    else:
        converter = xml_name

    if not verbose_list:
        verbose_list = []

    limit = int_conv(limit)
    if not limit:
        limit = 1000000
    start = int_conv(start)
    failed_only = int_conv(failed_only)

    def matches_search(text, search_text):
        # Replace * with .* and ' ' with .
        search_text = search_text.strip().replace('*', '.*').replace(' ', '.*') + '.*?'
        try:
            re_search = re.compile(search_text, re.I)
        except:
            logging.error(T('Failed to compile regex for search term: %s'), search_text)
            return False
        return re_search.search(text)

    # Grab any items that are active or queued in postproc
    queue = PostProcessor.do.get_queue()

    # Filter out any items that don't match the search
    if search:
        queue = [nzo for nzo in queue if matches_search(nzo.final_name, search)]

    # Multi-page support for postproc items
    full_queue_size = len(queue)
    if start > full_queue_size:
        # On a page where we shouldn't show postproc items
        queue = []
        h_limit = limit
    else:
        try:
            if limit:
                queue = queue[start:start + limit]
            else:
                queue = queue[start:]
        except:
            pass
        # Remove the amount of postproc items from the db request for history items
        h_limit = max(limit - len(queue), 0)

    h_start = max(start - full_queue_size, 0)

    # Aquire the db instance
    try:
        history_db = cherrypy.thread_data.history_db
        close_db = False
    except:
        # Required for repairs at startup because Cherrypy isn't active yet
        history_db = get_history_handle()
        close_db = True

    # Fetch history items
    if not h_limit:
        items, fetched_items, total_items = history_db.fetch_history(h_start, 1, search, failed_only, categories)
        items = []
        fetched_items = 0
    else:
        items, fetched_items, total_items = history_db.fetch_history(h_start, h_limit, search, failed_only, categories)

    # Fetch which items should show details from the cookie
    k = []
    if verbose:
        details_show_all = True
    else:
        details_show_all = False
    cookie = cherrypy.request.cookie
    if 'history_verbosity' in cookie:
        k = cookie['history_verbosity'].value
        c_path = cookie['history_verbosity']['path']
        c_age = cookie['history_verbosity']['max-age']
        c_version = cookie['history_verbosity']['version']

        if k == 'all':
            details_show_all = True
        k = k.split(',')
    k.extend(verbose_list)

    # Reverse the queue to add items to the top (faster than insert)
    items.reverse()

    # Add the postproc items to the top of the history
    items = get_active_history(queue, items)

    # Unreverse the queue
    items.reverse()

    retry_folders = []
    for item in items:
        for key in item:
            value = item[key]
            if isinstance(value, basestring):
                item[key] = converter(value)

        if details_show_all:
            item['show_details'] = 'True'
        else:
            if item['nzo_id'] in k:
                item['show_details'] = 'True'
            else:
                item['show_details'] = ''
        if item['bytes']:
            item['size'] = format_bytes(item['bytes'])
        else:
            item['size'] = ''
        if 'loaded' not in item:
            item['loaded'] = False

        path = platform_encode(item.get('path', ''))

        item['retry'] = int(bool(item.get('status') == 'Failed' and
                                 path and
                                 path not in retry_folders and
                                 starts_with_path(path, cfg.download_dir.get_path()) and
                                 os.path.exists(path)) and
                                 not bool(globber(os.path.join(path, JOB_ADMIN), 'SABnzbd_n*'))
                            )
        if item['report'] == 'future':
            item['retry'] = True

        if item['retry']:
            retry_folders.append(path)

        if Rating.do:
            rating = Rating.do.get_rating_by_nzo(item['nzo_id'])
        else:
            rating = None
        item['has_rating'] = rating is not None
        if rating:
            item['rating_avg_video'] = rating.avg_video
            item['rating_avg_audio'] = rating.avg_audio
            item['rating_avg_vote_up'] = rating.avg_vote_up
            item['rating_avg_vote_down'] = rating.avg_vote_down
            item['rating_user_video'] = rating.user_video
            item['rating_user_audio'] = rating.user_audio
            item['rating_user_vote'] = rating.user_vote

    total_items += full_queue_size
    fetched_items = len(items)

    if close_db:
        history_db.close()

    return (items, fetched_items, total_items)


def format_history_for_queue():
    """ Retrieves the information on currently active history items, and formats them for displaying in the queue """
    slotinfo = []
    history_items = get_active_history()

    for item in history_items:
        slot = {'nzo_id': item['nzo_id'],
                'bookmark': '', 'filename': xml_name(item['name']), 'loaded': False,
                'stages': item['stage_log'], 'status': item['status'], 'bytes': item['bytes'],
                'size': item['size']}
        slotinfo.append(slot)

    return slotinfo


def get_active_history(queue=None, items=None):
    """ Get the currently in progress and active history queue. """
    if items is None:
        items = []
    if queue is None:
        queue = PostProcessor.do.get_queue()

    for nzo in queue:
        history = build_history_info(nzo)
        item = {}
        item['completed'], item['name'], item['nzb_name'], item['category'], item['pp'], item['script'], item['report'], \
            item['url'], item['status'], item['nzo_id'], item['storage'], item['path'], item['script_log'], \
            item['script_line'], item['download_time'], item['postproc_time'], item['stage_log'], \
            item['downloaded'], item['completeness'], item['fail_message'], item['url_info'], item['bytes'], \
            dummy, dummy = history
        item['action_line'] = nzo.action_line
        item = unpack_history_info(item)

        item['loaded'] = nzo.pp_active
        if item['bytes']:
            item['size'] = format_bytes(item['bytes'])
        else:
            item['size'] = ''

        # Queue display needs Unicode instead of UTF-8
        for kw in item:
            if isinstance(item[kw], str):
                item[kw] = item[kw].decode('utf-8')

        items.append(item)

    return items


def format_bytes(bytes):
    b = to_units(bytes)
    if b == '':
        return b
    else:
        return b + 'B'


def calc_timeleft(bytesleft, bps):
    """ Calculate the time left in the format HH:MM:SS """
    try:
        totalseconds = int(bytesleft / bps)
        minutes, seconds = divmod(totalseconds, 60)
        hours, minutes = divmod(minutes, 60)
        if minutes < 10:
            minutes = '0%s' % minutes
        if seconds < 10:
            seconds = '0%s' % seconds
        return '%s:%s:%s' % (hours, minutes, seconds)
    except:
        return '0:00:00'


def calc_age(date, trans=False):
    """ Calculate the age difference between now and date.
        Value is returned as either days, hours, or minutes.
        When 'trans' is True, time symbols will be translated.
    """
    if trans:
        d = T('d')  # : Single letter abbreviation of day
        h = T('h')  # : Single letter abbreviation of hour
        m = T('m')  # : Single letter abbreviation of minute
    else:
        d = 'd'
        h = 'h'
        m = 'm'
    try:
        now = datetime.datetime.now()
        # age = str(now - date).split(".")[0] #old calc_age

        # time difference
        dage = now - date
        seconds = dage.seconds
        # only one value should be returned
        # if it is less than 1 day then it returns in hours, unless it is less than one hour where it returns in minutes
        if dage.days:
            age = '%s%s' % (dage.days, d)
        elif seconds / 3600:
            age = '%s%s' % (seconds / 3600, h)
        else:
            age = '%s%s' % (seconds / 60, m)
    except:
        age = "-"

    return age


def std_time(when):
    # Fri, 16 Nov 2007 16:42:01 GMT +0100
    item = time.strftime(time_format('%a, %d %b %Y %H:%M:%S'), time.localtime(when))
    item += " GMT %+05d" % (-time.timezone / 36)
    return item


def list_scripts(default=False):
    """ Return a list of script names, optionally with 'Default' added """
    lst = []
    path = cfg.script_dir.get_path()
    if path and os.access(path, os.R_OK):
        for script in globber_full(path):
            if os.path.isfile(script):
                if (sabnzbd.WIN32 and os.path.splitext(script)[1].lower() in PATHEXT and
                                      not (win32api.GetFileAttributes(script) & win32file.FILE_ATTRIBUTE_HIDDEN)) or \
                   script.endswith('.py') or \
                   (not sabnzbd.WIN32 and os.access(script, os.X_OK) and not os.path.basename(script).startswith('.')):
                    lst.append(os.path.basename(script))
        lst.insert(0, 'None')
        if default:
            lst.insert(0, 'Default')
    return lst


def list_cats(default=True):
    """ Return list of categories, when default==False use '*' for Default category """
    lst = sorted(config.get_categories().keys())
    if default:
        lst.remove('*')
        lst.insert(0, 'Default')
    return lst


def remove_callable(dic):
    """ Remove all callable items from dictionary """
    for key, value in dic.items():
        if callable(value):
            del dic[key]
    return dic


_PLURAL_TO_SINGLE = {
    'categories': 'category',
    'servers': 'server',
    'rss': 'feed',
    'scripts': 'script',
    'warnings': 'warning',
    'files': 'file',
    'jobs': 'job'
}


def plural_to_single(kw, def_kw=''):
    try:
        return _PLURAL_TO_SINGLE[kw]
    except KeyError:
        return def_kw


def del_from_section(kwargs):
    """ Remove keyword in section """
    section = kwargs.get('section', '')
    if section in ('servers', 'rss', 'categories'):
        keyword = kwargs.get('keyword')
        if keyword:
            item = config.get_config(section, keyword)
            if item:
                item.delete()
                del item
                config.save_config()
                if section == 'servers':
                    Downloader.do.update_server(keyword, None)
        return True
    else:
        return False


def history_remove_failed():
    """ Remove all failed jobs from history, including files """
    logging.info('Scheduled removal of all failed jobs')
    history_db = get_history_handle()
    del_job_files(history_db.get_failed_paths())
    history_db.remove_failed()
    history_db.close()
    del history_db


def history_remove_completed():
    """ Remove all completed jobs from history """
    logging.info('Scheduled removal of all completed jobs')
    history_db = get_history_handle()
    history_db.remove_completed()
    history_db.close()
    del history_db
