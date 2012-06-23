Release Notes  -  SABnzbd 0.7.1RC2
==================================

## Fixes in 0.7.1
### RC2
- Improved backup of sabnzbd.ini file, now uses backup when original is gone or corrupt
- Swedish translation extended
### RC1
- Plush skin: fix problems with pull-down menus in Mobile Safari
- On some Linux and OSX systems using localhost would still make SABnzbd
  give access to other computers
- Windows: the installer did not set an icon when associating NZB files with SABnzbd
- Fix problem that the Opera browser had with Config->Servers
- Retry a few times when accessing a mounted drive to create the
  final destination folder
- Minor fixes in  Window Tray icon and OSX top menu

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
