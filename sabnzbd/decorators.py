#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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

##############################################################################
# Decorators
##############################################################################
import time
import functools
from typing import Union, Callable
from threading import Lock, RLock, Condition

# All operations that modify the queue need to happen in a lock
# Also used when importing NZBs to prevent IO-race conditions
# Names of wrapper-functions should be the same in misc.caller_name
# The NzbQueueLocker both locks and notifies the Downloader
NZBQUEUE_LOCK = RLock()
DOWNLOADER_CV = Condition(NZBQUEUE_LOCK)

# All operations that modify downloader state need to be locked
DOWNLOADER_LOCK = RLock()


def synchronized(lock: Union[Lock, RLock, Condition, None] = None):
    def wrap(func: Callable):
        def call_func(*args, **kw):
            # Either use the supplied lock or the object-specific one
            # Because it's a variable in the upper function, we cannot use it directly
            lock_obj = lock
            if not lock_obj:
                lock_obj = getattr(args[0], "lock")

            # Using try/finally is ~25% faster than "with lock"
            try:
                lock_obj.acquire()
                return func(*args, **kw)
            finally:
                lock_obj.release()

        return call_func

    return wrap


def NzbQueueLocker(func: Callable):
    global DOWNLOADER_CV

    def call_func(*params, **kparams):
        DOWNLOADER_CV.acquire()
        try:
            return func(*params, **kparams)
        finally:
            DOWNLOADER_CV.notify_all()
            DOWNLOADER_CV.release()

    return call_func


def conditional_cache(cache_time: int):
    """
    A decorator that caches function results for a specified time, but only if the result is not empty.
    Empty results (None, empty collections, empty strings, False, 0) are not cached.
    If a keyword argument of `force=True` is used, the cache is skipped.

    Unhashable types (such as list) can not be used as an input to the wrapped function in the current implementation!

    :param cache_time: Time in seconds to cache non-empty results
    """

    def decorator(func):
        cache = {}

        def wrapper(*args, **kwargs):
            current_time = time.time()

            # Exclude force from the cache key
            force = kwargs.pop("force", False)

            # Create cache key using functools._make_key
            try:
                key = functools._make_key(args, kwargs, typed=False)
                # Make sure it's a hashable to be used as key, this changed in Python 3.14
                hash(key)
            except TypeError:
                # If args/kwargs aren't hashable, skip caching entirely
                return func(*args, **kwargs)

            # Allow force kwarg to skip cache
            if not force:
                # Check if we have a valid cached result
                entry = cache.get(key)
                if entry is not None:
                    cached_result, expires_at = entry
                    if current_time < expires_at:
                        return cached_result
                    # Cache entry expired, remove it
                    cache.pop(key, None)

            # Call the original function
            result = func(*args, **kwargs)

            # Only cache non-empty results
            # This excludes None, [], {}, "", 0, False, etc.
            if result:
                cache[key] = (result, current_time + cache_time)

            return result

        return wrapper

    return decorator
