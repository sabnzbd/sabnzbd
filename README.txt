Release Notes  -  SABnzbd 0.7.2RC2
==================================

## Fixes in 0.7.2RC2
- Improve support for nzbsrus.com
- Don't try to show NZB age when not known yet
- Prevent systems with unresolvable hostnames from always using 0.0.0.0

## Fixes in 0.7.2RC1
- Fix fatal error in nzbsrus.com support
- Initial "quota left" was not set correctly when enabling quota
- Report incorrect RSS filter expressions (instead of aborting analysis)
- Improve detection of invalid articles (so that backup server will be tried)
- Windows installer: improve NZB association so that a reboot isn't needed
- Windows installer: don't remove settimngs by default when uninstalling
- Fix sorting of rar files in job so that .rar preceeds .r00

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
