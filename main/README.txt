*************************************
*** This is SABnzbd 0.4.3RC4      ***
*************************************
SABnzbd is an open-source cross-platform binary newsreader.
It simplifies the process of downloading from Usenet dramatically,
thanks to its friendly web-based user interface and advanced
built-in post-processing options that automatically verify, repair,
extract and clean up posts downloaded from Usenet.
SABnzbd also has a fully customizable user interface,
and offers a complete API for third-party applications to hook into.

There is an extensive Wiki on the use of SABnzbd.
http://sabnzbd.wikidot.com/


*******************************************
*** Upgrading from 0.4.2                ***
*******************************************
Just install over the existing installation,
and you will be able to resume where you left off.


**************************************
*** Upgrading from 0.4.1 and older ***
**************************************
Do *not* install the new version over the old one.
Remove old one first or install seperately.
You can re-use your sabnzbd.ini file.
You cannot re-use an unfinished download queue or keep
the download history.



*******************************************
*** Changes since 0.4.2                 ***
*******************************************
New:
- Watched folder and UI now accept RAR files containing NZB-files.
- Add API call to retrieve version
- Sort the category list
Fixed:
- Watched folder: changed files will now be re-examined
- Duplicate RSS jobs were not filtered out
- Delete history made safer
- Proper script was not set when fetching from newzbin bookmarks
- Strip white-space around server host name (preventing copy-paste errors)
- Par2 checking would fail if first article of a par2 file is missing
- No error report was giben when server authentication is missing
- On schedule change, evaluate pause/resume state properly
- Fixed %s.n bug in the TV Sorting Preview
- Fixed %s.n and %s_n bug in TV Sorting output


*******************************************
*** Major changes since 0.3.4           ***
*******************************************

- Secure NNTP (SSL)
- RSS is finally useful
- Better newzbin support
    - Download based on Bookmarks
    - Compatible with the new www.newzbin.com
- User-defined categories for precise storage and handling
- Intelligent handling of seasons of TV shows
- The Windows binary distribution now comes with a PAR2
  program that supports a multi-core CPU.
  You can tune the performance of PAR2 (Config->Switches)
- iPhone skin
- Optional secondary web-interface on http://host:port/sabnzbd/m
- Improved bandwidth control
- Highly improved Plush and Smpl skins
- General improvement of robustness and usability

==============================================================
