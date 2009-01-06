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
from sabnzbd.misc import to_units, from_units, SplitHost
import sabnzbd.cfg as cfg


################################################################################
# EMAIL_SEND
#
#
################################################################################
def send(message):
    if cfg.EMAIL_SERVER.get() and cfg.EMAIL_TO.get() and cfg.EMAIL_FROM.get():

        failure = "Email failed"
        server, port = SplitHost(cfg.EMAIL_SERVER.get())
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
        if (cfg.EMAIL_ACCOUNT.get() != "") and (cfg.EMAIL_PWD.get() != ""):
            try:
                mailconn.login(cfg.EMAIL_ACCOUNT.get(), cfg.EMAIL_PWD.get())
            except:
                logging.error("[%s] Failed to authenticate to mail server", __NAME__)
                return failure

        try:
            mailconn.sendmail(cfg.EMAIL_FROM.get(), cfg.EMAIL_TO.get(), message)
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

def endjob(filename, msgid, cat, status, path, bytes, stages, script, script_output):
    """ Send email using templates """

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
    parm['to'] = cfg.EMAIL_TO.get()
    parm['from'] = cfg.EMAIL_FROM.get()
    parm['name'] = filename
    parm['path'] = path
    parm['msgid'] = str(msgid)
    parm['output'] = output
    parm['script'] = script
    parm['script_output'] = script_output
    parm['cat'] = cat
    parm['size'] = "%sB" % to_units(bytes)
    parm['end_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))

    path = cfg.EMAIL_DIR.get_path()
    if not (path and os.path.exists(path)):
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

    if not cfg.EMAIL_FULL.get():
        return

    message = """to: %s
from: %s
subject: SABnzbd reports Disk Full

Hi,

SABnzbd has stopped downloading, because the disk is almost full.
Please make room and resume SABnzbd manually.

""" % (cfg.EMAIL_TO.get(), cfg.EMAIL_FROM.get())

    return send(message)
