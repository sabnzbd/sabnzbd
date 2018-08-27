#!/usr/bin/python -OO
# Copyright 2007-2018 The SABnzbd-Team <team@sabnzbd.org>
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
tests.test_functional - The most basic testing if things work
"""

import unittest
import random

from selenium import webdriver
from selenium.common.exceptions import WebDriverException, NoSuchElementException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.keys import Keys

from testhelper import *


class SABnzbdBaseTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # We try Chrome, fallback to Firefox

        try:
            driver_options = ChromeOptions()
            # Headless on Appveyor/Travis
            if "CI" in os.environ:
                driver_options.add_argument("--headless")
                driver_options.add_argument("--no-sandbox")
            cls.driver = webdriver.Chrome(chrome_options=driver_options)
        except WebDriverException:
            driver_options = FirefoxOptions()
            # Headless on Appveyor/Travis
            if "CI" in os.environ:
                driver_options.headless = True
            cls.driver = webdriver.Firefox(firefox_options=driver_options)

        # Get the newsserver-info
        cls.newsserver_host = os.environ['SAB_NEWSSERVER_HOST']
        cls.newsserver_user = os.environ['SAB_NEWSSERVER_USER']
        cls.newsserver_password = os.environ['SAB_NEWSSERVER_PASSWORD']

    @classmethod
    def tearDownClass(cls):
        cls.driver.close()
        cls.driver.quit()

    def scroll_to_top(self):
        self.driver.find_element_by_tag_name('body').send_keys(Keys.CONTROL + Keys.HOME)
        time.sleep(2)

    def wait_for_ajax(self):
        wait = WebDriverWait(self.driver, 15)
        try:
            wait.until(lambda driver: self.driver.execute_script('return jQuery.active') == 0)
            wait.until(lambda driver: self.driver.execute_script('return document.readyState') == 'complete')
        except Exception:
            pass

    def no_page_crash(self):
        # Do a base test if CherryPy did not report test
        self.assertNotIn('500 Internal Server Error', self.driver.title)


class SABnzbdHappyFlow(SABnzbdBaseTest):

    def test_happy_flow(self):
        # So it get's executed in the right order
        self.start_wizard()
        self.add_nzb_from_url()

    def start_wizard(self):
        # Language-selection
        self.driver.get("http://%s:%s/sabnzbd/wizard/" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()
        self.driver.find_element_by_id("en").click()
        self.driver.find_element_by_css_selector('.btn.btn-default').click()

        # Fill server-info
        self.no_page_crash()
        host_inp = self.driver.find_element_by_name("host")
        host_inp.clear()
        host_inp.send_keys(self.newsserver_host)
        username_imp = self.driver.find_element_by_name("username")
        username_imp.clear()
        username_imp.send_keys(self.newsserver_user)
        pass_inp = self.driver.find_element_by_name("password")
        pass_inp.clear()
        pass_inp.send_keys(self.newsserver_password)

        # With SSL
        ssl_imp = self.driver.find_element_by_name("ssl")
        if not ssl_imp.get_attribute('checked'):
            ssl_imp.click()

        # Test server-check
        self.driver.find_element_by_id("serverTest").click()
        self.wait_for_ajax()
        self.assertIn("Connection Successful", self.driver.find_element_by_id("serverResponse").text)

        # Final page done
        self.driver.find_element_by_id("next-button").click()
        self.no_page_crash()
        self.assertIn("http://%s:%s/sabnzbd" % (SAB_HOST, SAB_PORT), self.driver.find_element_by_class_name("quoteBlock").text)

        # Go to SAB!
        self.driver.find_element_by_css_selector('.btn.btn-success').click()
        self.no_page_crash()

    def add_nzb_from_url(self):
        test_job_name = 'basic_rar5_%s' % random.randint(500, 1000)

        self.driver.get("http://%s:%s/sabnzbd/" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()

        # Wait for modal to open, add URL
        self.driver.find_element_by_css_selector('a[href="#modal-add-nzb"]').click()
        time.sleep(1)
        self.driver.find_element_by_name("nzbURL").send_keys("http://sabnzbd.org/tests/basic_rar5.nzb")
        self.driver.find_element_by_name("nzbname").send_keys(test_job_name)
        self.driver.find_element_by_css_selector('form[data-bind="submit: addNZBFromURL"] input[type="submit"]').click()

        # We wait for 30 seconds to let it complete
        for x in range(30):
            try:
                # Locate resulting row
                result_row = self.driver.find_element_by_xpath('//*[@id="history-tab"]//tr[td//text()[contains(., "%s")]]' % test_job_name)
                # Did it complete?
                if result_row.find_element_by_css_selector('td.status').text == 'Completed':
                    break
                else:
                    time.sleep(1)
            except NoSuchElementException:
                time.sleep(1)
                pass
        else:
            self.fail("Download did not complete")

        # Check if the file exists on disk
        self.assertTrue(os.path.exists(os.path.join(SAB_COMPLETE_DIR, test_job_name, 'testfile.bin')))


class SABnzbdConfigStart(SABnzbdBaseTest):

    def test_page(self):
        # Test if base page works
        self.driver.get("http://%s:%s/sabnzbd/config/" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()


class SABnzbdConfigGeneral(SABnzbdBaseTest):

    def test_page(self):
        # Test if base page works
        self.driver.get("http://%s:%s/sabnzbd/config/general" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()


class SABnzbdConfigFolders(SABnzbdBaseTest):

    def test_page(self):
        # Test if base page works
        self.driver.get("http://%s:%s/sabnzbd/config/folders" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()


class SABnzbdConfigServers(SABnzbdBaseTest):

    server_name = "_SeleniumServer"

    def open_config_servers(self):
        # Test if base page works
        self.driver.get("http://%s:%s/sabnzbd/config/server" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()
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
        self.assertTrue("authentication failed" in check_result or "invalid username or password" in check_result)

        # Test server-check with bad password
        pass_inp.send_keys("bad")
        self.driver.find_elements_by_css_selector(".testServer")[1].click()
        self.wait_for_ajax()
        self.assertTrue("authentication failed" in check_result or "invalid username or password" in check_result)

        # Finish
        self.remove_server()


class SABnzbdConfigCategories(SABnzbdBaseTest):

    category_name = "testCat"

    def test_page(self):
        # Test if base page works
        self.driver.get("http://%s:%s/sabnzbd/config/categories" % (SAB_HOST, SAB_PORT))

        # Add new category
        self.driver.find_elements_by_name("newname")[1].send_keys("testCat")
        self.driver.find_element_by_xpath("//button/text()[normalize-space(.)='Add']/parent::*").click()
        self.no_page_crash()
        self.assertNotIn(self.category_name, self.driver.page_source)


class SABnzbdConfigSwitches(SABnzbdBaseTest):

    def test_page(self):
        # Test if base page works
        self.driver.get("http://%s:%s/sabnzbd/config/switches" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()


class SABnzbdConfigSorting(SABnzbdBaseTest):

    def test_page(self):
        # Test if base page works
        self.driver.get("http://%s:%s/sabnzbd/config/sorting" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()


class SABnzbdConfigNotifications(SABnzbdBaseTest):

    def test_page(self):
        # Test if base page works
        self.driver.get("http://%s:%s/sabnzbd/config/notify" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()


class SABnzbdConfigScheduling(SABnzbdBaseTest):

    def test_page(self):
        # Test if base page works
        self.driver.get("http://%s:%s/sabnzbd/config/scheduling" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()


class SABnzbdConfigRSS(SABnzbdBaseTest):

    def test_page(self):
        # Test if base page works
        self.driver.get("http://%s:%s/sabnzbd/config/rss" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()


class SABnzbdConfigSpecials(SABnzbdBaseTest):

    def test_page(self):
        # Test if base page works
        self.driver.get("http://%s:%s/sabnzbd/config/special" % (SAB_HOST, SAB_PORT))
        self.no_page_crash()


if __name__ == "__main__":
    unittest.main(failfast=True)
