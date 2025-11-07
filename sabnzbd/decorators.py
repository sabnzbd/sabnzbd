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

##############################################################################
# Decorators
##############################################################################
import time
import functools
import concurrent.futures
from typing import Union, Callable, Optional, Any
from threading import Lock, RLock, Condition


# All operations that modify the queue need to happen in a lock
# Also used when importing NZBs to prevent IO-race conditions
# Names of wrapper-functions should be the same in misc.caller_name
# The NzbQueueLocker both locks and notifies the Downloader
NZBQUEUE_LOCK = RLock()
DOWNLOADER_CV = Condition(NZBQUEUE_LOCK)

# All operations that modify downloader state need to be locked
DOWNLOADER_LOCK = RLock()

# General threadpool
THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def synchronized(lock: Union[Lock, RLock]):
    def wrap(func: Callable):
        def call_func(*args, **kw):
            # Using the try/finally approach is 25% faster compared to using "with lock"
            try:
                lock.acquire()
                return func(*args, **kw)
            finally:
                lock.release()

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

    Unhashable types (such as List) can not be used as an input to the wrapped function in the current implementation!

    :param cache_time: Time in seconds to cache non-empty results
    """

    def decorator(func):
        cache = {}

        def wrapper(*args, **kwargs):
            current_time = time.time()

            # Create cache key using functools._make_key
            try:
                key = functools._make_key(args, kwargs, typed=False)
                # Make sure it's a hashable to be used as key, this changed in Python 3.14
                hash(key)
            except TypeError:
                # If args/kwargs aren't hashable, skip caching entirely
                return func(*args, **kwargs)

            # Allow force kward to skip cache
            if not kwargs.get("force"):
                # Check if we have a valid cached result
                if key in cache:
                    cached_result, timestamp = cache[key]
                    if current_time - timestamp < cache_time:
                        return cached_result
                    # Cache entry expired, remove it
                    del cache[key]

            # Call the original function
            result = func(*args, **kwargs)

            # Only cache non-empty results
            # This excludes None, [], {}, "", 0, False, etc.
            if result:
                cache[key] = (result, current_time)

            return result

        return wrapper

    return decorator


def timeout(max_timeout: int, timeout_return_value: Optional[Any] = None):
    """Timeout decorator, parameter in seconds.

    :param max_timeout: Maximum time in seconds before timeout
    :param timeout_return_value: Default value to return on timeout (defaults to None)
    """

    def timeout_decorator(item: Callable) -> Callable:
        """Wrap the original function."""

        @functools.wraps(item)
        def func_wrapper(*args, **kwargs):
            """Closure for function."""
            # Raises a TimeoutError if execution exceeds max_timeout
            # Raises a RuntimeError is SABnzbd is already shutting down when called
            try:
                return THREAD_POOL.submit(item, *args, **kwargs).result(max_timeout)
            except (TimeoutError, RuntimeError, concurrent.futures._base.TimeoutError):
                # Python <3.11 require specific TimeoutError
                return timeout_return_value

        return func_wrapper

    return timeout_decorator
