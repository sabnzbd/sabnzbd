; -*- coding: utf-8 -*-
;
; Copyright 2008-2015 The SABnzbd-Team (sabnzbd.org)
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

Unicode true

!addplugindir builder\win\nsis\Plugins
!addincludedir builder\win\nsis\Include

!include "MUI2.nsh"
!include "registerExtension.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"
!include "nsProcess.nsh"
!include "x64.nsh"
!include "servicelib.nsh"

;------------------------------------------------------------------
;
; Macro for removing existing and the current installation
; It shared by the installer and the uninstaller.
;
!define RemovePrev "!insertmacro RemovePrev"
!macro RemovePrev idir
  ; Remove the whole dir
  ; Users should not be putting stuff here!
  RMDir /r "${idir}"
!macroend

!define RemovePrevShortcuts "!insertmacro RemovePrevShortcuts"
!macro RemovePrevShortcuts
  ; Remove shortcuts, starting with current user ones (from old installs)
  SetShellVarContext current
  !insertmacro MUI_STARTMENU_GETFOLDER Application $MUI_TEMP
  Delete "$SMPROGRAMS\$MUI_TEMP\SABnzbd.lnk"
  Delete "$SMPROGRAMS\$MUI_TEMP\Uninstall.lnk"
  Delete "$SMPROGRAMS\$MUI_TEMP\SABnzbd - SafeMode.lnk"
  Delete "$SMPROGRAMS\$MUI_TEMP\SABnzbd - Documentation.url"
  RMDir  "$SMPROGRAMS\$MUI_TEMP"
  Delete "$SMPROGRAMS\Startup\SABnzbd.lnk"
  Delete "$DESKTOP\SABnzbd.lnk"

  SetShellVarContext all
  !insertmacro MUI_STARTMENU_GETFOLDER Application $MUI_TEMP
  Delete "$SMPROGRAMS\$MUI_TEMP\SABnzbd.lnk"
  Delete "$SMPROGRAMS\$MUI_TEMP\Uninstall.lnk"
  Delete "$SMPROGRAMS\$MUI_TEMP\SABnzbd - SafeMode.lnk"
  Delete "$SMPROGRAMS\$MUI_TEMP\SABnzbd - Documentation.url"
  RMDir  "$SMPROGRAMS\$MUI_TEMP"
  Delete "$SMPROGRAMS\Startup\SABnzbd.lnk"
  Delete "$DESKTOP\SABnzbd.lnk"
!macroend

;------------------------------------------------------------------
; Define names of the product
  Name "SABnzbd ${SAB_VERSION}"
  VIProductVersion "${SAB_VERSIONKEY}"
  VIFileVersion "${SAB_VERSIONKEY}"

  VIAddVersionKey "Comments" "SABnzbd ${SAB_VERSION}"
  VIAddVersionKey "CompanyName" "The SABnzbd-Team"
  VIAddVersionKey "FileDescription" "SABnzbd ${SAB_VERSION}"
  VIAddVersionKey "FileVersion" "${SAB_VERSION}"
  VIAddVersionKey "LegalCopyright" "The SABnzbd-Team"
  VIAddVersionKey "ProductName" "SABnzbd ${SAB_VERSION}"
  VIAddVersionKey "ProductVersion" "${SAB_VERSION}"

  OutFile "${SAB_FILE}"
  InstallDir "$PROGRAMFILES\SABnzbd"

;------------------------------------------------------------------
; Some default compiler settings (uncomment and change at will):
  SetCompress auto ; (can be off or force)
  SetDatablockOptimize on ; (can be off)
  CRCCheck on ; (can be off)
  AutoCloseWindow false ; (can be true for the window go away automatically at end)
  ShowInstDetails hide ; (can be show to have them shown, or nevershow to disable)
  SetDateSave off ; (can be on to have files restored to their original date)
  WindowIcon on
  SpaceTexts none


;------------------------------------------------------------------
; Vista/Win7 redirects $SMPROGRAMS to all users without this
  RequestExecutionLevel admin
  FileErrorText "If you have no admin rights, try to install into a user directory."

;------------------------------------------------------------------
;Variables
  Var MUI_TEMP
  Var STARTMENU_FOLDER
  Var PREV_INST_DIR

