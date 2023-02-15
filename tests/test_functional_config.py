#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team <team@sabnzbd.org>
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

from selenium.common.exceptions import NoSuchElementException, UnexpectedAlertPresentException, NoAlertPresentException
from selenium.webdriver.common.by import By
from pytest_httpserver import HTTPServer


from tests.testhelper import *


class TestBasicPages(SABnzbdBaseTest):
    def test_base_pages(self):
        # Quick-check of all Config pages
        test_urls = ["config", "config/server", "config/categories", "config/scheduling", "config/rss"]

        for test_url in test_urls:
            self.open_page("http://%s:%s/%s" % (SAB_HOST, SAB_PORT, test_url))

    def test_base_submit_pages(self):
        test_urls_with_submit = [
            "config/general",
            "config/folders",
            "config/switches",
            "config/sorting",
            "config/notify",
            "config/special",
        ]

        for test_url in test_urls_with_submit:
            self.open_page("http://%s:%s/%s" % (SAB_HOST, SAB_PORT, test_url))

            # Can only click the visible buttons
            submit_btns = self.selenium_wrapper(self.driver.find_elements, By.CLASS_NAME, "saveButton")
            for submit_btn in submit_btns:
                if submit_btn.is_displayed():
                    break
            else:
                raise NoSuchElementException

            # Click the right button
            submit_btn.click()

            try:
                self.wait_for_ajax()
            except UnexpectedAlertPresentException:
                try:
                    # Ignore restart-request due to empty sabnzbd.ini in tests
                    self.driver.switch_to.alert.dismiss()
                except NoAlertPresentException:
                    pass

            # For Specials page we get redirected after save, so check for no crash
            if "special" in test_url:
                self.no_page_crash()
            else:
                # For others if all is fine, button will be back to normal in 1 second
                time.sleep(1.5)
                assert submit_btn.text == "Save Changes"


class TestConfigLogin(SABnzbdBaseTest):
    def test_login(self):
        # Test if base page works
        self.open_page("http://%s:%s/sabnzbd/config/general" % (SAB_HOST, SAB_PORT))

        # Set the username and password
        username_imp = self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, "input[data-hide='username']")
        username_imp.clear()
        username_imp.send_keys("test_username")
        pass_inp = self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, "input[data-hide='password']")
        pass_inp.clear()
        pass_inp.send_keys("test_password")

        # Submit and ignore alert
        self.selenium_wrapper(self.driver.find_element, By.CLASS_NAME, "saveButton").click()

        try:
            self.wait_for_ajax()
        except UnexpectedAlertPresentException:
            try:
                # Ignore restart-request
                self.driver.switch_to.alert.dismiss()
            except NoAlertPresentException:
                pass

        # Open any page and check if we get redirected
        self.open_page("http://%s:%s/sabnzbd/general" % (SAB_HOST, SAB_PORT))
        assert "/login/" in self.driver.current_url

        # Fill nonsense and submit
        username_login = self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, "input[name='username']")
        username_login.clear()
        username_login.send_keys("nonsense")
        pass_login = self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, "input[name='password']")
        pass_login.clear()
        pass_login.send_keys("nonsense")
        self.driver.find_element(By.TAG_NAME, "button").click()

        # Check if we were denied
        assert (
            "Authentication failed"
            in self.selenium_wrapper(self.driver.find_element, By.CLASS_NAME, "alert-danger").text
        )

        # Fill right stuff
        username_login = self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, "input[name='username']")
        username_login.clear()
        username_login.send_keys("test_username")
        pass_login = self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, "input[name='password']")
        pass_login.clear()
        pass_login.send_keys("test_password")
        self.driver.find_element(By.TAG_NAME, "button").click()

        # Can we now go to the page and empty the settings again?
        self.open_page("http://%s:%s/sabnzbd/config/general" % (SAB_HOST, SAB_PORT))
        assert "/login/" not in self.driver.current_url

        # Set the username and password
        username_imp = self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, "input[data-hide='username']")
        username_imp.clear()
        pass_inp = self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, "input[data-hide='password']")
        pass_inp.clear()

        # Submit and ignore alert
        self.selenium_wrapper(self.driver.find_element, By.CLASS_NAME, "saveButton").click()

        try:
            self.wait_for_ajax()
        except UnexpectedAlertPresentException:
            try:
                # Ignore restart-request
                self.driver.switch_to.alert.dismiss()
            except NoAlertPresentException:
                pass

        # Open any page and check if we get redirected
        self.open_page("http://%s:%s/sabnzbd/general" % (SAB_HOST, SAB_PORT))
        assert "/login/" not in self.driver.current_url


class TestConfigCategories(SABnzbdBaseTest):
    category_name = "testCat"

    def test_page(self):
        # Test if base page works
        self.open_page("http://%s:%s/sabnzbd/config/categories" % (SAB_HOST, SAB_PORT))

        # Add new category
        self.driver.find_elements(By.NAME, "newname")[1].send_keys("testCat")
        self.selenium_wrapper(
            self.driver.find_element, By.XPATH, "//button/text()[normalize-space(.)='Add']/parent::*"
        ).click()
        self.no_page_crash()
        assert self.category_name not in self.driver.page_source


