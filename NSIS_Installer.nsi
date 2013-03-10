; -*- coding: latin-1 -*-
;
; Copyright 2008-2012 The SABnzbd-Team <team@sabnzbd.org>
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
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"
!include "WinSxSQuery.nsh"
!include "nsProcess.nsh"

;------------------------------------------------------------------
;
; Marco for removing existing and the current installation
; It share buy the installer and the uninstaller.
; Make sure it covers 0.5.x, 0.6.x and 0.7.x in one go.
;
!define RemovePrev "!insertmacro RemovePrev"
!macro RemovePrev idir
  Delete   "${idir}\email\email-de.tmpl"
  Delete   "${idir}\email\email-en.tmpl"
  Delete   "${idir}\email\email-nl.tmpl"
  Delete   "${idir}\email\email-fr.tmpl"
  Delete   "${idir}\email\email-sv.tmpl"
  Delete   "${idir}\email\email-da.tmpl"
  Delete   "${idir}\email\email-nb.tmpl"
  Delete   "${idir}\email\email-pl.tmpl"
  Delete   "${idir}\email\email-ro.tmpl"
  Delete   "${idir}\email\email-sr.tmpl"
  Delete   "${idir}\email\email-es.tmpl"
  Delete   "${idir}\email\email-pt_BR.tmpl"
  Delete   "${idir}\email\email-sr.tmpl"
  Delete   "${idir}\email\email-ru.tmpl"
  Delete   "${idir}\email\email-zh_CN.tmpl"
  Delete   "${idir}\email\rss-de.tmpl"
  Delete   "${idir}\email\rss-en.tmpl"
  Delete   "${idir}\email\rss-nl.tmpl"
  Delete   "${idir}\email\rss-pl.tmpl"
  Delete   "${idir}\email\rss-fr.tmpl"
  Delete   "${idir}\email\rss-sv.tmpl"
  Delete   "${idir}\email\rss-da.tmpl"
  Delete   "${idir}\email\rss-nb.tmpl"
  Delete   "${idir}\email\rss-ro.tmpl"
  Delete   "${idir}\email\rss-sr.tmpl"
  Delete   "${idir}\email\rss-es.tmpl"
  Delete   "${idir}\email\rss-pt_BR.tmpl"
  Delete   "${idir}\email\rss-sr.tmpl"
  Delete   "${idir}\email\rss-ru.tmpl"
  Delete   "${idir}\email\rss-zh_CN.tmpl"
  Delete   "${idir}\email\badfetch-da.tmpl"
  Delete   "${idir}\email\badfetch-de.tmpl"
  Delete   "${idir}\email\badfetch-en.tmpl"
  Delete   "${idir}\email\badfetch-fr.tmpl"
  Delete   "${idir}\email\badfetch-nb.tmpl"
  Delete   "${idir}\email\badfetch-nl.tmpl"
  Delete   "${idir}\email\badfetch-pl.tmpl"
  Delete   "${idir}\email\badfetch-ro.tmpl"
  Delete   "${idir}\email\badfetch-sr.tmpl"
  Delete   "${idir}\email\badfetch-sv.tmpl"
  Delete   "${idir}\email\badfetch-sr.tmpl"
  Delete   "${idir}\email\badfetch-es.tmpl"
  Delete   "${idir}\email\badfetch-pt_BR.tmpl"
  Delete   "${idir}\email\badfetch-ru.tmpl"
  Delete   "${idir}\email\badfetch-zh_CN.tmpl"
  RMDir    "${idir}\email"
  RMDir /r "${idir}\locale"
  RMDir /r "${idir}\interfaces\Classic"
  RMDir /r "${idir}\interfaces\Plush"
  RMDir /r "${idir}\interfaces\smpl"
  RMDir /r "${idir}\interfaces\Mobile"
  RMDir /r "${idir}\interfaces\wizard"
  RMDir /r "${idir}\interfaces\Config"
  RMDir    "${idir}\interfaces"
  RMDir /r "${idir}\win\curl"
  RMDir /r "${idir}\win\par2"
  RMDir /r "${idir}\win\unrar"
  RMDir /r "${idir}\win\unzip"
  RMDir /r "${idir}\win"
  RMDir /r "${idir}\licenses"
  RMDir /r "${idir}\lib\"
  RMDir /r "${idir}\po\email"
  RMDir /r "${idir}\po\main"
  RMDir /r "${idir}\po\nsis"
  RMDir    "${idir}\po"
  RMDir /r "${idir}\icons"
  Delete   "${idir}\CHANGELOG.txt"
  Delete   "${idir}\COPYRIGHT.txt"
  Delete   "${idir}\email.tmpl"
  Delete   "${idir}\GPL2.txt"
  Delete   "${idir}\GPL3.txt"
  Delete   "${idir}\INSTALL.txt"
  Delete   "${idir}\ISSUES.txt"
  Delete   "${idir}\LICENSE.txt"
  Delete   "${idir}\nzbmatrix.txt"
  Delete   "${idir}\MSVCR71.dll"
  Delete   "${idir}\nzb.ico"
  Delete   "${idir}\sabnzbd.ico"
  Delete   "${idir}\PKG-INFO"
  Delete   "${idir}\python25.dll"
  Delete   "${idir}\python26.dll"
  Delete   "${idir}\python27.dll"
  Delete   "${idir}\README.txt"
  Delete   "${idir}\README.rtf"
  Delete   "${idir}\ABOUT.txt"
  Delete   "${idir}\IMPORTANT_MESSAGE.txt"
  Delete   "${idir}\SABnzbd-console.exe"
  Delete   "${idir}\SABnzbd.exe"
  Delete   "${idir}\SABnzbd.exe.log"
  Delete   "${idir}\SABnzbd-helper.exe"
  Delete   "${idir}\SABnzbd-service.exe"
  Delete   "${idir}\Sample-PostProc.cmd"
  Delete   "${idir}\Uninstall.exe"
  Delete   "${idir}\w9xpopen.exe"
  RMDir    "${idir}"