;------------------------------------------------------------------
;Interface Settings

  !define MUI_ABORTWARNING

  ;Show all languages, despite user's codepage
  !define MUI_LANGDLL_ALLLANGUAGES

  !define MUI_ICON "dist\SABnzbd\icons\sabnzbd.ico"


;--------------------------------
;Pages

  !insertmacro MUI_PAGE_LICENSE "dist\SABnzbd\LICENSE.txt"
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
  ; !define MUI_FINISHPAGE_RUN
  ; !define MUI_FINISHPAGE_RUN_FUNCTION PageFinishRun
  ; !define MUI_FINISHPAGE_RUN_TEXT $(MsgRunSAB)
  !define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README.txt"
  !define MUI_FINISHPAGE_SHOWREADME_TEXT $(MsgShowRelNote)
  !define MUI_FINISHPAGE_LINK $(MsgSupportUs)
  !define MUI_FINISHPAGE_LINK_LOCATION "https://sabnzbd.org/donate"

  !insertmacro MUI_PAGE_FINISH

  !insertmacro MUI_UNPAGE_CONFIRM
  !define MUI_UNPAGE_COMPONENTSPAGE_NODESC
  !insertmacro MUI_UNPAGE_COMPONENTS
  !insertmacro MUI_UNPAGE_INSTFILES

;------------------------------------------------------------------
; Run as user-level at end of install
; DOES NOT WORK
; Function PageFinishRun
;   !insertmacro UAC_AsUser_ExecShell "" "$INSTDIR\SABnzbd.exe" "" "" ""
; FunctionEnd


;------------------------------------------------------------------
; Set supported languages
;
; If you edit this list you also need to edit apireg.py in SABnzbd!
;
  !insertmacro MUI_LANGUAGE "English" ;first language is the default language
  !insertmacro MUI_LANGUAGE "French"
  !insertmacro MUI_LANGUAGE "German"
  !insertmacro MUI_LANGUAGE "Dutch"
  !insertmacro MUI_LANGUAGE "Finnish"
  !insertmacro MUI_LANGUAGE "Polish"
  !insertmacro MUI_LANGUAGE "Swedish"
  !insertmacro MUI_LANGUAGE "Danish"
  !insertmacro MUI_LANGUAGE "Italian"
  !insertmacro MUI_LANGUAGE "Norwegian"
  !insertmacro MUI_LANGUAGE "Romanian"
  !insertmacro MUI_LANGUAGE "Spanish"
  !insertmacro MUI_LANGUAGE "PortugueseBR"
  !insertmacro MUI_LANGUAGE "Serbian"
  !insertmacro MUI_LANGUAGE "Hebrew"
  !insertmacro MUI_LANGUAGE "Russian"
  !insertmacro MUI_LANGUAGE "Czech"
  !insertmacro MUI_LANGUAGE "SimpChinese"



;------------------------------------------------------------------
;Reserve Files
  ;If you are using solid compression, files that are required before
  ;the actual installation should be stored first in the data block,
  ;because this will make your installer start faster.

  !insertmacro MUI_RESERVEFILE_LANGDLL


