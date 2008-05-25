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
from sabnzbd.constants import *
import sabnzbd
from sabnzbd.newsunpack import build_command
from sabnzbd.nzbstuff import SplitFileName
from sabnzbd.misc import to_units, from_units, SplitHost

################################################################################
# prepare_msg
#
# Prepare message.
# - Downloaded bytes
# - Decoded status array.
# - Output from external script
################################################################################
def prepare_msg(bytes, status, script, output):

    result  = "Downloaded %sB\n\n" % to_units(bytes)
    result += "Results of the job:\n\n"

    stage_keys = status.keys()
    stage_keys.sort()
    for stage in stage_keys:
        result += "Stage %s\n" % (STAGENAMES[stage])
        for action in status[stage]:
            result += "    %s %s\n" % (action, status[stage][action])

    if script and (output != ""):
    	  result += "\nExternal processing by %s:\n" % script
    	  result += output

    return result


################################################################################
# EMAIL_SEND
#
#
################################################################################
def email_send(header, message):
    if sabnzbd.EMAIL_SERVER and sabnzbd.EMAIL_TO and sabnzbd.EMAIL_FROM:

        failure = "Email failed"
        server, port = SplitHost(sabnzbd.EMAIL_SERVER)
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

        # Message header
        msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nX-Priority: 5\r\nX-MS-Priority: 5\r\n\r\n" % \
              (sabnzbd.EMAIL_FROM, sabnzbd.EMAIL_TO, header)

        # Authentication
        if (sabnzbd.EMAIL_ACCOUNT != "") and (sabnzbd.EMAIL_PWD != ""):
            try:
                mailconn.login(sabnzbd.EMAIL_ACCOUNT, sabnzbd.EMAIL_PWD)
            except:
                logging.error("[%s] Failed to authenticate to mail server", __NAME__)
                return failure

        msg += message

        try:
            mailconn.sendmail(sabnzbd.EMAIL_FROM, sabnzbd.EMAIL_TO, msg)
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
def email_endjob(filename, success, status_text):
    name, msgid = SplitFileName(filename)
    message  = "Hello,\n\nSABnzbd has downloaded \'%s\'.\n\n" % name
    message += "Finished at %s\n" % time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
    message += "%s\n\nEnjoy!\n" % status_text
    
    if success:
        header = "SABnzbd has completed job %s" % name
    else:
        header = "SABnzbd failed to complete job %s" % name

    return email_send(header, message)
