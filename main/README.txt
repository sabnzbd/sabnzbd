                                SABnzbd+ v0.4.0X

*************************************
*** This is SABnzbd+ 0.4.0X       ***
*************************************

Read carefully. Major changes from previous releases.
New users, also read the file INSTALL.txt

There is an extensive Wiki on the use of SABnzbd+ on sf.net:
http://sabnzbdplus.wiki.sourceforge.net/


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
*** Upgrading from 0.3.0           ***
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

If you have existing RSS jobs, you may want to save the file rss.sab.
Delete all in the cache directory, EXCEPT rss.sab


*********************
*** Windows Vista ***
*********************
SABnzbd is Vista compatible.
However, you cannot use it in combination with the ZoneAlarm firewall software.


*************************************************
*** Changes to Win32 binary ***
*************************************************
For the Win32-binary comes now in two flavours.
SABnzbd.exe will be a completely invisible application,
except for it's web-interface.

SABnzbd-console.exe will keep a visible black window that
will show the logging. Use this for troubleshooting only.


*************************************************
*** Overview of essential changes from 0.2.7: ***
*************************************************
* Introducing the "smpl" user interface (by swi-tch)
* Introducing the "Plush" user interface (by pairofdimes)
* Windows installer added
* Old 0.2.5 bug fixed: Sometimes corrupted downloads when using memory cache
* Old 0.2.5 bug fixed: Auto-shutdown will now wait for post-processing to complete
* Old 0.2.5 bug fixed: Solve memory overflow caused by high download speeds
* Old 0.2.5 bug fixed: Win32-bin did not always hide console window
* Option to disconnect from Usenet servers on empty queue and pause
* Unix --permissions (replaces old umask)
* Add "api" functions (for automation support)
* Better detection of Vista and other IPV6 enabled systems
* Detection and error message about incompatible firewall(s)
* Panic message in browser for all fatal errors (if enabled)
* Queuing of v3.newzbin.com queries (because of 5 queries/minute limitation of newzbin)
* Email notification of completed jobs and disk-full
* RSS-feed of the History (so you can monitor with an RSS reader)
* Automatic launch of a web browser showing SABnzbd's web-interface
* Automatic pause when download volume is almost full
* On-line Help pages (SABnzbd web-interface contains links)
* Automatic setup of working directories
* Allow normal Windows paths (with "\" characters)
* Automatic addition of missing keyword in older INI files
* For Windows, store working data in user-profile (Vista compatible)
* For Unix, store working data in ~/.sabnzbd
* Timeout setting per server
* Set logging levels on the commandline (will be stored in INI-file)
* Get logging files through the web-gui
* IPV6 compatible
