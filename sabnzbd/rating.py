#!/usr/bin/python3 -OO
# Copyright 2008-2012 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.rating - Rating support functions
"""

import http.client
import urllib.parse
import time
import logging
import copy
import queue
import collections
from threading import RLock, Thread
import sabnzbd
from sabnzbd.decorators import synchronized
import sabnzbd.cfg as cfg

# A queue which ignores duplicates but maintains ordering
class OrderedSetQueue(queue.Queue):
    def _init(self, maxsize):
        self.maxsize = maxsize
        self.queue = collections.OrderedDict()
    def _put(self, item):
        self.queue[item] = None
    def _get(self):
        return self.queue.popitem()[0]

_RATING_URL = "/releaseRatings/releaseRatings.php"
RATING_LOCK = RLock()

_g_warnings = 0


def _warn(msg):
    global _g_warnings
    _g_warnings += 1
    if _g_warnings < 3:
        logging.warning(msg)


def _reset_warn():
    global _g_warnings
    _g_warnings = 0


class NzbRating:

    def __init__(self):
        self.avg_video = 0
        self.avg_video_cnt = 0
        self.avg_audio = 0
        self.avg_audio_cnt = 0
        self.avg_vote_up = 0
        self.avg_vote_down = 0
        self.user_video = None
        self.user_audio = None
        self.user_vote = None
        self.user_flag = {}
        self.auto_flag = {}
        self.changed = 0


class NzbRatingV2(NzbRating):

    def __init__(self):
        super(NzbRatingV2, self).__init__()
        self.avg_spam_cnt = 0
        self.avg_spam_confirm = False
        self.avg_encrypted_cnt = 0
        self.avg_encrypted_confirm = False

    def to_v2(self, rating):
        self.__dict__.update(rating.__dict__)
        return self


class Rating(Thread):
    VERSION = 2

    VOTE_UP = 1
    VOTE_DOWN = 2

    FLAG_OK = 0
    FLAG_SPAM = 1
    FLAG_ENCRYPTED = 2
    FLAG_EXPIRED = 3
    FLAG_OTHER = 4
    FLAG_COMMENT = 5

    CHANGED_USER_VIDEO = 0x01
    CHANGED_USER_AUDIO = 0x02
    CHANGED_USER_VOTE = 0x04
    CHANGED_USER_FLAG = 0x08
    CHANGED_AUTO_FLAG = 0x10

    do = None

    def __init__(self):
        Rating.do = self
        self.shutdown = False
        self.queue = OrderedSetQueue()
        try:
            self.version, self.ratings, self.nzo_indexer_map = sabnzbd.load_admin("Rating.sab",
                                                                                  silent=not cfg.rating_enable())
            if self.version == 1:
                ratings = {}
                for k, v in self.ratings.items():
                    ratings[k] = NzbRatingV2().to_v2(v)
                self.ratings = ratings
                self.version = 2
            if self.version != Rating.VERSION:
                raise Exception()
        except:
            self.version = Rating.VERSION
            self.ratings = {}
            self.nzo_indexer_map = {}
        Thread.__init__(self)

    def stop(self):
        self.shutdown = True
        self.queue.put(None)  # Unblock queue

    def run(self):
        self.shutdown = False
        while not self.shutdown:
            time.sleep(1)
            if not cfg.rating_enable():
                continue
            indexer_id = self.queue.get()
            try:
                if indexer_id and not self._send_rating(indexer_id):
                    for unused in range(0, 60):
                        if self.shutdown:
                            break
                        time.sleep(1)
                    self.queue.put(indexer_id)
            except:
                pass
        logging.debug('Stopping ratings')

    @synchronized(RATING_LOCK)
    def save(self):
        if self.ratings and self.nzo_indexer_map:
            sabnzbd.save_admin((self.version, self.ratings, self.nzo_indexer_map), "Rating.sab")

    # The same file may be uploaded multiple times creating a new nzo_id each time
    @synchronized(RATING_LOCK)
    def add_rating(self, indexer_id, nzo_id, fields):
        if indexer_id and nzo_id:
            logging.debug('Add rating (%s, %s: %s, %s, %s, %s)', indexer_id, nzo_id, fields['video'], fields['audio'], fields['voteup'], fields['votedown'])
            try:
                rating = self.ratings.get(indexer_id, NzbRatingV2())
                if fields['video'] and fields['videocnt']:
                    rating.avg_video = int(float(fields['video']))
                    rating.avg_video_cnt = int(float(fields['videocnt']))
                if fields['audio'] and fields['audiocnt']:
                    rating.avg_audio = int(float(fields['audio']))
                    rating.avg_audio_cnt = int(float(fields['audiocnt']))
                if fields['voteup']:
                    rating.avg_vote_up = int(float(fields['voteup']))
                if fields['votedown']:
                    rating.avg_vote_down = int(float(fields['votedown']))
                if fields['spam']:
                    rating.avg_spam_cnt = int(float(fields['spam']))
                if fields['confirmed-spam']:
                    rating.avg_spam_confirm = (fields['confirmed-spam'].lower() == 'yes')
                if fields['passworded']:
                    rating.avg_encrypted_cnt = int(float(fields['passworded']))
                if fields['confirmed-passworded']:
                    rating.avg_encrypted_confirm = (fields['confirmed-passworded'].lower() == 'yes')
                # Indexers can supply a full URL or just a host
                if fields['host']:
                    rating.host = fields['host'][0] if fields['host'] and isinstance(fields['host'], list) else fields['host']
                if fields['url']:
                    rating.host = fields['url'][0] if fields['url'] and isinstance(fields['url'], list) else fields['url']
                self.ratings[indexer_id] = rating
                self.nzo_indexer_map[nzo_id] = indexer_id
            except:
                pass

    @synchronized(RATING_LOCK)
    def update_user_rating(self, nzo_id, video, audio, vote, flag, flag_detail=None):
        logging.debug('Updating user rating (%s: %s, %s, %s, %s)', nzo_id, video, audio, vote, flag)
        if nzo_id not in self.nzo_indexer_map:
            logging.warning(T('Indexer id (%s) not found for ratings file'), nzo_id)
            return
        indexer_id = self.nzo_indexer_map[nzo_id]
        rating = self.ratings[indexer_id]
        if video:
            rating.user_video = int(video)
            rating.avg_video = int((rating.avg_video_cnt * rating.avg_video + rating.user_video) / (rating.avg_video_cnt + 1))
            rating.changed = rating.changed | Rating.CHANGED_USER_VIDEO
        if audio:
            rating.user_audio = int(audio)
            rating.avg_audio = int((rating.avg_audio_cnt * rating.avg_audio + rating.user_audio) / (rating.avg_audio_cnt + 1))
            rating.changed = rating.changed | Rating.CHANGED_USER_AUDIO
        if flag:
            rating.user_flag = {'val': int(flag), 'detail': flag_detail}
            rating.changed = rating.changed | Rating.CHANGED_USER_FLAG
        if vote:
            rating.changed = rating.changed | Rating.CHANGED_USER_VOTE
            if int(vote) == Rating.VOTE_UP:
                rating.avg_vote_up += 1
                # Update if already a vote
                if rating.user_vote and rating.user_vote == Rating.VOTE_DOWN:
                    rating.avg_vote_down -= 1
            else:
                rating.avg_vote_down += 1
                # Update if already a vote
                if rating.user_vote and rating.user_vote == Rating.VOTE_UP:
                    rating.avg_vote_up -= 1

            rating.user_vote = int(vote)
        self.queue.put(indexer_id)

    @synchronized(RATING_LOCK)
    def update_auto_flag(self, nzo_id, flag, flag_detail=None):
        if not flag or not cfg.rating_enable() or (nzo_id not in self.nzo_indexer_map):
            return
        logging.debug('Updating auto flag (%s: %s)', nzo_id, flag)
        indexer_id = self.nzo_indexer_map[nzo_id]
        rating = self.ratings[indexer_id]
        rating.auto_flag = {'val': int(flag), 'detail': flag_detail}
        rating.changed = rating.changed | Rating.CHANGED_AUTO_FLAG
        self.queue.put(indexer_id)

    @synchronized(RATING_LOCK)
    def get_rating_by_nzo(self, nzo_id):
        if nzo_id not in self.nzo_indexer_map:
            return None
        return copy.copy(self.ratings[self.nzo_indexer_map[nzo_id]])

    @synchronized(RATING_LOCK)
    def _get_rating_by_indexer(self, indexer_id):
        return copy.copy(self.ratings[indexer_id])

    def _flag_request(self, val, flag_detail, auto):
        if val == Rating.FLAG_SPAM:
            return {'m': 'rs', 'auto': auto}
        if val == Rating.FLAG_ENCRYPTED:
            return {'m': 'rp', 'auto': auto}
        if val == Rating.FLAG_EXPIRED:
            expired_host = flag_detail if flag_detail and len(flag_detail) > 0 else 'Other'
            return {'m': 'rpr', 'pr': expired_host, 'auto': auto}
        if (val == Rating.FLAG_OTHER) and flag_detail and len(flag_detail) > 0:
            return {'m': 'o', 'r': flag_detail}
        if (val == Rating.FLAG_COMMENT) and flag_detail and len(flag_detail) > 0:
            return {'m': 'rc', 'r': flag_detail}

    def _send_rating(self, indexer_id):
        logging.debug('Updating indexer rating (%s)', indexer_id)

        api_key = cfg.rating_api_key()
        rating_host = cfg.rating_host()
        rating_url = _RATING_URL

        requests = []
        _headers = {'User-agent': 'SABnzbd+/%s' % sabnzbd.version.__version__, 'Content-type': 'application/x-www-form-urlencoded'}
        rating = self._get_rating_by_indexer(indexer_id)  # Requesting info here ensures always have latest information even on retry
        if hasattr(rating, 'host') and rating.host:
            host_parsed = urllib.parse.urlparse(rating.host)
            rating_host = host_parsed.netloc
            # Is it an URL or just a HOST?
            if host_parsed.path and host_parsed.path != '/':
                rating_url = host_parsed.path + '?' + host_parsed.query if host_parsed.query else host_parsed.path

        if not rating_host:
            _warn('%s: %s' % (T('Cannot send, missing required data'), T('Server address')))
            return True

        if not api_key:
            _warn('%s [%s]: %s - %s' % (T('Cannot send, missing required data'), rating_host, T('API Key'), T('This key provides identity to indexer. Check your profile on the indexer\'s website.')))
            return True

        if rating.changed & Rating.CHANGED_USER_VIDEO:
            requests.append({'m': 'r', 'r': 'videoQuality', 'rn': rating.user_video})
        if rating.changed & Rating.CHANGED_USER_AUDIO:
            requests.append({'m': 'r', 'r': 'audioQuality', 'rn': rating.user_audio})
        if rating.changed & Rating.CHANGED_USER_VOTE:
            up_down = 'up' if rating.user_vote == Rating.VOTE_UP else 'down'
            requests.append({'m': 'v', 'v': up_down, 'r': 'overall'})
        if rating.changed & Rating.CHANGED_USER_FLAG:
            requests.append(self._flag_request(rating.user_flag.get('val'), rating.user_flag.get('detail'), 0))
        if rating.changed & Rating.CHANGED_AUTO_FLAG:
            requests.append(self._flag_request(rating.auto_flag.get('val'), rating.auto_flag.get('detail'), 1))

        try:
            conn = http.client.HTTPSConnection(rating_host)
            for request in [r for r in requests if r is not None]:
                if api_key:
                    request['apikey'] = api_key
                request['i'] = indexer_id
                conn.request('POST', rating_url, urllib.parse.urlencode(request), headers=_headers)

                response = conn.getresponse()
                response.read()
                if response.status == http.client.UNAUTHORIZED:
                    _warn('Ratings server unauthorized user')
                    return False
                elif response.status != http.client.OK:
                    _warn('Ratings server failed to process request (%s, %s)' % (response.status, response.reason))
                    return False
            self.ratings[indexer_id].changed = self.ratings[indexer_id].changed & ~rating.changed
            _reset_warn()
            return True
        except:
            _warn('Problem accessing ratings server: %s' % rating_host)
            return False
