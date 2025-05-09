#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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

import smtplib
import logging
import re
import time
import glob
import os

from Cheetah.Template import Template
from email.message import EmailMessage


import sabnzbd
from sabnzbd.constants import DEF_EMAIL_TMPL, CHEETAH_DIRECTIVES
from sabnzbd.misc import to_units, split_host, time_format
from sabnzbd.notifier import check_cat
import sabnzbd.cfg as cfg

RE_HEADER = re.compile(r"^([^:]+):(.*)")


def errormsg(msg):
    logging.error(msg)
    return msg


def get_email_date():
    """Return un-localized date string for the Date: field"""
    # Get locale independent date/time string: "Sun May 22 20:15:12 2011"
    day, month, dayno, hms, year = time.asctime(time.gmtime()).split()
    return "%s, %s %s %s %s +0000" % (day, dayno, month, year, hms)


def send_email(message, email_to, test=None):
    """Send message if message non-empty and email-parms are set"""
    # we should not use CFG if we are testing. we should use values
    # from UI instead.
    # email_to is replaced at send_with_template, since it can be an array
    if test:
        email_server = test.get("email_server")
        email_from = test.get("email_from")
        email_account = test.get("email_account")
        email_pwd = test.get("email_pwd")
        if email_pwd and not email_pwd.replace("*", ""):
            # If all stars, get stored password instead
            email_pwd = cfg.email_pwd()
    else:
        email_server = cfg.email_server()
        email_from = cfg.email_from()
        email_account = cfg.email_account()
        email_pwd = cfg.email_pwd()

    if not message.strip("\n\r\t "):
        return "Skipped empty message"

    # Prepare the email
    email_message = _prepare_message(message)

    if email_server and email_to and email_from:
        server, port = split_host(email_server)
        if not port:
            port = 25
        logging.debug("Connecting to server %s:%s", server, port)

        try:
            mailconn = smtplib.SMTP_SSL(server, port)
            mailconn.ehlo()
            logging.debug("Connected to server %s:%s", server, port)
        except Exception:
            # Non SSL mail server
            logging.debug("Non-SSL mail server detected reconnecting to server %s:%s", server, port)

            try:
                mailconn = smtplib.SMTP(server, port)
                mailconn.ehlo()
            except Exception:
                logging.info("Traceback: ", exc_info=True)
                return errormsg(T("Failed to connect to mail server"))

        # TLS support
        if mailconn.ehlo_resp and re.search(b"STARTTLS", mailconn.ehlo_resp, re.IGNORECASE):
            logging.debug("TLS mail server detected")
            try:
                mailconn.starttls()
                mailconn.ehlo()
            except Exception:
                logging.info("Traceback: ", exc_info=True)
                return errormsg(T("Failed to initiate TLS connection"))

        # Authentication
        if (email_account != "") and (email_pwd != ""):
            try:
                mailconn.login(email_account, email_pwd)
            except smtplib.SMTPHeloError:
                return errormsg(T("The server didn't reply properly to the helo greeting"))
            except smtplib.SMTPAuthenticationError:
                return errormsg(T("Failed to authenticate to mail server"))
            except smtplib.SMTPException:
                return errormsg(T("No suitable authentication method was found"))
            except Exception:
                logging.info("Traceback: ", exc_info=True)
                return errormsg(T("Unknown authentication failure in mail server"))

        try:
            mailconn.sendmail(email_from, email_to, email_message)
            msg = None
        except smtplib.SMTPHeloError:
            msg = errormsg("The server didn't reply properly to the helo greeting.")
        except smtplib.SMTPRecipientsRefused:
            msg = errormsg("The server rejected ALL recipients (no mail was sent).")
        except smtplib.SMTPSenderRefused:
            msg = errormsg("The server didn't accept the from_addr.")
        except smtplib.SMTPDataError:
            msg = errormsg("The server replied with an unexpected error code (other than a refusal of a recipient).")
        except Exception:
            logging.info("Traceback: ", exc_info=True)
            msg = errormsg(T("Failed to send e-mail"))

        try:
            mailconn.close()
        except Exception:
            logging.info("Traceback: ", exc_info=True)
            errormsg(T("Failed to close mail connection"))

        if msg:
            return msg
        else:
            logging.info("Notification e-mail successfully sent")
            return T("Email succeeded")
    else:
        return T("Cannot send, missing required data")


