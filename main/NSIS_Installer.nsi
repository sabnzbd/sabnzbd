;
; Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
;
; This program is free software; you can redistribute it and/or
; modify it under the terms of the GNU General Public License
; as published by the Free Software Foundation; either version 2
; of the License, or (at your option) any later version.
;
; This program is distributed in the hope that it will be useful,
; but WITHOUT ANY WARRANTY; without even the implied warranty of
; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
; GNU General Public License for more details.
;
; You should have received a copy of the GNU General Public License
; along with this program; if not, write to the Free Software
; Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

!addplugindir win\nsis\Plugins
!addincludedir win\nsis\Include

!include "MUI2.nsh"
!include "registerExtension.nsh"


Name "${SAB_PRODUCT}"
OutFile "${SAB_FILE}"


; Some default compiler settings (uncomment and change at will):
; SetCompress auto ; (can be off or force)
; SetDatablockOptimize on ; (can be off)
; CRCCheck on ; (can be off)
; AutoCloseWindow false ; (can be true for the window go away automatically at end)
; ShowInstDetails hide ; (can be show to have them shown, or nevershow to disable)
; SetDateSave off ; (can be on to have files restored to their orginal date)
WindowIcon on

InstallDir "$PROGRAMFILES\SABnzbd"
InstallDirRegKey HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd" ""
DirText "Select the directory to install SABnzbd+ in:"

  ;Vista redirects $SMPROGRAMS to all users without this
  RequestExecutionLevel admin
  FileErrorText "If you have no admin rights, try to install into a user directory."


;--------------------------------
;Variables

  Var MUI_TEMP
  Var STARTMENU_FOLDER
;--------------------------------
;Interface Settings

  !define MUI_ABORTWARNING

  !define MUI_ICON "interfaces/Classic/templates/static/images/favicon.ico"


;--------------------------------
;Pages

  !insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
  !define MUI_COMPONENTSPAGE_NODESC
  !insertmacro MUI_PAGE_COMPONENTS

  !insertmacro MUI_PAGE_DIRECTORY

  ;Start Menu Folder Page Configuration
  !define MUI_STARTMENUPAGE_REGISTRY_ROOT "HKCU"
  !define MUI_STARTMENUPAGE_REGISTRY_KEY "Software\SABnzbd"
  !define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "Start Menu Folder"
  !define MUI_STARTMENUPAGE_DEFAULTFOLDER "SABnzbd"

  !insertmacro MUI_PAGE_STARTMENU Application $STARTMENU_FOLDER


  !insertmacro MUI_PAGE_INSTFILES
  !define MUI_FINISHPAGE_RUN
  !define MUI_FINISHPAGE_RUN_FUNCTION "LaunchLink"
  !define MUI_FINISHPAGE_RUN_TEXT "Start SABnzbd (hidden)"
  !define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README.txt"
  !define MUI_FINISHPAGE_SHOWREADME_TEXT "Show Release Notes"
  ;!define MUI_FINISHPAGE_LINK "View the SABnzbdPlus Wiki"
  ;!define MUI_FINISHPAGE_LINK_LOCATION "http://sabnzbd.wikidot.com/"
  !define MUI_FINISHPAGE_LINK "Support the project, Donate!"
  !define MUI_FINISHPAGE_LINK_LOCATION "http://www.sabnzbd.org/contribute/"

  !insertmacro MUI_PAGE_FINISH

  !insertmacro MUI_UNPAGE_CONFIRM
  !define MUI_UNPAGE_COMPONENTSPAGE_NODESC
  !insertmacro MUI_UNPAGE_COMPONENTS
  !insertmacro MUI_UNPAGE_INSTFILES

Function LaunchLink
  ExecShell "" "$INSTDIR\SABnzbd.exe"
FunctionEnd

Function .onInit
;make sure sabnzbd.exe isnt running..if so abort

        loop:
        StrCpy $0 "SABnzbd.exe"
		KillProc::FindProcesses
        StrCmp $0 "0" endcheck
        MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION 'Please close "SABnzbd.exe" first' IDOK loop IDCANCEL exitinstall
        exitinstall:
        Abort
        endcheck:
