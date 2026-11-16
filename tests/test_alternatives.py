"""Stable duplicate identities, lifecycle, and existing ID-filter contracts."""

import os
import pickle
from types import SimpleNamespace

import pytest

import sabnzbd
from sabnzbd import api, cfg, database
from sabnzbd.constants import DuplicateStatus, Status
from sabnzbd.nzb import NzbObject
from sabnzbd.nzb.object import NzbRejected, NzbRejectToHistory
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


@pytest.mark.parametrize("identity", [None, ""])
@pytest.mark.parametrize("smart", [False, True])
@pytest.mark.parametrize("action", [1, 2, 3, 4])
@pytest.mark.config(
    lambda params: {
        "no_dupes": 0 if params["smart"] else params["action"],
        "no_smart_dupes": params["action"] if params["smart"] else 0,
    }
)
def test_history_missing_id_preserves_duplicate_actions(related_env, identity, smart, action):
    queue, _, pool = related_env
    original = job("legacy", status=Status.COMPLETED)
    original.duplicate_key = "show/1/2"
    with pool.connection() as db:
        db.add_history_db(original, "", 0, "", "")
        db.execute("UPDATE history SET nzo_id=? WHERE nzo_id=?", (identity, original.nzo_id))
    fresh = job("fresh")
    fresh.duplicate_key = original.duplicate_key
    NzbObject.duplicate_check(fresh)
    assert fresh.duplicate == (DuplicateStatus.SMART_DUPLICATE if smart else DuplicateStatus.DUPLICATE)
    assert fresh.duplicate_of is None  # Existence is not a fabricated linkable identity.
    queue._NzbQueue__nzo_list = [fresh]
    assert queue.get_duplicate_groups() == {}
    if action in (1, 3):
        with pytest.raises(NzbRejected if action == 1 else NzbRejectToHistory):
            NzbObject.handle_duplicate_action(fresh)
        assert fresh.purge_data.call_count == (1 if action == 1 else 0)
    else:
        NzbObject.handle_duplicate_action(fresh)
        assert fresh.pause.call_count == (1 if action == 2 else 0)


@pytest.mark.parametrize("identity", [None, ""])
@pytest.mark.parametrize("smart", [False, True])
@pytest.mark.parametrize("valid_first", [False, True])
@pytest.mark.config(
    lambda params: {"no_dupes": 0 if params["smart"] else 2, "no_smart_dupes": 2 if params["smart"] else 0}
)
def test_history_mixed_ids_prefers_linkable_match(related_env, identity, smart, valid_first):
    queue, _, pool = related_env
    missing = job("missing", status=Status.COMPLETED)
    valid = job("valid", status=Status.COMPLETED)
    for nzo in (missing, valid):
        nzo.duplicate_key = "show/1/2"
    with pool.connection() as db:
        for nzo in ((valid, missing) if valid_first else (missing, valid)):
            db.add_history_db(nzo, "", 0, "", "")
        db.execute("UPDATE history SET nzo_id=? WHERE nzo_id=?", (identity, missing.nzo_id))
        # Failed and unrelated rows must never supply a replacement identity.
        failed = job("failed", status=Status.FAILED)
        failed.duplicate_key = valid.duplicate_key
        db.add_history_db(failed, "", 0, "", "")
        other = job("other", final_name="other")
        other.md5sum = "other"
        db.add_history_db(other, "", 0, "", "")
    fresh = job("fresh")
    fresh.duplicate_key = valid.duplicate_key
    NzbObject.duplicate_check(fresh)
    assert fresh.duplicate == (DuplicateStatus.SMART_DUPLICATE if smart else DuplicateStatus.DUPLICATE)
    assert fresh.duplicate_of == "valid"
    queue._NzbQueue__nzo_list = [fresh]
    assert queue.get_duplicate_groups() == {"valid": ["valid", "fresh"]}


