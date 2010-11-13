#!/usr/bin/python -OO
# Copyright 2008-2010 The SABnzbd-Team <team@sabnzbd.org>
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
import cherrypy


import sabnzbd
from sabnzbd.constants import *
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.downloader as downloader
import sabnzbd.nzbqueue as nzbqueue
import sabnzbd.nzbstuff as nzbstuff
import sabnzbd.scheduler as scheduler
from sabnzbd.skintext import SKIN_TEXT

from sabnzbd.utils.rsslib import RSS, Item
from sabnzbd.utils.json import JsonWriter
from sabnzbd.misc import loadavg, to_units, diskfree, disktotal, get_ext, \
                         get_filename, int_conv, globber, time_format
from sabnzbd.encoding import xml_name, unicoder, special_fixer, platform_encode
from sabnzbd.postproc import PostProcessor
from sabnzbd.articlecache import ArticleCache
from sabnzbd.utils.servertests import test_nntp_server_dict
from sabnzbd.newzbin import Bookmarks
from sabnzbd.bpsmeter import BPSMeter
from sabnzbd.database import build_history_info, unpack_history_info, get_history_handle


#------------------------------------------------------------------------------
# API error messages
_MSG_NO_VALUE         = 'expect one parameter'
_MSG_NO_VALUE2        = 'expect two parameters'
_MSG_INT_VALUE        = 'expect integer value'
_MSG_NO_ITEM          = 'item does not exist'
_MSG_NOT_IMPLEMENTED  = 'not implemented'
_MSG_NO_FILE          = 'no file given'
_MSG_NO_PATH          = 'file does not exist'
_MSG_OUTPUT_FORMAT    = 'Format not supported'
_MSG_NO_SUCH_CONFIG   = 'Config item does not exist'
_MSG_BAD_SERVER_PARMS = 'Incorrect server settings'


#------------------------------------------------------------------------------
def api_handler(kwargs):
    """ API Dispatcher
    """
    mode = kwargs.get('mode', '')
    output = kwargs.get('output')
    name = kwargs.get('name', '')

    return _api_table.get(mode, _api_undefined)(name, output, kwargs)


#------------------------------------------------------------------------------
def _api_get_config(name, output, kwargs):
    """ API: accepts output, keyword, section """
    res, data = config.get_dconfig(kwargs.get('section'), kwargs.get('keyword'))
    return report(output, keyword='config', data=data)

def _api_set_config(name, output, kwargs):
    """ API: accepts output, keyword, section """
    if kwargs.get('section') == 'servers':
        kwargs['keyword'] = handle_server_api(output, kwargs)
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


#------------------------------------------------------------------------------
def _api_queue(name, output, kwargs):
    """ API: Dispatcher for mode=queue """
    value = kwargs.get('value', '')
    return _api_queue_table.get(name, _api_queue_default)(output, value, kwargs)


def _api_queue_delete(output, value, kwargs):
    """ API: accepts output, value """
    if value.lower()=='all':
        nzbqueue.remove_all_nzo()
        return report(output)
    elif value:
        items = value.split(',')
        nzbqueue.remove_multiple_nzos(items)
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE)


def _api_queue_delete_nzf(output, value, kwargs):
    """ API: accepts value(=nzo_id), value2(=nzf_id) """
    value2 = kwargs.get('value2')
    if value and value2:
        nzbqueue.remove_nzf(value, value2)
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_rename(output, value, kwargs):
    """ API: accepts output, value(=old name), value2(=new name) """
    value2 = kwargs.get('value2')
    if value and value2:
        nzbqueue.rename_nzo(value, special_fixer(value2))
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_change_complete_action(output, value, kwargs):
    """ API: accepts output, value(=action) """
    sabnzbd.change_queue_complete_action(value)
    return report(output)


def _api_queue_purge(output, value, kwargs):
    """ API: accepts output """
    nzbqueue.remove_all_nzo()
    return report(output)


def _api_queue_pause(output, value, kwargs):
    """ API: accepts output, value(=list of nzo_id) """
    if value:
        items = value.split(',')
        nzbqueue.pause_multiple_nzo(items)
    return report(output)


def _api_queue_resume(output, value, kwargs):
    """ API: accepts output, value(=list of nzo_id) """
    if value:
        items = value.split(',')
        nzbqueue.resume_multiple_nzo(items)
    return report(output)


def _api_queue_priority(output, value, kwargs):
    """ API: accepts output, value(=nzo_id), value2(=priority) """
    value2 = kwargs.get('value2')
    if value and value2:
        try:
            try:
                priority = int(value2)
            except:
                return report(output, _MSG_INT_VALUE)
            pos = nzbqueue.set_priority(value, priority)
            # Returns the position in the queue, -1 is incorrect job-id
            return report(output, keyword='position', data=pos)
        except:
            return report(output, _MSG_NO_VALUE2)
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_sort(output, value, kwargs):
    """ API: accepts output, sort, dir """
    sort = kwargs.get('sort')
    direction = kwargs.get('dir')
    if sort:
        nzbqueue.sort_queue(sort, direction)
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE2)


