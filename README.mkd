Release Notes  -  SABnzbd 0.7.20
================================


## Features

- Support of OSX Yosemite "Dark Mode"
- API call "Retry" now returns new job id (supporting nzbdrone)

## Bug fixes
- OSX unrar now really updated to 5.11 for Lion and higher
- unrar is now updated to 5.11 for Intel systems running (Snow)Leopard
- (Snow)Leopard on PPC still only has unrar 4.01, no new versions from rarlabs
- Fix email test issue


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

  (c) Copyright 2007-2014 by "The SABnzbd-team" \<team@sabnzbd.org\>


### IMPORTANT INFORMATION about release 0.7.x
<http://wiki.sabnzbd.org/introducing-0-7-0>

### Known problems and solutions
- Read the file "ISSUES.txt"

### Upgrading from 0.6.x
- Stop SABnzbd
- Install new version
- Start SABnzbd

### Upgrading from 0.5.x
- Stop SABnzbd
- Install new version
- Start SABnzbd.

The organization of the download queue is different from 0.5.x.
0.7.x will finish downloading an existing queue, but you
cannot go back to an older version without losing your queue.
Also, your sabnzbd.ini file will be upgraded, making it
incompatible with release 0.5.x

### Upgrading from 0.4.x
Download your current queue before upgrading.