@pytest.mark.parametrize("smart", [False, True])
@pytest.mark.parametrize("action", [2, 4])
@pytest.mark.parametrize("failed_candidate", [False, True])
@pytest.mark.config(
    lambda params: {
        "no_dupes": 0 if params["smart"] else params["action"],
        "no_smart_dupes": params["action"] if params["smart"] else 0,
    }
)
def test_promoted_winner_retargets_active_family(related_env, monkeypatch, smart, action, failed_candidate):
    queue, postproc, pool = related_env
    # These jobs have no disk state; actual checkpoint I/O is tested below.
    monkeypatch.setattr(sabnzbd.filesystem, "save_data", lambda *args, **kwargs: None)
    alternative_status = DuplicateStatus.SMART_DUPLICATE_ALTERNATIVE if smart else DuplicateStatus.DUPLICATE_ALTERNATIVE
    duplicate_status = DuplicateStatus.SMART_DUPLICATE if smart else DuplicateStatus.DUPLICATE
    original, first, winner, remaining, later, pp_peer, unrelated = (
        job(x) for x in ("R", "F", "A", "C", "D", "P", "U")
    )
    for nzo in (original, first, winner, remaining, later, pp_peer, unrelated):
        nzo.duplicate_key = "show/1/2"
        if smart:
            nzo.final_name = nzo.nzo_id
            nzo.md5sum = nzo.nzo_id
    for nzo in (first, winner, remaining, later, pp_peer, unrelated):
        nzo.duplicate = alternative_status
        nzo.duplicate_of = "R"
    # Same-name/key duplicate from another recorded family: action matching is
    # unchanged, but relationship metadata must not be inferred from those names.
    unrelated.duplicate_of = "other-root"
    queue._NzbQueue__nzo_list = ([first] if failed_candidate else []) + [winner, remaining, later, unrelated]
    assert queue.handle_duplicate_alternatives(original, success=False) is None
    if failed_candidate:
        assert first.duplicate is None
        assert first.resume.call_count == (action != 4)
        queue._NzbQueue__nzo_list.remove(first)
        postproc.history_queue = [first]
        assert queue.handle_duplicate_alternatives(first, success=False) is None
        first.status = Status.FAILED
    assert winner.duplicate is None
    assert winner.duplicate_of == "R"
    assert winner.resume.call_count == (action != 4)
    queue._NzbQueue__nzo_list.remove(winner)
    postproc.history_queue = [winner, pp_peer]
    for nzo in postproc.history_queue:
        nzo.admin_data_file_path = nzo.nzo_id
    assert queue.handle_duplicate_alternatives(winner, success=True) is None
    assert remaining.duplicate == duplicate_status
    assert later.duplicate == alternative_status  # Keep the existing first-retag return.
    assert winner.duplicate_of is None  # A PP lookup must now return A, not R.
    assert [nzo.duplicate_of for nzo in (remaining, later, pp_peer)] == ["A"] * 3
    assert unrelated.duplicate_of == "other-root"
    assert unrelated.duplicate == alternative_status
    lookup = queue.have_duplicate_key("show/1/2") if smart else queue.have_name_or_md5sum("test", "same-content")
    assert lookup == "A"
    during = job("during")
    during.duplicate_key = "show/1/2"
    NzbObject.duplicate_check(during)
    assert during.duplicate_of == "A"
    queue._NzbQueue__nzo_list.append(during)
    ids = queue.get_duplicate_groups()["A"]
    assert ids == ["A", "C", "D", "during", "P"]
    assert len(ids) == len(set(ids))
    # A real persisted winner must remain the target after it retires from PP.
    with pool.connection() as db:
        original.status = Status.FAILED
        db.add_history_db(original, "", 0, "", "")
        if failed_candidate:
            db.add_history_db(first, "", 0, "", "")
        winner.status = Status.COMPLETED
        db.add_history_db(winner, "", 0, "", "")
    postproc.history_queue = [pp_peer]
    fresh = job("B")
    fresh.duplicate_key = "show/1/2"
    NzbObject.duplicate_check(fresh)
    assert fresh.duplicate == duplicate_status
    assert fresh.duplicate_of == "A"
    queue._NzbQueue__nzo_list.append(fresh)
    ids = queue.get_duplicate_groups()[remaining.duplicate_of]
    assert ids == ["A", "C", "D", "during", "B", "P"]
    history, _, total = api.build_history(start=0, limit=20, nzo_ids=ids)
    assert {item["nzo_id"] for item in history} == {"A", "P"}
    assert total == 2


