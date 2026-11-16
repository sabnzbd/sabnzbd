"""Alternative labels filter the real Glitter UI and API by job identity."""

import os
import tempfile
from urllib.parse import parse_qs

import pytest
from playwright.sync_api import expect

from sabnzbd.constants import DB_HISTORY_NAME, DEF_ADMIN_DIR
from tests.testhelper import (
    FakeHistoryDB,
    SAB_CACHE_DIR,
    SAB_HOST,
    SAB_PORT,
    create_nzb,
    get_api_result,
)


def configure(keyword, value):
    result = get_api_result("set_config", extra_arguments={"section": "misc", "keyword": keyword, "value": value})
    assert "error" not in result, result


def add_job(name, data="basic_rar5"):
    with tempfile.TemporaryDirectory() as output:
        nzb = create_nzb(data, output_file=os.path.join(output, "test.nzb"))
        result = get_api_result("addlocalfile", extra_arguments={"name": nzb, "nzbname": name})
    assert result["status"]
    return result["nzo_ids"][0]


@pytest.mark.usefixtures("run_sabnzbd")
@pytest.mark.parametrize("tabbed", [False, True])
def test_alternative_label_filters_related_jobs(page, tabbed):
    get_api_result("pause")
    for mode in ("queue", "history"):
        get_api_result(mode, extra_arguments={"name": "delete", "value": "all", "del_files": 1})
    configure("no_dupes", 0)
    configure("no_smart_dupes", 0)
    original = add_job("original")
    configure("no_dupes", 2)
    alternatives = [add_job(f"alternative {index}") for index in range(1, 7)]
    configure("no_dupes", 0)
    unrelated = add_job("original", "basic_rar3")
    configure("no_dupes", 2)
    related = {original, *alternatives}
    query = " ".join(f"id:{job}" for job in [original, *alternatives])

    page.goto(f"http://{SAB_HOST}:{SAB_PORT}/?skip_wizard=1")
    page.evaluate("value => localStorage.setItem('displayTabbed', value)", str(tabbed).lower())
    page.evaluate("localStorage.setItem('useGlobalOptions', 'false')")
    page.reload()
    labels = page.locator(".queue-item .label", has_text="ALTERNATIVE")
    expect(labels).to_have_count(6)
    labels.first.click()
    queue_search = page.locator("#queue-tab .search-box input")
    history_search = page.locator("#history-tab .search-box input")
    # On the old UI clicking the label does nothing: this is the acceptance red.
    expect(queue_search).to_have_value(query)
    expect(history_search).to_have_value(queue_search.input_value())
    expect(page.locator(".queue-item")).to_have_count(7)
    ids = page.locator(".queue-item").evaluate_all("rows => rows.map(row => ko.dataFor(row).id)")
    assert set(ids) == related
    assert unrelated not in ids

    # Clearing each existing search restores its own normal view.
    queue_search.press("Escape")
    expect(queue_search).to_have_value("")
    expect(page.locator(".queue-item")).to_have_count(8)

    # Ordinary text and existing keyword filters keep their previous behavior.
    page.evaluate("ko.contextFor(document.querySelector('.queue-item')).$root.queue.paginationLimit(5)")
    expect(page.locator(".queue-item")).to_have_count(5)
    queue_search.fill("alternative status:Paused priority:Normal")
    expect(page.locator(".queue-item")).to_have_count(5)
    expect(page.locator(".queue-item").first).to_contain_text("alternative 1")
    queue_search.press("Escape")
    expect(page.locator(".queue-item").first).to_contain_text("original")

    # A label on page two returns both lists to page one. Use the production
    # pagination and clear button, not just JavaScript parser assertions.
    page.locator("#queue-tab ul.pagination").get_by_role("link", name="2", exact=True).click()
    expect(page.locator(".queue-item").first).to_contain_text("alternative 5")
    labels.first.click()
    expect(queue_search).to_have_value(query)
    expect(page.locator("#queue-tab ul.pagination li.active")).to_have_text("1")
    expect(page.locator(".queue-item")).to_have_count(5)
    expect(page.locator(".queue-item").first).to_contain_text("original")
    page.locator("#queue-tab ul.pagination").get_by_role("link", name="2", exact=True).click()
    expect(page.locator(".queue-item")).to_have_count(2)
    page.locator("#queue-tab .search-box a").click()
    expect(queue_search).to_have_value("")
    expect(page.locator("#queue-tab ul.pagination li.active")).to_have_text("1")
    page.evaluate("ko.contextFor(document.querySelector('.queue-item')).$root.queue.paginationLimit(20)")
    expect(page.locator(".queue-item")).to_have_count(8)

    # Move the original into persisted history without downloading from a server.
    get_api_result("queue", extra_arguments={"name": "delete", "value": original, "del_files": 1})
    with FakeHistoryDB(os.path.join(SAB_CACHE_DIR, DEF_ADMIN_DIR, DB_HISTORY_NAME)) as history:
        history_id = history.add_fake_history_job("original")
        history.execute("UPDATE history SET nzo_id = ? WHERE nzo_id = ?", (original, history_id))
        history.add_fake_history_job("original")  # Same name, unrelated identity.
    labels.first.click()
    expect(page.locator(".queue-item")).to_have_count(6)
    if tabbed:
        page.locator('.history-queue-swicher a[href="#history-tab"]').click()
    expect(page.locator(".history-item")).to_have_count(1)
    history_search.press("Escape")
    expect(history_search).to_have_value("")
    expect(page.locator(".history-item")).to_have_count(2)

    # An unknown ID must never turn into an unfiltered/all-results request.
    history_search.fill("id:SABnzbd_nzo_missing")
    expect(page.locator(".history-item")).to_have_count(0)
    if tabbed:
        page.locator('.history-queue-swicher a[href="#queue-tab"]').click()
    queue_search.fill("id:SABnzbd_nzo_missing")
    expect(page.locator(".queue-item")).to_have_count(0)
    queue_search.press("Escape")
    expect(page.locator(".queue-item")).to_have_count(7)


