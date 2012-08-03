Release Notes  -  SABnzbd 0.7.3
===============================

## Fixes in 0.7.3

- Prevent queue deadlock in case of fatally damaged par2 files
- Try to keep OSX Mountain Lion awake as long as downloading/postprocessing runs
- Add RSS filter-enable checkboxes to Plush, Smpl and Classic skins
- Fix problem with saving modified paramters of an already enabled server
- Extend "check new release" option with test releases
- Correct several errors in Sort function
- Improve organization of Config->Servers
- Make detection of samples less aggressive
- Ignore pseudo NZB files that start with a period in the name

The Special option "random_server_ip" has been renamed to "randomize_server_ip"
and the default is now "Off".
The reason is that this option kills the speed of some Usenet providers.
If you really need this feature, you have to re-enable it.


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