class TestConfigRSS(SABnzbdBaseTest):
    rss_name = "_SeleniumFeed"

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
        self.open_page("http://%s:%s/sabnzbd/config/rss" % (SAB_HOST, SAB_PORT))

        # Uncheck enabled-checkbox for new feeds
        self.selenium_wrapper(
            self.driver.find_element, By.XPATH, '//form[@action="add_rss_feed"]//input[@name="enable"]'
        ).click()
        input_name = self.selenium_wrapper(
            self.driver.find_element, By.XPATH, '//form[@action="add_rss_feed"]//input[@name="feed"]'
        )
        input_name.clear()
        input_name.send_keys(self.rss_name)
        self.selenium_wrapper(
            self.driver.find_element, By.XPATH, '//form[@action="add_rss_feed"]//input[@name="uri"]'
        ).send_keys(rss_url)
        self.selenium_wrapper(self.driver.find_element, By.XPATH, '//form[@action="add_rss_feed"]//button').click()

        # Check if we have results
        tab_results = int(
            self.selenium_wrapper(self.driver.find_element, By.XPATH, '//a[@href="#rss-tab-matched"]/span').text
        )
        assert tab_results > 0

        # Check if it matches the number of rows
        tab_table_results = len(self.driver.find_elements(By.XPATH, '//div[@id="rss-tab-matched"]/table/tbody/tr'))
        assert tab_table_results == tab_results

        # Pause the queue do we don't download stuff
        assert get_api_result("pause") == {"status": True}

        # Download something
        download_btn = self.selenium_wrapper(
            self.driver.find_element, By.XPATH, '//div[@id="rss-tab-matched"]/table/tbody//button'
        )
        download_btn.click()
        self.wait_for_ajax()

        # Does the page think it's a success?
        assert "Added NZB" in download_btn.text

        # Wait 2 seconds for the fetch
        time.sleep(2)

        # Let's check the queue
        for _ in range(10):
            queue_result_slots = get_api_result("queue")["queue"]["slots"]
            # Check if the fetch-request was added to the queue
            if queue_result_slots:
                break
            time.sleep(1)
        else:
            # The loop never stopped, so we fail
            pytest.fail("Did not find the RSS job in the queue")
            return

        # Let's remove this thing
        get_api_result("queue", extra_arguments={"name": "delete", "value": "all"})
        assert len(get_api_result("queue")["queue"]["slots"]) == 0

        # Unpause
        assert get_api_result("resume") == {"status": True}


class TestConfigServers(SABnzbdBaseTest):
    server_name = "_SeleniumServer"

    def open_config_servers(self):
        # Test if base page works
        self.open_page("http://%s:%s/sabnzbd/config/server" % (SAB_HOST, SAB_PORT))
        self.scroll_to_top()

        # Show advanced options
        advanced_btn = self.selenium_wrapper(self.driver.find_element, By.NAME, "advanced-settings-button")
        if not advanced_btn.get_attribute("checked"):
            advanced_btn.click()

    def add_test_server(self):
        # Add server
        self.selenium_wrapper(self.driver.find_element, By.ID, "addServerButton").click()
        host_inp = self.selenium_wrapper(self.driver.find_element, By.NAME, "host")
        host_inp.clear()
        host_inp.send_keys(SAB_NEWSSERVER_HOST)

        # Change port
        port_inp = self.selenium_wrapper(self.driver.find_element, By.NAME, "port")
        port_inp.clear()
        port_inp.send_keys(SAB_NEWSSERVER_PORT)

        # Disable SSL for testing
        self.selenium_wrapper(self.driver.find_element, By.NAME, "ssl").click()

        # Test server-check
        self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, "#addServerContent .testServer").click()
        self.wait_for_ajax()
        check_result = self.selenium_wrapper(
            self.driver.find_element, By.CSS_SELECTOR, "#addServerContent .result-box"
        ).text
        assert "Connection Successful" in check_result

        # Set test-servername
        self.selenium_wrapper(self.driver.find_element, By.ID, "displayname").send_keys(self.server_name)

        # Add and show details
        port_inp.send_keys(Keys.RETURN)
        time.sleep(1)
        if not self.selenium_wrapper(self.driver.find_element, By.ID, "host0").is_displayed():
            self.selenium_wrapper(self.driver.find_element, By.CLASS_NAME, "showserver").click()

    def remove_server(self):
        # Remove the first server and accept the confirmation
        self.selenium_wrapper(self.driver.find_element, By.CLASS_NAME, "delServer").click()
        self.driver.switch_to.alert.accept()

        # Check that it's gone
        time.sleep(2)
        assert self.server_name not in self.driver.page_source

    def test_add_and_remove_server(self):
        self.open_config_servers()
        self.add_test_server()
        self.remove_server()
