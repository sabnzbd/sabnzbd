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
tests.test_functional_config - Basic testing if Config pages work
"""

from playwright.sync_api import expect
from pytest_httpserver import HTTPServer


import os
import re
from tests.testhelper import (
    SAB_DATA_DIR,
    SAB_HOST,
    SAB_PORT,
    SAB_NEWSSERVER_HOST,
    SAB_NEWSSERVER_PORT,
    SABnzbdBaseTest,
    create_and_read_nzb_fp,
    get_api_result,
    wait_for,
)


class TestBasicPages(SABnzbdBaseTest):
    def test_base_pages(self):
        # Quick-check of all Config pages
        test_urls = ["config", "config/server", "config/categories", "config/scheduling", "config/rss"]

        for test_url in test_urls:
            self.open_page("http://%s:%s/%s" % (SAB_HOST, SAB_PORT, test_url))

    def test_base_submit_pages(self):
        # The save button is re-enabled on a 1s timer that is only scheduled once the response lands
        self.page.clock.install()
        test_urls_with_submit = [
            "config/general",
            "config/folders",
            "config/switches",
            "config/notify",
            "config/special",
        ]

        for test_url in test_urls_with_submit:
            self.open_page("http://%s:%s/%s" % (SAB_HOST, SAB_PORT, test_url))

            # Can only click the visible buttons
            submit_btn = self.page.locator(".saveButton:visible").first
            expect(submit_btn).to_be_visible()

            with self.page.expect_response(lambda r: r.request.method == "POST"):
                submit_btn.click()
            self.page.clock.run_for(1000)

            # For Specials page we get redirected after save, so check for no crash
            if "special" in test_url:
                self.no_page_crash()
            else:
                # For others if all is fine, the button will be back to normal
                expect(submit_btn).to_have_text("Save Changes", timeout=1500)


class TestConfigLogin(SABnzbdBaseTest):
    def test_login(self):
        # Test if base page works
        self.open_page("http://%s:%s/config/general" % (SAB_HOST, SAB_PORT))

        # Set the username and password
        self.page.locator("input[data-hide='username']").fill("test_username")
        self.page.locator("input[data-hide='password']").fill("test_password")

        # Submit and dismiss the restart-request (cancel, so no restart happens)
        self.click_expecting_dialog(self.page.locator(".saveButton").first)

        # Open any page and check if we get redirected
        self.open_page("http://%s:%s/config/general" % (SAB_HOST, SAB_PORT))
        assert "/login" in self.page.url

        # Fill nonsense and submit
        self.page.locator("input[name='username']").fill("nonsense")
        self.page.locator("input[name='password']").fill("nonsense")
        self.page.locator("button").first.click()

        # Check if we were denied
        expect(self.page.locator(".alert-danger")).to_contain_text("Authentication failed")

        # Fill right stuff
        self.page.locator("input[name='username']").fill("test_username")
        self.page.locator("input[name='password']").fill("test_password")
        self.page.locator("button").first.click()

        # Can we now go to the page and empty the settings again?
        self.open_page("http://%s:%s/config/general" % (SAB_HOST, SAB_PORT))
        assert "/login" not in self.page.url

        # Set the username and password
        self.page.locator("input[data-hide='username']").fill("")
        self.page.locator("input[data-hide='password']").fill("")

        # Submit and dismiss the restart-request (cancel, so no restart happens)
        self.click_expecting_dialog(self.page.locator(".saveButton").first)

        # Open any page and check we are NOT redirected to login (no credentials set)
        self.open_page("http://%s:%s/config/general" % (SAB_HOST, SAB_PORT))
        assert "/login" not in self.page.url


class TestConfigCategories(SABnzbdBaseTest):
    category_name = "testCat"

    def test_page(self):
        # Test if base page works
        self.open_page("http://%s:%s/config/categories" % (SAB_HOST, SAB_PORT))

        # Add new category
        self.page.locator("[name='newname']").nth(1).fill(self.category_name)
        with self.page.expect_response(lambda r: r.request.method == "POST"):
            self.page.locator("xpath=//button/text()[normalize-space(.)='Add']/parent::*").click()
        self.no_page_crash()

        # Category names are stored lowercased, so the name as typed must not come back
        assert self.category_name not in self.page.content()

        # Reload and confirm it was really saved. Without this the test passes whether the
        # POST was accepted or refused, because a rejected save leaves the name absent too.
        self.open_page("http://%s:%s/config/categories" % (SAB_HOST, SAB_PORT))
        assert self.category_name.lower() in self.page.content()


class TestConfigRSS(SABnzbdBaseTest):
    rss_name = "_PlaywrightFeed"

    def test_rss_basic_flow(self, httpserver: HTTPServer):
        # Setup the response for the NZB
        nzb_fp = create_and_read_nzb_fp("basic_rar5")
        httpserver.expect_request("/test_nzb.nzb").respond_with_data(nzb_fp.read())
        nzb_url = httpserver.url_for("/test_nzb.nzb")

        # Set the response for the RSS-feed, replacing the URL to the NZB
        with open(os.path.join(SAB_DATA_DIR, "rss_feed_test.xml")) as rss_file:
            rss_data = rss_file.read()
        rss_data = rss_data.replace("NZB_URL", nzb_url)
        httpserver.expect_request("/rss_feed.xml").respond_with_data(rss_data)
        rss_url = httpserver.url_for("/rss_feed.xml")

        # Test if base page works
        self.open_page("http://%s:%s/config/rss" % (SAB_HOST, SAB_PORT))

        # Uncheck enabled-checkbox for new feeds
        add_form = self.page.locator('form[data-form="add-rss-feed"]')
        add_form.locator("input[name='enable']").click()
        add_form.locator("input[name='feed']").fill(self.rss_name)
        add_form.locator("input[name='uri']").fill(rss_url)
        add_form.locator("button").click()

        # Check if we have results
        matched_count = self.page.locator('xpath=//a[@href="#rss-tab-matched"]/span')
        expect(matched_count).to_be_visible()
        tab_results = int(matched_count.inner_text())
        assert tab_results > 0

        # Check if it matches the number of rows
        tab_table_results = self.page.locator('xpath=//div[@id="rss-tab-matched"]/table/tbody/tr').count()
        assert tab_table_results == tab_results

        # Pause the queue do we don't download stuff
        assert get_api_result("pause") == {"status": True}

        # Download something
        download_btn = self.page.locator('xpath=//div[@id="rss-tab-matched"]/table/tbody//button').first
        download_btn.click()

        # Does the page think it's a success?
        expect(download_btn).to_contain_text("Added NZB", timeout=5000)

        # Check if the fetch-request was added to the queue
        wait_for(
            lambda: len(get_api_result("queue")["queue"]["slots"]) > 0,
            timeout=10,
            err_msg="Did not find the RSS job in the queue",
        )

        # Let's remove this thing
        get_api_result("queue", extra_arguments={"name": "delete", "value": "all"})
        assert len(get_api_result("queue")["queue"]["slots"]) == 0

        # Unpause
        assert get_api_result("resume") == {"status": True}


class TestConfigServers(SABnzbdBaseTest):
    server_name = "_PlaywrightServer"

    def open_config_servers(self):
        # Test if base page works
        self.open_page("http://%s:%s/config/server" % (SAB_HOST, SAB_PORT))

        # Show advanced options
        advanced_btn = self.page.locator("[name='advanced-settings-button']")
        if not advanced_btn.is_checked():
            advanced_btn.click()

    def add_test_server(self):
        # Add server
        self.page.locator("#addServerButton").click()
        self.page.locator("[name='host']").fill(SAB_NEWSSERVER_HOST)

        # Change port
        port_inp = self.page.locator("[name='port']")
        port_inp.fill(str(SAB_NEWSSERVER_PORT))

        # Disable SSL for testing
        self.page.locator("[name='ssl']").click()

        # Test server-check
        self.page.locator("#addServerContent .testServer").click()
        expect(self.page.locator("#addServerContent .result-box")).to_contain_text(
            "Connection Successful", timeout=5000
        )

        # Set test-servername
        self.page.locator("#displayname").fill(self.server_name)

        # Add and show details, once the reload that saving a new server triggers has landed
        with self.page.expect_navigation():
            port_inp.press("Enter")
        expect(self.page.locator("#host0")).to_be_hidden(timeout=2000)
        self.page.locator(".showserver").first.click()
        expect(self.page.locator(".delServer").first).to_be_visible()

    def remove_server(self):
        # Remove the first server and accept the confirmation
        self.click_expecting_dialog(self.page.locator(".delServer").first, accept=True)

        # Check that it's gone
        wait_for(
            lambda: self.server_name not in self.page.content(),
            timeout=2,
            err_msg=f"Page still contains '{self.server_name}'",
        )

    def test_add_and_remove_server(self):
        self.open_config_servers()
        self.add_test_server()
        self.remove_server()


class TestGlitterInterface(SABnzbdBaseTest):
    """Glitter funnels every call through callAPI, so a wrong CSRF header fails all of them at once"""

    def test_interface_loads_and_polls(self):
        # skip_wizard because the test ini configures no servers, so / would redirect there
        self.open_page("http://%s:%s/?skip_wizard=1" % (SAB_HOST, SAB_PORT))

        # Glitter polls forever, so there is no network-idle; isLoaded marks the first refresh
        expect(self.page.locator(".main-content")).to_have_class(re.compile(r"main-content-loaded"))

        # The token reached the page and was installed for every request. Checked because a
        # missing csrfToken global would throw inside glitter.basic.js and stop the rest of
        # the interface from initialising -- which leaves the overlay below hidden, so the
        # overlay alone would not notice.
        assert self.page.evaluate(
            "csrfToken.length === 64 && ($.ajaxSettings.headers || {})['X-SABnzbd-CSRF'] === csrfToken"
        ), "Glitter did not install the CSRF header on its API calls"

        # The queue and history refresh drop this overlay over the page when they fail, so
        # its absence is what says those calls came back authorized
        assert not self.page.locator(
            ".main-restarting"
        ).is_visible(), "Glitter showed the reconnect overlay, so its API calls failed"