!macroend

;------------------------------------------------------------------
; Define names of the product
  Name "${SAB_PRODUCT}"
  OutFile "${SAB_FILE}"
  InstallDir "$PROGRAMFILES\SABnzbd"
  InstallDirRegKey HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd" ""
  ;DirText $(MsgSelectDir)


;------------------------------------------------------------------
; Some default compiler settings (uncomment and change at will):
  SetCompress auto ; (can be off or force)
  SetDatablockOptimize on ; (can be off)
  CRCCheck on ; (can be off)
  AutoCloseWindow false ; (can be true for the window go away automatically at end)
  ShowInstDetails hide ; (can be show to have them shown, or nevershow to disable)
  SetDateSave off ; (can be on to have files restored to their orginal date)
  WindowIcon on


;------------------------------------------------------------------
; Vista/Win7 redirects $SMPROGRAMS to all users without this
  RequestExecutionLevel admin
  FileErrorText "If you have no admin rights, try to install into a user directory."


;------------------------------------------------------------------
;Variables
  Var MUI_TEMP
  Var STARTMENU_FOLDER

;------------------------------------------------------------------
;Interface Settings

  !define MUI_ABORTWARNING

  ;Show all languages, despite user's codepage
  !define MUI_LANGDLL_ALLLANGUAGES

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
  ;Remember the installer language
  !define MUI_LANGDLL_REGISTRY_ROOT "HKCU"
  !define MUI_LANGDLL_REGISTRY_KEY "Software\SABnzbd"
  !define MUI_LANGDLL_REGISTRY_VALUENAME "Installer Language"

  !insertmacro MUI_PAGE_STARTMENU Application $STARTMENU_FOLDER

  !insertmacro MUI_PAGE_INSTFILES
  !define MUI_FINISHPAGE_RUN
  !define MUI_FINISHPAGE_RUN_FUNCTION "LaunchLink"
  !define MUI_FINISHPAGE_RUN_TEXT $(MsgGoWiki)
  !define MUI_FINISHPAGE_RUN_NOTCHECKED
  !define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README.txt"
  !define MUI_FINISHPAGE_SHOWREADME_TEXT $(MsgShowRelNote)
  !define MUI_FINISHPAGE_LINK $(MsgSupportUs)
  !define MUI_FINISHPAGE_LINK_LOCATION "http://www.sabnzbd.org/contribute/"

  !insertmacro MUI_PAGE_FINISH

  !insertmacro MUI_UNPAGE_CONFIRM
  !define MUI_UNPAGE_COMPONENTSPAGE_NODESC
  !insertmacro MUI_UNPAGE_COMPONENTS
  !insertmacro MUI_UNPAGE_INSTFILES


