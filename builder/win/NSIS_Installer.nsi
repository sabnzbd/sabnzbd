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
!include "StdUtils.nsh"

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
  !define MUI_FINISHPAGE_RUN
  !define MUI_FINISHPAGE_RUN_FUNCTION PageFinishRun
  !define MUI_FINISHPAGE_RUN_TEXT $(MsgRunSAB)
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
Function PageFinishRun
  ; Check if SABnzbd service is installed
  !insertmacro SERVICE "installed" "SABnzbd" ""
  Pop $0 ;response
  ${If} $0 == true
    ; Service is installed, start the service
    !insertmacro SERVICE "start" "SABnzbd" ""
  ${Else}
    ; Service not installed, run executable as user
    ${StdUtils.ExecShellAsUser} $0 "$INSTDIR\SABnzbd.exe" "" ""
  ${EndIf}
FunctionEnd


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
  !insertmacro MUI_LANGUAGE "Turkish"
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
  LangString MsgShowRelNote ${LANG_CZECH} "Zobrazit poznámky k vydání"
  LangString MsgShowRelNote ${LANG_DANISH} "Vis udgivelsesbemærkninger"
  LangString MsgShowRelNote ${LANG_GERMAN} "Versionshinweise anzeigen"
  LangString MsgShowRelNote ${LANG_SPANISH} "Mostrar notas de la versión"
  LangString MsgShowRelNote ${LANG_FINNISH} "Näytä julkaisutiedot"
  LangString MsgShowRelNote ${LANG_FRENCH} "Afficher les notes de version"
  LangString MsgShowRelNote ${LANG_HEBREW} "הראה הערות שחרור"
  LangString MsgShowRelNote ${LANG_ITALIAN} "Mostra note di rilascio"
  LangString MsgShowRelNote ${LANG_NORWEGIAN} "Vis versjonsmerknader"
  LangString MsgShowRelNote ${LANG_DUTCH} "Toon opmerkingen bij deze uitgave"
  LangString MsgShowRelNote ${LANG_POLISH} "Pokaż informacje o wydaniu"
  LangString MsgShowRelNote ${LANG_PORTUGUESEBR} "Mostrar Notas de Lançamento"
  LangString MsgShowRelNote ${LANG_ROMANIAN} "Arată Notele de Publicare"
  LangString MsgShowRelNote ${LANG_RUSSIAN} "Показать заметки о выпуске"
  LangString MsgShowRelNote ${LANG_SERBIAN} "Прикажи белешке о издању"
  LangString MsgShowRelNote ${LANG_SWEDISH} "Visa releasenoteringar"
  LangString MsgShowRelNote ${LANG_TURKISH} "Yayın Notlarını Göster"
  LangString MsgShowRelNote ${LANG_SIMPCHINESE} "显示版本说明"

  LangString MsgRunSAB      ${LANG_ENGLISH} "Run SABnzbd"
  LangString MsgRunSAB      ${LANG_CZECH} "Spustit SABnzbd"
  LangString MsgRunSAB      ${LANG_DANISH} "Kør SABnzbd"
  LangString MsgRunSAB      ${LANG_GERMAN} "SABnzbd starten"
  LangString MsgRunSAB      ${LANG_SPANISH} "Ejecutar SABnzbd"
  LangString MsgRunSAB      ${LANG_FINNISH} "Käynnistä SABnzbd"
  LangString MsgRunSAB      ${LANG_FRENCH} "Lancer SABnzbd"
  LangString MsgRunSAB      ${LANG_HEBREW} "הפעל את SABnzbd"
  LangString MsgRunSAB      ${LANG_ITALIAN} "Avvia SABnzbd"
  LangString MsgRunSAB      ${LANG_NORWEGIAN} "Kjør SABnzbd"
  LangString MsgRunSAB      ${LANG_DUTCH} "SABnzbd starten"
  LangString MsgRunSAB      ${LANG_POLISH} "Uruchom SABnzbd"
  LangString MsgRunSAB      ${LANG_PORTUGUESEBR} "Executar o SABnzbd"
  LangString MsgRunSAB      ${LANG_ROMANIAN} "Rulați SABnzbd"
  LangString MsgRunSAB      ${LANG_RUSSIAN} "Запустить SABnzbd"
  LangString MsgRunSAB      ${LANG_SERBIAN} "Покрени SABnzbd"
  LangString MsgRunSAB      ${LANG_SWEDISH} "Kör SABnzbd"
  LangString MsgRunSAB      ${LANG_TURKISH} "SABnzbd'yi çalıştır"
  LangString MsgRunSAB      ${LANG_SIMPCHINESE} "运行 SABnzbd"

  LangString MsgSupportUs   ${LANG_ENGLISH} "Support the project, Donate!"
  LangString MsgSupportUs   ${LANG_CZECH} "Podpořte projekt!"
  LangString MsgSupportUs   ${LANG_DANISH} "Støt projektet, donér!"
  LangString MsgSupportUs   ${LANG_GERMAN} "Bitte unterstützen Sie das Projekt durch eine Spende!"
  LangString MsgSupportUs   ${LANG_SPANISH} "¡Apoye el proyecto, haga una  donación!"
  LangString MsgSupportUs   ${LANG_FINNISH} "Tue projektia, lahjoita!"
  LangString MsgSupportUs   ${LANG_FRENCH} "Soutenez le projet, faites un don !"
  LangString MsgSupportUs   ${LANG_HEBREW} "תמוך במיזם, תרום!"
  LangString MsgSupportUs   ${LANG_ITALIAN} "Sostieni il progetto, dona!"
  LangString MsgSupportUs   ${LANG_NORWEGIAN} "Støtt prosjektet, donèr!"
  LangString MsgSupportUs   ${LANG_DUTCH} "Steun het project, doneer!"
  LangString MsgSupportUs   ${LANG_POLISH} "Wspomóż projekt!"
  LangString MsgSupportUs   ${LANG_PORTUGUESEBR} "Apoie o projeto. Faça uma doação!"
  LangString MsgSupportUs   ${LANG_ROMANIAN} "Susţine proiectul, Donează!"
  LangString MsgSupportUs   ${LANG_RUSSIAN} "Поддержите проект. Сделайте пожертвование!"
  LangString MsgSupportUs   ${LANG_SERBIAN} "Подржите пројекат, дајте добровољан прилог!"
  LangString MsgSupportUs   ${LANG_SWEDISH} "Donera och stöd detta projekt!"
  LangString MsgSupportUs   ${LANG_TURKISH} "Projeye destek olun, Bağış Yapın!"
  LangString MsgSupportUs   ${LANG_SIMPCHINESE} "支持该项目，捐助!"

  LangString MsgServChange  ${LANG_ENGLISH} "The SABnzbd Windows Service changed in SABnzbd 3.0.0. $\nYou will need to reinstall the SABnzbd service. $\n$\nClick `OK` to remove the existing services or `Cancel` to cancel this upgrade."
  LangString MsgServChange  ${LANG_CZECH} "Služba SABnzbd pro Windows byla ve verzi SABnzbd 3.0.0 změněna.$\nBudete muset znovu nainstalovat službu SABnzbd.$\n$\nKlikněte na `OK` pro odstranění stávajících služeb nebo na `Zrušit` pro zrušení této aktualizace."
  LangString MsgServChange  ${LANG_DANISH} "SABnzbd Windows-tjenesten blev ændret i SABnzbd 3.0.0.$\nDu skal geninstallere SABnzbd-tjenesten.$\n$\nKlik på `OK` for at fjerne de eksisterende tjenester eller `Annuller` for at afbryde denne opgradering."
  LangString MsgServChange  ${LANG_GERMAN} "Aufgrund von Änderungen am SABnzbd Windows Service ab Version 3.0.0 ist es nötig,$\nden Windows Service neu zu installieren.$\n$\n$\r$\nDrücke `OK` um den existierenden Service zu löschen oder `Abbrechen` um dieses Upgrade abzubrechen."
  LangString MsgServChange  ${LANG_SPANISH} "El servicio de Windows para SABnzbd ha cambiado en la versión SABnzbd 3.0.0.$\nNecesitará volver a instalar el servicio SABnzbd. $\n$\nHaga clic en $\"OK$\" para eliminar los servicios existentes o $\"Cancelar$\" para cancelar la actualización."
  LangString MsgServChange  ${LANG_FINNISH} "SABnzbdin Windows-palvelu muuttui versiossa SABnzbd 3.0.0.$\nSinun täytyy asentaa SABnzbd-palvelu uudelleen.$\n$\nNapsauta `OK` poistaaksesi olemassa olevat palvelut tai `Peruuta` peruuttaaksesi tämän päivityksen."
  LangString MsgServChange  ${LANG_FRENCH} "Le service Windows SABnzbd a changé dans SABnzbd 3.0.0. $\nVous allez devoir réinstaller le service SABnzbd. $\n$\nCliquez sur 'OK' pour supprimer les services existants ou sur 'Annuler' pour annuler cette mise à niveau."
  LangString MsgServChange  ${LANG_HEBREW} "שירות Windows של SABnzbd השתנה ב־SABnzbd 3.0.0. $\nתצטרך להתקין מחדש את השירות של SABnzbd. $\n$\nלחץ על `אישור` כדי להסיר את השירותים הקיימים או על `ביטול` כדי לבטל שדרוג זה."
  LangString MsgServChange  ${LANG_ITALIAN} "Il servizio Windows di SABnzbd è cambiato in SABnzbd 3.0.0. $\nSarà necessario reinstallare il servizio SABnzbd. $\n$\nFai clic su `OK` per rimuovere i servizi esistenti o su `Annulla` per annullare questo aggiornamento."
  LangString MsgServChange  ${LANG_NORWEGIAN} "SABnzbd Windows-tjenesten ble endret i SABnzbd 3.0.0.$\nDu må installere SABnzbd-tjenesten på nytt.$\n$\nKlikk `OK` for å fjerne eksisterende tjenester eller `Avbryt` for å avbryte denne oppgraderingen."
  LangString MsgServChange  ${LANG_DUTCH} "De SABnzbd Windows Service is aangepast in SABnzbd 3.0.0. Hierdoor zal je de service opnieuw moeten installeren.$\n$\n$\r$\nKlik `Ok` om de bestaande services te verwijderen of `Annuleren` om te stoppen."
  LangString MsgServChange  ${LANG_POLISH} "Usługa SABnzbd dla Windows została zmieniona w wersji SABnzbd 3.0.0.$\nMusisz ponownie zainstalować usługę SABnzbd.$\n$\nKliknij `OK`, aby usunąć istniejące usługi, lub `Anuluj`, aby przerwać tę aktualizację."
  LangString MsgServChange  ${LANG_PORTUGUESEBR} "O Serviço do Windows do SABnzbd mudou no SABnzbd 3.0.0.$\nVocê precisará reinstalar o serviço do SABnzbd.$\n$\nClique em `OK` para remover os serviços existentes ou em `Cancelar` para cancelar esta atualização."
  LangString MsgServChange  ${LANG_ROMANIAN} "Serviciul SABnzbd pentru Windows s-a schimbat în SABnzbd 3.0.0.$\nVa trebui să reinstalați serviciul SABnzbd.$\n$\nFaceți clic pe `OK` pentru a elimina serviciile existente sau pe `Anulare` pentru a anula această actualizare."
  LangString MsgServChange  ${LANG_RUSSIAN} "Служба SABnzbd для Windows была изменена в SABnzbd 3.0.0.$\nВам необходимо переустановить службу SABnzbd.$\n$\nНажмите «ОК», чтобы удалить существующие службы, или «Отмена», чтобы прервать это обновление."
  LangString MsgServChange  ${LANG_SERBIAN} "Windows услуга за SABnzbd је измењена у верзији SABnzbd 3.0.0.$\nМораћете поново да инсталирате SABnzbd услугу.$\n$\nКликните „У реду“ да уклоните постојеће услуге или „Откажи“ да откажете ово ажурирање."
  LangString MsgServChange  ${LANG_SWEDISH} "SABnzbd Windows tjänsten ändrades i SABnzbd 3.0.0.$\nSABnzbd tjänsten behöver installeras om.$\n$\nVälj OK` för att ta bort den befintliga tjänsten, eller välj `Cancel`för att avbryta uppdateringen."
  LangString MsgServChange  ${LANG_TURKISH} "SABnzbd Windows Servisi SABnzbd 3.0.0.0 ile değişmiştir.$\nSABnzbd servisini yeniden kurmanız gerekecektir.$\n$\nMevcut servisleri kaldırmak için `Tamam` üzerine veya bu güncellemeyi iptal etmek için `İptal` üzerine tıklayın."
  LangString MsgServChange  ${LANG_SIMPCHINESE} "SABnzbd 的 Windows 服务在 SABnzbd 3.0.0 中发生了变化。$\n您需要重新安装 SABnzbd 服务。$\n$\n点击“确定”以移除现有服务，或点击“取消”以取消此次升级。"

  LangString MsgOnly64bit   ${LANG_ENGLISH} "SABnzbd only supports 64-bit Windows."
  LangString MsgOnly64bit   ${LANG_CZECH} "SABnzbd podporuje pouze 64bitové Windows."
  LangString MsgOnly64bit   ${LANG_DANISH} "SABnzbd understøtter kun 64-bit Windows."
  LangString MsgOnly64bit   ${LANG_GERMAN} "SABnzbd unterstützt nur 64-Bit-Windows."
  LangString MsgOnly64bit   ${LANG_SPANISH} "SABnzbd solo es compatible con Windows de 64 bits."
  LangString MsgOnly64bit   ${LANG_FINNISH} "SABnzbd tukee vain 64-bittistä Windowsia."
  LangString MsgOnly64bit   ${LANG_FRENCH} "SABnzbd n'est compatible qu'avec Windows 64 bits."
  LangString MsgOnly64bit   ${LANG_HEBREW} "SABnzbd תומך רק במערכות Windows מסוג 64 סיביות."
  LangString MsgOnly64bit   ${LANG_ITALIAN} "SABnzbd supporta solo Windows a 64 bit."
  LangString MsgOnly64bit   ${LANG_NORWEGIAN} "SABnzbd støtter kun 64-bit Windows."
  LangString MsgOnly64bit   ${LANG_DUTCH} "SABnzbd ondersteund alleen 64bit Windows."
  LangString MsgOnly64bit   ${LANG_POLISH} "SABnzbd obsługuje tylko system Windows 64-bit."
  LangString MsgOnly64bit   ${LANG_PORTUGUESEBR} "O SABnzbd oferece suporte apenas ao Windows de 64 bits."
  LangString MsgOnly64bit   ${LANG_ROMANIAN} "SABnzbd acceptă doar Windows pe 64 de biți."
  LangString MsgOnly64bit   ${LANG_RUSSIAN} "SABnzbd поддерживает только 64-битные версии Windows."
  LangString MsgOnly64bit   ${LANG_SERBIAN} "SABnzbd подржава само 64‑битни Windows."
  LangString MsgOnly64bit   ${LANG_SWEDISH} "SABnzbd stöder endast 64-bitars Windows."
  LangString MsgOnly64bit   ${LANG_TURKISH} "SABnzbd sadece 64 bit Windows'u destekler."
  LangString MsgOnly64bit   ${LANG_SIMPCHINESE} "SABnzbd 仅支持 64 位 Windows。"

  LangString MsgNoWin7      ${LANG_ENGLISH} "SABnzbd only supports Windows 8.1 and above."
  LangString MsgNoWin7      ${LANG_CZECH} "SABnzbd podporuje pouze Windows 8.1 a novější."
  LangString MsgNoWin7      ${LANG_DANISH} "SABnzbd understøtter kun Windows 8.1 og nyere."
  LangString MsgNoWin7      ${LANG_GERMAN} "SABnzbd unterstützt nur Windows 8.1 und höher."
  LangString MsgNoWin7      ${LANG_SPANISH} "SABnzbd solo es compatible con Windows 8.1 y superiores."
  LangString MsgNoWin7      ${LANG_FINNISH} "SABnzbd tukee vain Windows 8.1:tä ja uudempia."
  LangString MsgNoWin7      ${LANG_FRENCH} "SABnzbd n'est compatible qu'avec Windows 8.1 et plus."
  LangString MsgNoWin7      ${LANG_HEBREW} "SABnzbd תומך רק במערכות Windows 8.1 ומעלה."
  LangString MsgNoWin7      ${LANG_ITALIAN} "SABnzbd supporta solo Windows 8.1 e versioni successive."
  LangString MsgNoWin7      ${LANG_NORWEGIAN} "SABnzbd støtter kun Windows 8.1 og nyere."
  LangString MsgNoWin7      ${LANG_DUTCH} "SABnzbd ondersteund alleen Windows 8.1 en hoger."
  LangString MsgNoWin7      ${LANG_POLISH} "SABnzbd obsługuje tylko Windows 8.1 i nowsze."
  LangString MsgNoWin7      ${LANG_PORTUGUESEBR} "O SABnzbd oferece suporte apenas ao Windows 8.1 e superior."
  LangString MsgNoWin7      ${LANG_ROMANIAN} "SABnzbd acceptă doar Windows 8.1 și versiunile ulterioare."
  LangString MsgNoWin7      ${LANG_RUSSIAN} "SABnzbd поддерживает только Windows 8.1 и более новые."
  LangString MsgNoWin7      ${LANG_SERBIAN} "SABnzbd подржава само Windows 8.1 и новије."
  LangString MsgNoWin7      ${LANG_SWEDISH} "SABnzbd stöder endast Windows 8.1 och senare."
  LangString MsgNoWin7      ${LANG_TURKISH} "SABnzbd sadece Windows 8.1 ve üzerini destekler."
  LangString MsgNoWin7      ${LANG_SIMPCHINESE} "SABnzbd 仅支持 Windows 8.1 及更高版本。"

  LangString MsgShutting    ${LANG_ENGLISH} "Shutting down SABnzbd"
  LangString MsgShutting    ${LANG_CZECH} "Vypínání SABnzbd"
  LangString MsgShutting    ${LANG_DANISH} "Lukker SABnzbd"
  LangString MsgShutting    ${LANG_GERMAN} "Beende SABnzbd"
  LangString MsgShutting    ${LANG_SPANISH} "Apagando SABnzbd"
  LangString MsgShutting    ${LANG_FINNISH} "Sammutetaan SABnzbd"
  LangString MsgShutting    ${LANG_FRENCH} "Arrêt de SABnzbd"
  LangString MsgShutting    ${LANG_HEBREW} "מכבה את SABnzbd"
  LangString MsgShutting    ${LANG_ITALIAN} "Arresto di SABnzbd in corso"
  LangString MsgShutting    ${LANG_NORWEGIAN} "Slår av SABnzbd"
  LangString MsgShutting    ${LANG_DUTCH} "SABnzbd wordt afgesloten"
  LangString MsgShutting    ${LANG_POLISH} "Zamykanie SABnzbd"
  LangString MsgShutting    ${LANG_PORTUGUESEBR} "Encerrando o SABnzbd"
  LangString MsgShutting    ${LANG_ROMANIAN} "Se oprește SABnzbd"
  LangString MsgShutting    ${LANG_RUSSIAN} "Завершение работы SABnzbd"
  LangString MsgShutting    ${LANG_SERBIAN} "Искључивање SABnzbd"
  LangString MsgShutting    ${LANG_SWEDISH} "Stänger av SABnzbd."
  LangString MsgShutting    ${LANG_TURKISH} "SABnzbd kapatılıyor"
  LangString MsgShutting    ${LANG_SIMPCHINESE} "正在关闭 SABnzbd"

  LangString MsgUninstall   ${LANG_ENGLISH} "This will uninstall SABnzbd from your system"
  LangString MsgUninstall   ${LANG_CZECH} "Tímto odinstalujete SABnzbd z vašeho systému"
  LangString MsgUninstall   ${LANG_DANISH} "Dette vil afinstallere SABnzbd fra dit system"
  LangString MsgUninstall   ${LANG_GERMAN} "Dies entfernt SABnzbd von Ihrem System"
  LangString MsgUninstall   ${LANG_SPANISH} "Esto desinstalará SABnzbd de su sistema"
  LangString MsgUninstall   ${LANG_FINNISH} "Tämä poistaa SABnzbd:n tietokoneestasi"
  LangString MsgUninstall   ${LANG_FRENCH} "Ceci désinstallera SABnzbd de votre système"
  LangString MsgUninstall   ${LANG_HEBREW} "זה יסיר את SABnzbd מהמערכת שלך"
  LangString MsgUninstall   ${LANG_ITALIAN} "Questo disinstallerà SABnzbd dal tuo sistema"
  LangString MsgUninstall   ${LANG_NORWEGIAN} "Dette vil avinstallere SABnzbd fra ditt system"
  LangString MsgUninstall   ${LANG_DUTCH} "Dit verwijdert SABnzbd van je systeem"
  LangString MsgUninstall   ${LANG_POLISH} "To odinstaluje SABnzbd z systemu"
  LangString MsgUninstall   ${LANG_PORTUGUESEBR} "Isso irá desinstalar SABnzbd de seu sistema"
  LangString MsgUninstall   ${LANG_ROMANIAN} "Acest lucru va dezinstala SABnzbd din sistem"
  LangString MsgUninstall   ${LANG_RUSSIAN} "Приложение SABnzbd будет удалено из вашей системы"
  LangString MsgUninstall   ${LANG_SERBIAN} "Ово ће уклонити САБнзбд са вашег система"
  LangString MsgUninstall   ${LANG_SWEDISH} "Detta kommer att avinstallera SABnzbd från systemet"
  LangString MsgUninstall   ${LANG_TURKISH} "Bu, SABnzbd'yi sisteminizden kaldıracaktır"
  LangString MsgUninstall   ${LANG_SIMPCHINESE} "这将从您的系统中卸载 SABnzbd"

  LangString MsgRunAtStart  ${LANG_ENGLISH} "Run at startup"
  LangString MsgRunAtStart  ${LANG_CZECH} "Spouštět při startu systému"
  LangString MsgRunAtStart  ${LANG_DANISH} "Kør ved opstart"
  LangString MsgRunAtStart  ${LANG_GERMAN} "Beim Systemstart ausführen"
  LangString MsgRunAtStart  ${LANG_SPANISH} "Ejecutar al inicio"
  LangString MsgRunAtStart  ${LANG_FINNISH} "Suorita käynnistyksen yhteydessä"
  LangString MsgRunAtStart  ${LANG_FRENCH} "Lancer au démarrage"
  LangString MsgRunAtStart  ${LANG_HEBREW} "הרץ בהזנק"
  LangString MsgRunAtStart  ${LANG_ITALIAN} "Esegui all'avvio"
  LangString MsgRunAtStart  ${LANG_NORWEGIAN} "Kjør ved oppstart"
  LangString MsgRunAtStart  ${LANG_DUTCH} "Starten met Windows"
  LangString MsgRunAtStart  ${LANG_POLISH} "Uruchom wraz z systemem"
  LangString MsgRunAtStart  ${LANG_PORTUGUESEBR} "Executar na inicialização"
  LangString MsgRunAtStart  ${LANG_ROMANIAN} "Executare la pornire"
  LangString MsgRunAtStart  ${LANG_RUSSIAN} "Запускать вместе с системой"
  LangString MsgRunAtStart  ${LANG_SERBIAN} "Покрени са системом"
  LangString MsgRunAtStart  ${LANG_SWEDISH} "Kör vid uppstart"
  LangString MsgRunAtStart  ${LANG_TURKISH} "Başlangıçta Çalıştır"
  LangString MsgRunAtStart  ${LANG_SIMPCHINESE} "启动时运行"

  LangString MsgIcon        ${LANG_ENGLISH} "Desktop Icon"
  LangString MsgIcon        ${LANG_CZECH} "Ikona na ploše"
  LangString MsgIcon        ${LANG_DANISH} "Skrivebordsikon"
  LangString MsgIcon        ${LANG_GERMAN} "Desktop-Symbol"
  LangString MsgIcon        ${LANG_SPANISH} "Icono del escritorio"
  LangString MsgIcon        ${LANG_FINNISH} "Työpöydän kuvake"
  LangString MsgIcon        ${LANG_FRENCH} "Icône sur le Bureau"
  LangString MsgIcon        ${LANG_HEBREW} "צור קיצור דרך בשולחן העבודה"
  LangString MsgIcon        ${LANG_ITALIAN} "Icona sul desktop"
  LangString MsgIcon        ${LANG_NORWEGIAN} "Skrivebordsikon"
  LangString MsgIcon        ${LANG_DUTCH} "Bureaubladpictogram"
  LangString MsgIcon        ${LANG_POLISH} "Ikona pulpitu"
  LangString MsgIcon        ${LANG_PORTUGUESEBR} "Ícone na Área de Trabalho"
  LangString MsgIcon        ${LANG_ROMANIAN} "Icoană Desktop"
  LangString MsgIcon        ${LANG_RUSSIAN} "Значок на рабочем столе"
  LangString MsgIcon        ${LANG_SERBIAN} "Иконица радне површи"
  LangString MsgIcon        ${LANG_SWEDISH} "Skrivbordsikon"
  LangString MsgIcon        ${LANG_TURKISH} "Masaüstü İkonu"
  LangString MsgIcon        ${LANG_SIMPCHINESE} "桌面图标"

  LangString MsgAssoc       ${LANG_ENGLISH} "NZB File association"
  LangString MsgAssoc       ${LANG_CZECH} "Přiřazení souborů NZB"
  LangString MsgAssoc       ${LANG_DANISH} "NZB-filtilknytning"
  LangString MsgAssoc       ${LANG_GERMAN} "Mit NZB-Dateien verknüpfen"
  LangString MsgAssoc       ${LANG_SPANISH} "Asociación de archivos NZB"
  LangString MsgAssoc       ${LANG_FINNISH} "NZB tiedostosidos"
  LangString MsgAssoc       ${LANG_FRENCH} "Association des fichiers NZB"
  LangString MsgAssoc       ${LANG_HEBREW} "NZB שייך קבצי"
  LangString MsgAssoc       ${LANG_ITALIAN} "Associazione file NZB"
  LangString MsgAssoc       ${LANG_NORWEGIAN} "NZB-filassosiering"
  LangString MsgAssoc       ${LANG_DUTCH} "NZB-bestanden openen met SABnzbd"
  LangString MsgAssoc       ${LANG_POLISH} "powiązanie pliku NZB"
  LangString MsgAssoc       ${LANG_PORTUGUESEBR} "Associação com Arquivos NZB"
  LangString MsgAssoc       ${LANG_ROMANIAN} "Asociere cu Fişierele NZB"
  LangString MsgAssoc       ${LANG_RUSSIAN} "Ассоциировать с файлами NZB"
  LangString MsgAssoc       ${LANG_SERBIAN} "Придруживање НЗБ датотеке"
  LangString MsgAssoc       ${LANG_SWEDISH} "NZB Filassosication"
  LangString MsgAssoc       ${LANG_TURKISH} "NZB Dosya ilişkilendirmesi"
  LangString MsgAssoc       ${LANG_SIMPCHINESE} "NZB 文件关联"

  LangString MsgDelProgram  ${LANG_ENGLISH} "Delete Program"
  LangString MsgDelProgram  ${LANG_CZECH} "Odstranit program"
  LangString MsgDelProgram  ${LANG_DANISH} "Slet program"
  LangString MsgDelProgram  ${LANG_GERMAN} "Programm löschen"
  LangString MsgDelProgram  ${LANG_SPANISH} "Eliminar programa"
  LangString MsgDelProgram  ${LANG_FINNISH} "Poista sovellus"
  LangString MsgDelProgram  ${LANG_FRENCH} "Supprimer le programme"
  LangString MsgDelProgram  ${LANG_HEBREW} "מחק תוכנית"
  LangString MsgDelProgram  ${LANG_ITALIAN} "Elimina programma"
  LangString MsgDelProgram  ${LANG_NORWEGIAN} "Fjern program"
  LangString MsgDelProgram  ${LANG_DUTCH} "Programma verwijderen"
  LangString MsgDelProgram  ${LANG_POLISH} "Usuń program"
  LangString MsgDelProgram  ${LANG_PORTUGUESEBR} "Excluir o Programa"
  LangString MsgDelProgram  ${LANG_ROMANIAN} "Şterge Program"
  LangString MsgDelProgram  ${LANG_RUSSIAN} "Удалить программу"
  LangString MsgDelProgram  ${LANG_SERBIAN} "Обриши програм"
  LangString MsgDelProgram  ${LANG_SWEDISH} "Radera programmet"
  LangString MsgDelProgram  ${LANG_TURKISH} "Programı Sil"
  LangString MsgDelProgram  ${LANG_SIMPCHINESE} "删除程序"

  LangString MsgDelSettings ${LANG_ENGLISH} "Delete Settings"
  LangString MsgDelSettings ${LANG_CZECH} "Smazat nastavení"
  LangString MsgDelSettings ${LANG_DANISH} "Slet indstillinger"
  LangString MsgDelSettings ${LANG_GERMAN} "Einstellungen löschen"
  LangString MsgDelSettings ${LANG_SPANISH} "Eliminar Ajustes"
  LangString MsgDelSettings ${LANG_FINNISH} "Poista asetukset"
  LangString MsgDelSettings ${LANG_FRENCH} "Supprimer les paramètres"
  LangString MsgDelSettings ${LANG_HEBREW} "מחק הגדרות"
  LangString MsgDelSettings ${LANG_ITALIAN} "Elimina impostazioni"
  LangString MsgDelSettings ${LANG_NORWEGIAN} "Slett innstillinger"
  LangString MsgDelSettings ${LANG_DUTCH} "Verwijder alle instellingen"
  LangString MsgDelSettings ${LANG_POLISH} "Skasuj obecne ustawienia"
  LangString MsgDelSettings ${LANG_PORTUGUESEBR} "Apagar Configurações"
  LangString MsgDelSettings ${LANG_ROMANIAN} "Ştergeţi Setări"
  LangString MsgDelSettings ${LANG_RUSSIAN} "Удалить параметры"
  LangString MsgDelSettings ${LANG_SERBIAN} "Обриши подешавања"
  LangString MsgDelSettings ${LANG_SWEDISH} "Radera inställningar"
  LangString MsgDelSettings ${LANG_TURKISH} "Ayarları Sil"
  LangString MsgDelSettings ${LANG_SIMPCHINESE} "删除设置"

  LangString MsgLangCode    ${LANG_ENGLISH} "en"
  LangString MsgLangCode    ${LANG_CZECH} "cs"
  LangString MsgLangCode    ${LANG_DANISH} "da"
  LangString MsgLangCode    ${LANG_GERMAN} "de"
  LangString MsgLangCode    ${LANG_SPANISH} "es"
  LangString MsgLangCode    ${LANG_FINNISH} "fi"
  LangString MsgLangCode    ${LANG_FRENCH} "fr"
  LangString MsgLangCode    ${LANG_HEBREW} "he"
  LangString MsgLangCode    ${LANG_ITALIAN} "it"
  LangString MsgLangCode    ${LANG_NORWEGIAN} "nb"
  LangString MsgLangCode    ${LANG_DUTCH} "nl"
  LangString MsgLangCode    ${LANG_POLISH} "pl"
  LangString MsgLangCode    ${LANG_PORTUGUESEBR} "pt_BR"
  LangString MsgLangCode    ${LANG_ROMANIAN} "ro"
  LangString MsgLangCode    ${LANG_RUSSIAN} "ru"
  LangString MsgLangCode    ${LANG_SERBIAN} "sr"
  LangString MsgLangCode    ${LANG_SWEDISH} "sv"
  LangString MsgLangCode    ${LANG_TURKISH} "tr"
  LangString MsgLangCode    ${LANG_SIMPCHINESE} "zh_CN"

Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd
