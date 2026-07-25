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

import os
import threading
import time
from contextlib import suppress
from unittest import mock

import pytest

import sabnzbd.cfg as cfg
import sabnzbd.directunpacker
from sabnzbd.directunpacker import ACTIVE_UNPACKERS, ACTIVE_UNPACKERS_LOCK, DirectUnpacker
from sabnzbd.newsunpack import rar_unpack
from sabnzbd.nzb import NzbFile, NzbObject
from tests.testhelper import wait_for


def make_nzf(filename: str, setname: str, vol: int) -> NzbFile:
    nzf = mock.MagicMock(spec=NzbFile)
    nzf.filename = filename
    nzf.setname = setname
    nzf.vol = vol
    nzf.assembled = True
    return nzf


def make_nzo(tmp_path) -> NzbObject:
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
    nzo.password = None
    nzo.correct_password = None
    return nzo


@pytest.fixture
def patched_cfg():
    with mock.patch.multiple(
        cfg,
        direct_unpack_tested=mock.Mock(return_value=True),
        direct_unpack=mock.Mock(return_value=True),
        enable_unrar=mock.Mock(return_value=True),
    ):
        yield


@pytest.fixture
def unpacker(tmp_path, patched_cfg):
    """A DirectUnpacker with an active unrar instance that finished volume 1 of the
    set "test", positioned as if unrar is waiting for volume 2 to appear.
    """
    unpacker = DirectUnpacker(make_nzo(tmp_path))
    unpacker.cur_setname = "test"
    unpacker.cur_volume = 1
    # Pretend unrar is running, so add() will not try to start a real one
    unpacker.active_instance = mock.MagicMock()
    yield unpacker


class FakeUnrar:
    """An unrar process on a real pipe, so it can be polled like the real thing.
    Stays silent until something is written to it.
    """

    def __init__(self):
        read_fd, self.write_fd = os.pipe()
        self.instance = mock.MagicMock()
        self.instance.poll.return_value = None
        self.instance.stdout = open(read_fd, "rb", buffering=0)

    def write(self, output: bytes):
        os.write(self.write_fd, output)

    def close(self):
        with suppress(OSError):
            os.close(self.write_fd)


@pytest.fixture
def startable_unpacker(tmp_path, patched_cfg):
    """A DirectUnpacker that has not started yet, with volume 1 of the set "test" ready
    on disk and a fake unrar that stays silent, so add() will start the real code path.
    """
    nzo = make_nzo(tmp_path)
    nzo.finished_files.append(make_nzf("test.part01.rar", "test", 1))

    unpacker = DirectUnpacker(nzo)
    unpacker.unpack_dir_info = (str(tmp_path), str(tmp_path), None, False, None)
    unpacker.fake_unrar = FakeUnrar()

    with mock.patch.object(sabnzbd.directunpacker, "build_and_run_command", return_value=unpacker.fake_unrar.instance):
        yield unpacker

    unpacker.killed = True
    unpacker.fake_unrar.close()
    if unpacker.is_alive():
        unpacker.join(timeout=10)
    while unpacker in ACTIVE_UNPACKERS:
        ACTIVE_UNPACKERS.remove(unpacker)


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
        """Damaged articles have to be repaired by par2 first. A notification is the only
        thing that gets a running unpacker going, so this one may not send one.
        """
        nzf = make_nzf("test.part02.rar", "test", 2)
        unpacker.nzo.finished_files.append(nzf)
        unpacker.nzo.bad_articles = 1

        with mock.patch.object(unpacker, "next_file_lock") as next_file_lock:
            unpacker.add(nzf)

        next_file_lock.notify.assert_not_called()
        next_file_lock.notify_all.assert_not_called()


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
        unpacker.success_sets["test"] = (["test.part01.rar"], [])
        start = time.time()
        with (
            mock.patch.object(DirectUnpacker, "is_alive", side_effect=waiting.is_alive),
            mock.patch.object(DirectUnpacker, "join", side_effect=waiting.join),
        ):
            rar_unpack(unpacker.nzo, str(unpacker.nzo.download_path), False, ["test.part01.rar"])

        assert not waiting.is_alive(), "rar_unpack() did not resume the parked unpacker"
        # Picked up the moment it finished, instead of sitting out the poll interval
        assert time.time() - start < 1