FunctionEnd
;--------------------------------
;Languages

  !insertmacro MUI_LANGUAGE "English"

;--------------------------------

Section "SABnzbd" SecDummy
SetOutPath "$INSTDIR"

;IfFileExists $INSTDIR\sabnzbd.exe 0 endWarnExist
;    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION 'Warning: overwriting an existing installation is not recommended' IDOK endWarnExist IDCANCEL 0
;    Abort
;endWarnExist:

;IfFileExists "$LOCALAPPDATA\sabnzbd\cache\queue.sab" 0 endWarnCache
;    IfFileExists "$LOCALAPPDATA\sabnzbd\cache\queue7.sab" endWarnCache 0
;        MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION 'Warning: do not re-use an older download queue' IDOK endWarnCache IDCANCEL 0
;        Abort
;endWarnCache:

; add files / whatever that need to be installed here.
File /r "dist\*"


WriteRegStr HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd" "" "$INSTDIR"
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "DisplayName" "SABnzbd (remove only)"
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "UninstallString" '"$INSTDIR\uninstall.exe"'
;WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "DisplayIcon" '"$INSTDIR\need-a-.ico"'
; write out uninstaller
WriteUninstaller "$INSTDIR\Uninstall.exe"

  !insertmacro MUI_STARTMENU_WRITE_BEGIN Application

    ;Create shortcuts
    CreateDirectory "$SMPROGRAMS\$STARTMENU_FOLDER"
    CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\SABnzbd.lnk" "$INSTDIR\SABnzbd.exe"
    CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\SABnzbd - SafeMode.lnk" "$INSTDIR\SABnzbd-console.exe"
    WriteINIStr "$SMPROGRAMS\$STARTMENU_FOLDER\SABnzbd - Documentation.url" "InternetShortcut" "URL" "http://sabnzbd.wikidot.com/"
    CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\Uninstall.lnk" "$INSTDIR\Uninstall.exe"



  !insertmacro MUI_STARTMENU_WRITE_END


SectionEnd ; end of default section

Section /o "Run at startup" startup
    CreateShortCut "$SMPROGRAMS\Startup\SABnzbd.lnk" "$INSTDIR\SABnzbd.exe" "-b0"
SectionEnd ;

Section "Desktop Icon" desktop
    CreateShortCut "$DESKTOP\SABnzbd.lnk" "$INSTDIR\SABnzbd.exe"
SectionEnd ; end of desktop icon section

Section /o "NZB File association" assoc
    ${registerExtension} "$INSTDIR\nzb.ico" "$INSTDIR\SABnzbd.exe" ".nzb" "NZB File"
    ;${registerExtension} "$INSTDIR\SABnzbd.exe" ".nzb" "NZB File"
SectionEnd ; end of file association section

; begin uninstall settings/section
UninstallText "This will uninstall SABnzbd+ from your system"

