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

"""
tests.test_par2repair - par2 repair sessions
"""

import sys
from unittest import mock

import sabnzbd.cfg as cfg
from sabnzbd.constants import GIGI, MEBI, PAR2_MINIMUM_MEMORY, PAR2_RESERVED_MEMORY
from sabnzbd.par2repair import RepairSession, memory_limit


class TestPar2MemoryLimit:
    """par2 defaults to half the host's physical memory. We give it a quarter of
    get_memory() instead, which is clamped by any cgroup limit."""

    def test_a_quarter_of_available_memory(self):
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=int(8192 * MEBI)):
            assert memory_limit() == int(2048 * MEBI)

    def test_the_article_cache_has_its_own_claim(self):
        """Both are taken out of the same memory, so the cache's share is not par2's."""
        with mock.patch.object(cfg.cache_limit, "get_int", return_value=int(7 * GIGI)):
            with mock.patch("sabnzbd.par2repair.get_memory", return_value=int(8 * GIGI)):
                assert memory_limit() == int(8 * GIGI) - PAR2_RESERVED_MEMORY - int(7 * GIGI)

    def test_never_zero_on_a_tiny_budget(self):
        """Reserved headroom can exceed the whole budget; par2 reads 0 as "decide for
        yourself", which would throw away the clamp entirely."""
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=int(128 * MEBI)):
            assert memory_limit() == PAR2_MINIMUM_MEMORY

    def test_respects_a_cgroup_limit(self):
        # A 2GB container on a 32GB host
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=int(2 * GIGI)):
            assert memory_limit() == int(512 * MEBI)

    def test_falls_back_when_memory_is_unknown(self):
        # A conservative guess at the machine, and no clamp to apply
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=0):
            assert memory_limit() == int(128 * MEBI)

    def test_never_returns_zero(self):
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=1024):
            assert memory_limit() == PAR2_MINIMUM_MEMORY

    def test_capped_on_32bit(self):
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=int(16384 * MEBI)):
            with mock.patch.object(sys, "maxsize", 2**31 - 1):
                assert memory_limit() == int(1024 * MEBI)
            # 64-bit gets the full quarter
            assert memory_limit() == int(4096 * MEBI)


class TestPar2Threads:
    """Left at 0, par2 counts the host's CPUs. get_cpus() knows about cgroup quotas."""

    def opened_with(self, tmp_path):
        """Open a session against a stubbed repairer and return the keyword arguments"""
        parfile = tmp_path / "test.par2"
        parfile.write_bytes(b"")
        session = RepairSession(mock.Mock(), "test", str(parfile))
        with mock.patch("sabnzbd.par2repair.sabctools.Par2Repairer") as repairer:
            session.open([])
        return repairer.call_args.kwargs

    def test_leaves_one_cpu_for_the_rest_of_sabnzbd(self, tmp_path):
        with mock.patch("sabnzbd.par2repair.get_cpus", return_value=4):
            assert self.opened_with(tmp_path)["threads"] == 3

    def test_a_single_cpu_still_gets_a_thread(self, tmp_path):
        with mock.patch("sabnzbd.par2repair.get_cpus", return_value=1):
            assert self.opened_with(tmp_path)["threads"] == 1

    def test_falls_back_to_par2_when_undetectable(self, tmp_path):
        """Zero hands the decision back to par2, which is better than guessing 1"""
        with mock.patch("sabnzbd.par2repair.get_cpus", return_value=0):
            assert self.opened_with(tmp_path)["threads"] == 0

    def test_file_threads_are_left_to_par2(self, tmp_path):
        """This one is about I/O concurrency, not CPU count - par2's 2 stands"""
        assert "file_threads" not in self.opened_with(tmp_path)