def _api_queue_default(output, value, kwargs):
    """ API: accepts output, sort, dir, start, limit """
    sort = kwargs.get('sort')
    direction = kwargs.get('dir')
    start = kwargs.get('start')
    limit = kwargs.get('limit')
    if output in ('xml', 'json'):
        if sort and sort != 'index':
            reverse = direction.lower() == 'desc'
            nzbqueue.sort_queue(sort, reverse)

        # &history=1 will show unprocessed items in the history
        history = bool(kwargs.get('history'))

        info, pnfo_list, bytespersec, verboseList, dictn = \
            build_queue(history=history, start=start, limit=limit, output=output)
        info['categories'] = info.pop('cat_list')
        info['scripts'] = info.pop('script_list')
        return report(output, keyword='queue', data=remove_callable(info))
    elif output == 'rss':
        return rss_qstatus()
    else:
        return report(output, _MSG_NOT_IMPLEMENTED)


#------------------------------------------------------------------------------
def _api_options(name, output, kwargs):
    """ API: accepts output """
    return options_list(output)


def _api_translate(name, output, kwargs):
    """ API: accepts output, value(=acronym) """
    return report(output, keyword='value', data=Tx(kwargs.get('value', '')))


def _api_addfile(name, output, kwargs):
    """ API: accepts name, output, pp, script, cat, priority, nzbname """
    # When uploading via flash it will send the nzb in a kw arg called Filedata
    if name is None or isinstance(name, str) or isinstance(name, unicode):
        name = kwargs.get('Filedata')
    # Normal upload will send the nzb in a kw arg called nzbfile
    if name is None or isinstance(name, str) or isinstance(name, unicode):
        name = kwargs.get('nzbfile')

    if name is not None and name.filename and name.value:
        sabnzbd.add_nzbfile(name, kwargs.get('pp'), kwargs.get('script'), kwargs.get('cat'),
                            kwargs.get('priority'), kwargs.get('nzbname'))
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE)


def _api_retry(name, output, kwargs):
    """ API: accepts name, output, value(=nzo_id), nzbfile(=optional NZB) """
    value = kwargs.get('value')
    # When uploading via flash it will send the nzb in a kw arg called Filedata
    if name is None or isinstance(name, str) or isinstance(name, unicode):
        name = kwargs.get('Filedata')
    # Normal upload will send the nzb in a kw arg called nzbfile
    if name is None or isinstance(name, str) or isinstance(name, unicode):
        name = kwargs.get('nzbfile')

    if retry_job(value, name):
        return report(output)
    else:
        return report(output, _MSG_NO_ITEM)


def _api_addlocalfile(name, output, kwargs):
    """ API: accepts name, output, pp, script, cat, priority, nzbname """
    if name:
        if os.path.exists(name):
            fn = get_filename(name)
            if fn:
                pp = kwargs.get('pp')
                script = kwargs.get('script')
                cat = kwargs.get('cat')
                priority = kwargs.get('priority')
                nzbname = kwargs.get('nzbname')

                if get_ext(name) in ('.zip', '.rar', '.gz'):
                    sabnzbd.dirscanner.ProcessArchiveFile(\
                        fn, name, pp=pp, script=script, cat=cat, priority=priority, keep=True)
                elif get_ext(name) in ('.nzb'):
                    sabnzbd.dirscanner.ProcessSingleFile(\
                        fn, name, pp=pp, script=script, cat=cat, priority=priority, keep=True, nzbname=nzbname)
            else:
                return report(output, _MSG_NO_FILE)
        else:
            return report(output, _MSG_NO_PATH)
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE)


def _api_switch(name, output, kwargs):
    """ API: accepts output, value(=first id), value2(=second id) """
    value = kwargs.get('value')
    value2 = kwargs.get('value2')
    if value and value2:
        pos, prio = nzbqueue.switch(value, value2)
        # Returns the new position and new priority (if different)
        if output not in ('xml', 'json'):
            return report(output, data=(pos, prio))
        else:
            return report(output, keyword='result', data={'position':pos, 'priority':prio})
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
        nzbqueue.change_cat(nzo_id, cat)
        return report(output)
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
        nzbqueue.change_script(nzo_id, script)
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE)

def _api_change_opts(name, output, kwargs):
    """ API: accepts output, value(=nzo_id), value2(=pp) """
    value = kwargs.get('value')
    value2 = kwargs.get('value2')
    if value and value2 and value2.isdigit():
        nzbqueue.change_opts(value, int(value2))
    return report(output)


def _api_fullstatus(name, output, kwargs):
    """ API: not implemented """
    return report(output, _MSG_NOT_IMPLEMENTED + ' YET') #xml_full()


def _api_history(name, output, kwargs):
    """ API: accepts output, value(=nzo_id), start, limit, search """
    value = kwargs.get('value')
    start = kwargs.get('start')
    limit = kwargs.get('limit')
    search = kwargs.get('search')

    if name == 'delete':
        if value.lower()=='all':
            history_db = cherrypy.thread_data.history_db
            history_db.remove_history()
            return report(output)
        elif value:
            jobs = value.split(',')
            history_db = cherrypy.thread_data.history_db
            history_db.remove_history(jobs)
            return report(output)
        else:
            return report(output, _MSG_NO_VALUE)
    elif not name:
        history, pnfo_list, bytespersec = build_header(True)
        history['total_size'], history['month_size'], history['week_size'] = get_history_size()
        history['slots'], fetched_items, history['noofslots'] = build_history(start=start, limit=limit, verbose=True, search=search)
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

