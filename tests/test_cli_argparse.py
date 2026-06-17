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

"""Tests for SABnzbd CLI argument parsing (argparse migration)."""

from unittest import mock

import argparse
import pytest

import sabnzbd
from SABnzbd import build_parser


@pytest.fixture(autouse=True)
def _mock_sabnzbd_env(monkeypatch):
    """Set sabnzbd module state for CLI tests."""
    monkeypatch.setattr(sabnzbd, "MY_NAME", "SABnzbd")
    monkeypatch.setattr(sabnzbd, "__version__", "4.0.0")
    monkeypatch.setattr(sabnzbd, "WINDOWS", False)


class TestBuildParser:
    """Tests for build_parser()."""

    def test_parser_returns_argument_parser(self):
        parser = build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_boolean_flags(self):
        parser = build_parser()
        for flag in [
            "--daemon",
            "--nobrowser",
            "--clean",
            "--weblogging",
            "--pause",
            "--no-login",
            "--log-all",
            "--disable-file-log",
            "--console",
            "--new",
            "--autorestarted",
            "--repair",
            "--repair-all",
        ]:
            opts = parser.parse_args([flag])
            attr = flag.lstrip("-").replace("-", "_")
            assert getattr(opts, attr) is True, f"{flag} should be True"

    def test_short_boolean_flags(self):
        parser = build_parser()
        for short, attr in [
            ("-d", "daemon"),
            ("-n", "nobrowser"),
            ("-c", "clean"),
            ("-w", "weblogging"),
            ("-p", "pause"),
        ]:
            opts = parser.parse_args([short])
            assert getattr(opts, attr) is True, f"{short} should set {attr}"

    def test_config_file_option(self):
        parser = build_parser()
        opts = parser.parse_args(["-f", "/tmp/test.ini"])
        assert opts.config_file == "/tmp/test.ini"

    def test_config_file_long_option(self):
        parser = build_parser()
        opts = parser.parse_args(["--config-file", "/tmp/test.ini"])
        assert opts.config_file == "/tmp/test.ini"

    def test_config_file_alias(self):
        parser = build_parser()
        opts = parser.parse_args(["--config", "/tmp/test.ini"])
        assert opts.config_file == "/tmp/test.ini"

    def test_server_option(self):
        parser = build_parser()
        opts = parser.parse_args(["-s", "0.0.0.0:8080"])
        assert opts.server == "0.0.0.0:8080"

    def test_templates_option(self):
        parser = build_parser()
        opts = parser.parse_args(["-t", "/my/templates"])
        assert opts.templates == "/my/templates"

    def test_logging_valid_range(self):
        parser = build_parser()
        for level in (-1, 0, 1, 2):
            processed = ["--logging=%d" % level]
            opts = parser.parse_args(processed)
            assert opts.logging == level

    def test_logging_invalid_range(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--logging=3"])

    def test_logging_invalid_negative(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--logging=-5"])

    def test_browser_option(self):
        parser = build_parser()
        opts = parser.parse_args(["-b", "1"])
        assert opts.browser == 1

    def test_browser_off(self):
        parser = build_parser()
        opts = parser.parse_args(["-b", "0"])
        assert opts.browser == 0

    def test_https_port(self):
        parser = build_parser()
        opts = parser.parse_args(["--https", "9090"])
        assert opts.https == 9090

    def test_ipv6_hosting(self):
        parser = build_parser()
        opts = parser.parse_args(["--ipv6_hosting", "1"])
        assert opts.ipv6_hosting == 1

    def test_ipv6_alias(self):
        parser = build_parser()
        opts = parser.parse_args(["--ipv6", "1"])
        assert opts.ipv6_hosting == 1

    def test_inet_exposure_valid(self):
        parser = build_parser()
        for level in range(6):
            opts = parser.parse_args(["--inet_exposure", str(level)])
            assert opts.inet_exposure == level

    def test_inet_exposure_invalid(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--inet_exposure", "6"])

    def test_inet_alias(self):
        parser = build_parser()
        opts = parser.parse_args(["--inet", "3"])
        assert opts.inet_exposure == 3

    def test_disable_file_log_alias(self):
        parser = build_parser()
        opts = parser.parse_args(["--disable"])
        assert opts.disable_file_log is True

    def test_pid_option(self):
        parser = build_parser()
        opts = parser.parse_args(["--pid", "/var/run/sabnzbd.pid"])
        assert opts.pid == "/var/run/sabnzbd.pid"

    def test_pidfile_option(self):
        parser = build_parser()
        opts = parser.parse_args(["--pidfile", "/var/run/sabnzbd.pid"])
        assert opts.pidfile == "/var/run/sabnzbd.pid"

    def test_pid_not_on_windows(self, monkeypatch):
        monkeypatch.setattr(sabnzbd, "WINDOWS", True)
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--pid", "/tmp/pid"])

    def test_pidfile_not_on_windows(self, monkeypatch):
        monkeypatch.setattr(sabnzbd, "WINDOWS", True)
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--pidfile", "/tmp/pid"])

    def test_nzb_files_as_remaining_args(self):
        parser = build_parser()
        opts = parser.parse_args(["movie.nzb", "album.nzb"])
        assert opts.args == ["movie.nzb", "album.nzb"]

    def test_mixed_flags_and_nzb_files(self):
        parser = build_parser()
        opts = parser.parse_args(["-d", "-c", "movie.nzb"])
        assert opts.daemon is True
        assert opts.clean is True
        assert opts.args == ["movie.nzb"]

    def test_win32_service_options_hidden(self):
        parser = build_parser()
        opts = parser.parse_args(["--password", "secret", "--username", "admin"])
        assert opts.password == "secret"
        assert opts.username == "admin"

    def test_version_flag(self):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_help_flag(self, capsys):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "config-file" in captured.out.lower() or "config" in captured.out.lower()

    def test_no_args_defaults(self):
        parser = build_parser()
        opts = parser.parse_args([])
        assert opts.config_file is None
        assert opts.server is None
        assert opts.logging is None
        assert opts.https is None
        assert opts.daemon is False
        assert opts.clean is False


class TestCommandlineHandler:
    """Tests for commandline_handler()."""

    def _run_handler(self, args):
        from SABnzbd import commandline_handler

        with mock.patch("sys.argv", ["SABnzbd", *args]):
            return commandline_handler()

    def test_simple_flags(self):
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(["-d", "-c", "-p"])
        assert opts.daemon is True
        assert opts.clean is True
        assert opts.pause is True

    def test_config_file(self):
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(["-f", "/tmp/test.ini"])
        assert opts.config_file == "/tmp/test.ini"

    def test_server_option(self):
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(["-s", "0.0.0.0:8080"])
        assert opts.server == "0.0.0.0:8080"

    def test_nzb_files_collected(self):
        _service, _opts, _serv_opts, upload_nzbs = self._run_handler(["movie.nzb", "album.nzb"])
        assert len(upload_nzbs) == 2
        assert any("movie.nzb" in f for f in upload_nzbs)
        assert any("album.nzb" in f for f in upload_nzbs)

    def test_nzb_with_flags(self):
        _service, opts, _serv_opts, upload_nzbs = self._run_handler(["-d", "movie.nzb"])
        assert opts.daemon is True
        assert len(upload_nzbs) == 1

    def test_invalid_logging_exits(self):
        with pytest.raises(SystemExit):
            self._run_handler(["-l", "5"])

    def test_logging_negative_works(self):
        """Verify -l -1 is handled by pre-processing."""
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(["-l", "-1"])
        assert opts.logging == -1

    def test_logging_positive_works(self):
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(["-l", "2"])
        assert opts.logging == 2

    def test_invalid_inet_exposure_exits(self):
        with pytest.raises(SystemExit):
            self._run_handler(["--inet_exposure", "10"])

    def test_help_exits(self):
        with pytest.raises(SystemExit):
            self._run_handler(["--help"])

    def test_version_exits(self):
        with pytest.raises(SystemExit):
            self._run_handler(["--version"])

    def test_all_boolean_flags(self):
        args = [
            "--daemon",
            "--nobrowser",
            "--clean",
            "--weblogging",
            "--pause",
            "--no-login",
            "--log-all",
            "--disable-file-log",
            "--console",
            "--new",
            "--repair",
            "--repair-all",
        ]
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(args)
        for attr in [
            "daemon",
            "nobrowser",
            "clean",
            "weblogging",
            "pause",
            "no_login",
            "log_all",
            "disable_file_log",
            "console",
            "new",
            "repair",
            "repair_all",
        ]:
            assert getattr(opts, attr) is True, f"{attr} should be True"

    def test_backward_compat_short_flags(self):
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(["-d", "-c", "-p", "-w", "-n"])
        assert opts.daemon is True
        assert opts.clean is True
        assert opts.pause is True
        assert opts.weblogging is True
        assert opts.nobrowser is True

    def test_backward_compat_config_file_alias(self):
        """--config should work as backward compat for --config-file."""
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(["--config", "/tmp/test.ini"])
        assert opts.config_file == "/tmp/test.ini"

    def test_backward_compat_ipv6_alias(self):
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(["--ipv6", "1"])
        assert opts.ipv6_hosting == 1

    def test_backward_compat_inet_alias(self):
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(["--inet", "3"])
        assert opts.inet_exposure == 3

    def test_backward_compat_disable_alias(self):
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(["--disable"])
        assert opts.disable_file_log is True

    def test_complex_mix(self):
        args = ["-f", "/tmp/test.ini", "-d", "-l", "2", "--https", "9090", "--inet_exposure", "3", "movie.nzb"]
        _service, opts, _serv_opts, upload_nzbs = self._run_handler(args)
        assert opts.config_file == "/tmp/test.ini"
        assert opts.daemon is True
        assert opts.logging == 2
        assert opts.https == 9090
        assert opts.inet_exposure == 3
        assert len(upload_nzbs) == 1

    def test_archives_also_collected(self):
        _service, _opts, _serv_opts, upload_nzbs = self._run_handler(["movie.rar", "album.7z"])
        assert len(upload_nzbs) == 2

    def test_non_nzb_files_not_collected(self):
        _service, _opts, _serv_opts, upload_nzbs = self._run_handler(["readme.txt", "movie.nzb"])
        assert len(upload_nzbs) == 1
        assert any("movie.nzb" in f for f in upload_nzbs)

    def test_wait_option(self):
        _service, opts, _serv_opts, _upload_nzbs = self._run_handler(["--wait", "30"])
        assert opts.wait == "30"
