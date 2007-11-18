@echo off

set prod=SABnzbd-0.2.8rc3

ren dist %prod%
if errorlevel 1 goto error

"c:\Program Files\7-Zip\7z.exe" a -r -w -sfx7z.sfx %prod%.exe  %prod%
if errorlevel 1 goto error

ren %prod% dist
if errorlevel 1 goto error

goto end


:error
echo Sorry, something went wrong

:end