def send_with_template(prefix, parm, test=None):
    """Send an email using template"""
    parm["from"] = cfg.email_from()
    parm["date"] = get_email_date()

    ret = None
    email_templates = []
    path = cfg.email_dir.get_path()
    if path and os.path.exists(path):
        try:
            email_templates = glob.glob(os.path.join(path, "%s-*.tmpl" % prefix))
        except Exception:
            logging.error(T("Cannot find email templates in %s"), path)
    else:
        path = os.path.join(sabnzbd.DIR_PROG, DEF_EMAIL_TMPL)
        tpath = os.path.join(path, "%s-%s.tmpl" % (prefix, cfg.language()))
        if os.path.exists(tpath):
            email_templates = [tpath]
        else:
            email_templates = [os.path.join(path, "%s-en.tmpl" % prefix)]

    for template_file in email_templates:
        logging.debug("Trying to send email using template %s", template_file)
        if os.access(template_file, os.R_OK):
            if test:
                recipients = [test.get("email_to")]
            else:
                recipients = cfg.email_to()

            if len(recipients):
                for recipient in recipients:
                    # Force-open as UTF-8, otherwise Cheetah breaks it
                    with open(template_file, "r", encoding="utf-8") as template_fp:
                        parm["to"] = recipient
                        message = Template(file=template_fp, searchList=[parm], compilerSettings=CHEETAH_DIRECTIVES)
                        ret = send_email(message.respond(), recipient, test)
            else:
                ret = T("No recipients given, no email sent")
        else:
            # Can't open or read file, stop
            return errormsg(T("Cannot read %s") % template_file)

    # Did we send any emails at all?
    if not ret:
        ret = T("No email templates found")
    return ret


def endjob(
    filename, cat, status, path, bytes_downloaded, fail_msg, stages, script, script_output, script_ret, test=None
):
    """Send end-of-job email"""
    # Is it allowed?
    if not check_cat("misc", cat, keyword="email") and not test:
        return None

    # Translate the stage names
    tr = sabnzbd.api.Ttemplate
    if not status and fail_msg:
        xstages = {tr("stage-fail"): (fail_msg,)}
    else:
        xstages = {}

    for stage in stages:
        lines = []
        for line in stages[stage]:
            if "\n" in line or "<br/>" in line:
                lines.extend(line.replace("<br/>", "\n").split("\n"))
            else:
                lines.append(line)
        xstages[tr("stage-" + stage.lower())] = lines

    parm = {}
    parm["status"] = status
    parm["name"] = filename
    parm["path"] = path
    parm["msgid"] = ""
    parm["stages"] = xstages
    parm["script"] = script
    parm["script_output"] = script_output
    parm["script_ret"] = script_ret
    parm["cat"] = cat
    parm["size"] = "%sB" % to_units(bytes_downloaded)
    parm["end_time"] = time.strftime(time_format("%Y-%m-%d %H:%M:%S"))

    return send_with_template("email", parm, test)


def rss_mail(feed, jobs):
    """Send notification email containing list of files"""
    parm = {"amount": len(jobs), "feed": feed, "jobs": jobs}
    return send_with_template("rss", parm)


def badfetch_mail(msg, url):
    """Send notification email about failed NZB fetch"""
    parm = {"url": url, "msg": msg}
    return send_with_template("badfetch", parm)


def diskfull_mail():
    """Send email about disk full, no templates"""
    if cfg.email_full():
        return send_email(
            T(
                """To: %s
From: %s
Date: %s
Subject: SABnzbd reports Disk Full

Hi,

SABnzbd has stopped downloading, because the disk is almost full.
Please make room and resume SABnzbd manually.

"""
            )
            % (cfg.email_to.get_string(), cfg.email_from(), get_email_date()),
            cfg.email_to(),
        )
    else:
        return ""


def _prepare_message(txt):
    """Parse the headers in the template to real headers"""
    msg = EmailMessage()
    payload = []
    body = False
    header = False
    for line in txt.split("\n"):
        if header and not line:
            body = True
        if body:
            payload.append(line)
        elif m := RE_HEADER.search(line):
            # If we match a header
            header = True
            keyword = m.group(1).strip()
            value = m.group(2).strip()
            msg[keyword] = value

    msg.set_content("\n".join(payload))
    return msg.as_bytes(policy=msg.policy.clone(linesep="\r\n"))