class TestDirectUnpackerOutput:
    def test_reading_output_does_not_block_add(self, startable_unpacker):
        """Reading unrar's output may not hold the lock that add() needs. add() is called
        from the single Assembler thread, so a quiet or stalled unrar would otherwise stop
        assembly for the whole job.
        """
        unpacker = startable_unpacker
        unpacker.add(make_nzf("test.part01.rar", "test", 1))
        assert unpacker.is_alive(), "add() did not start the unpacker"

        # The Assembler thread hands us the next volume while unrar produces nothing
        adding = threading.Thread(target=unpacker.add, args=(make_nzf("test.part02.rar", "test", 2),), daemon=True)
        adding.start()
        adding.join(timeout=5)

        assert not adding.is_alive(), "add() was blocked by a silent unrar"

    @pytest.mark.parametrize("chunked", [False, True], ids=["char_by_char", "all_at_once"])
    def test_reads_all_output_of_the_instance(self, startable_unpacker, chunked):
        """Whole lines and the prompt that has no newline after it both have to be picked
        up, no matter how the output is spread over the reads.
        """
        unpacker = startable_unpacker
        output = b"\nUNRAR 6.11 freeware\n\nExtracting from test.part01.rar\n\nInsert disk with test.part02.rar [C]ontinue, [Q]uit "

        with mock.patch.object(DirectUnpacker, "wait_for_next_volume") as wait_for_next_volume:
            unpacker.add(make_nzf("test.part01.rar", "test", 1))
            if chunked:
                unpacker.fake_unrar.write(output)
            else:
                for index in range(len(output)):
                    unpacker.fake_unrar.write(output[index : index + 1])
            wait_for(lambda: unpacker.fake_unrar.instance.stdin.write.called, timeout=10)
            unpacker.fake_unrar.close()
            unpacker.join(timeout=10)

        assert not unpacker.is_alive(), "unpacker did not stop at the end of the output"
        # The prompt has no newline after it, so it is only found in the leftover buffer
        wait_for_next_volume.assert_called_once()
        unpacker.fake_unrar.instance.stdin.write.assert_called_once_with(b"C\n")

    @pytest.mark.parametrize("later_volume", [False, True], ids=["nothing_left", "later_volume_arrived"])
    def test_missing_volume_aborts_once_repair_is_done(self, startable_unpacker, later_volume):
        """Volume 2 never arrives. Once post-processing tells us nothing is coming anymore
        we have to give up right away, also when a later volume did arrive.
        """
        unpacker = startable_unpacker
        if later_volume:
            unpacker.nzo.finished_files.append(make_nzf("test.part03.rar", "test", 3))

        unpacker.add(make_nzf("test.part01.rar", "test", 1))
        unpacker.fake_unrar.write(
            b"\nExtracting from test.part01.rar\n\nInsert disk with test.part02.rar [C]ontinue, [Q]uit "
        )
        wait_for(lambda: unpacker.cur_volume == 1 and unpacker.active_instance, timeout=10)
        assert unpacker.is_alive(), "gave up before post-processing said so"

        unpacker.set_no_more_files()
        unpacker.join(timeout=30)

        assert not unpacker.is_alive(), "kept asking for a volume that is never coming"
        assert unpacker.killed
        # Straight to the abort, no rounds of repeating output first
        assert not unpacker.duplicate_lines
        assert unpacker.fake_unrar.instance.stdin.write.call_args_list == [mock.call(b"Q\n")]

    def test_no_more_files_releases_the_wait(self, unpacker):
        """The wait is only released by a notification, so post-processing has to send one"""
        waiting = park_in_wait_for_next_volume(unpacker)

        unpacker.set_no_more_files()

        waiting.join(timeout=10)
        assert not waiting.is_alive(), "set_no_more_files() did not wake the unpacker"


class TestDirectUnpackerAbort:
    def test_aborts_between_sets(self, unpacker):
        """run() clears cur_setname while it moves on to the next set, and reset_active()
        can sit there for two seconds waiting for the old instance. An abort landing in
        that window still has to stop us, or the next set gets unpacked anyway.
        """
        unpacker.cur_setname = None

        unpacker.abort()

        assert unpacker.killed
        assert not unpacker.check_requirements()

    def test_aborts_without_a_rarfile(self, unpacker, tmp_path):
        """The one-folder cleanup needs the rarfile to know what to remove. Without it the
        files are left alone, the shared folder may hold files that are not ours.
        """
        shared_file = tmp_path / "not-ours.mkv"
        shared_file.touch()
        unpacker.rarfile_nzf = None
        unpacker.unpack_dir_info = (str(tmp_path), str(tmp_path), None, True, None)

        unpacker.abort()

        assert unpacker.killed
        assert shared_file.exists(), "abort() removed files it did not unpack"


class TestDirectUnpackerLock:
    def test_unpackers_do_not_share_a_lock(self, unpacker, startable_unpacker):
        """abort() holds the lock while it kills unrar and removes the extracted files,
        which can take seconds. That may not hold up add() for another job, because all
        jobs are added from the single Assembler thread.
        """
        assert unpacker.lock is not startable_unpacker.lock

        # As held by a slow abort() of another job
        with unpacker.lock:
            adding = threading.Thread(
                target=startable_unpacker.add, args=(make_nzf("test.part01.rar", "test", 1),), daemon=True
            )
            adding.start()
            adding.join(timeout=5)

            assert not adding.is_alive(), "add() waited for an unrelated job"

    def test_claiming_a_slot_is_atomic(self, startable_unpacker):
        """Checking the direct_unpack_threads limit and taking one of the slots have to
        happen together, or two callers of add() could both claim the last one.
        """
        unpacker = startable_unpacker
        spawning = threading.Event()
        release = threading.Event()

        def slow_spawn(*args, **kwargs):
            spawning.set()
            assert release.wait(timeout=60)
            return unpacker.fake_unrar.instance

        with mock.patch.object(sabnzbd.directunpacker, "build_and_run_command", side_effect=slow_spawn):
            adding = threading.Thread(target=unpacker.add, args=(make_nzf("test.part01.rar", "test", 1),), daemon=True)
            adding.start()
            assert spawning.wait(timeout=10), "unrar was never started"

            # Nobody else gets to look at the slots while we are claiming one
            assert not ACTIVE_UNPACKERS_LOCK.acquire(blocking=False), "the slots were readable mid-claim"

            release.set()
            adding.join(timeout=10)

        assert unpacker in ACTIVE_UNPACKERS