@pytest.mark.parametrize("smart", [False, True])
@pytest.mark.config(
    lambda params: {"no_dupes": 0 if params["smart"] else 2, "no_smart_dupes": 2 if params["smart"] else 0}
)
def test_promoted_family_queue_and_postproc_checkpoints(related_env, tmp_path, monkeypatch, smart):
    queue, postproc, pool = related_env
    monkeypatch.setattr(cfg.download_dir, "get_path", lambda: str(tmp_path / "incomplete"))
    monkeypatch.setattr(cfg.admin_dir, "get_path", lambda: str(tmp_path / "admin"))
    os.makedirs(cfg.admin_dir.get_path(), exist_ok=True)
    monkeypatch.setattr(sabnzbd, "Downloader", SimpleNamespace(servers=[]), raising=False)
    winner, remaining, pp_peer = [NzbObject("test", nzbname="test") for _ in range(3)]
    for nzo, nzo_id in zip((winner, remaining, pp_peer), ("A", "C", "P")):
        nzo.nzo_id = nzo_id
        nzo.work_name = nzo_id
        nzo.duplicate_key = "show/1/2"
        nzo.duplicate_of = "R"
        nzo.md5sum = "same-content"
        os.makedirs(nzo.admin_path, exist_ok=True)
    alternative_status = DuplicateStatus.SMART_DUPLICATE_ALTERNATIVE if smart else DuplicateStatus.DUPLICATE_ALTERNATIVE
    remaining.duplicate = pp_peer.duplicate = alternative_status
    winner.duplicate = None  # Already promoted after R failed.
    winner.removed_from_queue = pp_peer.removed_from_queue = True
    queue._NzbQueue__nzo_list = [remaining]
    postproc.history_queue = [winner, pp_peer]
    # PP.save stores paths, not object state: seed actual state as at handoff.
    for nzo in postproc.history_queue:
        sabnzbd.filesystem.save_data(nzo, os.path.basename(nzo.admin_data_file_path), nzo.admin_path)
    queue.save()
    PostProcessor.save(postproc)
    queue.handle_duplicate_alternatives(winner, success=True)
    queue.save()
    PostProcessor.save(postproc)
    restored = sabnzbd.filesystem.load_data(
        os.path.basename(remaining.admin_data_file_path), remaining.admin_path, remove=False
    )
    assert restored.duplicate_of == "A"
    assert restored.duplicate == (DuplicateStatus.SMART_DUPLICATE if smart else DuplicateStatus.DUPLICATE)
    successor = NzbQueue()
    successor._NzbQueue__nzo_list = [restored]
    monkeypatch.setattr(sabnzbd, "NzbQueue", successor)
    postproc.history_queue = []
    PostProcessor.load(postproc)
    assert [(nzo.nzo_id, nzo.duplicate_of) for nzo in postproc.history_queue] == [("A", None), ("P", "A")]
    assert successor.get_duplicate_groups() == {"A": ["A", "C", "P"]}
    lookup = (
        successor.have_duplicate_key("show/1/2") if smart else successor.have_name_or_md5sum("test", "same-content")
    )
    assert lookup == "A"
    with pool.connection() as db:
        winner.status = Status.COMPLETED
        db.add_history_db(winner, "", 0, "", "")
    postproc.history_queue = [postproc.history_queue[1]]
    fresh = job("B")
    fresh.duplicate_key = "show/1/2"
    NzbObject.duplicate_check(fresh)
    successor._NzbQueue__nzo_list.append(fresh)
    assert fresh.duplicate_of == "A"
    assert successor.get_duplicate_groups() == {"A": ["A", "C", "B", "P"]}


@pytest.mark.parametrize("route", ["sqlite", "api"])
def test_automatic_1001_id_history_filter(related_env, route):
    queue, _, pool = related_env
    original = job("original", final_name="selected original", status=Status.COMPLETED)
    alternatives = [job(f"alternative-{i}") for i in range(1000)]
    for nzo in alternatives:
        nzo.duplicate_of = original.nzo_id
    queue._NzbQueue__nzo_list = alternatives
    ids = queue.get_duplicate_groups()[original.nzo_id]
    assert len(ids) == 1001  # The actual automatic label input, without capping.
    with pool.connection() as db:
        for nzo in (
            original,
            job(ids[1], final_name="selected second", status=Status.COMPLETED),
            job(ids[2], final_name="selected wrong category", cat="other", status=Status.COMPLETED),
            job(ids[3], final_name="selected failed", status=Status.FAILED),
            job(ids[4], final_name="not matching search", status=Status.COMPLETED),
            job(ids[5], final_name="selected archived", status=Status.COMPLETED),
            job("unrelated", final_name="selected unrelated", status=Status.COMPLETED),
        ):
            db.add_history_db(nzo, "", 0, "", "")
        db.execute("UPDATE history SET completed=1 WHERE nzo_id=?", (original.nzo_id,))
        db.execute("UPDATE history SET completed=2 WHERE nzo_id=?", (ids[1],))
        db.execute("UPDATE history SET archive=1 WHERE nzo_id=?", (ids[5],))

        def fetch(**kwargs):
            filters = dict(search="selected", categories=["Default"], statuses=[Status.COMPLETED], **kwargs)
            if route == "sqlite":
                return db.fetch_history(**filters)
            items, pp_count, total = api.build_history(**filters)
            assert pp_count == 0
            return items, total

        first, total = fetch(start=0, limit=1, nzo_ids=ids)
        assert total == 2
        assert [item["nzo_id"] for item in first] == [ids[1]]
        second, total = fetch(start=1, limit=1, nzo_ids=ids)
        assert total == 2
        assert [item["nzo_id"] for item in second] == [original.nzo_id]
        beyond, total = fetch(start=2, limit=1, nzo_ids=ids)
        assert beyond == [] and total == 2
        all_selected, total = fetch(start=0, limit=10, nzo_ids=ids)
        assert {item["nzo_id"] for item in all_selected} == {original.nzo_id, ids[1]}
        assert total == 2
        unknown, total = fetch(start=0, limit=10, nzo_ids=[f"missing-{i}" for i in range(1001)])
        assert unknown == [] and total == 0
