; -*- coding: utf-8 -*-
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
  Delete   "${idir}\email\email-ro.tmpl"
  Delete   "${idir}\email\email-sr.tmpl"
  Delete   "${idir}\email\email-es.tmpl"
  Delete   "${idir}\email\email-sr.tmpl"
  Delete   "${idir}\email\email-ru.tmpl"
  Delete   "${idir}\email\rss-de.tmpl"
  Delete   "${idir}\email\rss-en.tmpl"
  Delete   "${idir}\email\rss-nl.tmpl"
  Delete   "${idir}\email\rss-fr.tmpl"
  Delete   "${idir}\email\rss-sv.tmpl"
  Delete   "${idir}\email\rss-da.tmpl"
  Delete   "${idir}\email\rss-nb.tmpl"
  Delete   "${idir}\email\rss-ro.tmpl"
  Delete   "${idir}\email\rss-sr.tmpl"
  Delete   "${idir}\email\rss-es.tmpl"
  Delete   "${idir}\email\rss-sr.tmpl"
  Delete   "${idir}\email\rss-ru.tmpl"
  Delete   "${idir}\email\badfetch-da.tmpl"
  Delete   "${idir}\email\badfetch-de.tmpl"
  Delete   "${idir}\email\badfetch-en.tmpl"
  Delete   "${idir}\email\badfetch-fr.tmpl"
  Delete   "${idir}\email\badfetch-nb.tmpl"
  Delete   "${idir}\email\badfetch-nl.tmpl"
  Delete   "${idir}\email\badfetch-ro.tmpl"
  Delete   "${idir}\email\badfetch-sr.tmpl"
  Delete   "${idir}\email\badfetch-sv.tmpl"
  Delete   "${idir}\email\badfetch-es.tmpl"
  Delete   "${idir}\email\badfetch-sr.tmpl"
  Delete   "${idir}\email\badfetch-ru.tmpl"
  RMDir    "${idir}\email"
  RMDir /r "${idir}\locale"
  RMDir /r "${idir}\interfaces\Classic"
  RMDir /r "${idir}\interfaces\Plush"
  RMDir /r "${idir}\interfaces\smpl"
  RMDir /r "${idir}\interfaces\Mobile"
  RMDir /r "${idir}\interfaces\wizard"
  RMDir /r "${idir}\interfaces\Config"
  RMDir    "${idir}\interfaces"
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
  !insertmacro MUI_LANGUAGE "Swedish"
  !insertmacro MUI_LANGUAGE "Danish"
  !insertmacro MUI_LANGUAGE "NORWEGIAN"
  !insertmacro MUI_LANGUAGE "Romanian"
  !insertmacro MUI_LANGUAGE "Serbian"
  !insertmacro MUI_LANGUAGE "Russian"


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
  IfFileExists $INSTDIR\python25.dll 0 endWarnExist
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "$(MsgRemoveOld)$\n$\n$(MsgRemoveOld2)" IDOK uninst
    Abort
uninst:
    ${RemovePrev} "$INSTDIR"
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


SectionEnd ; end of uninstall section

Section "un.$(MsgDelSettings)" DelSettings
  DetailPrint "Uninstall settings $LOCALAPPDATA"
  Delete "$LOCALAPPDATA\sabnzbd\sabnzbd.ini"
  RMDir /r "$LOCALAPPDATA\sabnzbd"
SectionEnd

; eof

