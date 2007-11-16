#!/usr/bin/python -OO
# Copyright 2007 The ShyPike <shypike@users.sourceforge.net>
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

import os
import logging
import subprocess
import re
import datetime
import time
import tempfile
from sabnzbd.constants import *
import sabnzbd
from sabnzbd.newsunpack import build_command

################################################################################
# iso_units
#
# Return bytes in K/M/G/T/P units.
################################################################################
def iso_units(bytes):
    units = ('', 'K', 'M', 'G', 'T', 'P')
    n= 0
    while (float(bytes) > 1023.0) and (n < 6):
        bytes = float(bytes) / 1024.0
        n= n+1
    unit = units[n]
    return "%.1f %sB" % (bytes, unit)


################################################################################
# prepare_msg
#
# Prepare message.
# - Downloaded bytes
# - Decoded status array.
# - Output from external script
################################################################################
def prepare_msg(bytes, status, output):

    result  = "Downloaded %s\n\n" % iso_units(bytes)
    result += "Results of the job:\n\n"

    stage_keys = status.keys()
    stage_keys.sort()
    for stage in stage_keys:
        result += "Stage %s\n" % (STAGENAMES[stage])
        for action in status[stage]:
            result += "    %s %s\n" % (action, status[stage][action])

    if output != "":
    	  result += "\nExternal processing:\n" + output

    return result


################################################################################
# EMAIL_SEND
#
# Uses external sendEmail progam
#
################################################################################
def email_send(header, message):
    if (sabnzbd.newsunpack.EMAIL_COMMAND != []) and (sabnzbd.EMAIL_SERVER != "") and (sabnzbd.EMAIL_TO != "") and (sabnzbd.EMAIL_FROM != ""):

        msgfile, msgname = tempfile.mkstemp()
        os.write(msgfile, message)
        os.close(msgfile)
                  
        command = []
        command.extend(sabnzbd.newsunpack.EMAIL_COMMAND)
        command.extend(['-s',
                        '%s' % sabnzbd.EMAIL_SERVER,
                        '-f',
                        '%s' % sabnzbd.EMAIL_FROM,
                        '-t',
                        '%s' % sabnzbd.EMAIL_TO,
                        '-o',
                        'tls=auto',
                        '-u',
                        '%s' % header,
                        '-o',
                        'message-file=%s' %  msgname
                       ])

        logging.info('[%s] Starting email program %s', __NAME__, command)

        if (sabnzbd.EMAIL_ACCOUNT != "") and (sabnzbd.EMAIL_PWD != ""):
            command.extend(['-xu',
                            '%s' % sabnzbd.EMAIL_ACCOUNT,
                            '-xp',
                            '%s' % sabnzbd.EMAIL_PWD
                           ])
    
        stup, need_shell, command, creationflags = build_command(command)

        p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             startupinfo=stup, creationflags=creationflags)
                         
        output = p.stdout.read()
        p.wait()
        os.remove(msgname)
        if re.search('Email was sent successfully', output):
            logging.info("[%s] %s", __NAME__, output)
        else:
            logging.error("[%s] %s", __NAME__, output)
        return output
	  

################################################################################
# EMAIL_ENDJOB
#
#
################################################################################
def email_endjob(filename, status_text):
    if (sabnzbd.newsunpack.EMAIL_COMMAND != "") and sabnzbd.EMAIL_ENDJOB and (sabnzbd.EMAIL_SERVER != "") and (sabnzbd.EMAIL_TO != "") and (sabnzbd.EMAIL_FROM != ""):

        message  = "Hello,\n\nSABnzbd has downloaded \'%s\'.\n\n" % filename
        message += "Finished at %s\n" % time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        message += "%s\n\nEnjoy!\n" % status_text

        header = "SABnzbd has completed job %s" % filename

        return email_send(header, message)
