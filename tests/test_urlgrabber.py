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
tests.test_urlgrabber - Testing functions in urlgrabber.py
"""

import base64

import binascii
import json
import re
import urllib.error
import urllib.parse

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request, Response

import sabnzbd
import sabnzbd.urlgrabber as urlgrabber
import sabnzbd.cfg as cfg


def _json_response(payload, status: int = 200) -> Response:
    return Response(json.dumps(payload), status=status, content_type="application/json")


def _basic_auth_credentials(request: Request):
    """Return the (username, password) of the Basic auth header, or None"""
    scheme, _, payload = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "basic":
        return None
    try:
        # Credentials are sent as utf-8, so they may contain non-ascii characters
        username, _, password = base64.b64decode(payload).decode("utf-8").partition(":")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    return username, password


def _request_handler(request: Request) -> Response:
    """Handle the (subset of the) httpbin endpoints used by the tests below"""
    if request.path.startswith("/status/"):
        return Response(status=int(request.path[len("/status/") :]))

    if request.path == "/user-agent":
        return _json_response({"user-agent": request.headers.get("User-Agent")})

    if request.path.startswith("/basic-auth/"):
        username, _, password = request.path[len("/basic-auth/") :].partition("/")
        if _basic_auth_credentials(request) != (username, password):
            return Response(status=401, headers={"WWW-Authenticate": 'Basic realm="Test"'})
        return _json_response({"authenticated": True, "user": username})

    if request.path in ("/", "/headers") or request.path.startswith("/anything"):
        return _json_response({"headers": dict(request.headers), "url": request.url})

    return Response(status=404)


@pytest.fixture(scope="class")
def local_server(request):
    """Local webserver serving a minimal, httpbin-like API on a random port"""
    server = HTTPServer(host="127.0.0.1")
    server.expect_request(re.compile(r".*")).respond_with_handler(_request_handler)
    server.start()
    request.cls.server = server
    yield
    server.stop()


@pytest.mark.usefixtures("local_server")
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
        self._runner("http://" + cfg.selftest_host(), 200)
        # Repeat with the local server, which runs on a random non-standard port
        self._runner(self.server.url_for("/"), 200)

    def test_https_basic(self):
        # Use a real HTTPS server, since the local server only serves plain HTTP
        self._runner("https://" + cfg.selftest_host(), 200)
        # Repeat with the port explicitly specified
        self._runner("https://" + cfg.selftest_host() + ":443/", 200)

    def test_http_code(self):
        # Make the server reply with a non-standard status code
        self._runner(self.server.url_for("/status/242"), 242)

    def test_user_agent(self):
        # Verify the User-Agent string
        assert ("SABnzbd/%s" % sabnzbd.__version__) in self._runner(self.server.url_for("/user-agent"), 200, True)

    def test_http_userpass(self):
        usr = "abcdefghijklm01234"
        pwd = "56789nopqrstuvwxyz"
        common = "@" + self.server.host + ":" + str(self.server.port) + "/basic-auth/" + usr + "/" + pwd
        self._runner("http://" + usr + ":" + pwd + common, 200)
        with pytest.raises(urllib.error.HTTPError):
            # Authorisation should fail
            self._runner("http://totally:wrong" + common, 401)

    def test_http_userpass_email(self):
        for usr, pwd in [("nobody@example.org", "secret!"), ("USER", "P@SS"), ("a@B.cd", "e@F.gh")]:
            host = "http://" + usr + ":" + pwd + "@" + self.server.host + ":" + str(self.server.port)
            self._runner(host + "/basic-auth/" + usr + "/" + pwd, 200)

    def test_http_userpass_non_ascii(self):
        usr = "유즈넷"
        pwd = "َอักษรไทย"
        host = "http://" + usr + ":" + pwd + "@" + self.server.host + ":" + str(self.server.port)
        path = "/basic-auth/" + urllib.parse.quote(usr) + "/" + urllib.parse.quote(pwd)
        self._runner(host + path, 200)

    def test_http_user_only(self):
        h = self._runner("http://root@" + self.server.host + ":" + str(self.server.port) + "/headers", 200, True)
        self._check_auth(h)

    def test_http_pass_only(self):
        h = self._runner("http://:pass@" + self.server.host + ":" + str(self.server.port) + "/headers", 200, True)
        self._check_auth(h)

    def test_http_userpass_empty(self):
        # Add colon and at-sign but no username or password
        host = "http://:@" + self.server.host + ":" + str(self.server.port)
        h = self._runner(host + "/headers", 200, True)
        self._check_auth(h)

    def test_http_params_etc(self):
        self._runner(self.server.url_for("/anything/test/this.html?urlgrabber=test#says_hi"), 200)
        # Add all possible elements, even unnecessary authorisation parameters
        host = "http://abcdefghijklm:nopqrstuvwxyz@" + self.server.host + ":" + str(self.server.port)
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
            self._runner("_://" + self.server.host + ":" + str(self.server.port) + "/")

    def test_http_not_found(self):
        with pytest.raises(urllib.error.HTTPError):
            self._runner(self.server.url_for("/status/404"), 404)
        with pytest.raises(urllib.error.HTTPError):
            self._runner(self.server.url_for("/no/such/file"), 404)


class TestFilenameFromDispositionHeader:
    @pytest.mark.parametrize(
        "header, result",
        [
            (
                # In this case the first filename (not the UTF-8 encoded) is parsed.
                "attachment; filename=jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz; filename*=UTF-8''jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz",
                "jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz",
            ),
            (
                "filename=jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz;",
                "jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz",
            ),
            (
                "filename*=UTF-8''jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz",
                "jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz",
            ),
            (
                "attachment; filename=jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz",
                "jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz",
            ),
            (
                'attachment; filename="jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz"',
                "jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz",
            ),
            (
                "attachment; filename=/what/ever/filename.tar.gz",
                "filename.tar.gz",
            ),
            (
                "attachment; filename=",
                None,
            ),
        ],
    )
    def test_filename_from_disposition_header(self, header, result):
        """Test the parsing of different disposition-headers."""
        assert urlgrabber.filename_from_content_disposition(header) == result
