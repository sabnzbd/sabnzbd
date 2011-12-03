************************  SABnzbd 0.6.12 ************************

What's new (0.6.12):
- Fix issue with new localhost handling on some IPv4-only Unixes
- Fix job folder creation by Movie Sort when the Sort expression specifies one
- Fix problem with retrieving ZIP files from some web sites

What's new (0.6.11):
- Improve detection of encrypted RAR files during download
- SABnzbd will now listen on all "localhost" addresses
  This should prevent problems on IPV6-enabled systems
- Remove unneeded extra temporary folder level in Generic Sort
- When par2 fails and SFV-check enabled, verify using SFV files
- Perform extra checks on job administration
- Fix logging of pre-queue script result
- Better support for Yahoo pipes
- Accept NZB files containing incorrect dates
- Make newzbin "Get bookmarks now" button independent of automatic readout
- OSX: Fix Growl issues
- OSX: Show the promised 10 queue entries in the OSX menu instead of 9


About:
  SABnzbd is an open-source cross-platform binary newsreader.
  It simplifies the process of downloading from Usenet dramatically,
  thanks to its friendly web-based user interface and advanced
  built-in post-processing options that automatically verify, repair,
  extract and clean up posts downloaded from Usenet.

  (c) Copyright 2007-2011 by "The SABnzbd-team" <team@sabnzbd.org>
