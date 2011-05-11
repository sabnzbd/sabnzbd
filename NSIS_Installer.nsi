; -*- coding: latin-1 -*-
;
; Copyright 2008-2011 The SABnzbd-Team <team@sabnzbd.org>
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
;DirText $(MsgSelectDir)

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
  !define MUI_FINISHPAGE_RUN_TEXT $(MsgStartSab)
  !define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README.txt"
  !define MUI_FINISHPAGE_SHOWREADME_TEXT $(MsgShowRelNote)
  ;!define MUI_FINISHPAGE_LINK "View the SABnzbdPlus Wiki"
  ;!define MUI_FINISHPAGE_LINK_LOCATION "http://wiki.sabnzbd.org/"
  !define MUI_FINISHPAGE_LINK $(MsgSupportUs)
  !define MUI_FINISHPAGE_LINK_LOCATION "http://www.sabnzbd.org/contribute/"

  !insertmacro MUI_PAGE_FINISH

  !insertmacro MUI_UNPAGE_CONFIRM
  !define MUI_UNPAGE_COMPONENTSPAGE_NODESC
  !insertmacro MUI_UNPAGE_COMPONENTS
  !insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------
;Languages

  ; Set supported languages
  !insertmacro MUI_LANGUAGE "English" ;first language is the default language
  !insertmacro MUI_LANGUAGE "French"
  !insertmacro MUI_LANGUAGE "German"
  !insertmacro MUI_LANGUAGE "Dutch"
  !insertmacro MUI_LANGUAGE "Swedish"
  !insertmacro MUI_LANGUAGE "Danish"
  !insertmacro MUI_LANGUAGE "NORWEGIAN"
  !insertmacro MUI_LANGUAGE "Romanian"


;--------------------------------
;Reserve Files

  ;If you are using solid compression, files that are required before
  ;the actual installation should be stored first in the data block,
  ;because this will make your installer start faster.

  !insertmacro MUI_RESERVEFILE_LANGDLL


Function LaunchLink
  ExecShell "" "$INSTDIR\SABnzbd.exe"
FunctionEnd

;--------------------------------
Function .onInit
  !insertmacro MUI_LANGDLL_DISPLAY

;make sure sabnzbd.exe isnt running..if so abort
  loop:
  StrCpy $0 "SABnzbd.exe"
  KillProc::FindProcesses
  StrCmp $0 "0" endcheck
  MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION $(MsgCloseSab) IDOK loop IDCANCEL exitinstall
  exitinstall:
  Abort
  endcheck:
FunctionEnd


Section "SABnzbd" SecDummy
SetOutPath "$INSTDIR"

IfFileExists $INSTDIR\sabnzbd.exe 0 endWarnExist
  IfFileExists $INSTDIR\locale\nl\LC_MESSAGES\SABnzbd.mo endWarnExist 0
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION $(MsgOldQueue) IDOK endWarnExist IDCANCEL 0
    Abort
endWarnExist:

; add files / whatever that need to be installed here.
File /r "dist\*"


WriteRegStr HKEY_LOCAL_MACHINE "SOFTWARE\SABnzbd" "" "$INSTDIR"
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "DisplayName" "SABnzbd ${SAB_VERSION}"
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "UninstallString" '"$INSTDIR\uninstall.exe"'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "DisplayVersion" '${SAB_VERSION}'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "Publisher" 'The SABnzbd Team'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "HelpLink" 'http://forums.sabnzbd.org/'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "URLInfoAbout" 'http://wiki.sabnzbd.org/'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "URLUpdateInfo" 'http://sabnzbd.org/'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "Comments" 'The automated Usenet download tool'
WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "DisplayIcon" '$INSTDIR\interfaces\Classic\templates\static\images\favicon.ico'
WriteRegDWORD HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Uninstall\SABnzbd" "EstimatedSize" 18400
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
  ${registerExtension} "$INSTDIR\nzb.ico" "$INSTDIR\SABnzbd.exe" ".nzb" "NZB File"
  ;${registerExtension} "$INSTDIR\SABnzbd.exe" ".nzb" "NZB File"
SectionEnd ; end of file association section

; begin uninstall settings/section
UninstallText $(MsgUninstall)

