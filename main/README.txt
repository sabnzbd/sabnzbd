                                SABnzbd+ v0.4.0rc3

*************************************
*** This is SABnzbd+ 0.4.0rc3     ***
*************************************

============>> THIS IS RELEASE CANDIDATE SOFTWARE <<===============

READ THE "ISSUES.txt" file too!

It should be complete and have no serious problems, however
we can use your help to determine the actual quality.

Important **changes** from previous versions:

- RSS setup is simplified (see Wiki)
- RSS and Bookmark rates are now in minutes between scans
  so no longer times per day!
- Group-based folder feature has been removed
  but now you can use groupnames in user-categories
  and you get the groupname as a script parameter
- Newzbin-category based folder feature has been removed
  Use the user-defined categories instead, which is much
  more flexible.
- The Windows binary distribution now comes with a PAR2
  program that supports a multi-core CPU.
  You can tune the performance of PAR2 (Config->Switches)

This RC3 release will not re-use an existing download queue
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
Do not install the new version over the old one.
Remove old one first or install seperately.
You can re-use your sabnzbd.ini file.
You cannot re-use an unfinished download queue or keep
the download history.

**************************************
*** Upgrading from 0.2.5 and 0.2.7 ***
**************************************
See 0.3.x

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
