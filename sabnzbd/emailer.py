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
from sabnzbd.misc import to_units, split_host, time_format
from sabnzbd.encoding import LatinFilter
import sabnzbd.cfg as cfg


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

        message = _prepare_message(message)

        failure = T('Failed to send e-mail')
        server, port = split_host(cfg.email_server())
        if not port:
            port = 25

        logging.debug("Connecting to server %s:%s", server, port)

        try:
            mailconn = ssmtplib.SMTP_SSL(server, port)
            mailconn.ehlo()

            logging.debug("Connected to server %s:%s", server, port)

        except Exception, errorcode:
            if errorcode[0]:

                # Non SSL mail server
                logging.debug("Non-SSL mail server detected " \
                             "reconnecting to server %s:%s", server, port)

                try:
                    mailconn = smtplib.SMTP(server, port)
                    mailconn.ehlo()
                except:
                    logging.error(Ta('Failed to connect to mail server'))
                    return failure
            else:
                logging.error(Ta('Failed to connect to mail server'))
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
                    logging.error(Ta('Failed to initiate TLS connection'))
                    return failure

        # Authentication
        if (cfg.email_account() != "") and (cfg.email_pwd() != ""):
            try:
                mailconn.login(cfg.email_account(), cfg.email_pwd())
            except:
                logging.error(Ta('Failed to authenticate to mail server'))
                return failure

        try:
            mailconn.sendmail(cfg.email_from(), cfg.email_to(), message)
        except:
            logging.error(Ta('Failed to send e-mail'))
            return failure

        try:
            mailconn.close()
        except:
            logging.warning(Ta('Failed to close mail connection'))

        logging.info("Notification e-mail succesfully sent")
        return T('Email succeeded')



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
    parm['date'] = time.strftime(time_format('%a, %d %b %Y %H:%M:%S +0000'), time.gmtime())

    lst = []
    path = cfg.email_dir.get_path()
    if path and os.path.exists(path):
        try:
            lst = glob.glob(os.path.join(path, '%s-*.tmpl' % prefix))
        except:
            logging.error(Ta('Cannot find email templates in %s'), path)
    else:
        path = os.path.join(sabnzbd.DIR_PROG, DEF_EMAIL_TMPL)
        tpath = os.path.join(path, '%s-%s.tmpl' % (prefix, cfg.language()))
        if os.path.exists(tpath):
            lst = [tpath]
        else:
            lst = [os.path.join(path, '%s-en.tmpl' % prefix)]

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
        xstages[Tx('stage-'+stage.lower())] = stages[stage]

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
    parm['end_time'] = time.strftime(time_format('%Y-%m-%d %H:%M:%S'), time.localtime(time.time()))

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
        return send(T('''to: %s
from: %s
subject: SABnzbd reports Disk Full

Hi,

SABnzbd has stopped downloading, because the disk is almost full.
Please make room and resume SABnzbd manually.

''') % (cfg.email_to.get_string(), cfg.email_from()))
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
try:
    from email.message import Message
    from email.header import Header
    from email.encoders import encode_quopri
except:
    # Python 2.4 uses different names
    from email.Message import Message
    from email.Header import Header
    from email.Encoders import encode_quopri

RE_HEADER = re.compile(r'^([^:]+):(.*)')

def _prepare_message(txt):
    """ Apply the proper encoding to all email fields.
        The body will be Latin-1, the headers will be 'quopri'd when necessary.
    """
    def plain(val):
        """ Return True when val is plain ASCII """
        try:
            val.decode('ascii')
            return True
        except:
            return False

    # Use Latin-1 because not all email clients know UTF-8.
    code = 'ISO-8859-1'

    msg = Message()
    msg.set_charset(code)
    payload = []
    body = False
    header = False
    for line in txt.encode(code, 'replace').split('\n'):
        if header and not line:
            body = True
        if body:
            payload.append(line)
        else:
            m = RE_HEADER.search(line)
            if m:
                header = True
                keyword = m.group(1).strip()
                value = m.group(2).strip()
                if plain(value):
                    # Don't encode if not needed, because some email clients
                    # choke when headers like "date" are encoded.
                    msg.add_header(keyword, value)
                else:
                    header = Header(value, code)
                    msg[keyword] = header

    msg.set_payload('\n'.join(payload), code)

    # Prevent double header (because it will be added again by encode_quopri)
    try:
        del msg['Content-Transfer-Encoding']
    except:
        pass

    encode_quopri(msg)
    return msg.as_string()
