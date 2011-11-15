************************  SABnzbd 0.6.11RC1  ************************

What's new:
- Improve detection of encrypted RAR files during download
- SABnzbd will now listen on all "localhost" addresses
  This should prevent problems on IPV6-enabled systems
- Remove unneeded extra temporary folder level in Generic Sort
- When par2 fails and SFV-check enabled, verify using SFV files
- Perform extra checks on job administration
- Fix logging of pre-queue script result
- OSX: Fix Growl issues
- OSX: Show the promised 10 queue entries in the OSX menu instead of 9

PLEASE NOTE:
This RC will reject new NZB files and running jobs when it detects
problems with saving and reading of job administration files.
This is done to get more information on issues reported by some
users on unsupported operating systems and those using
external storage for the "temporary download folder".
This will not affect users who did not have such problems in the first place.

About:
  SABnzbd is an open-source cross-platform binary newsreader.
  It simplifies the process of downloading from Usenet dramatically,
  thanks to its friendly web-based user interface and advanced
  built-in post-processing options that automatically verify, repair,
  extract and clean up posts downloaded from Usenet.

  (c) Copyright 2007-2011 by "The SABnzbd-team" <team@sabnzbd.org>
