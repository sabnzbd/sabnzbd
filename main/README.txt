                                SABnzbd+ v0.3.0

*************************************
*** This is SABnzbd+ 0.3.0 Final. ***
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
*** Changes to --daemon mode and Win32 binary ***
*************************************************
-d or --daemon will now ignore any user profile data.
This means that the sabnzbd.ini file must either in the program directory
where SABnzbd.py or SABnzbd.exe is or that the -f option must be used.

For the Win32-binary, the black console windows disappears immediately.
For troubleshooting, you can use the --console paramater.
Open a command prompt and type:
   SABnzbd.exe --console


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