def _api_addurl(name, output, kwargs):
    """ API: accepts name, output, pp, script, cat, priority, nzbname """
    if name:
        sabnzbd.add_url(name, kwargs.get('pp'), kwargs.get('script'), kwargs.get('cat'),
                        kwargs.get('priority'), kwargs.get('nzbname'))
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE)


_RE_NEWZBIN_URL = re.compile(r'/browse/post/(\d+)')
def _api_addid(name, output, kwargs):
    """ API: accepts name, output, pp, script, cat, priority, nzbname """
    pp = kwargs.get('pp')
    script = kwargs.get('script')
    cat = kwargs.get('cat')
    priority = kwargs.get('priority')
    nzbname = kwargs.get('nzbname')

    newzbin_url = _RE_NEWZBIN_URL.search(name.lower())

    if name: name = name.strip()
    if name and (name.isdigit() or len(name)==5):
        sabnzbd.add_msgid(name, pp, script, cat, priority, nzbname)
        return report(output)
    elif newzbin_url:
        sabnzbd.add_msgid(newzbin_url.group(1), pp, script, cat, priority, nzbname)
        return report(output)
    elif name:
        sabnzbd.add_url(name, pp, script, cat, priority, nzbname)
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE)

def _api_pause(name, output, kwargs):
    """ API: accepts output """
    scheduler.plan_resume(0)
    downloader.pause_downloader()
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
    return report(output, keyword="scripts", data=list_scripts())


def _api_version(name, output, kwargs):
    """ API: accepts output """
    return report(output, keyword='version', data=sabnzbd.__version__)


def _api_auth(name, output, kwargs):
    """ API: accepts output """
    auth = 'None'
    if cfg.username() and cfg.password():
        auth = 'login'
    if not cfg.disable_key():
        auth = 'apikey'
    return report(output, keyword='auth', data=auth)


def _api_newzbin(name, output, kwargs):
    """ API: accepts output """
    if name == 'get_bookmarks':
        Bookmarks.do.run()
        return report(output)
    return report(output, _MSG_NOT_IMPLEMENTED)


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
    downloader.disconnect()
    return report(output)


def _api_osx_icon(name, output, kwargs):
    """ API: accepts output, value """
    value = kwargs.get('value', '1')
    sabnzbd.OSX_ICON = int(value != '0')
    return report(output)


def _api_rescan(name, output, kwargs):
    """ API: accepts output """
    nzbqueue.scan_jobs(all=False, action=True)
    return report(output)


def _api_undefined(name, output, kwargs):
    """ API: accepts output """
    return report(output, _MSG_NOT_IMPLEMENTED)


#------------------------------------------------------------------------------
def _api_config(name, output, kwargs):
    """ API: Dispather for "config" """
    return _api_config_table.get(name, _api_config_undefined)(output, kwargs)


def _api_config_speedlimit(output, kwargs):
    """ API: accepts output, value(=speed) """
    value = kwargs.get('value')
    if not value:
        value = '0'
    if value.isdigit():
        try:
            value = int(value)
        except:
            return report(output, _MSG_NO_VALUE)
        downloader.limit_speed(value)
        return report(output)
    else:
        return report(output, _MSG_NO_VALUE)


def _api_config_get_speedlimit(output, kwargs):
    """ API: accepts output """
    return report(output, keyword='speedlimit', data=int(downloader.get_limit()))


def _api_config_set_colorscheme(output, kwargs):
    """ API: accepts output, value(=color for primary), value2(=color for secundary) """
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


def _api_config_test_server(output, kwargs):
    """ API: accepts output, server-parms """
    result, msg = test_nntp_server_dict(kwargs)
    response = {'result': result, 'message': msg}
    if output:
        return report(output, data=response)
    else:
        return msg


def _api_config_undefined(output, kwargs):
    """ API: accepts output """
    return report(output, _MSG_NOT_IMPLEMENTED)


#------------------------------------------------------------------------------
_api_table = {
    'get_config'      : _api_get_config,
    'set_config'      : _api_set_config,
    'del_config'      : _api_del_config,
    'qstatus'         : _api_qstatus,
    'queue'           : _api_queue,
    'options'         : _api_options,
    'translate'       : _api_translate,
    'addfile'         : _api_addfile,
    'retry'           : _api_retry,
    'addlocalfile'    : _api_addlocalfile,
    'switch'          : _api_switch,
    'change_cat'      : _api_change_cat,
    'change_script'   : _api_change_script,
    'change_opts'     : _api_change_opts,
    'fullstatus'      : _api_fullstatus,
    'history'         : _api_history,
    'get_files'       : _api_get_files,
    'addurl'          : _api_addurl,
    'addid'           : _api_addid,
    'pause'           : _api_pause,
    'resume'          : _api_resume,
    'shutdown'        : _api_shutdown,
    'warnings'        : _api_warnings,
    'config'          : _api_config,
    'get_cats'        : _api_get_cats,
    'get_scripts'     : _api_get_scripts,
    'version'         : _api_version,
    'auth'            : _api_auth,
    'newzbin'         : _api_newzbin,
    'restart'         : _api_restart,
    'restart_repair'  : _api_restart_repair,
    'disconnect'      : _api_disconnect,
    'osx_icon'        : _api_osx_icon,
    'rescan'          : _api_rescan
}

