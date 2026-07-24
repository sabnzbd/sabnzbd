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
tests.test_directunpacker - Testing functions in directunpacker.py
"""

import threading
from unittest import mock

import pytest

import sabnzbd.cfg as cfg
from sabnzbd.directunpacker import DirectUnpacker
from sabnzbd.newsunpack import rar_unpack
from sabnzbd.nzb import NzbFile, NzbObject


def make_nzf(filename: str, setname: str, vol: int) -> NzbFile:
    nzf = mock.MagicMock(spec=NzbFile)
    nzf.filename = filename
    nzf.setname = setname
    nzf.vol = vol
    nzf.assembled = True
    return nzf


@pytest.fixture
def unpacker(tmp_path):
    """A DirectUnpacker with an active unrar instance that finished volume 1 of the
    set "test", positioned as if unrar is waiting for volume 2 to appear.
    """
    nzo = mock.MagicMock(spec=NzbObject)
    nzo.first_articles = []
    nzo.unpack = True
    nzo.bad_articles = 0
    nzo.pp_active = False
    nzo.removed_from_queue = False
    nzo.files = []
    nzo.finished_files = []
    nzo.download_path = str(tmp_path)
    nzo.final_name = "test.job"
    nzo.delete = False

    with mock.patch.multiple(
        cfg,
        direct_unpack_tested=mock.Mock(return_value=True),
        direct_unpack=mock.Mock(return_value=True),
        enable_unrar=mock.Mock(return_value=True),
    ):
        unpacker = DirectUnpacker(nzo)
        unpacker.cur_setname = "test"
        unpacker.cur_volume = 1
        # Pretend unrar is running, so add() will not try to start a real one
        unpacker.active_instance = mock.MagicMock()
        yield unpacker


def park_in_wait_for_next_volume(unpacker: DirectUnpacker) -> threading.Thread:
    """Start a thread in wait_for_next_volume() and return once it is really waiting,
    so that only a notification can release it again.
    """
    predicate_called = threading.Event()
    have_next_volume = unpacker.have_next_volume

    def wrapped_have_next_volume():
        predicate_called.set()
        return have_next_volume()

    unpacker.have_next_volume = wrapped_have_next_volume

    waiting = threading.Thread(target=unpacker.wait_for_next_volume, daemon=True)
    waiting.start()

    # The predicate is evaluated while holding the lock, so once it ran we only have to
    # wait for the lock to be released by Condition.wait() to know the thread is parked
    assert predicate_called.wait(timeout=10)
    with unpacker.next_file_lock:
        pass
    return waiting


class TestDirectUnpackerAdd:
    def test_notifies_waiting_thread(self, unpacker):
        """The notification at the end of add() is the only thing that releases a thread
        parked in wait_for_next_volume() while the job is still downloading.
        """
        waiting = park_in_wait_for_next_volume(unpacker)
        nzf = make_nzf("test.part02.rar", "test", 2)
        unpacker.nzo.finished_files.append(nzf)

        unpacker.add(nzf)

        waiting.join(timeout=10)
        assert not waiting.is_alive(), "wait_for_next_volume() was never woken up by add()"

    def test_damaged_download_keeps_unpacker_parked(self, unpacker):
        """Damaged articles have to be repaired by par2 first, so the unpacker is left
        waiting instead of being fed a volume unrar would choke on.
        """
        waiting = park_in_wait_for_next_volume(unpacker)
        nzf = make_nzf("test.part02.rar", "test", 2)
        unpacker.nzo.finished_files.append(nzf)
        unpacker.nzo.bad_articles = 1

        unpacker.add(nzf)

        waiting.join(timeout=2)
        assert waiting.is_alive(), "unpacker should stay parked until par2 repaired the damage"


class TestDirectUnpackerResume:
    def test_rar_unpack_resumes_parked_unpacker(self, unpacker):
        """Post-processing has to release an unpacker that add() left parked, otherwise
        the job keeps a stalled unrar around indefinitely.
        """
        waiting = park_in_wait_for_next_volume(unpacker)
        unpacker.nzo.bad_articles = 1

        # No more volumes are coming, so only rar_unpack() can release it
        unpacker.add(make_nzf("test.part02.rar", "test", 2))
        assert waiting.is_alive()

        # Post-processing repaired the set and now waits for direct unpack to finish
        unpacker.nzo.pp_active = True
        unpacker.success_sets["test"] = (["test.part01.rar"], [])
        with mock.patch.object(DirectUnpacker, "is_alive", side_effect=waiting.is_alive):
            rar_unpack(unpacker.nzo, str(unpacker.nzo.download_path), False, ["test.part01.rar"])

        assert not waiting.is_alive(), "rar_unpack() did not resume the parked unpacker"
