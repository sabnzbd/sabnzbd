@echo off
setlocal

set VERSION=0.3.1rc1


rem ***************************
rem **** Set the filenames ****
rem ***************************
set prod=SABnzbd-%VERSION%
set fileInst=%prod%-setup-win32.exe
set fileBin=%prod%-win32.zip
set fileSrc=%prod%-src.zip



rem *********************************
rem **** Determine what to build ****
rem *********************************
if not "%1" == "" goto check1
    echo.
    echo " Usage: packer.cmd all | inst | bin | src "
    echo.
    goto end
:check1
if not "%1" == "all" goto check2
    set inst=1
    set bin=1
    set src=1
:check2
if "%1" == "inst" set inst=1
if "%1" == "src" set src=1
if "%1" == "bin" set bin=1



rem ********************************
rem **** Installer distribution ****
rem ********************************
if "%inst%" == "" goto bin
del dist\*.ini >nul 2>&1
"c:\Program Files\NSIS\makensis.exe" /v3 /DSAB_PRODUCT=%prod% /DSAB_FILE=%fileInst% NSIS_Installer.nsi
if errorlevel 1 goto error



rem *****************************
rem **** Binary distribution ****
rem *****************************
:bin
if "%bin%" == "" goto src
ren dist %prod%
if errorlevel 1 goto error

if exist %fileBin% del /q %fileBin%
zip -9 -r -X %fileBin% %prod%
if errorlevel 1 goto error

ren %prod% dist
if errorlevel 1 goto error



rem *****************************
rem **** Source distribution ****
rem *****************************
:src
if "%src%" == "" goto end
ren srcdist %prod%
if errorlevel 1 goto error

if exist %fileSrc% del /q %fileSrc%
zip -9 -r -X %fileSrc% %prod%
if errorlevel 1 goto error

ren %prod% srcdist
if errorlevel 1 goto error

goto end


rem ***************
rem **** ERROR ****
rem ***************
:error
echo Sorry, something went wrong

rem ***************
rem ****  END  ****
rem ***************
:end
