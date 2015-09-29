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
sabnzbd.panic - Send panic message to the browser
"""

import os
import logging
import webbrowser
import tempfile

import sabnzbd
import sabnzbd.cfg as cfg

PANIC_NONE = 0
PANIC_PORT = 1
PANIC_TEMPL = 2
PANIC_QUEUE = 3
PANIC_FWALL = 4
PANIC_OTHER = 5
PANIC_XPORT = 6
PANIC_SQLITE = 7
PANIC_HOST = 8


def MSG_BAD_NEWS():
    # TODO: do we need Ta / T for this?
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


def MSG_BAD_FWALL():
    return Ta(r'''
    SABnzbd is not compatible with some software firewalls.<br>
    %s<br>
    Sorry, but we cannot solve this incompatibility right now.<br>
    Please file a complaint at your firewall supplier.<br>
    <br>
''')


def MSG_BAD_PORT():
    return Ta(r'''
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
        Ta(r'If you get this error message again, please try a different number.<br>')


def MSG_ILL_PORT():
    return Ta(r'''
    SABnzbd needs a free tcp/ip port for its internal web server.<br>
    Port %s on %s was tried , but the account used for SABnzbd has no permission to use it.<br>
    On OSX and Linux systems, normal users must use ports above 1023.<br>
    <br>
    Please restart SABnzbd with a different port number.''') + \
        '''<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --server %s:%s<br>
    <br>''' + \
        Ta(r'If you get this error message again, please try a different number.<br>')


def MSG_BAD_HOST():
    return Ta(r'''
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
    return Ta(r'''
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
    return Ta(r'''
    SABnzbd cannot find its web interface files in %s.<br>
    Please install the program again.<br>
    <br>
''')


def MSG_OTHER():
    return T('SABnzbd detected a fatal error:') + '<br>%s<br><br>%s<br>'


def MSG_OLD_QUEUE():
    return Ta(r'''
    SABnzbd detected a queue from an older release.<br><br>
    You can convert the queue by clicking "Repair" in Status-&gt;"Queue Repair".<br><br>
    You may choose to stop SABnzbd and finish the queue with the older program.<br><br>
    Click OK to proceed to SABnzbd''') + \
        ('''<br><br><FORM><input type="button" onclick="this.form.action='/.'; this.form.submit(); return false;" value="%s"/></FORM>''' % T('OK'))


def MSG_SQLITE():
    return Ta(r'''
    SABnzbd detected that the file sqlite3.dll is missing.<br><br>
    Some poorly designed virus-scanners remove this file.<br>
    Please check your virus-scanner, try to re-install SABnzbd and complain to your virus-scanner vendor.<br>
    <br>
''')


def panic_message(panic, a=None, b=None):
    """ Create the panic message from templates """
    if sabnzbd.WIN32:
        os_str = T('Press Startkey+R and type the line (example):')
        prog_path = '"%s"' % sabnzbd.MY_FULLNAME
    else:
        os_str = T('Open a Terminal window and type the line (example):')
        prog_path = sabnzbd.MY_FULLNAME

    if panic == PANIC_PORT:
        newport = int(b) + 1
        newport = "%s" % newport
        msg = MSG_BAD_PORT() % (b, a, os_str, prog_path, a, newport)
    elif panic == PANIC_XPORT:
        if int(b) < 1023:
            newport = 1024
        else:
            newport = int(b) + 1
        newport = "%s" % newport
        msg = MSG_ILL_PORT() % (b, a, os_str, prog_path, a, newport)
    elif panic == PANIC_TEMPL:
        msg = MSG_BAD_TEMPL() % a
    elif panic == PANIC_QUEUE:
        msg = MSG_BAD_QUEUE() % (a, os_str, prog_path)
    elif panic == PANIC_FWALL:
        if a:
            msg = MSG_BAD_FWALL() % T('It is likely that you are using ZoneAlarm on Vista.<br>')
        else:
            msg = MSG_BAD_FWALL() % "<br>"
    elif panic == PANIC_SQLITE:
        msg = MSG_SQLITE()
    elif panic == PANIC_HOST:
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
    os.write(msgfile, msg)
    os.close(msgfile)
    return url


def panic_fwall(vista):
    launch_a_browser(panic_message(PANIC_FWALL, vista))


def panic_port(host, port):
    launch_a_browser(panic_message(PANIC_PORT, host, port))


def panic_host(host, port):
    launch_a_browser(panic_message(PANIC_HOST, host, port))


def panic_xport(host, port):
    launch_a_browser(panic_message(PANIC_XPORT, host, port))
    logging.error(T('You have no permission to use port %s'), port)


def panic_queue(name):
    launch_a_browser(panic_message(PANIC_QUEUE, name, 0))


def panic_tmpl(name):
    launch_a_browser(panic_message(PANIC_TEMPL, name, 0))


def panic_sqlite(name):
    launch_a_browser(panic_message(PANIC_SQLITE, name, 0))


def panic_old_queue():
    msg = MSG_OLD_QUEUE()
    return MSG_BAD_NEWS() % (sabnzbd.MY_NAME, sabnzbd.__version__, sabnzbd.MY_NAME, sabnzbd.__version__, msg, '')


def panic(reason, remedy=""):
    print "\n%s:\n  %s\n%s" % (T('Fatal error'), reason, remedy)
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

    logging.info("Launching browser with %s", url)
    try:
        if url and not url.startswith('http'):
            url = 'file:///%s' % url
        webbrowser.open(url, 2, 1)
    except:
        logging.warning(T('Cannot launch the browser, probably not found'))
        logging.info("Traceback: ", exc_info=True)


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
      location.href = location.protocol + '//' + location.hostname + (location.port ? ':' + location.port : '') + '/sabnzbd/' ;
      //-->
      </script>
    </head>
    <body><br/></body>
</html>
'''