@pytest.mark.usefixtures("run_sabnzbd")
@pytest.mark.parametrize("flags", [False, True])
def test_related_filter_resets_both_offsets_before_refresh(page, flags):
    get_api_result("pause")
    for mode in ("queue", "history"):
        get_api_result(mode, extra_arguments={"name": "delete", "value": "all", "del_files": 1})
    configure("no_dupes", 0)
    configure("no_smart_dupes", 0)
    original = add_job("original")
    configure("no_dupes", 2)
    alternatives = [add_job(f"alternative {index}") for index in range(6)]
    get_api_result("queue", extra_arguments={"name": "delete", "value": original, "del_files": 1})
    with FakeHistoryDB(os.path.join(SAB_CACHE_DIR, DEF_ADMIN_DIR, DB_HISTORY_NAME)) as history:
        history_id = history.add_fake_history_job("original")
        history.execute("UPDATE history SET nzo_id = ? WHERE nzo_id = ?", (original, history_id))
        for index in range(6):
            history_id = history.add_fake_history_job(f"unrelated {index}")
            if flags:
                history.execute("UPDATE history SET status='Failed', archive=1 WHERE nzo_id=?", (history_id,))

    page.goto(f"http://{SAB_HOST}:{SAB_PORT}/?skip_wizard=1")
    page.evaluate(
        """flags => {
        localStorage.setItem('displayTabbed', 'false');
        localStorage.setItem('useGlobalOptions', 'false');
        localStorage.setItem('queuePaginationLimit', '5');
        localStorage.setItem('historyPaginationLimit', '5');
        localStorage.setItem('historyShowFailed', JSON.stringify(flags));
        localStorage.setItem('historyShowArchive', JSON.stringify(flags));
    }""",
        flags,
    )
    page.reload()
    expect(page.locator(".queue-item")).to_have_count(5)
    expect(page.locator(".history-item")).to_have_count(5)
    page.evaluate("""() => {
        window.relatedRoot = ko.contextFor(document.querySelector('.queue-item')).$root;
        relatedRoot.refreshRate('60');
    }""")
    page.locator("#queue-tab ul.pagination").get_by_role("link", name="2", exact=True).click()
    page.locator("#history-tab ul.pagination").get_by_role("link", name="2", exact=True).click()
    expect(page.locator("#queue-tab ul.pagination li.active")).to_have_text("2")
    expect(page.locator("#history-tab ul.pagination li.active")).to_have_text("2")
    page.wait_for_load_state("networkidle")
    page.evaluate("""() => {
        window.searchNotifications = 0;
        window.appliedRelated = {queue: 0, history: 0};
        for (const list of ['queue', 'history']) {
            relatedRoot[list].searchTerm.subscribe(() => searchNotifications++);
            const method = list === 'queue' ? 'updateQueue' : 'updateHistory';
            const update = relatedRoot[method];
            relatedRoot[method] = function(response) {
                update(response);
                appliedRelated[list]++;
            };
        }
    }""")
    staged = []
    normal = []
    holding = True

    def stage_real_response(route):
        query = parse_qs(route.request.post_data or "")
        mode = query.get("mode", [""])[0]
        if mode not in ("queue", "history") or "nzo_ids" not in query:
            route.continue_()
            return
        # Real API bytes, never fake payloads: only delivery is controlled.
        response = route.fetch()
        if holding:
            staged.append((route, response, query))
            page.evaluate("window.stagedCount = (window.stagedCount || 0) + 1")
        else:
            normal.append(query)
            route.fulfill(response=response)

    page.route("**/api", stage_real_response)
    page.locator(".queue-item .label", has_text="ALTERNATIVE").first.click()
    page.wait_for_function("searchNotifications === 2")
    # Both real rate-limited subscribers ran, each starting a request pair.
    page.wait_for_function("window.stagedCount >= 6 && stagedCount === jQuery.active")
    assert len(staged) >= 6
    starts = [(query["mode"][0], int(query["start"][0])) for _, _, query in staged]
    counts = {mode: sum(item[0] == mode for item in starts) for mode in ("queue", "history")}
    # Newest page-one responses first; the oldest wrong history offset last.
    for route, response, _ in reversed(staged):
        route.fulfill(response=response)
    page.wait_for_function(
        "counts => appliedRelated.queue === counts.queue && appliedRelated.history === counts.history", arg=counts
    )
    holding = False
    before_poll = page.locator(".history-item").evaluate_all(
        "rows => rows.map(row => ko.dataFor(row).historyStatus.nzo_id())"
    )
    # A normal, non-forced poll must not leave a wrong view behind lastUpdate.
    page.evaluate("relatedRoot.refresh()")
    page.wait_for_function(
        "counts => appliedRelated.queue > counts.queue && appliedRelated.history > counts.history", arg=counts
    )
    queue_ids = page.locator(".queue-item").evaluate_all("rows => rows.map(row => ko.dataFor(row).id)")
    history_ids = page.locator(".history-item").evaluate_all(
        "rows => rows.map(row => ko.dataFor(row).historyStatus.nzo_id())"
    )
    print(
        {
            "related_starts": starts,
            "before_normal_poll": before_poll,
            "after_normal_poll": history_ids,
            "normal_poll": normal,
        }
    )
    assert before_poll == history_ids == [original]
    assert queue_ids == alternatives[:5]
    assert all(start == 0 for _, start in starts)
    assert all(int(query["start"][0]) == 0 for query in normal)
    history_poll = next(query for query in normal if query["mode"] == ["history"])
    assert float(history_poll["last_history_update"][0]) > 0
    expect(page.locator("#queue-tab ul.pagination li.active")).to_have_text("1")
    assert page.evaluate("!relatedRoot.history.showFailed() && !relatedRoot.history.showArchive()")
    page.unroute("**/api", stage_real_response)