Section "un.$(MsgDelProgram)" Uninstall
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
  Delete   "$INSTDIR\email\email-de.tmpl"
  Delete   "$INSTDIR\email\email-en.tmpl"
  Delete   "$INSTDIR\email\email-nl.tmpl"
  Delete   "$INSTDIR\email\email-fr.tmpl"
  Delete   "$INSTDIR\email\email-sv.tmpl"
  Delete   "$INSTDIR\email\email-da.tmpl"
  Delete   "$INSTDIR\email\email-nb.tmpl"
  Delete   "$INSTDIR\email\rss-de.tmpl"
  Delete   "$INSTDIR\email\rss-en.tmpl"
  Delete   "$INSTDIR\email\rss-nl.tmpl"
  Delete   "$INSTDIR\email\rss-fr.tmpl"
  Delete   "$INSTDIR\email\rss-sv.tmpl"
  Delete   "$INSTDIR\email\rss-da.tmpl"
  Delete   "$INSTDIR\email\rss-nb.tmpl"
  RMDir    "$INSTDIR\email"
  RMDir /r "$INSTDIR\locale"
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
  RMDir  /r "$INSTDIR\po\email"
  RMDir  /r "$INSTDIR\po\main"
  RMDir  /r "$INSTDIR\po\nsis"
  RMDIR  "$INSTDIR\po"
  Delete "$INSTDIR\CHANGELOG.txt"
  Delete "$INSTDIR\COPYRIGHT.txt"
  Delete "$INSTDIR\email.tmpl"
  Delete "$INSTDIR\GPL2.txt"
  Delete "$INSTDIR\GPL3.txt"
  Delete "$INSTDIR\INSTALL.txt"
  Delete "$INSTDIR\ISSUES.txt"
  Delete "$INSTDIR\LICENSE.txt"
  Delete "$INSTDIR\nzbmatrix.txt"
  Delete "$INSTDIR\MSVCR71.dll"
  Delete "$INSTDIR\nzb.ico"
  Delete "$INSTDIR\PKG-INFO"
  Delete "$INSTDIR\python25.dll"
  Delete "$INSTDIR\python26.dll"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\SABnzbd-console.exe"
  Delete "$INSTDIR\SABnzbd.exe"
  Delete "$INSTDIR\SABnzbd-helper.exe"
  Delete "$INSTDIR\SABnzbd-service.exe"
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

Section "un.$(MsgDelSettings)" DelSettings
  Delete "$LOCALAPPDATA\sabnzbd\sabnzbd.ini"
  RMDir /r "$LOCALAPPDATA\sabnzbd\admin"
SectionEnd


Section "un.$(MsgDelLogs)" DelLogs
  RMDir /r "$LOCALAPPDATA\sabnzbd\logs"
SectionEnd


Section "un.$(MsgDelCache)" DelCache
  RMDir /r "$LOCALAPPDATA\sabnzbd\cache"
  RMDir "$LOCALAPPDATA\sabnzbd"
SectionEnd

; eof

