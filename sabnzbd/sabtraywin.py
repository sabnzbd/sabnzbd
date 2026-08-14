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
sabnzbd.sabtraywin - System tray icon on Windows

The low-level tray plumbing is based on SysTrayIcon.py by Simon Brunning
(http://www.brunningonline.net/simon/blog/archives/001835.html), with threading
and icon-preloading support added by Jan Schejbal.
"""

import functools
import itertools
import logging
import os
from threading import Thread
from time import sleep
from typing import Callable, Iterator, Optional

import pywintypes
import timer
import win32con
import win32gui
import win32gui_struct

import sabnzbd
import sabnzbd.api as api
import sabnzbd.cfg as cfg
from sabnzbd.misc import to_units
from sabnzbd.panic import launch_a_browser

# Win32 window class name of the hidden message window that owns the tray icon
WINDOW_CLASS_NAME = "SabTrayIcon"

# Tray icon per state. When updating these paths, also update them in the NSIS script!
SABICONS = {
    "default": "icons/sabnzbd16_32.ico",
    "green": "icons/sabnzbd16_32green.ico",
    "pause": "icons/sabnzbd16_32paused.ico",
}


class SABTrayThread(Thread):
    def __init__(self):
        super().__init__()

        # Wait for translated texts to be loaded
        while not sabnzbd.WEBUI_READY:
            sleep(0.2)
            logging.debug("language file not loaded, waiting")

        self.sabpaused = False
        self.counter = 0

        # Cache texts for performance, do_updates is called often
        self.txt_idle = T("Idle")
        self.txt_paused = T("Paused")
        self.txt_remaining = T("Remaining")

        menu_options = (
            (T("Show interface"), self.browse),
            (T("Open complete folder"), self.opencomplete),
            ("SEPARATOR", None),
            (T("Pause") + "/" + T("Resume"), self.pauseresume),
            (
                T("Pause for"),
                (
                    (T("Pause for 5 minutes"), functools.partial(self.pausefor, 5)),
                    (T("Pause for 15 minutes"), functools.partial(self.pausefor, 15)),
                    (T("Pause for 30 minutes"), functools.partial(self.pausefor, 30)),
                    (T("Pause for 1 hour"), functools.partial(self.pausefor, 60)),
                    (T("Pause for 3 hours"), functools.partial(self.pausefor, 3 * 60)),
                    (T("Pause for 6 hours"), functools.partial(self.pausefor, 6 * 60)),
                ),
            ),
            ("SEPARATOR", None),
            (T("Read all RSS feeds"), self.rss),
            ("SEPARATOR", None),
            (
                T("Troubleshoot"),
                (
                    (T("Restart"), self.restart_sab),
                    (T("Restart without login"), self.nologin),
                    (T("Restart") + " - 127.0.0.1:8080", self.defhost),
                ),
            ),
            (T("Shutdown"), self.shutdown),
        )

        self.terminate = False
        self.icon = "default"
        self.hover_text = "SABnzbd"

        # Assign a unique command id to every menu entry, counting up from 1
        self.menu_actions_by_id: dict[int, Callable[[], None]] = {}
        self.menu_options = self._add_ids_to_menu_options(menu_options, itertools.count(1))

        self.click_timer: Optional[int] = None

        self.start()

    def run(self):
        self.initialize()
        while not self.terminate:
            win32gui.PumpWaitingMessages()
            self.do_updates()
            sleep(0.1)
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))
        win32gui.DestroyMenu(self.menu)

    def stop(self):
        self.terminate = True
        sleep(0.15)

    def initialize(self):
        # Note that all functions should return True to prevent tracebacks
        message_map = {
            win32gui.RegisterWindowMessage("TaskbarCreated"): self.restart,
            win32con.WM_COMMAND: self.command,
            win32con.WM_USER + 20: self.notify,
        }
        # Register the Window class
        window_class = win32gui.WNDCLASS()
        hinst = window_class.hInstance = win32gui.GetModuleHandle(None)
        window_class.lpszClassName = WINDOW_CLASS_NAME
        window_class.style = win32con.CS_VREDRAW | win32con.CS_HREDRAW
        window_class.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
        window_class.hbrBackground = win32con.COLOR_WINDOW
        window_class.lpfnWndProc = message_map  # could also specify a wndproc
        class_atom = win32gui.RegisterClass(window_class)
        # Create the Window
        style = win32con.WS_OVERLAPPED | win32con.WS_SYSMENU
        self.hwnd = win32gui.CreateWindow(
            class_atom,
            WINDOW_CLASS_NAME,
            style,
            0,
            0,
            win32con.CW_USEDEFAULT,
            win32con.CW_USEDEFAULT,
            0,
            0,
            hinst,
            None,
        )
        win32gui.UpdateWindow(self.hwnd)
        self.notify_id: Optional[tuple] = None

        # Load the tray icons once
        icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        self.icons: dict[str, int] = {
            state: win32gui.LoadImage(0, path, win32con.IMAGE_ICON, 0, 0, icon_flags)
            for state, path in SABICONS.items()
        }
        self.refresh_icon()

        # The menu is static, so build it once and reuse it for every right-click
        self.menu = win32gui.CreatePopupMenu()
        self.create_menu(self.menu, self.menu_options)

    # called every ~0.1s by run(); refreshes the tray at most once per second
    def do_updates(self):
        """Refresh the icon and tooltip from the queue state, but only when they change"""
        self.counter += 1
        if self.counter <= 10:
            return
        self.counter = 0

        self.sabpaused, bytes_left, bpsnow, time_left = api.fast_queue()
        mb_left = to_units(bytes_left)
        speed = to_units(bpsnow)

        if self.sabpaused:
            if bytes_left > 0:
                hover_text = "%s - %s: %sB" % (self.txt_paused, self.txt_remaining, mb_left)
            else:
                hover_text = self.txt_paused
            icon = "pause"
        elif bytes_left > 0:
            hover_text = "%sB/s - %s: %sB (%s)" % (speed, self.txt_remaining, mb_left, time_left)
            icon = "green"
        else:
            hover_text = self.txt_idle
            icon = "default"
        hover_text = "SABnzbd %s\n%s" % (sabnzbd.__version__, hover_text)

        # Only notify the shell when the icon or tooltip actually changed
        if icon != self.icon or hover_text != self.hover_text:
            self.icon = icon
            self.hover_text = hover_text
            self.refresh_icon()

    def refresh_icon(self):
        hicon = self.icons[self.icon]
        if self.notify_id:
            message = win32gui.NIM_MODIFY
        else:
            message = win32gui.NIM_ADD
        self.notify_id = (
            self.hwnd,
            0,
            win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            win32con.WM_USER + 20,
            hicon,
            self.hover_text,
        )
        try:
            win32gui.Shell_NotifyIcon(message, self.notify_id)
        except Exception:
            # Timeouts can occur after system comes out of standby/hibernate
            pass

    def send_notification(self, title: str, msg: str):
        hicon = self.icons[self.icon]
        win32gui.Shell_NotifyIcon(
            win32gui.NIM_MODIFY,
            (self.hwnd, 0, win32gui.NIF_INFO, win32con.WM_USER + 20, hicon, "Balloon tooltip", msg, 200, title),
        )

    def _add_ids_to_menu_options(self, menu_options: tuple, action_ids: Iterator[int]) -> list:
        """Recursively tag every menu entry (and submenu entry) with a unique command id"""
        result = []
        for option_text, option_action in menu_options:
            option_id = next(action_ids)
            if callable(option_action):
                self.menu_actions_by_id[option_id] = option_action
                result.append((option_text, option_action, option_id))
            elif isinstance(option_action, (list, tuple)):
                submenu = self._add_ids_to_menu_options(option_action, action_ids)
                result.append((option_text, submenu, option_id))
            elif option_text == "SEPARATOR":
                result.append((option_text, option_action, option_id))
            else:
                logging.error("Unknown tray menu item: %s", (option_text, option_action))
        return result

    def show_menu(self):
        try:
            pos = win32gui.GetCursorPos()
            # See https://learn.microsoft.com/windows/win32/menurc/using-menus
            win32gui.SetForegroundWindow(self.hwnd)
            win32gui.TrackPopupMenu(self.menu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0, self.hwnd, None)
            win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        except pywintypes.error:
            # Weird PyWin/win32gui bug, just ignore it for now
            pass

    def create_menu(self, menu: int, menu_options: list):
        for option_text, option_action, option_id in menu_options[::-1]:
            if option_id in self.menu_actions_by_id:
                item, _extras = win32gui_struct.PackMENUITEMINFO(text=option_text, wID=option_id)
                win32gui.InsertMenuItem(menu, 0, 1, item)
            elif option_text == "SEPARATOR":
                item, _extras = win32gui_struct.PackMENUITEMINFO(fType=win32con.MFT_SEPARATOR)
                win32gui.InsertMenuItem(menu, 0, 1, item)
            else:
                submenu = win32gui.CreatePopupMenu()
                self.create_menu(submenu, option_action)
                item, _extras = win32gui_struct.PackMENUITEMINFO(text=option_text, hSubMenu=submenu)
                win32gui.InsertMenuItem(menu, 0, 1, item)

    def notify(self, hwnd: int, msg: int, wparam: int, lparam: int) -> bool:
        # A double click is actually a single click followed by a double-click event,
        # so we need a timed callback to tell them apart
        if lparam == win32con.WM_LBUTTONDBLCLK:
            # Double-click opens the interface (the default action)
            self.browse()
            self.stop_click_timer()
        elif lparam == win32con.WM_RBUTTONUP:
            self.show_menu()
        elif lparam == win32con.WM_LBUTTONDOWN:
            # Wait at least until what the user has defined as double click (timeout in ms)
            self.stop_click_timer()
            self.click_timer = timer.set_timer(win32gui.GetDoubleClickTime() * 2, self.click)
        return True

    def command(self, hwnd: int, msg: int, wparam: int, lparam: int) -> bool:
        self.execute_menu_option(win32gui.LOWORD(wparam))
        return True

    def restart(self, hwnd: int, msg: int, wparam: int, lparam: int) -> bool:
        self.notify_id = None
        self.refresh_icon()
        return True

    # left-click handler, fired by the timer set in notify()
    def click(self, *args):
        self.stop_click_timer()
        # Pause/resume and force an update of the icon/text
        self.pauseresume()
        self.counter = 11

    def stop_click_timer(self):
        if self.click_timer:
            timer.kill_timer(self.click_timer)
            self.click_timer = None

    def execute_menu_option(self, menu_id: int):
        self.menu_actions_by_id[menu_id]()

    # Menu handlers
    def browse(self):
        launch_a_browser(sabnzbd.BROWSER_URL, True)

    def opencomplete(self):
        try:
            os.startfile(cfg.complete_dir.get_path())
        except OSError:
            pass

    def pauseresume(self):
        if self.sabpaused:
            self.resume()
        else:
            self.pause()

    def pausefor(self, minutes: int):
        sabnzbd.Scheduler.plan_resume(minutes)

    def rss(self):
        sabnzbd.Scheduler.force_rss()

    def restart_sab(self):
        logging.info("Restart requested by tray")
        sabnzbd.trigger_restart()

    def nologin(self):
        sabnzbd.cfg.username.set("")
        sabnzbd.cfg.password.set("")
        sabnzbd.config.save_config()
        sabnzbd.trigger_restart()

    def defhost(self):
        sabnzbd.cfg.web_host.set("127.0.0.1")
        sabnzbd.cfg.enable_https.set(False)
        sabnzbd.config.save_config()
        sabnzbd.trigger_restart()

    def shutdown(self):
        # In a separate thread, because the shutdown also stops the tray icon
        Thread(target=sabnzbd.shutdown_program).start()

    def pause(self):
        sabnzbd.Scheduler.plan_resume(0)
        sabnzbd.Downloader.pause()

    def resume(self):
        sabnzbd.Scheduler.plan_resume(0)
        sabnzbd.downloader.unpause_all()
