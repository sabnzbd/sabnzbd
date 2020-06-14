#!/usr/bin/env python
# based on SysTrayIcon.py by Simon Brunning - simon@brunningonline.net
# http://www.brunningonline.net/simon/blog/archives/001835.html
# http://www.brunningonline.net/simon/blog/archives/SysTrayIcon.py.html
# modified on 2011-10-04 by Jan Schejbal to support threading and preload icons
#  override doUpdates to perform actions inside the icon thread
#  override click to perform actions when left-clicking the icon

import os
import pywintypes
import win32api
import win32con
import win32gui_struct
import timer

try:
    import winxpgui as win32gui
except ImportError:
    import win32gui
from threading import Thread
from time import sleep


class SysTrayIconThread(Thread):
    QUIT = "QUIT"
    SPECIAL_ACTIONS = [QUIT]

    FIRST_ID = 1023
    terminate = False

    def __init__(self, icon, hover_text, menu_options, on_quit=None, default_menu_index=None, window_class_name=None):
        Thread.__init__(self)
        self.icon = icon
        self.icons = {}
        self.hover_text = hover_text
        self.on_quit = on_quit

        # menu_options = menu_options + (('Quit', None, self.QUIT),)
        self._next_action_id = self.FIRST_ID
        self.menu_actions_by_id = set()
        self.menu_options = self._add_ids_to_menu_options(list(menu_options))
        self.menu_actions_by_id = dict(self.menu_actions_by_id)
        del self._next_action_id

        self.click_timer = None
        self.default_menu_index = default_menu_index or 0
        self.window_class_name = window_class_name or "SysTrayIconPy"

        self.start()

    def initialize(self):
        message_map = {
            win32gui.RegisterWindowMessage("TaskbarCreated"): self.restart,
            win32con.WM_DESTROY: self.destroy,
            win32con.WM_COMMAND: self.command,
            win32con.WM_USER + 20: self.notify,
        }
        # Register the Window class.
        window_class = win32gui.WNDCLASS()
        hinst = window_class.hInstance = win32gui.GetModuleHandle(None)
        window_class.lpszClassName = self.window_class_name
        window_class.style = win32con.CS_VREDRAW | win32con.CS_HREDRAW
        window_class.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
        window_class.hbrBackground = win32con.COLOR_WINDOW
        window_class.lpfnWndProc = message_map  # could also specify a wndproc.
        classAtom = win32gui.RegisterClass(window_class)
        # Create the Window.
        style = win32con.WS_OVERLAPPED | win32con.WS_SYSMENU
        self.hwnd = win32gui.CreateWindow(
            classAtom,
            self.window_class_name,
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
        self.notify_id = None
        self.refresh_icon()

    def run(self):
        self.initialize()
        while not self.terminate:
            win32gui.PumpWaitingMessages()
            self.doUpdates()
            sleep(0.100)
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))

    # Override this
    def doUpdates(self):
        pass

    # Notification
    def sendnotification(self, title, msg):
        hicon = self.get_icon(self.icon)
        win32gui.Shell_NotifyIcon(
            win32gui.NIM_MODIFY,
            (self.hwnd, 0, win32gui.NIF_INFO, win32con.WM_USER + 20, hicon, "Balloon tooltip", msg, 200, title),
        )

    def _add_ids_to_menu_options(self, menu_options):
        result = []
        for menu_option in menu_options:
            option_text, option_icon, option_action = menu_option
            if callable(option_action) or option_action in self.SPECIAL_ACTIONS:
                self.menu_actions_by_id.add((self._next_action_id, option_action))
                result.append(menu_option + (self._next_action_id,))
            elif non_string_iterable(option_action):
                result.append(
                    (option_text, option_icon, self._add_ids_to_menu_options(option_action), self._next_action_id)
                )
            elif option_text == "SEPARATOR":
                # Skip, add separator later
                result.append(menu_option + (self._next_action_id,))
            else:
                print(("Unknown item", option_text, option_icon, option_action))
            self._next_action_id += 1
        return result

    def get_icon(self, path):
        hicon = self.icons.get(path)
        if hicon != None:
            return hicon

        # Try and find a custom icon
        hinst = win32gui.GetModuleHandle(None)
        if os.path.isfile(path):
            icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
            hicon = win32gui.LoadImage(hinst, path, win32con.IMAGE_ICON, 0, 0, icon_flags)
        else:
            print("Can't find icon file - using default.")
            hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

        self.icons[path] = hicon
        return hicon

    def refresh_icon(self):
        hicon = self.get_icon(self.icon)
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
        except:
            # Timeouts can occur after system comes out of standby/hibernate
            pass

    def restart(self, hwnd, msg, wparam, lparam):
        self.refresh_icon()

    def destroy(self, hwnd, msg, wparam, lparam):
        if self.on_quit:
            self.on_quit(self)
        nid = (self.hwnd, 0)
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
        win32gui.PostQuitMessage(0)  # Terminate the app.

    def notify(self, hwnd, msg, wparam, lparam):
        # Double click is actually 1 single click followed
        # by a double-click event, no way to differentiate
        # So we need a timed callback to cancel
        if lparam == win32con.WM_LBUTTONDBLCLK:
            self.execute_menu_option(self.default_menu_index + self.FIRST_ID)
            self.stop_click_timer()
        elif lparam == win32con.WM_RBUTTONUP:
            self.show_menu()
        elif lparam == win32con.WM_LBUTTONDOWN:
            # Wrapper of win32api, timeout is in ms
            # We need to wait at least untill what user has defined as double click
            self.stop_click_timer()
            self.click_timer = timer.set_timer(win32gui.GetDoubleClickTime() * 2, self.click)
        return True

    def show_menu(self):
        menu = win32gui.CreatePopupMenu()
        self.create_menu(menu, self.menu_options)
        # win32gui.SetMenuDefaultItem(menu, 1000, 0)

        try:
            pos = win32gui.GetCursorPos()
            # See http://msdn.microsoft.com/library/default.asp?url=/library/en-us/winui/menus_0hdi.asp
            win32gui.SetForegroundWindow(self.hwnd)
            win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0, self.hwnd, None)
            win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        except pywintypes.error:
            # Weird PyWin/win32gui bug, just ignore it for now
            pass

    # Override this for left-click action
    # Need to call the stop-timer in that function!
    def click(self, *args):
        pass

    def stop_click_timer(self):
        # Stop the timer
        if self.click_timer:
            timer.kill_timer(self.click_timer)
            self.click_timer = None

    def create_menu(self, menu, menu_options):
        for option_text, option_icon, option_action, option_id in menu_options[::-1]:
            if option_icon:
                option_icon = self.prep_menu_icon(option_icon)

            if option_id in self.menu_actions_by_id:
                item, extras = win32gui_struct.PackMENUITEMINFO(text=option_text, hbmpItem=option_icon, wID=option_id)
                win32gui.InsertMenuItem(menu, 0, 1, item)
            elif option_text == "SEPARATOR":
                item, extras = win32gui_struct.PackMENUITEMINFO(fType=win32con.MFT_SEPARATOR)
                win32gui.InsertMenuItem(menu, 0, 1, item)
            else:
                submenu = win32gui.CreatePopupMenu()
                self.create_menu(submenu, option_action)
                item, extras = win32gui_struct.PackMENUITEMINFO(
                    text=option_text, hbmpItem=option_icon, hSubMenu=submenu
                )
                win32gui.InsertMenuItem(menu, 0, 1, item)

    def prep_menu_icon(self, icon):
        # First load the icon.
        ico_x = win32api.GetSystemMetrics(win32con.SM_CXSMICON)
        ico_y = win32api.GetSystemMetrics(win32con.SM_CYSMICON)
        hicon = win32gui.LoadImage(0, icon, win32con.IMAGE_ICON, ico_x, ico_y, win32con.LR_LOADFROMFILE)

        hdcBitmap = win32gui.CreateCompatibleDC(0)
        hdcScreen = win32gui.GetDC(0)
        hbm = win32gui.CreateCompatibleBitmap(hdcScreen, ico_x, ico_y)
        hbmOld = win32gui.SelectObject(hdcBitmap, hbm)
        # Fill the background.
        brush = win32gui.GetSysColorBrush(win32con.COLOR_MENU)
        win32gui.FillRect(hdcBitmap, (0, 0, 16, 16), brush)
        # unclear if brush needs to be feed.  Best clue I can find is:
        # "GetSysColorBrush returns a cached brush instead of allocating a new
        # one." - implies no DeleteObject
        # draw the icon
        win32gui.DrawIconEx(hdcBitmap, 0, 0, hicon, ico_x, ico_y, 0, 0, win32con.DI_NORMAL)
        win32gui.SelectObject(hdcBitmap, hbmOld)
        win32gui.DeleteDC(hdcBitmap)

        return hbm

    def command(self, hwnd, msg, wparam, lparam):
        id = win32gui.LOWORD(wparam)
        self.execute_menu_option(id)

    def execute_menu_option(self, id):
        menu_action = self.menu_actions_by_id[id]
        if menu_action == self.QUIT:
            win32gui.DestroyWindow(self.hwnd)
        else:
            menu_action(self)


def non_string_iterable(obj):
    try:
        iter(obj)
    except TypeError:
        return False
    else:
        return not isinstance(obj, str)