;--------------------------------
;Language strings
; MsgWarnRunning 'Please close "SABnzbd.exe" first'
  LangString MsgStartSab    ${LANG_ENGLISH} "Start SABnzbd (hidden)"
  LangString MsgStartSab    ${LANG_DANISH} "Start SABnzbd"
  LangString MsgStartSab    ${LANG_GERMAN} "SABnzbd starten (unsichtbar)"
  LangString MsgStartSab    ${LANG_FRENCH} "Démarrer SABnzbd (caché)"
  LangString MsgStartSab    ${LANG_NORWEGIAN} "Start SABnzbd (hidden)"
  LangString MsgStartSab    ${LANG_DUTCH} "Start SABnzbd (verborgen)"
  LangString MsgStartSab    ${LANG_ROMANIAN} "Porneste SABnzbd (ascuns)"
  LangString MsgStartSab    ${LANG_SWEDISH} "Starta SABnzbd (dold)"

  LangString MsgShowRelNote ${LANG_ENGLISH} "Show Release Notes"
  LangString MsgShowRelNote ${LANG_DANISH} "Vis udgivelsesbemærkninger"
  LangString MsgShowRelNote ${LANG_GERMAN} "Versionshinweise anzeigen"
  LangString MsgShowRelNote ${LANG_FRENCH} "Afficher les notes de version"
  LangString MsgShowRelNote ${LANG_NORWEGIAN} "Show Release Notes"
  LangString MsgShowRelNote ${LANG_DUTCH} "Toon vrijgave bericht"
  LangString MsgShowRelNote ${LANG_ROMANIAN} "Aratã Notele de Publicare"
  LangString MsgShowRelNote ${LANG_SWEDISH} "Visa release noteringar"

  LangString MsgSupportUs   ${LANG_ENGLISH} "Support the project, Donate!"
  LangString MsgSupportUs   ${LANG_DANISH} "Støtte projektet, donere!"
  LangString MsgSupportUs   ${LANG_GERMAN} "Bitte unterstützen Sie das Projekt durch eine Spende!"
  LangString MsgSupportUs   ${LANG_FRENCH} "Supportez le projet, faites un don !"
  LangString MsgSupportUs   ${LANG_NORWEGIAN} "Support the project, Donate!"
  LangString MsgSupportUs   ${LANG_DUTCH} "Steun het project, Doneer!"
  LangString MsgSupportUs   ${LANG_ROMANIAN} "Sustine proiectul, Doneazã!"
  LangString MsgSupportUs   ${LANG_SWEDISH} "Donera och stöd detta projekt!"

  LangString MsgCloseSab    ${LANG_ENGLISH} "Please close $\"SABnzbd.exe$\" first"
  LangString MsgCloseSab    ${LANG_DANISH} "Luk 'SABnzbd.exe' først"
  LangString MsgCloseSab    ${LANG_GERMAN} "Schliessen Sie bitte zuerst $\"SABnzbd.exe$\"."
  LangString MsgCloseSab    ${LANG_FRENCH} "Quittez $\"SABnzbd.exe$\" avant l'installation, SVP"
  LangString MsgCloseSab    ${LANG_NORWEGIAN} "Please close $\"SABnzbd.exe$\" first"
  LangString MsgCloseSab    ${LANG_DUTCH} "Sluit $\"SABnzbd.exe$\" eerst af"
  LangString MsgCloseSab    ${LANG_ROMANIAN} "Închideti mai întâi $\"SABnzbd.exe$\""
  LangString MsgCloseSab    ${LANG_SWEDISH} "Var vänlig stäng $\"SABnzbd.exe$\" först"

  LangString MsgOldQueue    ${LANG_ENGLISH} "                  >>>> WARNING <<<<$\r$\n$\r$\nPlease, first check the release notes or go to http://wiki.sabnzbd.org/introducing-0-6-0 !"
  LangString MsgOldQueue    ${LANG_DANISH} "                  >>>> WARNING <<<<$\r$\n$\r$\nVenligst, kontrollér først udgivelsesnoter eller gå til http://wiki.sabnzbd.org/introducing-0-6-0 !"
  LangString MsgOldQueue    ${LANG_GERMAN} "                  >>>> WARNUNG <<<<$\r$\n$\r$\nBitte zuerst die Versionsanmerkungen lesen oder $\"http://wiki.sabnzbd.org/introducing-0-6-0 besuchen!$\""
  LangString MsgOldQueue    ${LANG_FRENCH} "                  >>>> AVERTISSEMENT<<<<$\r$\n$\r$\nS'il vous plaît, vérifiez d'abord les notes de version ou visiter http://wiki.sabnzbd.org/introducing-0-6-0 !"
  LangString MsgOldQueue    ${LANG_NORWEGIAN} "                  >>>> WARNING <<<<$\r$\n$\r$\nPlease, first check the release notes or go to http://wiki.sabnzbd.org/introducing-0-6-0 !"
  LangString MsgOldQueue    ${LANG_DUTCH} "                  >>>> WAARSCHUWING <<<<$\r$\n$\r$\nLees eerst het vrijgave bericht of ga naar $\"http://wiki.sabnzbd.org/introducing-0-6-0 !$\""
  LangString MsgOldQueue    ${LANG_ROMANIAN} "                  >>>> ATENTIE <<<<$\r$\n$\r$\nVã rugãm, verificati mai întâi notele de publicare sau mergeti la http://wiki.sabnzbd.org/introducing-0-6-0 !"
  LangString MsgOldQueue    ${LANG_SWEDISH} "                  >>>> VARNING <<<<$\r$\n$\r$\nVar vänlig och läs versions noteringarna eller gå till http://wiki.sabnzbd.org/introducing-0-6-0 !"

  LangString MsgUninstall   ${LANG_ENGLISH} "This will uninstall SABnzbd from your system"
  LangString MsgUninstall   ${LANG_DANISH} "Dette vil afinstallere SABnzbd fra dit system"
  LangString MsgUninstall   ${LANG_GERMAN} "Dies entfernt SABnzbd von Ihrem System"
  LangString MsgUninstall   ${LANG_FRENCH} "Ceci désinstallera SABnzbd de votre système"
  LangString MsgUninstall   ${LANG_NORWEGIAN} "This will uninstall SABnzbd from your system"
  LangString MsgUninstall   ${LANG_DUTCH} "Dit verwijdert SABnzbd van je systeem"
  LangString MsgUninstall   ${LANG_ROMANIAN} "Acest lucru va dezinstala SABnzbd din sistem"
  LangString MsgUninstall   ${LANG_SWEDISH} "Detta kommer att avinstallera SABnzbd från systemet"

  LangString MsgRunAtStart  ${LANG_ENGLISH} "Run at startup"
  LangString MsgRunAtStart  ${LANG_DANISH} "Kør ved opstart"
  LangString MsgRunAtStart  ${LANG_GERMAN} "Beim Systemstart ausführen"
  LangString MsgRunAtStart  ${LANG_FRENCH} "Lancer au démarrage"
  LangString MsgRunAtStart  ${LANG_NORWEGIAN} "Run at startup"
  LangString MsgRunAtStart  ${LANG_DUTCH} "Opstarten bij systeem start"
  LangString MsgRunAtStart  ${LANG_ROMANIAN} "Executare la pornire"
  LangString MsgRunAtStart  ${LANG_SWEDISH} "Kör vid uppstart"

  LangString MsgIcon        ${LANG_ENGLISH} "Desktop Icon"
  LangString MsgIcon        ${LANG_DANISH} "Skrivebords ikon"
  LangString MsgIcon        ${LANG_GERMAN} "Desktop-Symbol"
  LangString MsgIcon        ${LANG_FRENCH} "Icône sur le Bureau"
  LangString MsgIcon        ${LANG_NORWEGIAN} "Desktop Icon"
  LangString MsgIcon        ${LANG_DUTCH} "Pictogram op bureaublad"
  LangString MsgIcon        ${LANG_ROMANIAN} "Icoanã Desktop"
  LangString MsgIcon        ${LANG_SWEDISH} "Skrivbordsikon"

  LangString MsgAssoc       ${LANG_ENGLISH} "NZB File association"
  LangString MsgAssoc       ${LANG_DANISH} "NZB filtilknytning"
  LangString MsgAssoc       ${LANG_GERMAN} "Mit NZB-Dateien verknüpfen"
  LangString MsgAssoc       ${LANG_FRENCH} "Association des fichiers NZB"
  LangString MsgAssoc       ${LANG_NORWEGIAN} "NZB File association"
  LangString MsgAssoc       ${LANG_DUTCH} "NZB bestanden koppelen aan SABnzbd"
  LangString MsgAssoc       ${LANG_ROMANIAN} "Asociere cu Fisierele NZB"
  LangString MsgAssoc       ${LANG_SWEDISH} "NZB Filassosication"

  LangString MsgDelProgram  ${LANG_ENGLISH} "Delete Program"
  LangString MsgDelProgram  ${LANG_DANISH} "Slet program"
  LangString MsgDelProgram  ${LANG_GERMAN} "Programm löschen"
  LangString MsgDelProgram  ${LANG_FRENCH} "Supprimer le programme"
  LangString MsgDelProgram  ${LANG_NORWEGIAN} "Delete Program"
  LangString MsgDelProgram  ${LANG_DUTCH} "Verwijder programma"
  LangString MsgDelProgram  ${LANG_ROMANIAN} "Sterge Program"
  LangString MsgDelProgram  ${LANG_SWEDISH} "Ta bort programmet"

  LangString MsgDelSettings ${LANG_ENGLISH} "Delete Settings"
  LangString MsgDelSettings ${LANG_DANISH} "Slet instillinger"
  LangString MsgDelSettings ${LANG_GERMAN} "Einstellungen löschen"
  LangString MsgDelSettings ${LANG_FRENCH} "Supprimer les Paramètres"
  LangString MsgDelSettings ${LANG_NORWEGIAN} "Delete Settings"
  LangString MsgDelSettings ${LANG_DUTCH} "Verwijder instellingen"
  LangString MsgDelSettings ${LANG_ROMANIAN} "Stergeti Setãri"
  LangString MsgDelSettings ${LANG_SWEDISH} "Ta bort inställningar"

  LangString MsgDelLogs     ${LANG_ENGLISH} "Delete Logs"
  LangString MsgDelLogs     ${LANG_DANISH} "Slet logs"
  LangString MsgDelLogs     ${LANG_GERMAN} "Protokoll löschen"
  LangString MsgDelLogs     ${LANG_FRENCH} "Supprimer les logs"
  LangString MsgDelLogs     ${LANG_NORWEGIAN} "Delete Logs"
  LangString MsgDelLogs     ${LANG_DUTCH} "Verwijder logging"
  LangString MsgDelLogs     ${LANG_ROMANIAN} "Stergeti Activitate"
  LangString MsgDelLogs     ${LANG_SWEDISH} "Ta bort logg"

  LangString MsgDelCache    ${LANG_ENGLISH} "Delete Cache"
  LangString MsgDelCache    ${LANG_DANISH} "Slet hukommelse"
  LangString MsgDelCache    ${LANG_GERMAN} "Cache löschen"
  LangString MsgDelCache    ${LANG_FRENCH} "Supprimer le Cache"
  LangString MsgDelCache    ${LANG_NORWEGIAN} "Delete Cache"
  LangString MsgDelCache    ${LANG_DUTCH} "Verwijder Cache"
  LangString MsgDelCache    ${LANG_ROMANIAN} "Stergeti Cache"
  LangString MsgDelCache    ${LANG_SWEDISH} "Ta bort temporär-mapp"

Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd
