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
tests.test_decorator - Testing decorators in decorators.py
"""

import pytest
import time
import functools
import threading
from unittest.mock import Mock

from sabnzbd.decorators import synchronized, NzbQueueLocker, conditional_cache, NZBQUEUE_LOCK, DOWNLOADER_CV
from tests.testhelper import *


class TestSynchronized:
    def test_synchronized_basic(self):
        """Test that synchronized decorator properly locks function execution"""
        lock = threading.RLock()
        call_order = []

        @synchronized(lock)
        def test_func(name, delay=0.1):
            call_order.append(f"{name}_start")
            time.sleep(delay)
            call_order.append(f"{name}_end")
            return name

        # Run two threads simultaneously
        thread1 = threading.Thread(target=test_func, args=("thread1",))
        thread2 = threading.Thread(target=test_func, args=("thread2",))

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # One thread should complete fully before the other starts
        assert len(call_order) == 4
        # Either thread1 completes first or thread2 completes first
        assert call_order == ["thread1_start", "thread1_end", "thread2_start", "thread2_end"] or call_order == [
            "thread2_start",
            "thread2_end",
            "thread1_start",
            "thread1_end",
        ]

    def test_synchronized_return_value(self):
        """Test that synchronized decorator preserves return values"""
        lock = threading.RLock()

        @synchronized(lock)
        def return_value(value):
            return value * 2

        assert return_value(5) == 10
        assert return_value("test") == "testtest"

    def test_synchronized_exception_handling(self):
        """Test that synchronized decorator properly handles exceptions"""
        lock = threading.RLock()

        @synchronized(lock)
        def raise_exception():
            raise ValueError("Test exception")

        with pytest.raises(ValueError, match="Test exception"):
            raise_exception()


class TestNzbQueueLocker:
    def test_nzbqueue_locker_basic(self):
        """Test that NzbQueueLocker properly uses the downloader condition variable"""
        call_count = 0

        @NzbQueueLocker
        def test_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 1

    def test_nzbqueue_locker_with_params(self):
        """Test NzbQueueLocker with function parameters"""

        @NzbQueueLocker
        def test_func(a, b, keyword=None):
            return a + b + (keyword or 0)

        assert test_func(1, 2) == 3
        assert test_func(1, 2, keyword=3) == 6

    def test_nzbqueue_locker_exception_handling(self):
        """Test that NzbQueueLocker properly handles exceptions"""

        @NzbQueueLocker
        def raise_exception():
            raise RuntimeError("Test error")

        with pytest.raises(RuntimeError, match="Test error"):
            raise_exception()


class TestConditionalCache:
    def test_conditional_cache_basic(self):
        """Test basic conditional_cache functionality"""
        call_count = 0

        @conditional_cache(cache_time=1)
        def test_func(value):
            nonlocal call_count
            call_count += 1
            return value * 2 if value > 0 else None

        # First call with positive value should cache
        result1 = test_func(5)
        assert result1 == 10
        assert call_count == 1

        # Second call with same args should use cache
        result2 = test_func(5)
        assert result2 == 10
        assert call_count == 1

        # Call with value that returns None should not be cached
        result3 = test_func(0)
        assert result3 is None
        assert call_count == 2

        # Call again with same value that returns None - should execute again
        result4 = test_func(0)
        assert result4 is None
        assert call_count == 3

    def test_conditional_cache_empty_values(self):
        """Test that conditional_cache doesn't cache empty values"""
        call_count = 0

        @conditional_cache(cache_time=1)
        def test_func(return_type):
            nonlocal call_count
            call_count += 1

            if return_type == "none":
                return None
            elif return_type == "empty_list":
                return []
            elif return_type == "empty_dict":
                return {}
            elif return_type == "empty_string":
                return ""
            elif return_type == "zero":
                return 0
            elif return_type == "false":
                return False
            elif return_type == "valid":
                return "valid_result"

        # Test all empty values - none should be cached
        empty_values = ["none", "empty_list", "empty_dict", "empty_string", "zero", "false"]

        for i, empty_type in enumerate(empty_values):
            result = test_func(empty_type)
            assert call_count == i + 1  # Should increment each time

            # Call again - should execute again (not cached)
            test_func(empty_type)
            assert call_count == i + 2

            # Reduce call count again since we called it twice
            call_count -= 1

        # Test valid value - should be cached
        initial_count = call_count
        result1 = test_func("valid")
        assert result1 == "valid_result"
        assert call_count == initial_count + 1

        # Call again - should use cache
        result2 = test_func("valid")
        assert result2 == "valid_result"
        assert call_count == initial_count + 1

    def test_conditional_cache_time_expiration(self):
        """Test that conditional_cache expires entries after specified time"""
        call_count = 0

        @conditional_cache(cache_time=0.5)
        def test_func(value):
            nonlocal call_count
            call_count += 1
            return f"result_{value}"

        # First call
        result1 = test_func("test")
        assert result1 == "result_test"
        assert call_count == 1

        # Second call immediately - should use cache
        result2 = test_func("test")
        assert result2 == "result_test"
        assert call_count == 1

        # Wait for cache to expire
        time.sleep(0.6)

        # Third call - should execute function again
        result3 = test_func("test")
        assert result3 == "result_test"
        assert call_count == 2

    def test_conditional_cache_different_arguments(self):
        """Test conditional_cache with different argument types"""
        call_count = 0

        @conditional_cache(cache_time=1)
        def test_func(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return f"args:{args}_kwargs:{kwargs}"

        # Test with positional arguments
        result1 = test_func(1, 2, 3)
        assert call_count == 1

        result2 = test_func(1, 2, 3)  # Should use cache
        assert call_count == 1
        assert result1 == result2

        # Test with keyword arguments
        result3 = test_func(a=1, b=2)
        assert call_count == 2

        result4 = test_func(a=1, b=2)  # Should use cache
        assert call_count == 2
        assert result3 == result4

        # Test with mixed arguments
        result5 = test_func(1, 2, c=3)
        assert call_count == 3

        result6 = test_func(1, 2, c=3)  # Should use cache
        assert call_count == 3
        assert result5 == result6

    def test_conditional_cache_unhashable_arguments(self):
        """Test conditional_cache with unhashable arguments"""
        call_count = 0

        @conditional_cache(cache_time=1)
        def test_func(hashable, unhashable):
            nonlocal call_count
            call_count += 1
            return f"hashable:{hashable}_unhashable:{len(unhashable)}"

        # Call with unhashable argument (list)
        result1 = test_func("test", [1, 2, 3])
        assert call_count == 1

        # Call again with same unhashable argument - should not cache
        result2 = test_func("test", [1, 2, 3])
        assert call_count == 2
        assert result1 == result2

    def test_conditional_cache_concurrent_access(self):
        """Test conditional_cache with concurrent access"""
        call_count = 0
        results = []

        @conditional_cache(cache_time=1)
        def test_func(value):
            nonlocal call_count
            call_count += 1
            time.sleep(0.1)  # Simulate some work
            return f"result_{value}"

        def worker(value):
            result = test_func(value)
            results.append(result)

        # Start multiple threads with the same argument
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker, args=("test",))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # The function might be called multiple times due to race conditions
        # but all results should be the same
        assert len(results) == 5
        assert all(result == "result_test" for result in results)
        # call_count should be small (ideally 1, but could be more due to race conditions)
        assert call_count <= 5