;------------------------------------------------------------------
; SECTION main program
;
Section "SABnzbd" SecDummy

  SetOutPath "$INSTDIR"
  SetShellVarContext all

  DetailPrint $(MsgShutting)

  ;------------------------------------------------------------------
  ; Shutdown any running service

  !insertmacro SERVICE "stop" "SABnzbd" ""

  ;------------------------------------------------------------------
  ; Terminate SABnzbd.exe
  loop:
    ${nsProcess::FindProcess} "SABnzbd.exe" $R0
    StrCmp $R0 0 0 endcheck
    ${nsProcess::CloseProcess} "SABnzbd.exe" $R0
    Sleep 500
    Goto loop
  endcheck:
  ${nsProcess::Unload}

  ;------------------------------------------------------------------
  ; Make sure old versions are gone (reg-key already read in onInt)
  StrCmp $PREV_INST_DIR "" noPrevInstallRemove
    ${RemovePrev} "$PREV_INST_DIR"
    Goto continueSetupAfterRemove

  ;------------------------------------------------------------------
  ; Add firewall rules for new installs
  noPrevInstallRemove:
    liteFirewallW::AddRule "$INSTDIR\SABnzbd.exe" "SABnzbd"
    liteFirewallW::AddRule "$INSTDIR\SABnzbd-console.exe" "SABnzbd-console"

  continueSetupAfterRemove:

  ; add files / whatever that need to be installed here.
  File /r "dist\SABnzbd\*"

  ;------------------------------------------------------------------
  ; Add to registry
  WriteRegStr HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd" "" "$INSTDIR"
  WriteRegStr HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd" "Installer Language" "$(MsgLangCode)"
  WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "DisplayName" "SABnzbd ${SAB_VERSION}"
  WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "DisplayVersion" '${SAB_VERSION}'
  WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "Publisher" 'The SABnzbd-Team'
  WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "HelpLink" 'https://forums.sabnzbd.org/'
  WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "URLInfoAbout" 'https://sabnzbd.org/wiki/'
  WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "URLUpdateInfo" 'https://sabnzbd.org/'
  WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "Comments" 'The automated Usenet download tool'
  WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "DisplayIcon" '$INSTDIR\icons\sabnzbd.ico'

  WriteRegDWORD HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "EstimatedSize"  40674
  WriteRegDWORD HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "NoRepair" -1
  WriteRegDWORD HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "NoModify" -1

  WriteRegStr HKEY_CURRENT_USER "Software\Classes\AppUserModelId\SABnzbd" "DisplayName" "SABnzbd"
  WriteRegStr HKEY_CURRENT_USER "Software\Classes\AppUserModelId\SABnzbd" "IconUri" '$INSTDIR\icons\sabnzbd16_32.ico'

  ; write out uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
    ;Create shortcuts
    CreateDirectory "$SMPROGRAMS\$STARTMENU_FOLDER"
    CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\SABnzbd.lnk" "$INSTDIR\SABnzbd.exe"
    CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\SABnzbd - SafeMode.lnk" "$INSTDIR\SABnzbd.exe" "--server 127.0.0.1:8080 -b1 --no-login"
    WriteINIStr "$SMPROGRAMS\$STARTMENU_FOLDER\SABnzbd - Documentation.url" "InternetShortcut" "URL" "https://sabnzbd.org/wiki/"
    CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  !insertmacro MUI_STARTMENU_WRITE_END
SectionEnd ; end of default section

Section $(MsgIcon) desktop
  CreateShortCut "$DESKTOP\SABnzbd.lnk" "$INSTDIR\SABnzbd.exe"
SectionEnd ; end of desktop icon section

Section $(MsgAssoc) assoc
  ${registerExtension} "$INSTDIR\icons\nzb.ico" "$INSTDIR\SABnzbd.exe" ".nzb" "NZB File"
  ${RefreshShellIcons}
SectionEnd ; end of file association section

Section /o $(MsgRunAtStart) startup
  CreateShortCut "$SMPROGRAMS\Startup\SABnzbd.lnk" "$INSTDIR\SABnzbd.exe" "-b0"
SectionEnd ;

;------------------------------------------------------------------
Function .onInit
  ; We need to modify the dir here for X64
  ${If} ${RunningX64}
      StrCpy $INSTDIR "$PROGRAMFILES64\SABnzbd"
  ${Else}
      MessageBox MB_OK|MB_ICONSTOP $(MsgOnly64bit)
      Abort
  ${EndIf}

  ; Python 3.9 no longer supports Windows 7
  ${If} ${AtMostWin8}
      MessageBox MB_OK|MB_ICONSTOP $(MsgNoWin7)
      Abort
  ${EndIf}

  ;------------------------------------------------------------------
  ; Change settings based on if SAB was already installed
  ReadRegStr $PREV_INST_DIR HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd" ""
  StrCmp $PREV_INST_DIR "" noPrevInstall
    ; We want to use the user's custom dir if he used one
    StrCmp $PREV_INST_DIR "$PROGRAMFILES\SABnzbd" noSpecialDir
      StrCmp $PREV_INST_DIR "$PROGRAMFILES64\SABnzbd" noSpecialDir
        ; Set what the user had before
        StrCpy $INSTDIR "$PREV_INST_DIR"
    noSpecialDir:

    ;------------------------------------------------------------------
    ; Check what the user has currently set for install options
    SetShellVarContext current
    IfFileExists "$SMPROGRAMS\Startup\SABnzbd.lnk" 0 endCheckStartupCurrent
      SectionSetFlags ${startup} 1
    endCheckStartupCurrent:
    SetShellVarContext all
    IfFileExists "$SMPROGRAMS\Startup\SABnzbd.lnk" 0 endCheckStartup
      SectionSetFlags ${startup} 1
    endCheckStartup:

    SetShellVarContext current
    IfFileExists "$DESKTOP\SABnzbd.lnk" endCheckDesktop 0
      ; If not present for current user, first check all user folder
      SetShellVarContext all
      IfFileExists "$DESKTOP\SABnzbd.lnk" endCheckDesktop 0
        SectionSetFlags ${desktop} 0 ; SAB is installed but desktop-icon not, so uncheck it
    endCheckDesktop:
    SetShellVarContext all

    Push $1
    ReadRegStr $1 HKCR ".nzb" ""  ; read current file association
    StrCmp "$1" "NZB File" noPrevInstall 0
      SectionSetFlags ${assoc} 0 ; Uncheck it when it wasn't checked before
  noPrevInstall:

  ;--------------------------------
  ; Display language chooser
  !insertmacro MUI_LANGDLL_DISPLAY

  ;------------------------------------------------------------------
  ; Tell users about the service change
  ;
  !insertmacro SERVICE "installed" "SABHelper" ""
  Pop $0 ;response
  ${If} $0 == true
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION $(MsgServChange) IDOK removeservices IDCANCEL exitinstall
    exitinstall:
      Abort
    removeservices:
        !insertmacro SERVICE "delete" "SABHelper" ""
        !insertmacro SERVICE "delete" "SABnzbd" ""
  ${EndIf}