_api_queue_table = {
    'delete'                  : _api_queue_delete,
    'delete_nzf'              : _api_queue_delete_nzf,
    'rename'                  : _api_queue_rename,
    'change_complete_action'  : _api_queue_change_complete_action,
    'purge'                   : _api_queue_purge,
    'pause'                   : _api_queue_pause,
    'resume'                  : _api_queue_resume,
    'priority'                : _api_queue_priority,
    'sort'                    : _api_queue_sort
}

_api_config_table = {
    'speedlimit'       : _api_config_speedlimit,
    'set_speedlimit'   : _api_config_speedlimit,
    'get_speedlimit'   : _api_config_get_speedlimit,
    'set_colorscheme'  : _api_config_set_colorscheme,
    'set_pause'        : _api_config_set_pause,
    'set_apikey'       : _api_config_set_apikey,
    'test_server'      : _api_config_test_server
}


#------------------------------------------------------------------------------
def report(output, error=None, keyword='value', data=None):
    """ Report message in json, xml or plain text
        If error is set, only an status/error report is made.
        If no error and no data, only a status report is made.
        Else, a data report is made (optional 'keyword' for outer XML section).
    """
    if output == 'json':
        content = "application/json;charset=UTF-8"
        if error:
            info = {'status':False, 'error':error}
        elif data is None:
            info = {'status':True}
        else:
            if hasattr(data,'__iter__') and not keyword:
                info = data
            else:
                info = {keyword:data}
        response = JsonWriter().write(info)

    elif output == 'xml':
        content = "text/xml"
        xmlmaker = xml_factory()
        if error:
            status_str = xmlmaker.run('result', {'status':False, 'error':error})
        elif data is None:
            status_str = xmlmaker.run('result', {'status':True})
        else:
            status_str = xmlmaker.run(keyword, data)
        response = '<?xml version="1.0" encoding="UTF-8" ?>\n%s\n' % status_str

    else:
        content = "text/plain"
        if error:
            response = "error: %s\n" % error
        elif data is None:
            response = 'ok\n'
        else:
            if type(data) in (list, tuple):
                # Special handling for list/tuple (backward compatibility)
                data = [str(val) for val in data]
                response = '%s\n' % ' '.join(data)
            else:
                response = '%s\n' % str(data)

    cherrypy.response.headers['Content-Type'] = content
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return response


