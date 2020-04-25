#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.panic - Send panic message to the browser
"""

import os
import logging
import tempfile
import ctypes

try:
    import webbrowser
except ImportError:
    webbrowser = None

import sabnzbd
import sabnzbd.cfg as cfg
from sabnzbd.encoding import utob

PANIC_PORT = 1
PANIC_TEMPL = 2
PANIC_QUEUE = 3
PANIC_OTHER = 5
PANIC_SQLITE = 7
PANIC_HOST = 8


def MSG_BAD_NEWS():
    return r'''
    <html>
    <head>
    <title>''' + T('Problem with') + ''' %s %s</title>
    </head>
    <body>
    <h1><font color="#0000FF"> %s %s</font></h1>
    <p align="center">&nbsp;</p>
    <p align="center"><font size="5">
    <blockquote>
        %s
    </blockquote>
    <br>%s<br>
    </body>
</html>
'''


def MSG_BAD_PORT():
    return T(r'''
    SABnzbd needs a free tcp/ip port for its internal web server.<br>
    Port %s on %s was tried , but it is not available.<br>
    Some other software uses the port or SABnzbd is already running.<br>
    <br>
    Please restart SABnzbd with a different port number.''') + \
        '''<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --server %s:%s<br>
    <br>''' + \
        T(r'If you get this error message again, please try a different number.<br>')


def MSG_BAD_HOST():
    return T(r'''
    SABnzbd needs a valid host address for its internal web server.<br>
    You have specified an invalid address.<br>
    Safe values are <b>localhost</b> and <b>0.0.0.0</b><br>
    <br>
    Please restart SABnzbd with a proper host address.''') + \
        '''<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --server %s:%s<br>
    <br>
'''


def MSG_BAD_QUEUE():
    return T(r'''
    SABnzbd detected saved data from an other SABnzbd version<br>
    but cannot re-use the data of the other program.<br><br>
    You may want to finish your queue first with the other program.<br><br>
    After that, start this program with the "--clean" option.<br>
    This will erase the current queue and history!<br>
    SABnzbd read the file "%s".''') + \
        '''<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --clean<br>
    <br>
'''


def MSG_BAD_TEMPL():
    return T(r'''
    SABnzbd cannot find its web interface files in %s.<br>
    Please install the program again.<br>
    <br>
''')


def MSG_OTHER():
    return T('SABnzbd detected a fatal error:') + '<br>%s<br><br>%s<br>'


def MSG_SQLITE():
    return T(r'''
    SABnzbd detected that the file sqlite3.dll is missing.<br><br>
    Some poorly designed virus-scanners remove this file.<br>
    Please check your virus-scanner, try to re-install SABnzbd and complain to your virus-scanner vendor.<br>
    <br>
''')


def panic_message(panic_code, a=None, b=None):
    """ Create the panic message from templates """
    if sabnzbd.WIN32:
        os_str = T('Press Startkey+R and type the line (example):')
        prog_path = '"%s"' % sabnzbd.MY_FULLNAME
    else:
        os_str = T('Open a Terminal window and type the line (example):')
        prog_path = sabnzbd.MY_FULLNAME

    if panic_code == PANIC_PORT:
        newport = int(b) + 1
        newport = "%s" % newport
        msg = MSG_BAD_PORT() % (b, a, os_str, prog_path, a, newport)
    elif panic_code == PANIC_TEMPL:
        msg = MSG_BAD_TEMPL() % a
    elif panic_code == PANIC_QUEUE:
        msg = MSG_BAD_QUEUE() % (a, os_str, prog_path)
    elif panic_code == PANIC_SQLITE:
        msg = MSG_SQLITE()
    elif panic_code == PANIC_HOST:
        msg = MSG_BAD_HOST() % (os_str, prog_path, 'localhost', b)
    else:
        msg = MSG_OTHER() % (a, b)

    msg = MSG_BAD_NEWS() % (sabnzbd.MY_NAME, sabnzbd.__version__, sabnzbd.MY_NAME, sabnzbd.__version__,
                          msg, T('Program did not start!'))

    if sabnzbd.WIN_SERVICE:
        sabnzbd.WIN_SERVICE.ErrLogger('Panic exit', msg)

    if (not cfg.autobrowser()) or sabnzbd.DAEMON:
        return

    msgfile, url = tempfile.mkstemp(suffix='.html')
    os.write(msgfile, utob(msg))
    os.close(msgfile)
    return url


def panic_port(host, port):
    show_error_dialog("\n%s:\n  %s" % (T('Fatal error'), T('Unable to bind to port %s on %s. Some other software uses the port or SABnzbd is already running.') % (port, host)))
    launch_a_browser(panic_message(PANIC_PORT, host, port))


def panic_host(host, port):
    launch_a_browser(panic_message(PANIC_HOST, host, port))


def panic_queue(name):
    launch_a_browser(panic_message(PANIC_QUEUE, name, 0))


def panic_tmpl(name):
    launch_a_browser(panic_message(PANIC_TEMPL, name, 0))


def panic(reason, remedy=""):
    show_error_dialog("\n%s:\n  %s\n%s" % (T('Fatal error'), reason, remedy))
    launch_a_browser(panic_message(PANIC_OTHER, reason, remedy))


def launch_a_browser(url, force=False):
    """ Launch a browser pointing to the URL """
    if not force and not cfg.autobrowser() or sabnzbd.DAEMON:
        return

    if '::1' in url and '[::1]' not in url:
        # Get around idiosyncrasy in Python runtime
        url = url.replace('::1', '[::1]')

    if cfg.enable_https() and not cfg.https_port.get_int():
        # Must use https, because http is not available
        url = url.replace('http:', 'https:')

    if 'localhost' in url and not cfg.ipv6_hosting():
        url = url.replace('localhost', '127.0.0.1')
    logging.info("Launching browser with %s", url)
    try:
        if url and not url.startswith('http'):
            url = 'file:///%s' % url
        if webbrowser:
            webbrowser.open(url, 2, 1)
        else:
            logging.info('Not showing panic message in webbrowser, no support found')
    except:
        logging.warning(T('Cannot launch the browser, probably not found'))
        logging.info("Traceback: ", exc_info=True)


def show_error_dialog(msg):
    """ Show a pop-up when program cannot start
        Windows-only, otherwise only print to console
    """
    if sabnzbd.WIN32:
        ctypes.windll.user32.MessageBoxW(0, msg, T('Fatal error'), 0)
    print(msg)


def error_page_401(status, message, traceback, version):
    """ Custom handler for 401 error """
    title = T('Access denied')
    body = T('Error %s: You need to provide a valid username and password.') % status
    return r'''
<html>
    <head>
    <title>%s</title>
    </head>
    <body>
    <br/><br/>
    <font color="#0000FF">%s</font>
    </body>
</html>
''' % (title, body)


def error_page_404(status, message, traceback, version):
    """ Custom handler for 404 error, redirect to main page """
    return r'''
<html>
    <head>
      <script type="text/javascript">
      <!--
      location.href = location.protocol + '//' + location.hostname + (location.port ? ':' + location.port : '') + '%s' ;
      //-->
      </script>
    </head>
    <body><br/></body>
</html>
''' % cfg.url_base()
