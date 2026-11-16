"""Stable duplicate identities, lifecycle, and existing ID-filter contracts."""

import pickle
from types import SimpleNamespace

import pytest

import sabnzbd
from sabnzbd import api, cfg, database
from sabnzbd.constants import DuplicateStatus, Status
from sabnzbd.nzb import NzbObject
from sabnzbd.nzbqueue import NzbQueue
from sabnzbd.postproc import PostProcessor
from tests.testhelper import make_mock_nzo


@pytest.fixture
def related_env(tmp_path, monkeypatch):
    monkeypatch.setattr(database.HistoryDB, "db_path", str(tmp_path / "history.db"))
    monkeypatch.setattr(database.HistoryDB, "startup_done", False)
    pool = database.HistoryDBPool()
    monkeypatch.setattr(sabnzbd, "db_pool", pool)
    queue = NzbQueue()
    monkeypatch.setattr(sabnzbd, "NzbQueue", queue, raising=False)
    # Run the actual postproc filtering method without starting its worker thread.
    postproc = SimpleNamespace(history_queue=[])
    postproc.get_queue = lambda **kwargs: PostProcessor.get_queue(postproc, **kwargs)
    monkeypatch.setattr(sabnzbd, "PostProcessor", postproc, raising=False)
    yield queue, postproc, pool
    pool.close()


def job(nzo_id, **kwargs):
    return make_mock_nzo(
        nzo_id=nzo_id,
        work_name=nzo_id,
        duplicate=None,
        duplicate_of=None,
        md5sum="same-content",
        **kwargs,
    )


@pytest.mark.parametrize("smart", [False, True])
@pytest.mark.parametrize("location", ["queue", "postproc", "history"])
@pytest.mark.config({"no_dupes": 2, "no_smart_dupes": 2})
def test_detection_records_stable_id(related_env, smart, location):
    queue, postproc, pool = related_env
    original = job("original-id")
    original.duplicate_key = "show/1/2"
    if location == "queue":
        queue._NzbQueue__nzo_list = [original]
    elif location == "postproc":
        postproc.history_queue = [original]
    else:
        original.status = Status.COMPLETED
        with pool.connection() as db:
            db.add_history_db(original, "", 0, "", "")
    alternative = job("alternative-id")
    alternative.duplicate_key = "show/1/2"
    alternative.final_name = "different-title" if smart else "test"
    if smart:
        alternative.md5sum = "different-content"
    NzbObject.duplicate_check(alternative)
    assert alternative.duplicate_of == original.nzo_id
    expected = (
        (DuplicateStatus.SMART_DUPLICATE if smart else DuplicateStatus.DUPLICATE)
        if location == "history"
        else (DuplicateStatus.SMART_DUPLICATE_ALTERNATIVE if smart else DuplicateStatus.DUPLICATE_ALTERNATIVE)
    )
    assert alternative.duplicate == expected


@pytest.mark.config({"no_dupes": 2})
def test_group_survives_promotion_and_removed_original(related_env):
    queue, postproc, _ = related_env
    original = job("original")
    first = job("first")
    second = job("second")
    for alternative in (first, second):
        alternative.duplicate = DuplicateStatus.DUPLICATE_ALTERNATIVE
        alternative.duplicate_of = original.nzo_id
    unrelated = job("unrelated")  # Same name/content is not a recorded relationship.
    queue._NzbQueue__nzo_list = [first, second, unrelated]
    assert queue.get_duplicate_groups() == {"original": ["original", "first", "second"]}
    queue.handle_duplicate_alternatives(original, success=False)
    assert first.duplicate is None
    first.resume.assert_called_once()
    assert first.duplicate_of == "original"
    # New alternatives inherit the stable group even after the original is gone.
    assert queue.have_name_or_md5sum("test", "same-content") == "original"
    assert queue.get_duplicate_groups() == {"original": ["original", "first", "second"]}
    queue._NzbQueue__nzo_list = [second, unrelated]
    postproc.history_queue = [first]
    assert queue.get_duplicate_groups() == {"original": ["original", "second", "first"]}


@pytest.mark.config({"no_dupes": 2})
def test_repeat_and_backup_only_do_not_fabricate_ids(related_env, monkeypatch):
    alternative = job("alternative")
    alternative.duplicate = DuplicateStatus.DUPLICATE_ALTERNATIVE
    alternative.duplicate_of = "stale-original"
    NzbObject.duplicate_check(alternative, repeat=True)
    assert alternative.duplicate is None
    assert alternative.duplicate_of is None
    monkeypatch.setattr(cfg.backup_for_duplicates, "get", lambda: True)
    monkeypatch.setattr("sabnzbd.nzb.object.backup_exists", lambda name: True)
    NzbObject.duplicate_check(alternative)
    assert alternative.duplicate == DuplicateStatus.DUPLICATE
    assert alternative.duplicate_of is None


def test_saved_and_legacy_job_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.download_dir, "get_path", lambda: str(tmp_path))
    monkeypatch.setattr(sabnzbd, "Downloader", SimpleNamespace(servers=[]), raising=False)
    nzo = NzbObject("test")
    nzo.duplicate = DuplicateStatus.DUPLICATE_ALTERNATIVE
    nzo.duplicate_of = "SABnzbd_nzo_original"
    restored = pickle.loads(pickle.dumps(nzo))
    assert restored.duplicate_of == "SABnzbd_nzo_original"
    state = nzo.__getstate__()
    del state["duplicate_of"]
    legacy = NzbObject.__new__(NzbObject)
    legacy.__setstate__(state)
    assert legacy.duplicate_of is None
    assert legacy.duplicate == nzo.duplicate


def test_history_filter_includes_postprocessing_and_pages(related_env):
    _, postproc, pool = related_env
    original = job("original")
    alternative = job("alternative")
    alternative.duplicate_of = original.nzo_id
    postproc.history_queue = [alternative]
    with pool.connection() as db:
        original.status = Status.COMPLETED
        db.add_history_db(original, "", 0, "", "")
        db.add_history_db(job("unrelated"), "", 0, "", "")
    ids = [original.nzo_id, alternative.nzo_id]
    first, pp_count, total = api.build_history(start=0, limit=1, nzo_ids=ids)
    assert [item["nzo_id"] for item in first] == ["alternative"]
    assert pp_count == 1
    assert total == 2
    second, _, total = api.build_history(start=1, limit=1, nzo_ids=ids)
    assert [item["nzo_id"] for item in second] == ["original"]
    assert total == 2
    empty, _, total = api.build_history(start=0, limit=10, nzo_ids=["missing"])
    assert empty == []
    assert total == 0


def test_failed_history_not_a_duplicate(related_env):
    _, _, pool = related_env
    failed = job("failed", status=Status.FAILED)
    failed.duplicate_key = "show/1/2"
    with pool.connection() as db:
        db.add_history_db(failed, "", 0, "", "")
        assert db.have_duplicate_key("show/1/2") is None
        assert db.have_name_or_md5sum("test", "same-content") is None


def test_legacy_unknown_relation_has_no_group(related_env):
    queue, _, _ = related_env
    legacy = job("legacy")
    legacy.duplicate = DuplicateStatus.DUPLICATE_ALTERNATIVE
    queue._NzbQueue__nzo_list = [legacy, job("same-name")]
    assert queue.get_duplicate_groups() == {}
