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
sabnzbd.config_callbacks - Configuration change callbacks
"""

import sabnzbd


class ConfigCallbacks:
    """Handles callbacks for configuration changes"""

    @staticmethod
    def new_limit(cache_limit):
        """Callback for article cache changes"""
        if sabnzbd.__INITIALIZED__:
            # Only update after full startup
            sabnzbd.ArticleCache.new_limit(cache_limit.get_int())

    @staticmethod
    def guard_restart():
        """Callback for config options requiring a restart"""
        sabnzbd.RESTART_REQ = True

    @staticmethod
    def guard_top_only(top_only):
        """Callback for change of top_only option"""
        sabnzbd.NzbQueue.set_top_only(top_only())

    @staticmethod
    def guard_pause_on_pp(pause_on_post_processing):
        """Callback for change of pause-download-on-pp"""
        if pause_on_post_processing():
            pass  # Not safe to idle downloader, because we don't know
            # if post-processing is active now
        else:
            sabnzbd.Downloader.resume_from_postproc()

    @staticmethod
    def guard_quota_size():
        """Callback for change of quota_size"""
        sabnzbd.BPSMeter.change_quota()

    @staticmethod
    def guard_quota_dp():
        """Callback for change of quota_day or quota_period"""
        sabnzbd.Scheduler.restart()

    @staticmethod
    def guard_language(language):
        """Callback for change of the interface language"""
        sabnzbd.lang.set_language(language())
        sabnzbd.api.clear_trans_cache()

    @staticmethod
    def guard_https_ver(enable_https_verification):
        """Callback for change of https verification"""
        sabnzbd.misc.set_https_verification(enable_https_verification())
