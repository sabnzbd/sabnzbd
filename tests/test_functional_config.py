#!/usr/bin/python3 -OO
# Copyright 2007-2019 The SABnzbd-Team <team@sabnzbd.org>
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

from selenium.common.exceptions import NoSuchElementException, UnexpectedAlertPresentException
from tests.testhelper import *


class SABnzbdBasicPagesTest(SABnzbdBaseTest):

    def test_base_pages(self):
        # Quick-check of all Config pages
        test_urls = ['config',
                     'config/server',
                     'config/categories',
                     'config/scheduling',
                     'config/rss']

        for test_url in test_urls:
            self.open_page("http://%s:%s/%s" % (SAB_HOST, SAB_PORT, test_url))

    def test_base_submit_pages(self):
        test_urls_with_submit = ['config/general',
                                 'config/folders',
                                 'config/switches',
                                 'config/sorting',
                                 'config/notify',
                                 'config/special']

        for test_url in test_urls_with_submit:
            self.open_page("http://%s:%s/%s" % (SAB_HOST, SAB_PORT, test_url))

            # Can only click the visible buttons
            submit_btns = self.driver.find_elements_by_class_name('saveButton')
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
                # Ignore restart-request due to empty sabnzbd.ini in tests
                self.driver.switch_to.alert.dismiss()

            # For Specials page we get redirected after save, so check for no crash
            if 'special' in test_url:
                self.no_page_crash()
            else:
                # For others if all is fine, button will be back to normal in 1 second
                time.sleep(1.0)
                assert submit_btn.text == "Save Changes"


class SABnzbdConfigCategories(SABnzbdBaseTest):

    category_name = "testCat"

    def test_page(self):
        # Test if base page works
        self.open_page("http://%s:%s/sabnzbd/config/categories" % (SAB_HOST, SAB_PORT))

        # Add new category
        self.driver.find_elements_by_name("newname")[1].send_keys("testCat")
        self.driver.find_element_by_xpath("//button/text()[normalize-space(.)='Add']/parent::*").click()
        self.no_page_crash()
        self.assertNotIn(self.category_name, self.driver.page_source)


@pytest.mark.skipif("SAB_NEWSSERVER_HOST" not in os.environ, reason="Test-server not specified")
class SABnzbdConfigServers(SABnzbdBaseTest):

    server_name = "_SeleniumServer"

    def open_config_servers(self):
        # Test if base page works
        self.open_page("http://%s:%s/sabnzbd/config/server" % (SAB_HOST, SAB_PORT))
        self.scroll_to_top()

        # Show advanced options
        advanced_btn = self.driver.find_element_by_name("advanced-settings-button")
        if not advanced_btn.get_attribute('checked'):
            advanced_btn.click()

    def add_test_server(self):
        # Add server
        self.driver.find_element_by_id("addServerButton").click()
        host_inp = self.driver.find_element_by_name("host")
        host_inp.clear()
        host_inp.send_keys(self.newsserver_host)
        username_imp = self.driver.find_element_by_css_selector("#addServerContent input[data-hide='username']")
        username_imp.clear()
        username_imp.send_keys(self.newsserver_user)
        pass_inp = self.driver.find_element_by_css_selector("#addServerContent input[data-hide='password']")
        pass_inp.clear()
        pass_inp.send_keys(self.newsserver_password)

        # With SSL
        ssl_imp = self.driver.find_element_by_name("ssl")
        if not ssl_imp.get_attribute('checked'):
            ssl_imp.click()

        # Check that we filled the right port automatically
        self.assertEqual(self.driver.find_element_by_id("port").get_attribute('value'), '563')

        # Test server-check
        self.driver.find_element_by_css_selector("#addServerContent .testServer").click()
        self.wait_for_ajax()
        self.assertIn("Connection Successful", self.driver.find_element_by_css_selector('#addServerContent .result-box').text)

        # Set test-servername
        self.driver.find_element_by_id("displayname").send_keys(self.server_name)

        # Add and show details
        pass_inp.send_keys(Keys.RETURN)
        time.sleep(1)
        if not self.driver.find_element_by_id("host0").is_displayed():
            self.driver.find_element_by_class_name("showserver").click()

    def remove_server(self):
        # Remove the first server and accept the confirmation
        self.driver.find_element_by_class_name("delServer").click()
        self.driver.switch_to.alert.accept()

        # Check that it's gone
        time.sleep(2)
        self.assertNotIn(self.server_name, self.driver.page_source)

    def test_add_and_remove_server(self):
        self.open_config_servers()
        self.add_test_server()
        self.remove_server()

    def test_empty_bad_password(self):
        self.open_config_servers()
        self.add_test_server()

        # Test server-check with empty password
        pass_inp = self.driver.find_elements_by_css_selector("input[data-hide='password']")[1]
        pass_inp.clear()
        self.driver.find_elements_by_css_selector(".testServer")[1].click()
        self.wait_for_ajax()
        check_result = self.driver.find_elements_by_css_selector('.result-box')[1].text.lower()
        assert "authentication failed" in check_result or "invalid username or password" in check_result

        # Test server-check with bad password
        pass_inp.send_keys("bad")
        self.driver.find_elements_by_css_selector(".testServer")[1].click()
        self.wait_for_ajax()
        assert "authentication failed" in check_result or "invalid username or password" in check_result

        # Finish
        self.remove_server()