Section Uninstall
;make sure sabnzbd.exe isnt running..if so shut it down

    StrCpy $0 "sabnzbd.exe"
    DetailPrint "Searching for processes called '$0'"
    KillProc::FindProcesses
    StrCmp $1 "-1" wooops
    DetailPrint "-> Found $0 processes"

    StrCmp $0 "0" completed
    Sleep 1500

    StrCpy $0 "sabnzbd.exe"
    DetailPrint "Killing all processes called '$0'"
    KillProc::KillProcesses
    StrCmp $1 "-1" wooops
    DetailPrint "-> Killed $0 processes, failed to kill $1 processes"

    Goto completed

    wooops:
    DetailPrint "-> Error: Something went wrong :-("
    Abort

    completed:
    DetailPrint "Process Killed"


    ; add delete commands to delete whatever files/registry keys/etc you installed here.
    Delete "$INSTDIR\uninstall.exe"
    DeleteRegKey HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd"
    DeleteRegKey HKEY_LOCAL_MACHINE "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd"

    ; Delete installation files are carefully as possible
    ; Using just rmdir /r "$instdir" is considered unsafe!
    RMDir /r "$INSTDIR\language"
    RMDir /r "$INSTDIR\interfaces\Classic"
    RMDir /r "$INSTDIR\interfaces\Plush"
    RMDir /r "$INSTDIR\interfaces\smpl"
    RMDir /r "$INSTDIR\interfaces\Mobile"
    RMDir /r "$INSTDIR\interfaces\wizard"
    RMDir "$INSTDIR\interfaces"
    RMDir /r "$INSTDIR\win\par2"
    RMDir /r "$INSTDIR\win\unrar"
    RMDir /r "$INSTDIR\win\unzip"
    RMDir /r "$INSTDIR\win"
    Delete "$INSTDIR\licenses\*.txt"
    Delete "$INSTDIR\licenses\Python\*.txt"
    RMDir "$INSTDIR\licenses\Python"
    RMDir "$INSTDIR\licenses"
    Delete "$INSTDIR\lib\libeay32.dll"
    Delete "$INSTDIR\lib\pywintypes25.dll"
    Delete "$INSTDIR\lib\ssleay32.dll"
    Delete "$INSTDIR\lib\sabnzbd.zip"
    Delete "$INSTDIR\lib\*.pyd"
    RMDir  /r "$INSTDIR\lib\"
    Delete "$INSTDIR\CHANGELOG.txt"
    Delete "$INSTDIR\COPYRIGHT.txt"
    Delete "$INSTDIR\email.tmpl"
    Delete "$INSTDIR\GPL2.txt"
    Delete "$INSTDIR\GPL3.txt"
    Delete "$INSTDIR\INSTALL.txt"
    Delete "$INSTDIR\ISSUES.txt"
    Delete "$INSTDIR\LICENSE.txt"
    Delete "$INSTDIR\MSVCR71.dll"
    Delete "$INSTDIR\nzb.ico"
    Delete "$INSTDIR\PKG-INFO"
    Delete "$INSTDIR\python25.dll"
    Delete "$INSTDIR\README.txt"
    Delete "$INSTDIR\SABnzbd-console.exe"
    Delete "$INSTDIR\SABnzbd.exe"
    Delete "$INSTDIR\Sample-PostProc.cmd"
    Delete "$INSTDIR\Uninstall.exe"
    Delete "$INSTDIR\w9xpopen.exe"
    RMDir "$INSTDIR"

    !insertmacro MUI_STARTMENU_GETFOLDER Application $MUI_TEMP

    Delete "$SMPROGRAMS\$MUI_TEMP\SABnzbd.lnk"
    Delete "$SMPROGRAMS\$MUI_TEMP\Uninstall.lnk"
    Delete "$SMPROGRAMS\$MUI_TEMP\SABnzbd - SafeMode.lnk"
    Delete "$SMPROGRAMS\$MUI_TEMP\SABnzbd - Documentation.url"
    RMDir  "$SMPROGRAMS\$MUI_TEMP"

    Delete "$SMPROGRAMS\Startup\SABnzbd.lnk"

    Delete "$DESKTOP\SABnzbd.lnk"

    DeleteRegKey HKEY_CURRENT_USER  "Software\SABnzbd"

    ${unregisterExtension} ".nzb" "NZB File"


SectionEnd ; end of uninstall section

Section "un.Delete Settings" DelSettings
    Delete "$LOCALAPPDATA\sabnzbd\sabnzbd.ini"
    RMDir /r "$LOCALAPPDATA\sabnzbd\admin"
SectionEnd


Section "un.Delete Logs" DelLogs
    RMDir /r "$LOCALAPPDATA\sabnzbd\logs"
SectionEnd


Section "un.Delete Cache" DelCache
    RMDir /r "$LOCALAPPDATA\sabnzbd\cache"
    RMDir "$LOCALAPPDATA\sabnzbd"
SectionEnd

; eof
;