#------------------------------------------------------------------------------
class xml_factory(object):
    """
    Recursive xml string maker. Feed it a mixed tuple/dict/item object and will output into an xml string
    Current limitations:
        In Two tiered lists hardcoded name of "item": <cat_list><item> </item></cat_list>
        In Three tiered lists hardcoded name of "slot": <tier1><slot><tier2> </tier2></slot></tier1>
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


#------------------------------------------------------------------------------
def handle_server_api(output, kwargs):
    """ Special handler for API-call 'set_config'
    """
    name = kwargs.get('keyword')
    if not name:
        name = kwargs.get('name')
    if not name:
        host = kwargs.get('host')
        port = kwargs.get('port', '119')
        if host:
            name = '%s:%s' % (host, port)
        else:
            return name

    server = config.get_config('servers', name)
    if server:
        server.set_dict(kwargs)
        old_name = name
        name = '%s:%s' % (server.host(), server.port())
        server.rename(name)
    else:
        config.ConfigServer(name, kwargs)
        old_name = None
    downloader.update_server(old_name, name)
    return name


#------------------------------------------------------------------------------
def build_queue(web_dir=None, root=None, verbose=False, prim=True, verboseList=None,
                dictionary=None, history=False, start=None, limit=None, dummy2=None, output=None):
    if output:
        converter = unicoder
    else:
        converter = xml_name

    if not verboseList:
        verboseList = []
    if dictionary:
        dictn = dictionary
    else:
        dictn = []
    #build up header full of basic information
    info, pnfo_list, bytespersec = build_header(prim)
    info['isverbose'] = verbose
    cookie = cherrypy.request.cookie
    if cookie.has_key('queue_details'):
        info['queue_details'] = str(int_conv(cookie['queue_details'].value))
    else:
        info['queue_details'] = '0'

    if cfg.newzbin_username() and cfg.newzbin_password():
        info['newzbinDetails'] = True

    if cfg.refresh_rate() > 0:
        info['refresh_rate'] = str(cfg.refresh_rate())
    else:
        info['refresh_rate'] = ''

    datestart = datetime.datetime.now()

    info['script_list'] = list_scripts()
    info['cat_list'] = list_cats(output is None)


    n = 0
    found_active = False
    running_bytes = 0
    slotinfo = []
    nzo_ids = []

    limit = int_conv(limit)
    start = int_conv(start)

    if history:
        #Collect nzo's from the history that are downloaded but not finished (repairing, extracting)
        slotinfo = format_history_for_queue()
        #if the specified start value is greater than the amount of history items, do no include the history (used for paging the queue)
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
        msgid = pnfo[PNFO_MSGID_FIELD]
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD]
        bytes = pnfo[PNFO_BYTES_FIELD]
        average_date = pnfo[PNFO_AVG_DATE_FIELD]
        status = pnfo[PNFO_STATUS_FIELD]
        priority = pnfo[PNFO_PRIORITY_FIELD]
        mbleft = (bytesleft / MEBI)
        mb = (bytes / MEBI)
        if verbose or verboseList:
            finished_files = pnfo[PNFO_FINISHED_FILES_FIELD]
            active_files = pnfo[PNFO_ACTIVE_FILES_FIELD]
            queued_files = pnfo[PNFO_QUEUED_FILES_FIELD]

        nzo_ids.append(nzo_id)

        slot = {'index':n, 'nzo_id':str(nzo_id)}
        unpackopts = sabnzbd.opts_to_pp(repair, unpack, delete)

        slot['unpackopts'] = str(unpackopts)
        if script:
            slot['script'] = script
        else:
            slot['script'] = 'None'
        slot['msgid'] = msgid
        slot['filename'] = converter(filename)
        slot['cat'] = cat
        slot['mbleft'] = "%.2f" % mbleft
        slot['mb'] = "%.2f" % mb
        slot['size'] = format_bytes(bytes)
        slot['sizeleft'] = format_bytes(bytesleft)
        if not downloader.paused() and status != 'Paused' and status != 'Fetching' and not found_active:
            slot['status'] = "Downloading"
            found_active = True
        else:
            slot['status'] = "%s" % (status)
        if priority == TOP_PRIORITY:
            slot['priority'] = 'Force'
        elif priority == HIGH_PRIORITY:
            slot['priority'] = 'High'
        elif priority == LOW_PRIORITY:
            slot['priority'] = 'Low'
        else:
            slot['priority'] = 'Normal'
        if mb == mbleft:
            slot['percentage'] = "0"
        else:
            slot['percentage'] = "%s" % (int(((mb-mbleft) / mb) * 100))

        if status == 'Paused':
            slot['timeleft'] = '0:00:00'
            slot['eta'] = 'unknown'
        else:
            running_bytes += bytesleft
            slot['timeleft'] = calc_timeleft(running_bytes, bytespersec)
            try:
                datestart = datestart + datetime.timedelta(seconds=bytesleft / bytespersec)
                #new eta format: 16:00 Fri 07 Feb
                slot['eta'] = '%s' % datestart.strftime(time_format('%H:%M %a %d %b'))
            except:
                datestart = datetime.datetime.now()
                slot['eta'] = 'unknown'

        slot['avg_age'] = calc_age(average_date)
        slot['verbosity'] = ""
        if web_dir:
            finished = []
            active = []
            queued = []
            if verbose or nzo_id in verboseList:#this will list files in the xml output, wanted yes/no?
                slot['verbosity'] = "True"
                for tup in finished_files:
                    bytes_left, bytes, fn, date = tup
                    fn = converter(fn)

                    age = calc_age(date)

                    line = {'filename':fn,
                            'mbleft':"%.2f" % (bytes_left / MEBI),
                            'mb':"%.2f" % (bytes / MEBI),
                            'size': format_bytes(bytes),
                            'sizeleft': format_bytes(bytes_left),
                            'age':age}
                    finished.append(line)

                for tup in active_files:
                    bytes_left, bytes, fn, date, nzf_id = tup
                    fn = converter(fn)

                    age = calc_age(date)

                    line = {'filename':fn,
                            'mbleft':"%.2f" % (bytes_left / MEBI),
                            'mb':"%.2f" % (bytes / MEBI),
                            'size': format_bytes(bytes),
                            'sizeleft': format_bytes(bytes_left),
                            'nzf_id':nzf_id,
                            'age':age}
                    active.append(line)

                for tup in queued_files:
                    _set, bytes_left, bytes, fn, date = tup
                    fn = converter(fn)
                    _set = converter(_set)

                    age = calc_age(date)

                    line = {'filename':fn, 'set':_set,
                            'mbleft':"%.2f" % (bytes_left / MEBI),
                            'mb':"%.2f" % (bytes / MEBI),
                            'size': format_bytes(bytes),
                            'sizeleft': format_bytes(bytes_left),
                            'age':age}
                    queued.append(line)

            slot['finished'] = finished
            slot['active'] = active
            slot['queued'] = queued


        if (start <= n  and n < start + limit) or not limit:
            slotinfo.append(slot)
        n += 1

    if slotinfo:
        info['slots'] = slotinfo
    else:
        info['slots'] = []
        verboseList = []

    #Paging of the queue using limit and/or start values
    if limit > 0:
        try:
            if start > 0:
                if start > len(pnfo_list):
                    pnfo_list = []
                else:
                    end = start+limit
                    if start+limit > len(pnfo_list):
                        end = len(pnfo_list)
                    pnfo_list = pnfo_list[start:end]
            else:
                if not limit > len(pnfo_list):
                    pnfo_list = pnfo_list[:limit]
        except:
            pass

    return info, pnfo_list, bytespersec, verboseList, dictn


#------------------------------------------------------------------------------
def qstatus_data():
    """Build up the queue status as a nested object and output as a JSON object
    """

    qnfo = nzbqueue.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    jobs = []
    bytesleftprogess = 0
    bpsnow = BPSMeter.do.get_bps()
    for pnfo in pnfo_list:
        filename = pnfo[PNFO_FILENAME_FIELD]
        msgid = pnfo[PNFO_MSGID_FIELD]
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
        bytesleftprogess += pnfo[PNFO_BYTES_LEFT_FIELD]
        bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        jobs.append( { "id" : nzo_id,
                        "mb":bytes,
                        "mbleft":bytesleft,
                        "filename":unicoder(filename),
                        "msgid":msgid,
                        "timeleft":calc_timeleft(bytesleftprogess, bpsnow) } )

    state = "IDLE"
    if downloader.paused():
        state = "PAUSED"
    elif qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI > 0:
        state = "DOWNLOADING"

    status = {
        "state" : state,
        "paused" : downloader.paused(),
        "pause_int" : scheduler.pause_int(),
        "kbpersec" : BPSMeter.do.get_bps() / KIBI,
        "speed" : to_units(BPSMeter.do.get_bps(), dec_limit=1),
        "mbleft" : qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI,
        "mb" : qnfo[QNFO_BYTES_FIELD] / MEBI,
        "noofslots" : len(pnfo_list),
        "have_warnings" : str(sabnzbd.GUIHANDLER.count()),
        "diskspace1" : diskfree(cfg.download_dir.get_path()),
        "diskspace2" : diskfree(cfg.complete_dir.get_path()),
        "timeleft" : calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], bpsnow),
        "loadavg" : loadavg(),
        "jobs" : jobs
    }
    return status


#------------------------------------------------------------------------------
def build_file_list(id):
    qnfo = nzbqueue.queue_info()
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

                line = {'filename':fn,
                        'mbleft':"%.2f" % (bytes_left / MEBI),
                        'mb':"%.2f" % (bytes / MEBI),
                        'bytes':"%.2f" % bytes,
                        'age':age, 'id':str(n), 'status':'finished'}
                jobs.append(line)
                n += 1

            for tup in active_files:
                bytes_left, bytes, fn, date, nzf_id = tup
                fn = xml_name(fn)

                age = calc_age(date)

                line = {'filename':fn,
                        'mbleft':"%.2f" % (bytes_left / MEBI),
                        'mb':"%.2f" % (bytes / MEBI),
                        'bytes':"%.2f" % bytes,
                        'nzf_id':nzf_id,
                        'age':age, 'id':str(n), 'status':'active'}
                jobs.append(line)
                n += 1

            for tup in queued_files:
                _set, bytes_left, bytes, fn, date = tup
                fn = xml_name(fn)
                _set = xml_name(_set)

                age = calc_age(date)

                line = {'filename':fn, 'set':_set,
                        'mbleft':"%.2f" % (bytes_left / MEBI),
                        'mb':"%.2f" % (bytes / MEBI),
                        'bytes':"%.2f" % bytes,
                        'age':age, 'id':str(n), 'status':'queued'}
                jobs.append(line)
                n += 1

    return jobs


#------------------------------------------------------------------------------
def json_list(section, lst):
    """Output a simple list as a JSON object
    """
    i = 0
    d = []
    for item in lst:
        c = {}
        c['id'] = '%s' % i
        c['name'] = item
        i += 1
        d.append(c)

    return { section : d }


#------------------------------------------------------------------------------
def rss_qstatus():
    """ Return a RSS feed with the queue status
    """
    qnfo = nzbqueue.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    rss = RSS()
    rss.channel.title = "SABnzbd Queue"
    rss.channel.description = "Overview of current downloads"
    rss.channel.link = "http://%s:%s/sabnzbd/queue" % ( \
        cfg.cherryhost(), cfg.cherryport() )
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
        msgid = pnfo[PNFO_MSGID_FIELD]
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
        bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
        mbleft = (bytesleft / MEBI)
        mb = (bytes / MEBI)


        if mb == mbleft:
            percentage = "0%"
        else:
            percentage = "%s%%" % (int(((mb-mbleft) / mb) * 100))

        filename = xml_name(filename)
        name = u'%s (%s)' % (filename, percentage)

        item = Item()
        item.title = name
        if msgid:
            item.link    = "https://newzbin.com/browse/post/%s/" % msgid
        else:
            item.link    = "http://%s:%s/sabnzbd/history" % ( \
            cfg.cherryhost(), cfg.cherryport() )
        statusLine  = []
        statusLine.append('<tr>')
        #Total MB/MB left
        statusLine.append('<dt>Remain/Total: %.2f/%.2f MB</dt>' % (bytesleft, bytes))
        #ETA
        sum_bytesleft += pnfo[PNFO_BYTES_LEFT_FIELD]
        statusLine.append("<dt>ETA: %s </dt>" % calc_timeleft(sum_bytesleft, BPSMeter.do.get_bps()))
        statusLine.append("<dt>Age: %s</dt>" % calc_age(pnfo[PNFO_AVG_DATE_FIELD]))
        statusLine.append("</tr>")
        item.description = ''.join(statusLine)
        rss.addItem(item)

    rss.channel.lastBuildDate = std_time(time.time())
    rss.channel.pubDate = rss.channel.lastBuildDate
    rss.channel.ttl = "1"
    return rss.write()


#------------------------------------------------------------------------------
def options_list(output):
    return report(output, keyword='options', data=
        {
        'yenc' : sabnzbd.decoder.HAVE_YENC,
        'par2' : sabnzbd.newsunpack.PAR2_COMMAND,
        'par2c' : sabnzbd.newsunpack.PAR2C_COMMAND,
        'rar' : sabnzbd.newsunpack.RAR_COMMAND,
        'zip' : sabnzbd.newsunpack.ZIP_COMMAND,
        'nice' : sabnzbd.newsunpack.NICE_COMMAND,
        'ionice' : sabnzbd.newsunpack.IONICE_COMMAND,
        'ssl' : sabnzbd.newswrapper.HAVE_SSL
        })



#------------------------------------------------------------------------------
def retry_job(job, new_nzb):
    """ Re enter failed job in the download queue """
    if job:
        history_db = cherrypy.thread_data.history_db
        path = history_db.get_path(job)
        if path:
            nzbqueue.repair_job(platform_encode(path), new_nzb)
            history_db.remove_history(job)
            return True
    return False


#------------------------------------------------------------------------------
def del_hist_job(job, del_files):
    """ Remove history element """
    if job:
        history_db = cherrypy.thread_data.history_db
        path = history_db.get_path(job)
        PostProcessor.do.delete(job, del_files=del_files)
        history_db.remove_history(job)
        if path and del_files and path.lower().startswith(cfg.download_dir.get_path().lower()):
            nzbstuff.clean_folder(os.path.join(path, JOB_ADMIN))
            nzbstuff.clean_folder(path)
    return True

#------------------------------------------------------------------------------
def Tspec(txt):
    """ Translate special terms """
    if txt == 'None':
        return T('None')
    elif txt == 'Default':
        return T('Default')
    else:
        return txt

_SKIN_CACHE = {}    # Stores pre-translated acronyms

# This special is to be used in interface.py for template processing
# to be paased for the $T function: so { ..., 'T' : Ttemplate, ...}
def Ttemplate(txt):
    """ Translation function for Skin texts
    """
    return _SKIN_CACHE.get(txt, txt)


def cache_skin_trans():
    """ Build cache for skin translations
    """
    global _SKIN_CACHE
    for txt in SKIN_TEXT:
        _SKIN_CACHE[txt] = Tx(SKIN_TEXT.get(txt, txt))


def build_header(prim):
    try:
        uptime = calc_age(sabnzbd.START)
    except:
        uptime = "-"

    if prim:
        color = sabnzbd.WEB_COLOR
    else:
        color = sabnzbd.WEB_COLOR2
    if color:
        color = color + '.css'
    else:
        color = ''

    header = { 'T': Ttemplate, 'Tspec': Tspec, 'Tx' : Ttemplate, 'version':sabnzbd.__version__, 'paused':downloader.paused(),
               'pause_int': scheduler.pause_int(), 'paused_all': sabnzbd.PAUSED_ALL,
               'uptime':uptime, 'color_scheme':color }
    speed_limit = downloader.get_limit()
    if speed_limit <= 0:
        speed_limit = ''

    header['helpuri'] = 'http://wiki.sabnzbd.org/'
    header['diskspace1'] = "%.2f" % diskfree(cfg.download_dir.get_path())
    header['diskspace2'] = "%.2f" % diskfree(cfg.complete_dir.get_path())
    header['diskspacetotal1'] = "%.2f" % disktotal(cfg.download_dir.get_path())
    header['diskspacetotal2'] = "%.2f" % disktotal(cfg.complete_dir.get_path())
    header['loadavg'] = loadavg()
    header['speedlimit'] = "%s" % speed_limit
    header['restart_req'] = sabnzbd.RESTART_REQ
    header['have_warnings'] = str(sabnzbd.GUIHANDLER.count())
    header['last_warning'] = sabnzbd.GUIHANDLER.last()
    header['active_lang'] = cfg.language()
    if prim:
        header['webdir'] = sabnzbd.WEB_DIR
    else:
        header['webdir'] = sabnzbd.WEB_DIR2

    header['finishaction'] = sabnzbd.QUEUECOMPLETE
    header['nt'] = sabnzbd.WIN32
    header['darwin'] = sabnzbd.DARWIN
    header['power_options'] = sabnzbd.WIN32 or sabnzbd.DARWIN or sabnzbd.LINUX_POWER

    header['session'] = cfg.api_key()

    bytespersec = BPSMeter.do.get_bps()
    qnfo = nzbqueue.queue_info()

    bytesleft = qnfo[QNFO_BYTES_LEFT_FIELD]
    bytes = qnfo[QNFO_BYTES_FIELD]

    header['kbpersec'] = "%.2f" % (bytespersec / KIBI)
    header['speed'] = to_units(bytespersec, spaces=1, dec_limit=1)
    header['mbleft']   = "%.2f" % (bytesleft / MEBI)
    header['mb']       = "%.2f" % (bytes / MEBI)
    header['sizeleft']   = format_bytes(bytesleft)
    header['size']       = format_bytes(bytes)

    status = ''
    if downloader.paused():
        status = 'Paused'
    elif bytespersec > 0:
        status = 'Downloading'
    else:
        status = 'Idle'
    header['status'] = "%s" % status

    anfo  = ArticleCache.do.cache_info()

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
        #new eta format: 16:00 Fri 07 Feb
        header['eta'] = '%s' % datestart.strftime(time_format('%H:%M %a %d %b'))
    except:
        datestart = datetime.datetime.now()
        header['eta'] = T('unknown')

    return (header, qnfo[QNFO_PNFO_LIST_FIELD], bytespersec)


#------------------------------------------------------------------------------
def get_history_size():
    history_db = cherrypy.thread_data.history_db
    bytes, month, week = history_db.get_history_size()
    return (format_bytes(bytes), format_bytes(month), format_bytes(week))

def build_history(start=None, limit=None, verbose=False, verbose_list=None, search=None):

    if not verbose_list:
        verbose_list = []

    try:
        limit = int(limit)
    except:
        limit = 0
    try:
        start = int(start)
    except:
        start = 0

    def matches_search(text, search_text):
        # Replace * with .* and ' ' with .
        search_text = search_text.strip().replace('*','.*').replace(' ','.*') + '.*?'
        try:
            re_search = re.compile(search_text, re.I)
        except:
            logging.error(Ta('Failed to compile regex for search term: %s'), search_text)
            return False
        return re_search.search(text)

    # Grab any items that are active or queued in postproc
    queue = PostProcessor.do.get_queue()

    # Filter out any items that don't match the search
    if search:
        queue = [nzo for nzo in queue if matches_search(nzo.final_name, search)]

    # Multi-page support for postproc items
    if start > len(queue):
        # On a page where we shouldn't show postproc items
        queue = []
    else:
        try:
            if start:
                if limit:
                    queue = queue[start:start+limit]
                else:
                    queue = queue[start:]
        except:
            pass
    # Remove the amount of postproc items from the db request for history items
    limit -= len(queue)

    # Aquire the db instance
    try:
        history_db = cherrypy.thread_data.history_db
    except:
        # Required for repairs at startup because Cherrypy isn't active yet
        history_db = get_history_handle()

    # Fetch history items
    items, fetched_items, total_items = history_db.fetch_history(start, limit, search)

    # Fetch which items should show details from the cookie
    k = []
    if verbose:
        details_show_all = True
    else:
        details_show_all = False
    cookie = cherrypy.request.cookie
    if cookie.has_key('history_verbosity'):
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
        if not item.has_key('loaded'):
            item['loaded'] = False
        path = platform_encode(item.get('path', ''))
        item['retry'] = int(bool(item.get('status') == 'Failed' and \
                                 path and \
                                 path not in retry_folders and \
                                 path.startswith(cfg.download_dir.get_path()) and \
                                 os.path.exists(path)) and \
                                 not bool(globber(os.path.join(path, JOB_ADMIN), 'SABnzbd_n*')) \
                                 )
        if item['retry']:
            retry_folders.append(path)

    return (items, fetched_items, total_items)



#------------------------------------------------------------------------------
def format_history_for_queue():
    ''' Retrieves the information on currently active history items, and formats them for displaying in the queue '''
    slotinfo = []
    history_items = get_active_history()

    for item in history_items:
        slot = {'nzo_id':item['nzo_id'],
                'msgid':item['report'], 'filename':xml_name(item['name']), 'loaded':False,
                'stages':item['stage_log'], 'status':item['status'], 'bytes':item['bytes'],
                'size':item['size']}
        slotinfo.append(slot)

    return slotinfo


def get_active_history(queue=None, items=None):
    # Get the currently in progress and active history queue.
    if items is None:
        items = []
    if queue is None:
        queue = PostProcessor.do.get_queue()

    for nzo in queue:
        t = build_history_info(nzo)
        item = {}
        item['completed'], item['name'], item['nzb_name'], item['category'], item['pp'], item['script'], item['report'], \
            item['url'], item['status'], item['nzo_id'], item['storage'], item['path'], item['script_log'], \
            item['script_line'], item['download_time'], item['postproc_time'], item['stage_log'], \
            item['downloaded'], item['completeness'], item['fail_message'], item['url_info'], item['bytes'] = t
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


#------------------------------------------------------------------------------
def format_bytes(bytes):
    b = to_units(bytes)
    if b == '':
        return b
    else:
        return b + 'B'


def calc_timeleft(bytesleft, bps):
    """
    Calculate the time left in the format HH:MM:SS
    """
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


def calc_age(date):
    """
    Calculate the age difference between now and date.
    Value is returned as either days, hours, or minutes.
    """
    try:
        now = datetime.datetime.now()
        #age = str(now - date).split(".")[0] #old calc_age

        #time difference
        dage = now-date
        seconds = dage.seconds
        #only one value should be returned
        #if it is less than 1 day then it returns in hours, unless it is less than one hour where it returns in minutes
        if dage.days:
            age = '%sd' % (dage.days)
        elif seconds/3600:
            age = '%sh' % (seconds/3600)
        else:
            age = '%sm' % (seconds/60)
    except:
        age = "-"

    return age


def std_time(when):
    # Fri, 16 Nov 2007 16:42:01 GMT +0100
    item  = time.strftime(time_format('%a, %d %b %Y %H:%M:%S'), time.localtime(when))
    item += " GMT %+05d" % (-time.timezone/36)
    return item


def list_scripts(default=False):
    """ Return a list of script names """
    lst = []
    dd = cfg.script_dir.get_path()

    if dd and os.access(dd, os.R_OK):
        if default:
            lst = ['Default', 'None']
        else:
            lst = ['None']
        for script in globber(dd):
            if os.path.isfile(script):
                sc = os.path.basename(script)
                if sc != "_svn" and sc != ".svn":
                    lst.append(sc)
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


#------------------------------------------------------------------------------
_PLURAL_TO_SINGLE = {
    'categories' : 'category',
    'servers' : 'server',
    'rss' : 'feed',
    'scripts' : 'script',
    'warnings' : 'warning',
    'files' : 'file',
    'jobs' : 'job'
    }
def plural_to_single(kw, def_kw=''):
    try:
        return _PLURAL_TO_SINGLE[kw]
    except KeyError:
        return def_kw


#------------------------------------------------------------------------------
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
                    downloader.update_server(keyword, None)
        return True
    else:
        return False