;------------------------------------------------------------------
; Set supported languages
  !insertmacro MUI_LANGUAGE "English" ;first language is the default language
  !insertmacro MUI_LANGUAGE "French"
  !insertmacro MUI_LANGUAGE "German"
  !insertmacro MUI_LANGUAGE "Dutch"
  !insertmacro MUI_LANGUAGE "Polish"
  !insertmacro MUI_LANGUAGE "Swedish"
  !insertmacro MUI_LANGUAGE "Danish"
  !insertmacro MUI_LANGUAGE "NORWEGIAN"
  !insertmacro MUI_LANGUAGE "Romanian"
  !insertmacro MUI_LANGUAGE "Spanish"
  !insertmacro MUI_LANGUAGE "PortugueseBR"
  !insertmacro MUI_LANGUAGE "Serbian"
  !insertmacro MUI_LANGUAGE "Russian"
  !insertmacro MUI_LANGUAGE "SimpChinese"


;------------------------------------------------------------------
;Reserve Files
  ;If you are using solid compression, files that are required before
  ;the actual installation should be stored first in the data block,
  ;because this will make your installer start faster.

  !insertmacro MUI_RESERVEFILE_LANGDLL


;------------------------------------------------------------------
Function LaunchLink
  ExecShell "" "http://wiki.sabnzbd.org/"
FunctionEnd


;------------------------------------------------------------------
Function .onInit
  !insertmacro MUI_LANGDLL_DISPLAY

;--------------------------------
;make sure that the requires MS Runtimes are installed
;
goto nodownload ; Not needed while still using Python25
runtime_loop:
  push 'msvcr90.dll'
  push 'Microsoft.VC90.CRT,version="9.0.21022.8",type="win32",processorArchitecture="x86",publicKeyToken="1fc8b3b9a1e18e3b"'
  call WinSxS_HasAssembly
  pop $0

  StrCmp $0 "1" nodownload
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION $(MsgNoRuntime) /SD IDOK IDOK download IDCANCEL noinstall
    download:
      inetc::get /BANNER $(MsgDLRuntime) \
      "http://download.microsoft.com/download/1/1/1/1116b75a-9ec3-481a-a3c8-1777b5381140/vcredist_x86.exe" \
      "$TEMP\vcredist_x86.exe"
      Pop $0
      DetailPrint "Downloaded MS runtime library"
      StrCmp $0 "OK" dlok
        MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION $(MsgDLError) /SD IDCANCEL IDCANCEL exitinstall IDOK download
      dlok:
        ExecWait "$TEMP\vcredist_x86.exe" $1
        DetailPrint "VCRESULT=$1"
        DetailPrint "Tried to install MS runtime library"
        delete "$TEMP\vcredist_x86.exe"
        StrCmp $1 "0" nodownload
      noinstall:
        MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION $(MsgDLNeed) /SD IDOK IDOK runtime_loop IDCANCEL exitinstall
        Abort
  nodownload:


;------------------------------------------------------------------
;make sure user terminates sabnzbd.exe or else abort
;
loop:
  ${nsProcess::FindProcess} "SABnzbd.exe" $R0
  StrCmp $R0 0 0 endcheck
  MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION $(MsgCloseSab) IDOK loop IDCANCEL exitinstall
  exitinstall:
    ${nsProcess::Unload}
    Abort
endcheck:

FunctionEnd


;------------------------------------------------------------------
; SECTION main program
;
Section "SABnzbd" SecDummy
SetOutPath "$INSTDIR"

;------------------------------------------------------------------
; Make sure old versions are gone
IfFileExists $INSTDIR\sabnzbd.exe 0 endWarnExist
  IfFileExists $INSTDIR\python27.dll 0 endWarnExist
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "$(MsgRemoveOld)$\n$\n$(MsgRemoveOld2)" IDOK uninst
    Abort
uninst:
    ${RemovePrev} "$INSTDIR"
endWarnExist:

; add files / whatever that need to be installed here.
File /r "dist\*"


WriteRegStr HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd" "" "$INSTDIR"
WriteRegStr HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd" "Installer Language" "$(MsgLangCode)"
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "DisplayName" "SABnzbd ${SAB_VERSION}"
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "UninstallString" '"$INSTDIR\uninstall.exe"'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "DisplayVersion" '${SAB_VERSION}'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "Publisher" 'The SABnzbd Team'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "HelpLink" 'http://forums.sabnzbd.org/'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "URLInfoAbout" 'http://wiki.sabnzbd.org/'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "URLUpdateInfo" 'http://sabnzbd.org/'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "Comments" 'The automated Usenet download tool'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "DisplayIcon" '$INSTDIR\interfaces\Classic\templates\static\images\favicon.ico'
WriteRegDWORD HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "EstimatedSize"  25674
WriteRegDWORD HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "NoRepair" -1
WriteRegDWORD HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "NoModify" -1
; write out uninstaller
WriteUninstaller "$INSTDIR\Uninstall.exe"

  !insertmacro MUI_STARTMENU_WRITE_BEGIN Application

  ;Create shortcuts
  CreateDirectory "$SMPROGRAMS\$STARTMENU_FOLDER"
  CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\SABnzbd.lnk" "$INSTDIR\SABnzbd.exe"
  CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\SABnzbd - SafeMode.lnk" "$INSTDIR\SABnzbd.exe" "--server 127.0.0.1:8080 -b1 --no-login -t Plush"
  WriteINIStr "$SMPROGRAMS\$STARTMENU_FOLDER\SABnzbd - Documentation.url" "InternetShortcut" "URL" "http://wiki.sabnzbd.org/"
  CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\Uninstall.lnk" "$INSTDIR\Uninstall.exe"



  !insertmacro MUI_STARTMENU_WRITE_END


