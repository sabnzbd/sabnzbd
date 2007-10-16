"""
sabnzbd.nzbgrab -  basend on grabnzb.py v0.4 by
                   Freddie (freddie@madcowdisease.org)

		   Updated by Thomas 'Freaky' Hurst (freaky@newzbin.com)
		   for basic DNZB support
"""

__NAME__ = "nzbgrab"

import httplib
import urllib
import time
import logging
import re

QUOTA = None

################################################################################
# 'Public' Methods                                                             #
################################################################################
def grabnzb(msgid, username_newzbin, password_newzbin):
    global QUOTA
    logging.warning('[%s] Fetching NZB for Newzbin report #%s', __NAME__, msgid)
    
    headers = {
         'User-Agent': 'grabnzb.py',
    }
    
    # Off we go then
    conn = httplib.HTTPConnection('v3.newzbin.com')
    
    postdata = { 'username': username_newzbin, 'password': password_newzbin, 'reportid': msgid }
    postdata = urllib.urlencode(postdata)
    
    headers['Content-type'] = 'application/x-www-form-urlencoded'
    
    fetchurl = '/api/dnzb/'
    conn.request('POST', fetchurl, postdata, headers)
    response = conn.getresponse()
    
    # Save debug info if we have to
    data = response.read()
	
    QUOTA = 0

    
    # Get the filename
    rcode = response.getheader('X-DNZB-RCode')
    rtext = response.getheader('X-DNZB-RText')
    report_name = response.getheader('X-DNZB-Name')
    report_cat  = response.getheader('X-DNZB-Category')
    cat_root = report_cat
    cat_tail = 'All' # DNZB has no subcategories

    if rcode != '200':
        logging.warning("[%s] DNZB request failed: %s - %s", __NAME__, rcode, rtext)
        return (None, None, None, None)

    # sanitize report_name
    sanitize_re = re.compile("[^ A-Za-z0-9\^&'@{}\\[\\]$=#()%.,+~_-]") # check this
    newname = sanitize_re.sub('_', report_name)
    newname += '.nzb'
    # length?

    logging.info('[%s] Successfully fetched %s %s (%s)', __NAME__, report_cat, report_name, newname)

    return (newname, data, cat_root, cat_tail)