FunctionEnd

;------------------------------------------------------------------
; Show the shortcuts at end of install so user can start SABnzbd
; This is instead of us trying to run SAB from the installer
;
Function .onInstSuccess
  ExecShell "open" "$SMPROGRAMS\$STARTMENU_FOLDER"
FunctionEnd

;--------------------------------
; begin uninstall settings/section
UninstallText $(MsgUninstall)

Section "un.$(MsgDelProgram)" Uninstall
;make sure sabnzbd.exe isn't running..if so shut it down
  DetailPrint $(MsgShutting)
  ${nsProcess::KillProcess} "SABnzbd.exe" $R0
  ${nsProcess::Unload}

  ; add delete commands to delete whatever files/registry keys/etc you installed here.
  Delete "$INSTDIR\uninstall.exe"
  DeleteRegKey HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd"
  DeleteRegKey HKEY_LOCAL_MACHINE "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd"
  DeleteRegKey HKEY_CURRENT_USER "Software\Classes\AppUserModelId\SABnzbd"
  DeleteRegKey HKEY_CURRENT_USER "Software\SABnzbd"

  ${RemovePrev} "$INSTDIR"
  ${RemovePrevShortcuts}

  ; Remove firewall entries
  liteFirewallW::RemoveRule "$INSTDIR\SABnzbd.exe" "SABnzbd"
  liteFirewallW::RemoveRule "$INSTDIR\SABnzbd-console.exe" "SABnzbd-console"

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
  LangString MsgShowRelNote ${LANG_ENGLISH} "Show Release Notes"

  LangString MsgSupportUs   ${LANG_ENGLISH} "Support the project, Donate!"

  LangString MsgServChange  ${LANG_ENGLISH} "The SABnzbd Windows Service changed in SABnzbd 3.0.0. $\nYou will need to reinstall the SABnzbd service. $\n$\nClick `OK` to remove the existing services or `Cancel` to cancel this upgrade."

  LangString MsgOnly64bit   ${LANG_ENGLISH} "SABnzbd only supports 64-bit Windows."

  LangString MsgNoWin7      ${LANG_ENGLISH} "SABnzbd only supports Windows 8.1 and above."

  LangString MsgShutting    ${LANG_ENGLISH} "Shutting down SABnzbd"

  LangString MsgUninstall   ${LANG_ENGLISH} "This will uninstall SABnzbd from your system"

  LangString MsgRunAtStart  ${LANG_ENGLISH} "Run at startup"

  LangString MsgIcon        ${LANG_ENGLISH} "Desktop Icon"

  LangString MsgAssoc       ${LANG_ENGLISH} "NZB File association"

  LangString MsgDelProgram  ${LANG_ENGLISH} "Delete Program"

  LangString MsgDelSettings ${LANG_ENGLISH} "Delete Settings"

  LangString MsgLangCode    ${LANG_ENGLISH} "en"

Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd
