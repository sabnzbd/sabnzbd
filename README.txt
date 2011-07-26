************************  SABnzbd 0.6.6  ************************

What's new:
- Compatible with OSX Lion
- End-of-queue action now ignores paused items in the queue
- Fetching extra par2 files now obeys pause too
- Extension-based cleanup now also cleans sub-folders
- When "Download only" is used, do not send downloaded NZB files to the queue
- Fix bad links coming from nzbclub.com
- A job sometimes fails verification when the option "don't download samples" is used.
  Now this option will be ignored when you click "Retry" in the history.
- File an error message when the RSS-email template is missing.
- Fix sending of duplicate emails when using a list of recipients
- Fix handle leakage on Windows
- On OSX, SABnzbd didn't handle "Open With" of nzb.gz files properly

About:
  SABnzbd is an open-source cross-platform binary newsreader.
  It simplifies the process of downloading from Usenet dramatically,
  thanks to its friendly web-based user interface and advanced
  built-in post-processing options that automatically verify, repair,
  extract and clean up posts downloaded from Usenet.

  (c) Copyright 2007-2011 by "The SABnzbd-team" <team@sabnzbd.org>