SectionEnd ; end of default section

Section /o $(MsgRunAtStart) startup
  CreateShortCut "$SMPROGRAMS\Startup\SABnzbd.lnk" "$INSTDIR\SABnzbd.exe" "-b0"
SectionEnd ;

Section $(MsgIcon) desktop
  CreateShortCut "$DESKTOP\SABnzbd.lnk" "$INSTDIR\SABnzbd.exe"
SectionEnd ; end of desktop icon section

Section /o $(MsgAssoc) assoc
  ${registerExtension} "$INSTDIR\icons\nzb.ico" "$INSTDIR\SABnzbd.exe" ".nzb" "NZB File"
  ${RefreshShellIcons}
SectionEnd ; end of file association section

; begin uninstall settings/section
UninstallText $(MsgUninstall)

Section "un.$(MsgDelProgram)" Uninstall
;make sure sabnzbd.exe isnt running..if so shut it down
  ${nsProcess::KillProcess} "SABnzbd.exe" $R0
  ${nsProcess::Unload}
  DetailPrint "Process Killed"


  ; add delete commands to delete whatever files/registry keys/etc you installed here.
  Delete "$INSTDIR\uninstall.exe"
  DeleteRegKey HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd"
  DeleteRegKey HKEY_LOCAL_MACHINE "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd"

  ${RemovePrev} "$INSTDIR"

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
  ${RefreshShellIcons}

SectionEnd ; end of uninstall section

Section /o "un.$(MsgDelSettings)" DelSettings
  DetailPrint "Uninstall settings $LOCALAPPDATA"
  Delete "$LOCALAPPDATA\sabnzbd\sabnzbd.ini"
  RMDir /r "$LOCALAPPDATA\sabnzbd"
SectionEnd

; eof

;--------------------------------
;Language strings
  LangString MsgGoWiki      ${LANG_ENGLISH} "Go to the SABnzbd Wiki"

  LangString MsgShowRelNote ${LANG_ENGLISH} "Show Release Notes"

  LangString MsgSupportUs   ${LANG_ENGLISH} "Support the project, Donate!"

  LangString MsgCloseSab    ${LANG_ENGLISH} "Please close $\"SABnzbd.exe$\" first"

  LangString MsgOldQueue    ${LANG_ENGLISH} "                  >>>> WARNING <<<<$\r$\n$\r$\nPlease, first check the release notes or go to http://wiki.sabnzbd.org/introducing-0-7-0 !"

  LangString MsgUninstall   ${LANG_ENGLISH} "This will uninstall SABnzbd from your system"

  LangString MsgRunAtStart  ${LANG_ENGLISH} "Run at startup"

  LangString MsgIcon        ${LANG_ENGLISH} "Desktop Icon"

  LangString MsgAssoc       ${LANG_ENGLISH} "NZB File association"

  LangString MsgDelProgram  ${LANG_ENGLISH} "Delete Program"

  LangString MsgDelSettings ${LANG_ENGLISH} "Delete Settings"

  LangString MsgNoRuntime   ${LANG_ENGLISH} "This system requires the Microsoft runtime library VC90 to be installed first. Do you want to do that now?"

  LangString MsgDLRuntime   ${LANG_ENGLISH} "Downloading Microsoft runtime installer..."

  LangString MsgDLError     ${LANG_ENGLISH} "Download error, retry?"

  LangString MsgDLNeed      ${LANG_ENGLISH} "Cannot install without runtime library, retry?"

  LangString MsgRemoveOld   ${LANG_ENGLISH} "You cannot overwrite an existing installation. $\n$\nClick `OK` to remove the previous version or `Cancel` to cancel this upgrade."

  LangString MsgRemoveOld2  ${LANG_ENGLISH} "Your settings and data will be preserved."

  LangString MsgLangCode    ${LANG_ENGLISH} "en"

Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd
