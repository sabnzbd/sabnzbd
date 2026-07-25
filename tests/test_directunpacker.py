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
import sabnzbd.directunpacker
from sabnzbd.directunpacker import ACTIVE_UNPACKERS, ACTIVE_UNPACKERS_LOCK, DirectUnpacker
from sabnzbd.newsunpack import rar_unpack
from sabnzbd.nzb import NzbFile, NzbObject


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
    """An unrar process that produces no output until it is released"""

    def __init__(self):
        self.reading = threading.Event()
        self.release = threading.Event()
        self.instance = mock.MagicMock()
        self.instance.poll.return_value = None
        self.instance.stdout.read.side_effect = self.read

    def read(self, _size: int) -> bytes:
        self.reading.set()
        assert self.release.wait(timeout=60)
        return b""


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

    unpacker.fake_unrar.release.set()
    unpacker.killed = True
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


class TestDirectUnpackerOutput:
    def test_reading_output_does_not_block_add(self, startable_unpacker):
        """Reading unrar's output may not hold the lock that add() needs. add() is called
        from the single Assembler thread, so a quiet or stalled unrar would otherwise stop
        assembly for the whole job.
        """
        unpacker = startable_unpacker
        unpacker.add(make_nzf("test.part01.rar", "test", 1))
        assert unpacker.is_alive(), "add() did not start the unpacker"
        assert unpacker.fake_unrar.reading.wait(timeout=10), "unrar output was never read"

        # The Assembler thread hands us the next volume while unrar produces nothing
        adding = threading.Thread(target=unpacker.add, args=(make_nzf("test.part02.rar", "test", 2),), daemon=True)
        adding.start()
        adding.join(timeout=5)

        assert not adding.is_alive(), "add() was blocked by a silent unrar"

    def test_reads_all_output_of_the_instance(self, startable_unpacker):
        """Whole lines, the prompt that has no newline after it and any trailing output
        all have to survive the move off the main loop.
        """
        unpacker = startable_unpacker
        output = b"\nUNRAR 6.11 freeware\n\nExtracting from test.part01.rar\n\nInsert disk with test.part02.rar [C]ontinue, [Q]uit "
        unpacker.fake_unrar.instance.stdout.read.side_effect = [output[i : i + 1] for i in range(len(output))] + [b""]

        with mock.patch.object(DirectUnpacker, "wait_for_next_volume") as wait_for_next_volume:
            unpacker.add(make_nzf("test.part01.rar", "test", 1))
            unpacker.join(timeout=10)

        assert not unpacker.is_alive(), "unpacker did not stop at the end of the output"
        # The prompt has no newline after it, so it is only recognized if partial output arrives
        wait_for_next_volume.assert_called_once()
        unpacker.fake_unrar.instance.stdin.write.assert_called_once_with(b"C\n")

    def test_each_instance_reads_its_own_output(self, startable_unpacker):
        """Output that a previous instance left behind may not leak into the next set"""
        unpacker = startable_unpacker
        unpacker.cur_setname = "test"
        unpacker.create_unrar_instance()
        first_queue = unpacker.output_queue
        first_queue.put(b"stale ")

        # This is how run() moves on to the next set
        unpacker.reset_active()
        unpacker.cur_setname = "test"
        unpacker.create_unrar_instance()

        assert unpacker.output_queue is not first_queue
        assert unpacker.output_queue.empty()


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
            assert not ACTIVE_UNPACKERS_LOCK.acquire(timeout=1), "the slots were readable mid-claim"

            release.set()
            adding.join(timeout=10)

        assert unpacker in ACTIVE_UNPACKERS
