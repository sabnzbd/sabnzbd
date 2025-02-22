#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
tests.test_notifier - Testing notification functionality
"""
import re
from sabnzbd.notifier import send_notification, send_apprise, NOTIFICATION_TYPES
from unittest import mock, TestCase
import sabnzbd.cfg as cfg
from sabnzbd.config import Option
from importlib import reload


class TestNotifier(TestCase):

    @classmethod
    def setUpClass(self):
        # hack since test_misc uses @set_config decorator eliminating all of the default configuration
        # We want to test with the default configuration in place; This safely resets all fields and
        # replaces them correctly in memory
        reload(cfg)

        # capture state of config so we can reverse it
        self._saved_cfg = {}
        for attr in dir(cfg):
            if isinstance(getattr(cfg, attr), Option):
                # Backup configuration as it was before entering this test object
                self._saved_cfg[attr] = getattr(cfg, attr).get()
                # Set our value to be a default
                getattr(cfg, attr).set(getattr(cfg, attr).default)

    @classmethod
    def setUp(self):
        # Enforce our default values associated with the class
        for attr in dir(cfg):
            if isinstance(getattr(cfg, attr), Option):
                getattr(cfg, attr).set(getattr(cfg, attr).default)

    @classmethod
    def tearDownClass(self):
        # rollback our assignments to be as they were
        for k, v in self._saved_cfg.items():
            getattr(cfg, k).set(v)

    @mock.patch("sabnzbd.DIR_PROG")
    @mock.patch("apprise.Apprise.notify")
    @mock.patch("apprise.Apprise.add")
    def test_send_apprise_notification(self, mock_add, mock_notify, mock_sabdir):
        """
        Test send_apprise() outside of threading call to verify it handles requests properly
        """

        #
        # Mocks below pertain to testing
        #

        # Asset just needs to be anything at all
        mock_sabdir.return_value = "/tmp"
        cfg.apprise_enable.set(True)
        urls = ", ".join(
            [
                "json://localhost",
                "xml://localhost",
                "pbul://credentials",
            ]
        )
        cfg.apprise_urls.set(urls)
        mock_notify.return_value = True

        # Startup is disabled by default
        assert send_apprise("title", "body", "startup") == ""
        assert mock_notify.call_count == 0
        mock_notify.reset_mock()
        mock_add.reset_mock()

        cfg.apprise_target_startup_enable.set(True)
        assert send_apprise("title", "body", "startup") == ""
        assert mock_notify.call_count == 1
        mock_add.assert_called_once_with(urls)
        mock_notify.reset_mock()
        mock_add.reset_mock()

        for attr in dir(cfg):
            # Enable all of our apprise attributes
            if isinstance(getattr(cfg, attr), Option) and re.match("^apprise_target_.+_enable$", attr):
                getattr(cfg, attr).set(True)

        for t in NOTIFICATION_TYPES.keys():
            mock_notify.reset_mock()
            mock_add.reset_mock()
            assert send_apprise("title", "body", t) == ""
            assert mock_notify.call_count == 1
            assert mock_add.call_count == 1
            mock_add.assert_called_once_with(urls)

        # Garbage in, get's garbage out
        mock_notify.reset_mock()
        mock_add.reset_mock()
        assert send_apprise("title", "body", "garbage_type") == ""
        # Nothing sent
        assert mock_notify.call_count == 0
        assert mock_add.call_count == 0

        # No URLs defined
        cfg.apprise_urls.set("")
        mock_notify.reset_mock()
        mock_add.reset_mock()
        assert send_apprise("title", "body", "other") == ""
        assert mock_notify.call_count == 0
        assert mock_add.call_count == 0

        # Special Targets
        mock_notify.reset_mock()
        mock_add.reset_mock()
        cfg.apprise_target_other.set("xml://custom/other")
        assert send_apprise("title", "body", "other") == ""
        assert mock_notify.call_count == 1
        assert mock_add.call_count == 1
        # Target value over-rides; this tests that a user can provide
        # over-rides to the Apprise URLs
        mock_add.assert_called_once_with("xml://custom/other")

        # Over-ride is still set even if general URLS are provided
        cfg.apprise_urls.set(urls)
        mock_notify.reset_mock()
        mock_add.reset_mock()
        assert send_apprise("title", "body", "other") == ""
        assert mock_notify.call_count == 1
        assert mock_add.call_count == 1
        # Target value over-rides; this tests that a user can provide
        # over-rides to the Apprise URLs
        mock_add.assert_called_once_with("xml://custom/other")

        # Test case where notify() fails
        mock_notify.return_value = False
        mock_notify.reset_mock()
        mock_add.reset_mock()
        # A non-string is returned
        assert send_apprise("title", "body", "other") != ""
        assert mock_notify.call_count == 1
        assert mock_add.call_count == 1

        # Test other exception handlings
        mock_notify.return_value = None
        mock_notify.side_effect = AttributeError
        mock_notify.reset_mock()
        mock_add.reset_mock()
        # A non-string is returned
        assert send_apprise("title", "body", "other") != ""
        assert mock_notify.call_count == 1
        assert mock_add.call_count == 1

        # Test Mode
        # Return the status to being a proper return value
        mock_notify.return_value = True
        mock_notify.side_effect = None
        mock_notify.reset_mock()
        mock_add.reset_mock()
        # Download is enabled by default; set Test flag
        assert send_apprise("title", "body", "download", test={"apprise_urls": urls}) == ""
        assert mock_notify.call_count == 1
        assert mock_add.call_count == 1
        mock_add.assert_called_once_with(urls)

    @mock.patch("threading.Thread.start")
    def test_send_notification_as_apprise(self, mock_thread):
        """
        Test send_apprise() inside it's threaded check environment
        """

        # Set up our config the way we want it
        cfg.apprise_enable.set(True)
        cfg.apprise_urls.set("okay://")

        # startup is disabled by default
        assert not cfg.apprise_target_startup_enable.get()
        send_notification("title", "body", "startup")
        assert mock_thread.call_count == 0
        mock_thread.reset_mock()

        cfg.apprise_target_startup_enable.set(True)
        assert cfg.apprise_target_startup_enable.get()
        send_notification("title", "body", "startup")
        assert mock_thread.call_count == 1
        mock_thread.reset_mock()
