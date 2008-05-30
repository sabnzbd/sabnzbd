                                SABnzbd+ v0.4.0rc1

*************************************
*** This is SABnzbd+ 0.4.0rc1     ***
*************************************

============>> THIS IS RELEASE CANDIDATE SOFTWARE <<===============

Only use it when your are prepared to accept bugs and are ready
for some troubleshooting.

This RC1 release will not re-use an existing download queue
from an earlier release than 0.4.0Beta5.
It will automatically create a new empty queue and history.
However, the old queue remains in the cache directory and can
still be accessed by the previous release.
Do not run two releases of SABnzbd at the same time on the
same Cache directory!

!! Using the --clean option will remove both queues !!

==============================================================


Read carefully. Major changes from previous releases.
New users, also read the file INSTALL.txt

There is an extensive Wiki on the use of SABnzbd+ on sf.net:
http://sabnzbd.wikidot.com/


*******************************
*** Where are my downloads? ***
*******************************
Windows:
    SABnzbd will create a folder in "My Documents", called "Downloads".
Unix/Linux/OSX:
    SABnzbd will create a folder in $HOME, called "Downloads".
This folder contains the folders "incomplete" and "complete".
"complete" will contain the end result of the downloads.
(You may change this in the configuration screens.)


**************************************
*** Upgrading from 0.3.x           ***
**************************************
Just install the new version over the old one.
If you want to un-install the old version first, keep the data!


**************************************
*** Upgrading from 0.2.5 and 0.2.7 ***
**************************************
If you want, you can copy your existing sabnzbd.ini file to the new program dir.
This way you keep all your settings.

If you have an unfinished download queue, finish it first with 0.2.5/0.2.7.
This release cannot re-use the queue!


*********************
*** Windows Vista ***
*********************
SABnzbd is Vista compatible.
However, we have seen issues with some ZoneAlarm firewall versions.


*************************************************
*** Changes to Win32 binary ***
*************************************************
For the Win32-binary comes now in two flavours.
SABnzbd.exe will be a completely invisible application,
except for it's web-interface.

SABnzbd-console.exe will keep a visible black window that
will show the logging. Use this for troubleshooting only.


*************************************************
*** Overview of essential changes from 0.3.x: ***
*************************************************
Secure NNTP (SSL)
User-defined categories
Complete redesign of RSS scanning
Intelligent handling of seasons of TV shows
Streaming-friendly ordering of files
Automatic removal of samples before downloading
Major upgrade of Plush and SMPL
iPhone template
Optional secundary web-interface on http://host:port/sabnzbd/m
Selectable colour schemes for SMPL and Default
Improved bandwidth control
