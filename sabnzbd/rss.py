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
sabnzbd.rss - rss client functionality
"""

import re
import logging
import time
import threading

import sabnzbd
from sabnzbd.constants import RSS_FILE_NAME, DEFAULT_PRIORITY, NORMAL_PRIORITY, DUP_PRIORITY
from sabnzbd.decorators import synchronized
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.misc import cat_convert, wildcard_to_re, cat_to_opts, \
    match_str, from_units, int_conv, get_urlbase
import sabnzbd.emailer as emailer
from sabnzbd.encoding import unicoder, xml_name

import sabnzbd.utils.feedparser as feedparser

__RSS = None  # Global pointer to RSS-scanner instance


##############################################################################
# Wrapper functions
##############################################################################

def init():
    global __RSS
    __RSS = RSSQueue()


def stop():
    global __RSS
    if __RSS:
        __RSS.stop()
        try:
            __RSS.join()
        except:
            pass


def del_feed(feed):
    global __RSS
    if __RSS:
        __RSS.delete(feed)


def run_feed(feed, download, ignoreFirst=False, force=False, readout=True):
    global __RSS
    if __RSS:
        return __RSS.run_feed(feed, download, ignoreFirst, force=force, readout=readout)


def show_result(feed):
    global __RSS
    if __RSS:
        return __RSS.show_result(feed)


def flag_downloaded(feed, fid):
    global __RSS
    if __RSS:
        __RSS.flag_downloaded(feed, fid)


def lookup_url(feed, fid):
    global __RSS
    if __RSS:
        return __RSS.lookup_url(feed, fid)


def run_method():
    global __RSS
    if __RSS:
        return __RSS.run()
    else:
        return None


def next_run(t=None):
    global __RSS
    if __RSS:
        if t:
            __RSS.next_run = t
        else:
            return __RSS.next_run
    else:
        return time.time()


def save():
    global __RSS
    if __RSS:
        __RSS.save()


def clear_feed(feed):
    global __RSS
    if __RSS:
        __RSS.clear_feed(feed)


def clear_downloaded(feed):
    global __RSS
    if __RSS:
        __RSS.clear_downloaded(feed)


##############################################################################

def notdefault(item):
    """ Return True if not 'Default|''|*' """
    return bool(item) and str(item).lower() not in ('default', '*', '', str(DEFAULT_PRIORITY))


def ListUris():
    """ Return list of all RSS uris """
    uris = []
    for uri in config.get_rss():
        uris.append(uri)
    return uris


def convert_filter(text):
    """ Return compiled regex.
        If string starts with re: it's a real regex
        else quote all regex specials, replace '*' by '.*'
    """
    text = text.strip().lower()
    if text.startswith('re:'):
        txt = text[3:].strip()
    else:
        txt = wildcard_to_re(text)
    try:
        return re.compile(txt, re.I)
    except:
        logging.debug('Could not compile regex: %s', text)
        return None


def remove_obsolete(jobs, new_jobs):
    """ Expire G/B links that are not in new_jobs (mark them 'X')
        Expired links older than 3 days are removed from 'jobs'
    """
    now = time.time()
    limit = now - 259200  # 3days (3x24x3600)
    olds = jobs.keys()
    for old in olds:
        tm = jobs[old]['time']
        if old not in new_jobs:
            if jobs[old].get('status', ' ')[0] in ('G', 'B'):
                jobs[old]['status'] = 'X'
        if jobs[old]['status'] == 'X' and tm < limit:
            logging.debug("Purging link %s", old)
            del jobs[old]


LOCK = threading.RLock()


class RSSQueue(object):

    def __init__(self):
        def check_str(p):
            return p is None or p == '' or isinstance(p, basestring)

        def check_int(p):
            try:
                int(p)
                return True
            except:
                return False

        self.jobs = {}
        self.next_run = time.time()

        try:
            defined = config.get_rss().keys()
            feeds = sabnzbd.load_admin(RSS_FILE_NAME)
            if type(feeds) == type({}):
                for feed in feeds:
                    if feed not in defined:
                        logging.debug('Dropping obsolete data for feed "%s"', feed)
                        continue
                    self.jobs[feed] = {}
                    for link in feeds[feed]:
                        data = feeds[feed][link]
                        if type(data) == type([]):
                            # Convert previous list-based store to dictionary
                            new = {}
                            try:
                                new['status'] = data[0]
                                new['title'] = data[1]
                                new['url'] = data[2]
                                new['cat'] = data[3]
                                new['pp'] = data[4]
                                new['script'] = data[5]
                                new['time'] = data[6]
                                new['prio'] = str(NORMAL_PRIORITY)
                                new['rule'] = 0
                                self.jobs[feed][link] = new
                            except IndexError:
                                del new
                        else:
                            # Consistency check on data
                            try:
                                item = feeds[feed][link]
                                if not isinstance(item, dict) or not isinstance(item.get('title'), unicode):
                                    raise IndexError
                                if item.get('status', ' ')[0] not in ('D', 'G', 'B', 'X'):
                                    item['status'] = 'X'
                                if not isinstance(item.get('url'), unicode):
                                    item['url'] = ''
                                if not check_str(item.get('cat')):
                                    item['cat'] = ''
                                if not check_str(item.get('orgcat')):
                                    item['orgcat'] = ''
                                if not check_str(item.get('pp')):
                                    item['pp'] = '3'
                                if not check_str(item.get('script')):
                                    item['script'] = 'None'
                                if not check_str(item.get('prio')):
                                    item['prio'] = '-100'
                                if not check_int(item.get('rule', 0)):
                                    item['rule'] = 0
                                if not check_int(item.get('size', 0L)):
                                    item['size'] = 0L
                                if not isinstance(item.get('time'), float):
                                    item['time'] = time.time()
                                if not check_int(item.get('order', 0)):
                                    item.get['order'] = 0
                                self.jobs[feed][link] = item
                            except (KeyError, IndexError):
                                logging.info('Incorrect entry in %s detected, discarding %s', RSS_FILE_NAME, item)

                    remove_obsolete(self.jobs[feed], self.jobs[feed].keys())

        except IOError:
            logging.debug('Cannot read file %s', RSS_FILE_NAME)

        # jobs is a NAME-indexed dictionary
        #    Each element is link-indexed dictionary
        #        Each element is another dictionary:
        #           status : 'D', 'G', 'B', 'X' (downloaded, good-match, bad-match, obsolete)
        #               '*' added means: from the initial batch
        #               '-' added to 'D' means downloaded, but not displayed anymore
        #           title : Title
        #           url : URL
        #           cat : category
        #           orgcat : category as read from feed
        #           pp : pp
        #           script : script
        #           prio : priority
        #           time : timestamp (used for time-based clean-up)
        #           order : order in the RSS feed
        #           size : size in bytes

        self.shutdown = False

    def stop(self):
        self.shutdown = True

    @synchronized(LOCK)
    def run_feed(self, feed=None, download=False, ignoreFirst=False, force=False, readout=True):
        """ Run the query for one URI and apply filters """
        self.shutdown = False

        def dup_title(title):
            """ Check if this title was in this or other feeds
                Return matching feed name
            """
            title = title.lower()
            for fd in self.jobs:
                for lk in self.jobs[fd]:
                    item = self.jobs[fd][lk]
                    if item.get('status', ' ')[0] == 'D' and \
                       item.get('title', '').lower() == title:
                        return fd
            return ''

        if not feed:
            return 'No such feed'

        newlinks = []
        new_downloads = []

        # Preparations, get options
        try:
            feeds = config.get_rss()[feed]
        except KeyError:
            logging.error(T('Incorrect RSS feed description "%s"'), feed)
            logging.info("Traceback: ", exc_info=True)
            return T('Incorrect RSS feed description "%s"') % feed

        uri = feeds.uri()
        defCat = feeds.cat()
        import sabnzbd.api
        if not notdefault(defCat) or defCat not in sabnzbd.api.list_cats(default=False):
            defCat = None
        defPP = feeds.pp()
        if not notdefault(defPP):
            defPP = None
        defScript = feeds.script()
        if not notdefault(defScript):
            defScript = None
        defPrio = feeds.priority()
        if not notdefault(defPrio):
            defPrio = None

        # Preparations, convert filters to regex's
        regexes = []
        reTypes = []
        reCats = []
        rePPs = []
        rePrios = []
        reScripts = []
        reEnabled = []
        for filter in feeds.filters():
            reCat = filter[0]
            if defCat in ('', '*'):
                reCat = None
            reCats.append(reCat)
            rePPs.append(filter[1])
            reScripts.append(filter[2])
            reTypes.append(filter[3])
            if filter[3] in ('<', '>', 'F', 'S'):
                regexes.append(filter[4])
            else:
                regexes.append(convert_filter(filter[4]))
            rePrios.append(filter[5])
            reEnabled.append(filter[6] != '0')
        regcount = len(regexes)

        # Set first if this is the very first scan of this URI
        first = (feed not in self.jobs) and ignoreFirst

        # Add sabnzbd's custom User Agent
        feedparser.USER_AGENT = 'SABnzbd+/%s' % sabnzbd.version.__version__

        # Check for nzbs.org
        if 'nzbs.org/' in uri and '&dl=1' not in uri:
            uri += '&dl=1'

        # Read the RSS feed
        msg = None
        entries = None
        if readout:
            uri = uri.replace(' ', '%20')
            logging.debug("Running feedparser on %s", uri)
            d = feedparser.parse(uri.replace('feed://', 'http://'))
            logging.debug("Done parsing %s", uri)
            if not d:
                msg = T('Failed to retrieve RSS from %s: %s') % (uri, '?')
                logging.info(msg)
                return unicoder(msg)

            status = d.get('status', 999)
            if status in (401, 402, 403):
                msg = T('Do not have valid authentication for feed %s') % feed
                logging.info(msg)
                return unicoder(msg)
            if status >= 500 and status <= 599:
                msg = T('Server side error (server code %s); could not get %s on %s') % (status, feed, uri)
                logging.info(msg)
                return unicoder(msg)

            entries = d.get('entries')
            if 'bozo_exception' in d and not entries:
                msg = str(d['bozo_exception'])
                if 'CERTIFICATE_VERIFY_FAILED' in msg:
                    msg = T('Server %s uses an untrusted HTTPS certificate') % get_urlbase(uri)
                    logging.error(msg)
                else:
                    msg = T('Failed to retrieve RSS from %s: %s') % (uri, xml_name(msg))
                logging.info(msg)
                return unicoder(msg)
            if not entries:
                msg = T('RSS Feed %s was empty') % uri
                logging.info(msg)

        if feed not in self.jobs:
            self.jobs[feed] = {}
        jobs = self.jobs[feed]
        if readout:
            if not entries:
                return unicoder(msg)
        else:
            entries = jobs.keys()
            # Sort in the order the jobs came from the feed
            entries.sort(lambda x, y: jobs[x].get('order', 0) - jobs[y].get('order', 0))

        order = 0
        # Filter out valid new links
        for entry in entries:
            if self.shutdown:
                return

            if readout:
                try:
                    link, category, size = _get_link(uri, entry)
                except (AttributeError, IndexError):
                    link = None
                    category = u''
                    size = 0L
                    logging.info(T('Incompatible feed') + ' ' + uri)
                    logging.info("Traceback: ", exc_info=True)
                    return T('Incompatible feed')
                title = entry.title
            else:
                link = entry
                category = jobs[link].get('orgcat', '')
                if category in ('', '*'):
                    category = None
                title = jobs[link].get('title', '')
                size = jobs[link].get('size', 0L)

            if link:
                # Make sure spaces are quoted in the URL
                link = link.strip().replace(' ', '%20')

                newlinks.append(link)

                if link in jobs:
                    jobstat = jobs[link].get('status', ' ')[0]
                else:
                    jobstat = 'N'
                if jobstat in 'NGB' or (jobstat == 'X' and readout):
                    # Match this title against all filters
                    logging.debug('Trying title %s', title)
                    result = False
                    myCat = defCat
                    myPP = defPP
                    myScript = defScript
                    myPrio = defPrio
                    n = 0
                    if 'F' in reTypes or 'S' in reTypes:
                        season, episode = sabnzbd.newsunpack.analyse_show(title)[1:3]
                        season = int_conv(season)
                        episode = int_conv(episode)
                    else:
                        season = episode = 0

                    # Match against all filters until an positive or negative match
                    logging.debug('Size %s for %s', size, title)
                    for n in xrange(regcount):
                        if reEnabled[n]:
                            if category and reTypes[n] == 'C':
                                found = re.search(regexes[n], category)
                                if not found:
                                    logging.debug("Filter rejected on rule %d", n)
                                    result = False
                                    break
                            elif reTypes[n] == '<' and size and from_units(regexes[n]) < size:
                                # "Size at most" : too large
                                logging.debug('Filter rejected on rule %d', n)
                                result = False
                                break
                            elif reTypes[n] == '>' and size and from_units(regexes[n]) > size:
                                # "Size at least" : too small
                                logging.debug('Filter rejected on rule %d', n)
                                result = False
                                break
                            elif reTypes[n] == 'F' and not ep_match(season, episode, regexes[n]):
                                # "Starting from SxxEyy", too early episode
                                logging.debug('Filter requirement match on rule %d', n)
                                result = False
                                break
                            elif reTypes[n] == 'S' and season and episode and ep_match(season, episode, regexes[n], title):
                                logging.debug('Filter matched on rule %d', n)
                                result = True
                                break
                            else:
                                if regexes[n]:
                                    found = re.search(regexes[n], title)
                                else:
                                    found = False
                                if reTypes[n] == 'M' and not found:
                                    logging.debug("Filter rejected on rule %d", n)
                                    result = False
                                    break
                                if found and reTypes[n] == 'A':
                                    logging.debug("Filter matched on rule %d", n)
                                    result = True
                                    break
                                if found and reTypes[n] == 'R':
                                    logging.debug("Filter rejected on rule %d", n)
                                    result = False
                                    break

                    if len(reCats):
                        if notdefault(reCats[n]):
                            myCat = reCats[n]
                        elif category and not defCat:
                            myCat = cat_convert(category)
                        if myCat:
                            myCat, catPP, catScript, catPrio = cat_to_opts(myCat)
                        else:
                            myCat = catPP = catScript = catPrio = None
                        if notdefault(rePPs[n]):
                            myPP = rePPs[n]
                        elif not (reCats[n] or category):
                            myPP = catPP
                        if notdefault(reScripts[n]):
                            myScript = reScripts[n]
                        elif not (notdefault(reCats[n]) or category):
                            myScript = catScript
                        if rePrios[n] not in (str(DEFAULT_PRIORITY), ''):
                            myPrio = rePrios[n]
                        elif not ((rePrios[n] != str(DEFAULT_PRIORITY)) or category):
                            myPrio = catPrio

                    if cfg.no_dupes() and dup_title(title):
                        if cfg.no_dupes() == 1:
                            logging.info("Ignoring duplicate job %s", title)
                            continue
                        else:
                            myPrio = DUP_PRIORITY

                    act = download and not first
                    if link in jobs:
                        act = act and not jobs[link].get('status', '').endswith('*')
                        act = act or force
                        star = first or jobs[link].get('status', '').endswith('*')
                    else:
                        star = first
                    if result:
                        _HandleLink(jobs, link, title, size, 'G', category, myCat, myPP, myScript,
                                    act, star, order, priority=myPrio, rule=str(n))
                        if act:
                            new_downloads.append(title)
                    else:
                        _HandleLink(jobs, link, title, size, 'B', category, myCat, myPP, myScript,
                                    False, star, order, priority=myPrio, rule=str(n))
            order += 1

        # Send email if wanted and not "forced"
        if new_downloads and cfg.email_rss() and not force:
            emailer.rss_mail(feed, new_downloads)

        remove_obsolete(jobs, newlinks)
        return ''

    def run(self):
        """ Run all the URI's and filters """
        if not sabnzbd.PAUSED_ALL:
            active = False
            if self.next_run < time.time():
                self.next_run = time.time() + cfg.rss_rate.get() * 60
            feeds = config.get_rss()
            for feed in feeds.keys():
                try:
                    if feeds[feed].enable.get():
                        logging.info('Starting scheduled RSS read-out for "%s"', feed)
                        active = True
                        self.run_feed(feed, download=True, ignoreFirst=True)
                        # Wait 15 seconds, else sites may get irritated
                        for unused in xrange(15):
                            if self.shutdown:
                                return
                            else:
                                time.sleep(1.0)
                except KeyError:
                    # Feed must have been deleted
                    pass
            if active:
                self.save()
                logging.info('Finished scheduled RSS read-outs')

    @synchronized(LOCK)
    def show_result(self, feed):
        if feed in self.jobs:
            try:
                return self.jobs[feed]
            except:
                return {}
        else:
            return {}

    @synchronized(LOCK)
    def save(self):
        sabnzbd.save_admin(self.jobs, RSS_FILE_NAME)

    @synchronized(LOCK)
    def delete(self, feed):
        if feed in self.jobs:
            del self.jobs[feed]

    @synchronized(LOCK)
    def flag_downloaded(self, feed, fid):
        if feed in self.jobs:
            lst = self.jobs[feed]
            for link in lst:
                if lst[link].get('url', '') == fid:
                    lst[link]['status'] = 'D'

    @synchronized(LOCK)
    def lookup_url(self, feed, url):
        if url and feed in self.jobs:
            lst = self.jobs[feed]
            for link in lst:
                if lst[link].get('url') == url:
                    return lst[link]
        return None

    @synchronized(LOCK)
    def clear_feed(self, feed):
        # Remove any previous references to this feed name, and start fresh
        if feed in self.jobs:
            del self.jobs[feed]

    @synchronized(LOCK)
    def clear_downloaded(self, feed):
        # Mark downloaded jobs, so that they won't be displayed any more.
        if feed in self.jobs:
            for item in self.jobs[feed]:
                if self.jobs[feed][item]['status'] == 'D':
                    self.jobs[feed][item]['status'] = 'D-'