;--------------------------------
;Language strings
  LangString MsgGoWiki      ${LANG_ENGLISH} "Go to the SABnzbd Wiki"
  LangString MsgGoWiki      ${LANG_DANISH} "Go to the SABnzbd Wiki"
  LangString MsgGoWiki      ${LANG_GERMAN} "Go to the SABnzbd Wiki"
  LangString MsgGoWiki      ${LANG_SPANISH} "Go to the SABnzbd Wiki"
  LangString MsgGoWiki      ${LANG_FRENCH} "Go to the SABnzbd Wiki"
  LangString MsgGoWiki      ${LANG_NORWEGIAN} "Go to the SABnzbd Wiki"
  LangString MsgGoWiki      ${LANG_DUTCH} "Go to the SABnzbd Wiki"
  LangString MsgGoWiki      ${LANG_ROMANIAN} "Go to the SABnzbd Wiki"
  LangString MsgGoWiki      ${LANG_RUSSIAN} "Go to the SABnzbd Wiki"
  LangString MsgGoWiki      ${LANG_SERBIAN} "Go to the SABnzbd Wiki"
  LangString MsgGoWiki      ${LANG_SWEDISH} "Go to the SABnzbd Wiki"

  LangString MsgShowRelNote ${LANG_ENGLISH} "Show Release Notes"
  LangString MsgShowRelNote ${LANG_DANISH} "Vis udgivelsesbemærkninger"
  LangString MsgShowRelNote ${LANG_GERMAN} "Versionshinweise anzeigen"
  LangString MsgShowRelNote ${LANG_SPANISH} "Mostrar notas de la versión"
  LangString MsgShowRelNote ${LANG_FRENCH} "Afficher les notes de version"
  LangString MsgShowRelNote ${LANG_NORWEGIAN} "Show Release Notes"
  LangString MsgShowRelNote ${LANG_DUTCH} "Toon vrijgave bericht"
  LangString MsgShowRelNote ${LANG_ROMANIAN} "Aratã Notele de Publicare"
  LangString MsgShowRelNote ${LANG_RUSSIAN} "Показать заметки о выпуске"
  LangString MsgShowRelNote ${LANG_SERBIAN} "Прикажи белешке о издању"
  LangString MsgShowRelNote ${LANG_SWEDISH} "Visa release noteringar"

  LangString MsgSupportUs   ${LANG_ENGLISH} "Support the project, Donate!"
  LangString MsgSupportUs   ${LANG_DANISH} "Støtte projektet, donere!"
  LangString MsgSupportUs   ${LANG_GERMAN} "Bitte unterstützen Sie das Projekt durch eine Spende!"
  LangString MsgSupportUs   ${LANG_SPANISH} "Apoya el proyecto, haz una donación!"
  LangString MsgSupportUs   ${LANG_FRENCH} "Supportez le projet, faites un don !"
  LangString MsgSupportUs   ${LANG_NORWEGIAN} "Support the project, Donate!"
  LangString MsgSupportUs   ${LANG_DUTCH} "Steun het project, Doneer!"
  LangString MsgSupportUs   ${LANG_ROMANIAN} "Sustine proiectul, Doneazã!"
  LangString MsgSupportUs   ${LANG_RUSSIAN} "Поддержите проект. Сделайте пожертвование!"
  LangString MsgSupportUs   ${LANG_SERBIAN} "Подржите пројекат, дајте добровољан прилог!"
  LangString MsgSupportUs   ${LANG_SWEDISH} "Donera och stöd detta projekt!"

  LangString MsgCloseSab    ${LANG_ENGLISH} "Please close $\"SABnzbd.exe$\" first"
  LangString MsgCloseSab    ${LANG_DANISH} "Luk 'SABnzbd.exe' først"
  LangString MsgCloseSab    ${LANG_GERMAN} "Schliessen Sie bitte zuerst $\"SABnzbd.exe$\"."
  LangString MsgCloseSab    ${LANG_SPANISH} "Por favor, cierra $\"SABnzbd.exe$\" primero"
  LangString MsgCloseSab    ${LANG_FRENCH} "Quittez $\"SABnzbd.exe$\" avant l'installation, SVP"
  LangString MsgCloseSab    ${LANG_NORWEGIAN} "Please close $\"SABnzbd.exe$\" first"
  LangString MsgCloseSab    ${LANG_DUTCH} "Sluit $\"SABnzbd.exe$\" eerst af"
  LangString MsgCloseSab    ${LANG_ROMANIAN} "Închideti mai întâi $\"SABnzbd.exe$\""
  LangString MsgCloseSab    ${LANG_RUSSIAN} "Завершите сначала работу процесса SABnzbd.exe"
  LangString MsgCloseSab    ${LANG_SERBIAN} "Прво затворите „SABnzbd.exe“"
  LangString MsgCloseSab    ${LANG_SWEDISH} "Var vänlig stäng $\"SABnzbd.exe$\" först"

  LangString MsgOldQueue    ${LANG_ENGLISH} "                  >>>> WARNING <<<<$\r$\n$\r$\nPlease, first check the release notes or go to http://wiki.sabnzbd.org/introducing-0-7-0 !"
  LangString MsgOldQueue    ${LANG_DANISH} "                  >>>> WARNING <<<<$\r$\n$\r$\nVenligst, kontrollér først udgivelsesnoter eller gå til http://wiki.sabnzbd.org/introducing-0-7-0 !"
  LangString MsgOldQueue    ${LANG_GERMAN} "                  >>>> WARNUNG <<<<$\r$\n$\r$\nBitte zuerst die Versionsanmerkungen lesen oder $\"http://wiki.sabnzbd.org/introducing-0-7-0 besuchen!$\""
  LangString MsgOldQueue    ${LANG_SPANISH} "                  >>>> ADVERTENCIA <<<<$\ r $\ n $\ r $\ nPor favor, compruebe primero las notas de lanzamiento o ir a http://wiki.sabnzbd.org/introducing-0-7-0!"
  LangString MsgOldQueue    ${LANG_FRENCH} "                  >>>> AVERTISSEMENT<<<<$\r$\n$\r$\nS'il vous plaît, vérifiez d'abord les notes de version ou visiter http://wiki.sabnzbd.org/introducing-0-7-0 !"
  LangString MsgOldQueue    ${LANG_NORWEGIAN} "                  >>>> WARNING <<<<$\r$\n$\r$\nPlease, first check the release notes or go to http://wiki.sabnzbd.org/introducing-0-7-0 !"
  LangString MsgOldQueue    ${LANG_DUTCH} "                  >>>> WAARSCHUWING <<<<$\r$\n$\r$\nLees eerst het vrijgave bericht of ga naar $\"http://wiki.sabnzbd.org/introducing-0-7-0 !$\""
  LangString MsgOldQueue    ${LANG_ROMANIAN} "                  >>>> ATENTIE <<<<$\r$\n$\r$\nVã rugãm, verificati mai întâi notele de publicare sau mergeti la http://wiki.sabnzbd.org/introducing-0-7-0 !"
  LangString MsgOldQueue    ${LANG_RUSSIAN} "                  >>>> WARNING <<<<$\r$\n$\r$\nPlease, first check the release notes or go to http://wiki.sabnzbd.org/introducing-0-7-0 !"
  LangString MsgOldQueue    ${LANG_SERBIAN} "                  >>>> WARNING <<<<$\r$\n$\r$\nPlease, first check the release notes or go to http://wiki.sabnzbd.org/introducing-0-7-0 !"
  LangString MsgOldQueue    ${LANG_SWEDISH} "                  >>>> VARNING <<<<$\r$\n$\r$\nVar vänlig och läs versions noteringarna eller gå till http://wiki.sabnzbd.org/introducing-0-7-0 !"

  LangString MsgUninstall   ${LANG_ENGLISH} "This will uninstall SABnzbd from your system"
  LangString MsgUninstall   ${LANG_DANISH} "Dette vil afinstallere SABnzbd fra dit system"
  LangString MsgUninstall   ${LANG_GERMAN} "Dies entfernt SABnzbd von Ihrem System"
  LangString MsgUninstall   ${LANG_SPANISH} "Esto desinstalará SABnzbd de su sistema"
  LangString MsgUninstall   ${LANG_FRENCH} "Ceci désinstallera SABnzbd de votre système"
  LangString MsgUninstall   ${LANG_NORWEGIAN} "This will uninstall SABnzbd from your system"
  LangString MsgUninstall   ${LANG_DUTCH} "Dit verwijdert SABnzbd van je systeem"
  LangString MsgUninstall   ${LANG_ROMANIAN} "Acest lucru va dezinstala SABnzbd din sistem"
  LangString MsgUninstall   ${LANG_RUSSIAN} "Приложение SABnzbd будет удалено из вашей системы"
  LangString MsgUninstall   ${LANG_SERBIAN} "Ово ће уклонити САБнзбд са вашег система"
  LangString MsgUninstall   ${LANG_SWEDISH} "Detta kommer att avinstallera SABnzbd från systemet"

  LangString MsgRunAtStart  ${LANG_ENGLISH} "Run at startup"
  LangString MsgRunAtStart  ${LANG_DANISH} "Kør ved opstart"
  LangString MsgRunAtStart  ${LANG_GERMAN} "Beim Systemstart ausführen"
  LangString MsgRunAtStart  ${LANG_SPANISH} "Ejecutar al inicio"
  LangString MsgRunAtStart  ${LANG_FRENCH} "Lancer au démarrage"
  LangString MsgRunAtStart  ${LANG_NORWEGIAN} "Run at startup"
  LangString MsgRunAtStart  ${LANG_DUTCH} "Opstarten bij systeem start"
  LangString MsgRunAtStart  ${LANG_ROMANIAN} "Executare la pornire"
  LangString MsgRunAtStart  ${LANG_RUSSIAN} "Запускать вместе с системой"
  LangString MsgRunAtStart  ${LANG_SERBIAN} "Покрени са системом"
  LangString MsgRunAtStart  ${LANG_SWEDISH} "Kör vid uppstart"

  LangString MsgIcon        ${LANG_ENGLISH} "Desktop Icon"
  LangString MsgIcon        ${LANG_DANISH} "Skrivebords ikon"
  LangString MsgIcon        ${LANG_GERMAN} "Desktop-Symbol"
  LangString MsgIcon        ${LANG_SPANISH} "Icono del escritorio"
  LangString MsgIcon        ${LANG_FRENCH} "Icône sur le Bureau"
  LangString MsgIcon        ${LANG_NORWEGIAN} "Desktop Icon"
  LangString MsgIcon        ${LANG_DUTCH} "Pictogram op bureaublad"
  LangString MsgIcon        ${LANG_ROMANIAN} "Icoanã Desktop"
  LangString MsgIcon        ${LANG_RUSSIAN} "Значок на рабочем столе"
  LangString MsgIcon        ${LANG_SERBIAN} "Иконица радне површи"
  LangString MsgIcon        ${LANG_SWEDISH} "Skrivbordsikon"

  LangString MsgAssoc       ${LANG_ENGLISH} "NZB File association"
  LangString MsgAssoc       ${LANG_DANISH} "NZB filtilknytning"
  LangString MsgAssoc       ${LANG_GERMAN} "Mit NZB-Dateien verknüpfen"
  LangString MsgAssoc       ${LANG_SPANISH} "Asociación de archivos NZB"
  LangString MsgAssoc       ${LANG_FRENCH} "Association des fichiers NZB"
  LangString MsgAssoc       ${LANG_NORWEGIAN} "NZB File association"
  LangString MsgAssoc       ${LANG_DUTCH} "NZB bestanden koppelen aan SABnzbd"
  LangString MsgAssoc       ${LANG_ROMANIAN} "Asociere cu Fisierele NZB"
  LangString MsgAssoc       ${LANG_RUSSIAN} "Ассоциировать с файлами NZB"
  LangString MsgAssoc       ${LANG_SERBIAN} "Придруживање НЗБ датотеке"
  LangString MsgAssoc       ${LANG_SWEDISH} "NZB Filassosication"

  LangString MsgDelProgram  ${LANG_ENGLISH} "Delete Program"
  LangString MsgDelProgram  ${LANG_DANISH} "Slet program"
  LangString MsgDelProgram  ${LANG_GERMAN} "Programm löschen"
  LangString MsgDelProgram  ${LANG_SPANISH} "Eliminar programa"
  LangString MsgDelProgram  ${LANG_FRENCH} "Supprimer le programme"
  LangString MsgDelProgram  ${LANG_NORWEGIAN} "Delete Program"
  LangString MsgDelProgram  ${LANG_DUTCH} "Verwijder programma"
  LangString MsgDelProgram  ${LANG_ROMANIAN} "Sterge Program"
  LangString MsgDelProgram  ${LANG_RUSSIAN} "Удалить программу"
  LangString MsgDelProgram  ${LANG_SERBIAN} "Обриши програм"
  LangString MsgDelProgram  ${LANG_SWEDISH} "Ta bort programmet"

  LangString MsgDelSettings ${LANG_ENGLISH} "Delete Settings"
  LangString MsgDelSettings ${LANG_DANISH} "Slet instillinger"
  LangString MsgDelSettings ${LANG_GERMAN} "Einstellungen löschen"
  LangString MsgDelSettings ${LANG_SPANISH} "Eliminar Ajustes"
  LangString MsgDelSettings ${LANG_FRENCH} "Supprimer les Paramètres"
  LangString MsgDelSettings ${LANG_NORWEGIAN} "Delete Settings"
  LangString MsgDelSettings ${LANG_DUTCH} "Verwijder instellingen"
  LangString MsgDelSettings ${LANG_ROMANIAN} "Stergeti Setãri"
  LangString MsgDelSettings ${LANG_RUSSIAN} "Удалить параметры"
  LangString MsgDelSettings ${LANG_SERBIAN} "Обриши подешавања"
  LangString MsgDelSettings ${LANG_SWEDISH} "Ta bort inställningar"

  LangString MsgNoRuntime   ${LANG_ENGLISH} "This system requires the Microsoft runtime library VC90 to be installed first. Do you want to do that now?"
  LangString MsgNoRuntime   ${LANG_DANISH} "Dette system kræver, at Microsoft runtime biblioteket VC90, der skal installeres først. Ønsker du at gøre det nu?"
  LangString MsgNoRuntime   ${LANG_GERMAN} "Dieses System erfordert die Installation der Laufzeitbibliothek VC90 von Microsoft. Möchten Sie die Installation jetzt durchführen?"
  LangString MsgNoRuntime   ${LANG_SPANISH} "Este sistema requiere la ejecución de la biblioteca Microsoft runtime VC90 que debe ser instalada. ¿Quieres hacerlo ahora?"
  LangString MsgNoRuntime   ${LANG_FRENCH} "Ce système nécessite que la bibliothèque d'exécution Microsoft vc90 soit installée en premier. Voulez-vous le faire maintenant?"
  LangString MsgNoRuntime   ${LANG_NORWEGIAN} "This system requires the Microsoft runtime library VC90 to be installed first. Do you want to do that now?"
  LangString MsgNoRuntime   ${LANG_DUTCH} "Op dit systeem moeten eerst de Microsoft runtime bibliotheek VC90 geïnstalleerd worden. Wilt u dat nu doen?"
  LangString MsgNoRuntime   ${LANG_ROMANIAN} "Acest sistem necesitã librãria Microsoft VC90 instalatã. Dortiti sã faceti asta acum ?"
  LangString MsgNoRuntime   ${LANG_RUSSIAN} "Для этой системы сначала необходимо установить библиотеку времени выполнения Microsoft VC90. Сделать это сейчас?"
  LangString MsgNoRuntime   ${LANG_SERBIAN} "Овај систем захтева да буде прво инсталирана Мајкрософтова извршивачка библиотека VC90. Да ли желите то да урадите?"
  LangString MsgNoRuntime   ${LANG_SWEDISH} "This system requires the Microsoft runtime library VC90 to be installed first. Do you want to do that now?"

  LangString MsgDLRuntime   ${LANG_ENGLISH} "Downloading Microsoft runtime installer..."
  LangString MsgDLRuntime   ${LANG_DANISH} "Downloading Microsoft runtime installer..."
  LangString MsgDLRuntime   ${LANG_GERMAN} "Installationsprogramm für Microsoft-Laufzeitbibliothek wird heruntergeladen..."
  LangString MsgDLRuntime   ${LANG_SPANISH} "Descargando el instalador de Microsoft runtime..."
  LangString MsgDLRuntime   ${LANG_FRENCH} "Téléchargement de Microsoft runtime installateur ..."
  LangString MsgDLRuntime   ${LANG_NORWEGIAN} "Downloading Microsoft runtime installer..."
  LangString MsgDLRuntime   ${LANG_DUTCH} "Downloaden van de Microsoft bibliotheek"
  LangString MsgDLRuntime   ${LANG_ROMANIAN} "Descãrcare rutinã instalare Microsoft..."
  LangString MsgDLRuntime   ${LANG_RUSSIAN} "Загрузка программы установки Microsoft..."
  LangString MsgDLRuntime   ${LANG_SERBIAN} "Преузимам Мајкрософтов извршивачки програм за инсталацију..."
  LangString MsgDLRuntime   ${LANG_SWEDISH} "Downloading Microsoft runtime installer..."

  LangString MsgDLError     ${LANG_ENGLISH} "Download error, retry?"
  LangString MsgDLError     ${LANG_DANISH} "Download fejl, prøv igen?"
  LangString MsgDLError     ${LANG_GERMAN} "Download-Fehler. Erneut versuchen?"
  LangString MsgDLError     ${LANG_SPANISH} "Error en la descarga, ¿probamos de nuevo?"
  LangString MsgDLError     ${LANG_FRENCH} "Erreur téléchargement, réessayer?"
  LangString MsgDLError     ${LANG_NORWEGIAN} "Download error, retry?"
  LangString MsgDLError     ${LANG_DUTCH} "Download mislukt, opnieuw?"
  LangString MsgDLError     ${LANG_ROMANIAN} "Eroare descãrcare, încerc din nou?"
  LangString MsgDLError     ${LANG_RUSSIAN} "Ошибка загрузки. Повторить попытку?"
  LangString MsgDLError     ${LANG_SERBIAN} "Грешка у преузимању, да поновим?"
  LangString MsgDLError     ${LANG_SWEDISH} "Download error, retry?"

  LangString MsgDLNeed      ${LANG_ENGLISH} "Cannot install without runtime library, retry?"
  LangString MsgDLNeed      ${LANG_DANISH} "Kan ikke installere uden runtime bibliotek, prøv igen?"
  LangString MsgDLNeed      ${LANG_GERMAN} "Installation ohne Laufzeitbibliothek nicht möglich. Erneut versuchen?"
  LangString MsgDLNeed      ${LANG_SPANISH} "No se puede instalar sin la biblioteca runtime, ¿Lo volvemos a intentar?"
  LangString MsgDLNeed      ${LANG_FRENCH} "Impossible d'installer sans bibliothèque d'exécution, réessayer?"
  LangString MsgDLNeed      ${LANG_NORWEGIAN} "Cannot install without runtime library, retry?"
  LangString MsgDLNeed      ${LANG_DUTCH} "Installeren heeft geen zin zonder de bibliotheek, opnieuw?"
  LangString MsgDLNeed      ${LANG_ROMANIAN} "Nu pot instala fãrã rutinã librãrie, încerc din nou?"
  LangString MsgDLNeed      ${LANG_RUSSIAN} "Не удаётся выполнить установку без библиотеки времени выполнения. Повторить попытку?"
  LangString MsgDLNeed      ${LANG_SERBIAN} "Не могу да инсталирам без извршивачке библиотеке, да поновим?"
  LangString MsgDLNeed      ${LANG_SWEDISH} "Cannot install without runtime library, retry?"

  LangString MsgRemoveOld   ${LANG_ENGLISH} "You cannot overwrite an existing installation. $\n$\nClick `OK` to remove the previous version or `Cancel` to cancel this upgrade."
  LangString MsgRemoveOld   ${LANG_DANISH} "Du kan ikke overskrive en eksisterende installation. Klik `OK` for at fjerne den tidligere version eller `Annuller` for at annullere denne opgradering."
  LangString MsgRemoveOld   ${LANG_GERMAN} "Eine vorhandene Installation kann nicht überschrieben werden. $\n$\nWählen Sie 'OK', um die vorherige Version zu entfernen oder 'Abbrechen' um die Aktualisierung abzubrechen."
  LangString MsgRemoveOld   ${LANG_SPANISH} "No es posible sobrescribir una instalación existente. $\n$\nPresione `OK' para quitar la versión anterior o 'Cancelar' para cancelar la actualización."
  LangString MsgRemoveOld   ${LANG_FRENCH} "Vous ne pouvez pas remplacer une installation existante. $\n$\nCliquez `OK` pour supprimer la version précédente ou `Annuler` pour annuler cette mise à niveau."
  LangString MsgRemoveOld   ${LANG_NORWEGIAN} "You cannot overwrite an existing installation. $\n$\nClick `OK` to remove the previous version or `Cancel` to cancel this upgrade."
  LangString MsgRemoveOld   ${LANG_DUTCH} "U kunt geen bestaande installatie overschrijven.$\n$\nKlik op `OK` om de vorige versie te verwijderen of op `Annuleren` om te stoppen."
  LangString MsgRemoveOld   ${LANG_ROMANIAN} "Nu puteti suprascrie instalarea existentã. $\n$\nClick `OK` pentru a elimina versiunea anterioarã sau `Anulare` pentru a anula actualizarea."
  LangString MsgRemoveOld   ${LANG_RUSSIAN} "Нельзя перезаписать существующее установленное приложение. $\n$\nЧтобы удалить предыдущую версию, нажмите кнопку «ОК». Чтобы отменить обновление, нажмите кнопку «Отмена»."
  LangString MsgRemoveOld   ${LANG_SERBIAN} "Не можете да препишете постојећу инсталацију. $\n$\nКликните „У реду“ да уклоните претходно издање или „Откажи“ да поништите ову надоградњу."
  LangString MsgRemoveOld   ${LANG_SWEDISH} "You cannot overwrite an existing installation. $\n$\nClick `OK` to remove the previous version or `Cancel` to cancel this upgrade."

  LangString MsgRemoveOld2  ${LANG_ENGLISH} "Your settings and data will be preserved."
  LangString MsgRemoveOld2  ${LANG_DANISH} "Dine indstillinger og data vil blive opbevaret."
  LangString MsgRemoveOld2  ${LANG_GERMAN} "Your settings and data will be preserved."
  LangString MsgRemoveOld2  ${LANG_SPANISH} "Tus ajustes y datos se mantendrán intactos."
  LangString MsgRemoveOld2  ${LANG_FRENCH} "Vos paramètres et les données seront conservées."
  LangString MsgRemoveOld2  ${LANG_NORWEGIAN} "Your settings and data will be preserved."
  LangString MsgRemoveOld2  ${LANG_DUTCH} "Your settings and data will be preserved."
  LangString MsgRemoveOld2  ${LANG_ROMANIAN} "Your settings and data will be preserved."
  LangString MsgRemoveOld2  ${LANG_RUSSIAN} "Ваши параметры и данные будут сохранены."
  LangString MsgRemoveOld2  ${LANG_SERBIAN} "Your settings and data will be preserved."
  LangString MsgRemoveOld2  ${LANG_SWEDISH} "Your settings and data will be preserved."


Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd
