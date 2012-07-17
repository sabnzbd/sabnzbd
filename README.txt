Release Notes  -  SABnzbd 0.7.2
===============================

## Fixes in 0.7.2
- Improve support for nzbsrus.com
- Don't try to show NZB age when not known yet
- Prevent systems with unresolvable hostnames from always using 0.0.0.0
- Initial "quota left" was not set correctly when enabling quota
- Report incorrect RSS filter expressions (instead of aborting analysis)
- Improve detection of invalid articles (so that backup server will be tried)
- Windows installer: don't remove settings by default when uninstalling
- Fix sorting of rar files in job so that .rar preceeds .r00
- Fix for NZB-icon issue when 0.7.0 was previously installed
- Fix startup problem on Windows when IPv4 has precedence over IPv6

## Fixes in 0.7.1
- Fixed problem were fetching par2 files after first verification could stall in the queue
- Fixed retry behaviour of NZB fetching from URL (with handling of nzbsrus.com error codes)
- Verification/repair would not be executed properly when one more RAR files
  missed their first article.
- Improved backup of sabnzbd.ini file, now uses backup when original is gone or corrupt
- Several translations extended/improved
- Plush skin: fix problems with pull-down menus in Mobile Safari
- On some Linux and OSX systems using localhost would still make SABnzbd
  give access to other computers
- Windows: the installer did not set an icon when associating NZB files with SABnzbd
- Fix problem that the Opera browser had with Config->Servers
- Retry a few times when accessing a mounted drive to create the
  final destination folder
- Minor fixes in Window Tray icon and OSX top menu
- Add no_ipv6 special for systems that keep having issues with [::1]
- Fix crash in QuickCheck when expected par2 file wasn't downloaded
- API calls "addurl" and "addid" (newzbin) can now be used interchangeably
- Fix endless par2-fetch loop after retrying failed job
- Don't send "bad fetch" email when emailing is off
- Add some support for nzbrus.com's non-VIP limiting
- Fix signing of OSX DMG

## What's new in 0.7.0

- Download quota management
- Windows: simple system tray menu
- Multi-platform Growl support
- NotifyOSD support for Linux distros that have it
- Option to set maximum number of retries for servers (prevents deadlock)
- Pre-download check to estimate completeness (reliability is limited)
- Prevent partial downloading of par2 files that are not needed yet
- Config->Special for settings previously only available in the sabnzbd.ini file
- For Usenet servers with multiple IP addresses, pick a random one per connection
- Add pseudo-priority "Stop" that will send the job immediately to the post-processing queue
- Allow jobs still  waiting for post-processing to be deleted too
- More persistent retries for unreliable indexers
- Single Configuration skin for all others skins (there is an option for the old style)
- Config->Special for settings that were previously only changeable in the sabnzbd.ini file
- Add Spanish, Portuguese (Brazil) and Polish translations
- Individual RSS filter toggle
- Unified OSX DMG


## About
  SABnzbd is an open-source cross-platform binary newsreader.
  It simplifies the process of downloading from Usenet dramatically,
  thanks to its web-based user interface and advanced
  built-in post-processing options that automatically verify, repair,
  extract and clean up posts downloaded from Usenet.

  (c) Copyright 2007-2012 by "The SABnzbd-team" <team@sabnzbd.org>
