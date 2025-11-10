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
sabnzbd.config_migrations - Configuration migration handlers
"""

import logging

import sabnzbd
from sabnzbd.config import get_servers, save_config


class ConfigConverter:
    """Handles configuration migrations between different versions"""

    @staticmethod
    def convert_version_1(
        config_conversion_version,
        auto_sort,
        sorters_converted,
        no_series_dupes,
        no_smart_dupes,
        history_retention,
        host_whitelist,
        cache_limit,
    ):
        """Convert from version 0 to version 1"""
        logging.info("Config conversion set 1")
        # Convert auto-sort
        if auto_sort() == "0":
            auto_sort.set("")
        elif auto_sort() == "1":
            auto_sort.set("avg_age asc")

        # Convert old series/date/movie sorters
        if not sorters_converted():
            sabnzbd.misc.convert_sorter_settings()
            sorters_converted.set(True)

        # Convert duplicate settings
        if no_series_dupes():
            no_smart_dupes.set(no_series_dupes())
            no_series_dupes.set(0)

        # Convert history retention setting
        if history_retention():
            sabnzbd.misc.convert_history_retention()
            history_retention.set("")

        # Add hostname to the whitelist
        if not host_whitelist():
            import socket

            host_whitelist.set(socket.gethostname())

        # Set cache limit for new users
        if not cache_limit():
            cache_limit.set(sabnzbd.misc.get_cache_limit())

        # Done
        config_conversion_version.set(1)

    @staticmethod
    def convert_version_2(config_conversion_version):
        """Convert from version 1 to version 2"""
        # We did not end up applying this conversion, so we skip this conversion_version
        logging.info("Config conversion set 2")
        config_conversion_version.set(2)

    @staticmethod
    def convert_version_3(config_conversion_version, par_option):
        """Convert from version 2 to version 3"""
        logging.info("Config conversion set 3")
        if sabnzbd.WINDOWS and par_option():
            # Just empty it, so we don't pass the wrong parameters
            logging.warning("The par2 application was switched, any custom par2 parameters were removed")
            par_option.set("")

        # Done
        config_conversion_version.set(3)

    @staticmethod
    def convert_version_4(config_conversion_version):
        """Convert from version 3 to version 4"""
        logging.info("Config conversion set 4")

        all_servers = get_servers()
        for server in all_servers:
            if all_servers[server].ssl_verify() == 2:
                all_servers[server].ssl_verify.set(3)

        # Done
        config_conversion_version.set(4)

    @staticmethod
    def run_all_conversions(
        config_conversion_version,
        auto_sort,
        sorters_converted,
        no_series_dupes,
        no_smart_dupes,
        history_retention,
        host_whitelist,
        cache_limit,
        par_option,
    ):
        """Run all pending configuration conversions"""
        if config_conversion_version() < 1:
            ConfigConverter.convert_version_1(
                config_conversion_version,
                auto_sort,
                sorters_converted,
                no_series_dupes,
                no_smart_dupes,
                history_retention,
                host_whitelist,
                cache_limit,
            )

        if config_conversion_version() < 2:
            ConfigConverter.convert_version_2(config_conversion_version)

        if config_conversion_version() < 3:
            ConfigConverter.convert_version_3(config_conversion_version, par_option)

        if config_conversion_version() < 4:
            ConfigConverter.convert_version_4(config_conversion_version)

        # Make sure we store the new values
        save_config()