def _HandleLink(jobs, link, title, size, flag, orgcat, cat, pp, script, download, star, order,
                priority=NORMAL_PRIORITY, rule=0):
    """ Process one link """
    if script == '':
        script = None
    if pp == '':
        pp = None

    jobs[link] = {}
    jobs[link]['order'] = order
    jobs[link]['orgcat'] = orgcat
    jobs[link]['size'] = size
    if special_rss_site(link):
        nzbname = None
    else:
        nzbname = title

    if download:
        jobs[link]['status'] = 'D'
        jobs[link]['title'] = title
        logging.info("Adding %s (%s) to queue", link, title)
        sabnzbd.add_url(link, pp=pp, script=script, cat=cat, priority=priority, nzbname=nzbname)
    else:
        if star:
            jobs[link]['status'] = flag + '*'
        else:
            jobs[link]['status'] = flag
        jobs[link]['title'] = title
        jobs[link]['url'] = link
        jobs[link]['cat'] = cat
        jobs[link]['pp'] = pp
        jobs[link]['script'] = script
        jobs[link]['prio'] = str(priority)

    jobs[link]['time'] = time.time()
    jobs[link]['rule'] = rule


def _get_link(uri, entry):
    """ Retrieve the post link from this entry
        Returns (link, category, size)
    """
    link = None  # @UnusedVariable -- pep8 bug?
    category = ''
    size = 0L
    uri = uri.lower()

    # Try standard link and enclosures first
    link = entry.link
    if not link:
        link = entry.links[0].href
    if 'enclosures' in entry:
        try:
            link = entry.enclosures[0]['href']
            size = int(entry.enclosures[0]['length'])
            logging.debug('Found size %s for %s', size, uri)
        except:
            pass

    if size == 0L:
        _RE_SIZE1 = re.compile(r'Size:\s*(\d+\.\d+\s*[KMG]{0,1})B\W*', re.I)
        _RE_SIZE2 = re.compile(r'\W*(\d+\.\d+\s*[KMG]{0,1})B\W*', re.I)
        # Try to find size in Description
        try:
            desc = entry.description.replace('\n', ' ')
            m = _RE_SIZE1.search(desc) or _RE_SIZE2.search(desc)
            if m:
                size = from_units(m.group(1))
                logging.debug('Found size %s for %s', size, uri)
        except:
            pass

    if link and 'http' in link.lower():
        try:
            category = entry.cattext
        except:
            try:
                category = entry.category
            except:
                try:  # nzb.su
                    category = entry.tags[0]['term']
                except:
                    try:
                        category = entry.description
                    except:
                        category = ''
        return link, category, size
    else:
        logging.warning(T('Empty RSS entry found (%s)'), link)
        return None, '', 0L


def special_rss_site(url):
    """ Return True if url describes an RSS site with odd titles """
    return cfg.rss_filenames() or match_str(url, cfg.rss_odd_titles())


_RE_SP = re.compile(r's*(\d+)[ex](\d+)', re.I)
def ep_match(season, episode, expr, title=None):
    """ Return True if season, episode is at or above expected
        Optionally `title` can be matched
    """
    m = _RE_SP.search(expr)
    if m:
        req_season = int(m.group(1))
        req_episode = int(m.group(2))
        if season > req_season or (season == req_season and episode >= req_episode):
            if title:
                show = expr[:m.start()].replace('.', ' ').replace('_', ' ').strip()
                show = show.replace(' ', '[._ ]+')
                return bool(re.search(show, title, re.I))
            else:
                return True
        else:
            return False
    else:
        return True
