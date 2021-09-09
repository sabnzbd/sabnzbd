#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
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
tests.test_urlgrabber - Testing functions in urlgrabber.py
"""
import json
import urllib.error
import urllib.parse

import pytest_httpbin

import sabnzbd.urlgrabber as urlgrabber
import sabnzbd.version
from sabnzbd.cfg import selftest_host
from tests.testhelper import *


@pytest_httpbin.use_class_based_httpbin
class TestBuildRequest:
    def test_empty(self):
        with pytest.raises(ValueError):
            urlgrabber._build_request(None)
        with pytest.raises(ValueError):
            urlgrabber._build_request("")

    @staticmethod
    def _runner(test_url, exp_code=None, return_body=False):
        """
        Generic test runner for _build_request().

        Arguments:
            str test_url: complete URL, including scheme, user:pass, and query.
            int exp_code: the HTTP status code expected from the web server.
            bool return_body: whether to return the body of the server reply.

        Returns: (str) response body as utf-8 text or None
        """
        with urlgrabber._build_request(test_url) as r:
            assert r is not None
            if exp_code:
                assert r.code == exp_code
            t = urllib.parse.urlparse(test_url)
            u = urllib.parse.urlparse(r.geturl())

            # Verify user:pass was not included in the URL (should only be sent via HTTP Basic Auth)
            if t.username is not None or t.password is not None:
                if t.username:
                    assert t.username not in u.netloc
                if t.password:
                    assert t.password not in u.netloc

            # Check path, params, query and fragment match for test_url and request
            assert t.path.lstrip("/") == u.path.lstrip("/")  # Account for urllib's handling of that slash
            assert t.params == u.params
            assert t.query == u.query
            assert t.fragment == u.fragment

            if return_body:
                return r.read().decode("utf-8")

    @staticmethod
    def _check_auth(headers):
        # Ensure the Authorization header was *not* send with the HTTP request
        json_headers = json.loads(headers.lower())
        assert "authorization" not in json_headers["headers"].keys()

    def test_http_basic(self):
        # Use selftest_host for the most basic URL
        self._runner("http://" + selftest_host(), 200)
        # Repeat with httpbin, which runs on a random non-standard port
        self._runner(self.httpbin.url, 200)

    def test_https_basic(self):
        # Use a real HTTPS server; httpbin_secure uses a self-signed cert
        self._runner("https://" + selftest_host(), 200)
        # Repeat with the port explicitly specified
        self._runner("https://" + selftest_host() + ":443/", 200)

    def test_http_code(self):
        # Make the server reply with a non-standard status code
        self._runner(self.httpbin.url + "/status/242", 242)

    def test_user_agent(self):
        # Verify the User-Agent string
        assert ("SABnzbd/%s" % sabnzbd.__version__) in self._runner(self.httpbin.url + "/user-agent", 200, True)

    def test_http_userpass(self):
        usr = "abcdefghijklm01234"
        pwd = "56789nopqrstuvwxyz"
        common = "@" + self.httpbin.host + ":" + str(self.httpbin.port) + "/basic-auth/" + usr + "/" + pwd
        self._runner("http://" + usr + ":" + pwd + common, 200)
        with pytest.raises(urllib.error.HTTPError):
            # Authorisation should fail
            self._runner("http://totally:wrong" + common, 401)

    def test_http_userpass_email(self):
        for usr, pwd in [("nobody@example.org", "secret!"), ("USER", "P@SS"), ("a@B.cd", "e@F.gh")]:
            host = "http://" + usr + ":" + pwd + "@" + self.httpbin.host + ":" + str(self.httpbin.port)
            self._runner(host + "/basic-auth/" + usr + "/" + pwd, 200)

    def test_http_userpass_non_ascii(self):
        usr = "유즈넷"
        pwd = "َอักษรไทย"
        host = "http://" + usr + ":" + pwd + "@" + self.httpbin.host + ":" + str(self.httpbin.port)
        path = "/basic-auth/" + urllib.parse.quote(usr) + "/" + urllib.parse.quote(pwd)
        self._runner(host + path, 200)

    def test_http_user_only(self):
        h = self._runner("http://root@" + self.httpbin.host + ":" + str(self.httpbin.port) + "/headers", 200, True)
        self._check_auth(h)

    def test_http_pass_only(self):
        h = self._runner("http://:pass@" + self.httpbin.host + ":" + str(self.httpbin.port) + "/headers", 200, True)
        self._check_auth(h)

    def test_http_userpass_empty(self):
        # Add colon and at-sign but no username or password
        host = "http://:@" + self.httpbin.host + ":" + str(self.httpbin.port)
        h = self._runner(host + "/headers", 200, True)
        self._check_auth(h)

    def test_http_params_etc(self):
        self._runner(self.httpbin.url + "/anything/test/this.html?urlgrabber=test#says_hi", 200)
        # Add all possible elements, even unnecessary authorisation parameters
        host = "http://abcdefghijklm:nopqrstuvwxyz@" + self.httpbin.host + ":" + str(self.httpbin.port)
        path = "/anything/goes/even/params.like;this?testing=urlgrabber&more=tests#longpath"
        self._runner(host + path, 200)

    def test_http_invalid_hostname(self):
        with pytest.raises(urllib.error.URLError):
            self._runner("http://sabnzbd.invalid")

    def test_http_no_hostname(self):
        with pytest.raises(urllib.error.URLError):
            self._runner("http://foo:bar@/")

    def test_http_invalid_scheme(self):
        with pytest.raises(urllib.error.URLError):
            self._runner("_://" + self.httpbin.host + ":" + str(self.httpbin.port) + "/")

    def test_http_not_found(self):
        with pytest.raises(urllib.error.HTTPError):
            self._runner(self.httpbin.url + "/status/404", 404)
        with pytest.raises(urllib.error.HTTPError):
            self._runner(self.httpbin.url + "/no/such/file", 404)


class TestFilenameFromDispositionHeader:
    @pytest.mark.parametrize(
        "header, result",
        [
            (
                # In this case the first filename (not the UTF-8 encoded) is parsed.
                "filename=Zombie.Land.Saga.Revenge.S02E12.480p.x264-mSD.nzb; filename*=UTF-8''Zombie.Land.Saga.Revenge.S02E12.480p.x264-mSD-utf.nzb",
                "Zombie.Land.Saga.Revenge.S02E12.480p.x264-mSD.nzb"
            ),
            (
                "filename=Zombie.Land.Saga.Revenge.S02E12.480p.x264-mSD.nzb;",
                "Zombie.Land.Saga.Revenge.S02E12.480p.x264-mSD.nzb"
            ),
            (
                "filename*=UTF-8''Zombie.Land.Saga.Revenge.S02E12.480p.x264-mSD.nzb",
                "Zombie.Land.Saga.Revenge.S02E12.480p.x264-mSD.nzb"
            ),
            (
                "attachment; filename=jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz",
                "jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz"
            ),
            (
                "attachment; filename=\"jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz\"",
                "jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz"
            ),
            (
                "attachment; filename=/what/ever/filename.tar.gz",
                "filename.tar.gz"
            ),
            (
                "attachment; filename=",
                None
            )
        ]
    )
    def test_filename_from_disposition_header(self, header, result):
        """Test the parsing of different disposition-headers."""
        assert urlgrabber.filename_from_content_disposition(header) == result
