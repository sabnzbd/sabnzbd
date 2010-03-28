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
sabnzbd.emailer - Send notification emails
"""
#------------------------------------------------------------------------------

from sabnzbd.utils import ssmtplib
import smtplib
import os
import logging
import re
import time
import glob
from sabnzbd.constants import *
import sabnzbd
from sabnzbd.misc import to_units, split_host
from sabnzbd.encoding import LatinFilter
import sabnzbd.cfg as cfg
from sabnzbd.lang import T, Ta


################################################################################
# EMAIL_SEND
#
#
################################################################################
def send(message):
    """ Send message if message non-empty and email-parms are set """
    if not message.strip('\n\r\t '):
        return "Skipped empty message"

    if cfg.email_server() and cfg.email_to() and cfg.email_from():

        failure = T('error-mailSend')
        server, port = split_host(cfg.email_server())
        if not port:
            port = 25

        logging.info("Connecting to server %s:%s", server, port)

        try:
            mailconn = ssmtplib.SMTP_SSL(server, port)
            mailconn.ehlo()

            logging.info("Connected to server %s:%s", server, port)

        except Exception, errorcode:
            if errorcode[0]:

                # Non SSL mail server
                logging.debug("Non-SSL mail server detected " \
                             "reconnecting to server %s:%s", server, port)

                try:
                    mailconn = smtplib.SMTP(server, port)
                    mailconn.ehlo()
                except:
                    logging.error(Ta('error-mailNoConn'))
                    return failure
            else:
                logging.error(Ta('error-mailNoConn'))
                return failure

        # TLS support
        if mailconn.ehlo_resp:
            m = re.search('STARTTLS', mailconn.ehlo_resp, re.IGNORECASE)
            if m:
                logging.debug("TLS mail server detected")

                try:
                    mailconn.starttls()
                    mailconn.ehlo()
                except:
                    logging.error(Ta('error-mailTLS'))
                    return failure

        # Authentication
        if (cfg.email_account() != "") and (cfg.email_pwd() != ""):
            try:
                mailconn.login(cfg.email_account(), cfg.email_pwd())
            except:
                logging.error(Ta('error-mailAuth'))
                return failure

        message = _prepare_message(message)
        try:
            mailconn.sendmail(cfg.email_from(), cfg.email_to(), message)
        except:
            logging.error(Ta('error-mailSend'))
            return failure

        try:
            mailconn.close()
        except:
            logging.warning(Ta('warn-noEmailClose'))

        logging.info("Notification e-mail succesfully sent")
        return T('msg-emailOK')



################################################################################
# email_endjob
#
#
################################################################################
from Cheetah.Template import Template

def send_with_template(prefix, parm):
    """ Send an email using template """

    parm['to'] = cfg.email_to.get_string()
    parm['from'] = cfg.email_from()
    parm['date'] = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())

    lst = []
    path = cfg.email_dir.get_path()
    if path and os.path.exists(path):
        try:
            lst = glob.glob(os.path.join(path, '%s-*.tmpl' % prefix))
        except:
            logging.error(Ta('error-mailTempl@1'), path)
    else:
        path = os.path.join(sabnzbd.DIR_PROG, DEF_LANGUAGE)
        tpath = os.path.join(path, '%s-%s.tmpl' % (prefix, cfg.language()))
        if os.path.exists(tpath):
            lst = [tpath]
        else:
            lst = [os.path.join(path, '%s-us-en.tmpl' % prefix)]

    ret = "No templates found"
    for temp in lst:
        if os.access(temp, os.R_OK):
            source = _decode_file(temp)
            message = Template(source=source,
                                searchList=[parm],
                                filter=LatinFilter,
                                compilerSettings={'directiveStartToken': '<!--#',
                                                  'directiveEndToken': '#-->'})
            ret = send(message.respond())
            del message
    return ret


def endjob(filename, msgid, cat, status, path, bytes, stages, script, script_output, script_ret):
    """ Send end-of-job email """

    # Translate the stage names
    xstages = {}
    for stage in stages:
        xstages[T('stage-'+stage.lower())] = stages[stage]

    parm = {}
    parm['status'] = status
    parm['name'] = filename
    parm['path'] = path
    parm['msgid'] = str(msgid)
    parm['stages'] = xstages
    parm['script'] = script
    parm['script_output'] = script_output
    parm['script_ret'] = script_ret
    parm['cat'] = cat
    parm['size'] = "%sB" % to_units(bytes)
    parm['end_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))

    return send_with_template('email', parm)


def rss_mail(feed, jobs):
    """ Send notification email containing list of files """

    parm = {'amount' : len(jobs), 'feed' : feed, 'jobs' : jobs}
    return send_with_template('rss', parm)


################################################################################
# EMAIL_DISKFULL
#
#
################################################################################
def diskfull():
    """ Send email about disk full, no templates """

    if cfg.email_full():
        return send(T('email-full@2') % (cfg.email_to.get_string(), cfg.email_from()))
    else:
        return ""


################################################################################
def _decode_file(path):
    """ Return content of file in Unicode string
        using encoding as specified in the file.
        Work-around for dumb handling of decoding by Cheetah.
    """
    fp = open(path, 'r')
    txt = fp.readline()
    m = re.search(r'#encoding[:\s]+(\S+)', txt)
    if m and m.group(1):
        encoding = m.group(1)
    else:
        encoding = 'latin-1'
    source = fp.read()
    fp.close()

    return source.decode(encoding)


################################################################################
from email.message import Message
RE_HEADER = re.compile(r'^([^:]+):(.*)')
def _prepare_message(txt):
    """ Do the proper message encodings
    """
    msg = Message()
    msg.set_charset('iso-8859-1')
    payload = []
    body = False
    for line in txt.encode('latin-1').split('\n'):
        if not line:
            body = True
        if body:
            payload.append(line)
        else:
            m = RE_HEADER.search(line)
            if m:
                msg.add_header(m.group(1).strip(), m.group(2).strip())
    msg.set_payload('\n'.join(payload), 'iso-8859-1')
    return msg.as_string()
