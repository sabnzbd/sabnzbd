#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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
import sys
from sabnzbd.notifier import send_apprise, NOTIFICATION_TYPES
from unittest import mock

if sys.version_info[0] == 3 and sys.version_info[1] < 11:

    class TestNotifier:

        @mock.patch("sabnzbd.notifier.get_target")
        @mock.patch("sabnzbd.DIR_PROG")
        @mock.patch("apprise.Apprise.notify")
        @mock.patch("apprise.Apprise.add")
        @mock.patch("sabnzbd.cfg.apprise_urls")
        def test_send_apprise_notification(self, mock_urls, mock_add, mock_notify, mock_sabdir, mock_get_target):
            """
            Test send_apprise() outside of threading call to verify it handles requests properly
            """

            #
            # Underlining Notifier functions that should be tested in another unit test
            #
            mock_get_target.return_value = True

            #
            # Mocks below pertain to testing
            #

            # Asset just needs to be anything at all
            mock_sabdir.return_value = "/tmp"
            mock_notify.return_value = True
            mock_urls.return_value = [
                "json://localhost",
                "xml://localhost",
                "pbul://credentials",
            ]

            for t in NOTIFICATION_TYPES.keys():
                mock_notify.reset_mock()
                mock_add.reset_mock()
                assert send_apprise("title", "body", t) == ""
                assert mock_notify.call_count == 1
                mock_add.assert_called_once_with(mock_urls.return_value)

            # Garbage in, get's garbage out
            mock_notify.reset_mock()
            mock_add.reset_mock()
            assert send_apprise("title", "body", "garbage_type") != ""
            assert mock_notify.call_count == 0
            mock_add.assert_called_once_with(mock_urls.return_value)

            # No URLs defined
            mock_urls.return_value = []
            assert send_apprise("title", "body", "other") == ""

            # Special Targets
            mock_notify.reset_mock()
            mock_add.reset_mock()
            mock_get_target.return_value = "xml://localhost"
            assert send_apprise("title", "body", "other") == ""
            assert mock_notify.call_count == 1
            # Target value over-rides; this tests that a user can provide
            # over-rides to the Apprise URLs
            mock_add.assert_called_once_with(mock_get_target.return_value)

            # Test other exception handlings
            mock_notify.return_value = None
            mock_notify.side_effect = AttributeError
            mock_notify.reset_mock()
            mock_add.reset_mock()
            # A non-string is returned
            assert send_apprise("title", "body", "other") != ""
            assert mock_notify.call_count == 1

            # Handle case where get_target() returns False (hence it failed for whatever reason)
            mock_notify.return_value = True
            mock_notify.side_effect = None
            mock_get_target.return_value = False
            mock_notify.reset_mock()
            mock_add.reset_mock()
            # Nothing notified
            assert send_apprise("title", "body", "other") == ""
            assert mock_notify.call_count == 0
            assert mock_add.call_count == 0

else:

    class TestNotifier:

        @mock.patch("sabnzbd.notifier.get_target")
        @mock.patch("sabnzbd.DIR_PROG")
        @mock.patch("apprise.Apprise.Apprise.notify")
        @mock.patch("apprise.Apprise.Apprise.add")
        @mock.patch("sabnzbd.cfg.apprise_urls")
        def test_send_apprise_notification(self, mock_urls, mock_add, mock_notify, mock_sabdir, mock_get_target):
            """
            Test send_apprise() outside of threading call to verify it handles requests properly
            """

            #
            # Underlining Notifier functions that should be tested in another unit test
            #
            mock_get_target.return_value = True

            #
            # Mocks below pertain to testing
            #

            # Asset just needs to be anything at all
            mock_sabdir.return_value = "/tmp"
            mock_notify.return_value = True
            mock_urls.return_value = [
                "json://localhost",
                "xml://localhost",
                "pbul://credentials",
            ]

            for t in NOTIFICATION_TYPES.keys():
                mock_notify.reset_mock()
                mock_add.reset_mock()
                assert send_apprise("title", "body", t) == ""
                assert mock_notify.call_count == 1
                mock_add.assert_called_once_with(mock_urls.return_value)

            # Garbage in, get's garbage out
            mock_notify.reset_mock()
            mock_add.reset_mock()
            assert send_apprise("title", "body", "garbage_type") != ""
            assert mock_notify.call_count == 0
            mock_add.assert_called_once_with(mock_urls.return_value)

            # No URLs defined
            mock_urls.return_value = []
            assert send_apprise("title", "body", "other") == ""

            # Special Targets
            mock_notify.reset_mock()
            mock_add.reset_mock()
            mock_get_target.return_value = "xml://localhost"
            assert send_apprise("title", "body", "other") == ""
            assert mock_notify.call_count == 1
            # Target value over-rides; this tests that a user can provide
            # over-rides to the Apprise URLs
            mock_add.assert_called_once_with(mock_get_target.return_value)

            # Test other exception handlings
            mock_notify.return_value = None
            mock_notify.side_effect = AttributeError
            mock_notify.reset_mock()
            mock_add.reset_mock()
            # A non-string is returned
            assert send_apprise("title", "body", "other") != ""
            assert mock_notify.call_count == 1

            # Handle case where get_target() returns False (hence it failed for whatever reason)
            mock_notify.return_value = True
            mock_notify.side_effect = None
            mock_get_target.return_value = False
            mock_notify.reset_mock()
            mock_add.reset_mock()
            # Nothing notified
            assert send_apprise("title", "body", "other") == ""
            assert mock_notify.call_count == 0
            assert mock_add.call_count == 0
