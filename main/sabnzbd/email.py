#!/usr/bin/python -OO
# Copyright 2008 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.email - Send notification emails
"""
#------------------------------------------------------------------------------

__NAME__ = "email"

from utils import ssmtplib
import smtplib
import os
import logging
import subprocess
import re
import datetime
import time
import tempfile
import socket
import glob
from sabnzbd.constants import *
import sabnzbd
from sabnzbd.newsunpack import build_command
from sabnzbd.nzbstuff import SplitFileName
from sabnzbd.misc import to_units, from_units, SplitHost, decodePassword

EMAIL_SERVER = None
EMAIL_TO = None
EMAIL_FROM = None
EMAIL_ACCOUNT = None
EMAIL_PWD = None
EMAIL_ENDJOB = 0
EMAIL_FULL = False
EMAIL_DIR = ''

def init():
    """ Setup email parameters """
    global EMAIL_SERVER, EMAIL_TO, EMAIL_FROM, EMAIL_ACCOUNT, EMAIL_PWD, \
           EMAIL_ENDJOB, EMAIL_FULL, EMAIL_DIR

    EMAIL_SERVER = sabnzbd.check_setting_str(sabnzbd.CFG, 'misc', 'email_server', '')
    EMAIL_TO     = sabnzbd.check_setting_str(sabnzbd.CFG, 'misc', 'email_to', '')
    EMAIL_FROM   = sabnzbd.check_setting_str(sabnzbd.CFG, 'misc', 'email_from', '')
    EMAIL_ACCOUNT= sabnzbd.check_setting_str(sabnzbd.CFG, 'misc', 'email_account', '')
    EMAIL_PWD    = decodePassword(sabnzbd.check_setting_str(sabnzbd.CFG, 'misc', 'email_pwd', '', False), 'email')
    EMAIL_ENDJOB = sabnzbd.check_setting_int(sabnzbd.CFG, 'misc', 'email_endjob', 0)
    EMAIL_FULL   = bool(sabnzbd.check_setting_int(sabnzbd.CFG, 'misc', 'email_full', 0))
    EMAIL_DIR    = sabnzbd.dir_setup(sabnzbd.CFG, 'email_dir', sabnzbd.DIR_HOME, '')


################################################################################
# EMAIL_SEND
#
#
################################################################################
def send(message):
    global EMAIL_SERVER, EMAIL_TO, EMAIL_FROM, EMAIL_ACCOUNT, EMAIL_PWD, \
           EMAIL_ENDJOB, EMAIL_FULL, EMAIL_DIR
    if EMAIL_SERVER and EMAIL_TO and EMAIL_FROM:

        failure = "Email failed"
        server, port = SplitHost(EMAIL_SERVER)
        if not port:
            port = 25

        logging.info("[%s] Connecting to server %s:%s",__NAME__, server, port)

        try:
            mailconn = ssmtplib.SMTP_SSL(server, port)
            mailconn.ehlo()

            logging.info("[%s] Connected to server %s:%s", __NAME__, server, port)

        except Exception, errorcode:
            if errorcode[0]:

                # Non SSL mail server
                logging.debug("[%s] Non-SSL mail server detected " \
                             "reconnecting to server %s:%s", __NAME__, server, port)

                try:
                    mailconn = smtplib.SMTP(server, port)
                    mailconn.ehlo()
                except:
                    logging.error("[%s] Failed to connect to mail server", __NAME__)
                    return failure
            else:
                logging.error("[%s] Failed to connect to mail server", __NAME__)
                return failure

        # TLS support
        if mailconn.ehlo_resp:
            m = re.search('STARTTLS', mailconn.ehlo_resp, re.IGNORECASE)
            if m:
                logging.debug("[%s] TLS mail server detected")

                try:
                    mailconn.starttls()
                    mailconn.ehlo()
                except:
                    logging.error("[%s] Failed to initiate TLS connection", __NAME__)
                    return failure

        # Authentication
        if (EMAIL_ACCOUNT != "") and (EMAIL_PWD != ""):
            try:
                mailconn.login(EMAIL_ACCOUNT, EMAIL_PWD)
            except:
                logging.error("[%s] Failed to authenticate to mail server", __NAME__)
                return failure

        try:
            mailconn.sendmail(EMAIL_FROM, EMAIL_TO, message)
        except:
            logging.error("[%s] Failed to send e-mail", __NAME__)
            return failure

        try:
            mailconn.close()
        except:
            logging.warning("[%s] Failed to close mail connection", __NAME__)

        logging.info("[%s] Notification e-mail succesfully sent", __NAME__)
        return "Email succeeded"



################################################################################
# EMAIL_ENDJOB
#
#
################################################################################
from Cheetah.Template import Template

def endjob(filename, cat, status, path, bytes, stages, script, script_output):
    """ Send email using templates """
    global EMAIL_SERVER, EMAIL_TO, EMAIL_FROM, EMAIL_ACCOUNT, EMAIL_PWD, \
           EMAIL_ENDJOB, EMAIL_FULL, EMAIL_DIR
    
    name, msgid = SplitFileName(filename)

    output = []
    stage_keys = stages.keys()
    stage_keys.sort()
    for stage in stage_keys:
        res = {}
        res['name'] = STAGENAMES[stage]
        res['actions'] = stages[stage]
        output.append(res)

    parm = {}
    parm['status'] = status
    parm['to'] = EMAIL_TO
    parm['from'] = EMAIL_FROM
    parm['name'] = name
    parm['path'] = path
    parm['msgid'] = msgid
    parm['output'] = output
    parm['script'] = script
    parm['script_output'] = script_output
    parm['cat'] = cat
    parm['size'] = "%sB" % to_units(bytes)
    parm['end_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))

    if EMAIL_DIR and os.path.exists(EMAIL_DIR):
        path = EMAIL_DIR
    else:
        path = sabnzbd.DIR_PROG
    try:
        lst = glob.glob(os.path.join(path, '*.tmpl'))
    except:
        logging.error('[%s] Cannot find email templates in %s', __NAME__, path)
        lst = []

    ret = "No templates found"
    for temp in lst:
        if os.access(temp, os.R_OK):
            message = Template(file=temp,
                                searchList=[parm],
                                compilerSettings={'directiveStartToken': '<!--#',
                                                  'directiveEndToken': '#-->'})
            ret = send(message.respond())
            del message
    return ret



################################################################################
# EMAIL_DISKFULL
#
#
################################################################################
def diskfull():
    """ Send email about disk full, no templates """
    global EMAIL_TO, EMAIL_FROM, EMAIL_FULL

    if not EMAIL_FULL:
        return

    message = """to: %s
from: %s
subject: SABnzbd reports Disk Full

Hi,

SABnzbd has stopped downloading, because the disk is almost full.
Please make room and resume SABnzbd manually.

""" % (EMAIL_TO, EMAIL_FROM)

    return send(message)
