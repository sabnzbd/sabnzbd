*******************************************
*** This is SABnzbd 0.6.0 ALpha 10      ***
*******************************************
SABnzbd is an open-source cross-platform binary newsreader.
It simplifies the process of downloading from Usenet dramatically,
thanks to its friendly web-based user interface and advanced
built-in post-processing options that automatically verify, repair,
extract and clean up posts downloaded from Usenet.
SABnzbd also has a fully customizable user interface,
and offers a complete API for third-party applications to hook into.

There is an extensive Wiki on the use of SABnzbd.
http://wiki.sabnzbd.org/

>>> PLEASE ALSO READ THE FILE "ISSUES.txt" <<<

*******************************************
*** WARNING ... WARNING                 ***
*******************************************
This is Alpha software.
It works but may contain smaller bugs plus incomplete and
less fortunate design decisions.
We released it to get feedback from experienced users.

The organisation of the download queue is different from 0.5.x.
0.6.x will finish downloading an existing queue, but you
cannot go back to an older version without losing your queue.


*******************************************
*** Upgrading from 0.5.x                ***
*******************************************
Stop SABnzbd.
Uninstall current version, keeping the data.
Install new version
Start SABnzbd.


*******************************************
*** Upgrading from 0.4.x                ***
*******************************************

>>>>> PLEASE DOWNLOAD YOUR CURRENT QUEUE BEFORE UPGRADING <<<<<<

When upgrading from a 0.4.x release such as 0.4.12 your old settings will be kept.
You will however be given a fresh queue and history. If you have items in your queue
from the older version of SABnzbd, you can either re-import the nzb files if you kept
an nzb backup folder, or temporarily go back to 0.4.x until your queue is complete.

The history is now stored in a better format meaning future upgrades should be backwards
compatible.


*******************************************
*** Changes since 0.4.12                ***
*******************************************
Core Upgrades
- New Quick-Start Wizard - If you don't have any servers set you'll get a neat
  little five-page wizard allowing you to change all the config settings you
  really need to worry about. Stuff like "How should SABnzbd be accessible?
  Remotely or locally?" and "What's your server address", in a step by step manner.
  Features a button on the server page to test the connection to the news server,
  to make sure you have entered your details correctly.
- HTTPS Support - The Web-UI now supports HTTPS and has a standard login window
  (if you use a login/pass). The URL no longer requires the /sabnzbd/ part,
  though the old URL is still supported.
- File Quick-Check - We can now skip par2 verification altogether in most cases
  by performing a quick-check of file hashes before post-processing.
  If quick-check passes, then all the files are complete and we can proceed
  without doing the lengthy par2 verification step.
- Localization System - We now ship with five localizations,
  English, French, Dutch, German and Swedish, and have a rather simple system
  for implementing new translations. If you'd like to contribute one,
  please inquire on our forums.
- More Indexing Sites - SABnzbd now supports more than just Newzbin.
  See the support list for full details. Highlights include the RSS feeds
  for NZBMatrix and Nzbs.org
- Revamped Config System - The configuration backend was overhauled in 0.5.
  Many of the config pages have been changed around to make more sense,
  you can now easily enable/disable servers, you can turn servers on and off
  with schedules and in general all server interaction is much faster than before.
  You also only have to restart SABnzbd for major changes to take effect.
- File Association - .nzb files can now be associated with SABnzbd in Windows,
  so you can just double click them to load the file into your queue.
  You can set this up manually on other operating systems by launching SABnzbd
  with arguments containing a path, or multiple paths to local nzb/rar/zip files.
- Password Support - Basic support for password protected rar-files is now in.
  It's limited, but it works.
- .TS filejoining - The file joining system now supports merging .TS files.
- New Sorting Options - Date and Custom sorting options have been added, so downloads
  with a date can be sorted as such, and further customized sorting options
  can be developed by users.
- Email Templates - You can now design custom email templates to report
  whatever information you want, including multiple recipients.
- OSX Finder menu - SABnzbd now embeds itself in the Finder menubar to give
  you some basic functions.

The API
- 0.4 introduced our API, 0.5 expands it to cover everything SABnzbd is capable of.
  Why does this matter? It means if you know any programming language and
  understand how to parse XML/JSON and POST data to an address,
  then you can write some application which can communicate with SABnzbd
  almost as easily as a template can.

The Queue & History

- Per-Item Pause - Now, in addition to being able to pause the whole queue,
  you can also pause individual items in the queue. You can also force downloads
  to start while the whole queue is paused.
- Temporary Pause - 0.5 also brings the ability to pause the queue temporarily.
  So if you just want to pause for 30 minutes while you use your internet connection
  for something else, you can. This is nice, as it means you don't have
  to remember to go back and unpause SABnzbd.
- Priorities - The queue now has four priorities, Normal, High, Low and force.
  Think of this as an easy method to move things around your queue, or to insert
  things into specific areas of your queue. One use case is to set everything
  to "normal" by default, so it works like 0.4.x. However, you can then add
  a new post or RSS feed as high-priority to have it be inserted to the top of the queue,
  or add one as low-priority to have it inserted at the bottom of the queue
  and keep below normal downloads that are added. Forced items will go straight
  to the top of the queue, and will continue to download even if the queue is paused.
- Renaming - You can now rename items in the Queue, SABnzbd will use the new name
  as the completed directory name.
- New History Backend - The history is now stored in a database,
  so we can handle larger histories better, and store more information about downloads.
  It also now survives between having the queue cleared.

Templates

- New Default Template - With 0.5, the "smpl" template is now the default.
  The old basic template is still there, but is now called "Classic".
- SMPL - Has been reworked to be much faster and friendlier to use.
  The default page now shows the top 5 items from the queue and history.
  The queue and history are also now paginated to stop loading a massive number of items.
- Plush - Complete backend rewrite to work almost exclusively off the API
  [so it's MUCH faster], and a reorganized (and more accessible!) main menu.
  The Queue and History also now have pagination built in, so you can have hundreds
  of items in both, and only ever have to deal with a manageable number of items on any given page.
- Mobile - Thanks to the new API and the jQTouch Framework, we've got
  a brand new mobile theme. It's full featured (save for config options),
  and gives you the ability to add new nzbs, reorder existing ones, manage the queue, etc.
  "Mobile" replaces the old "iPhone" template.

Bugfixes:
* Sure!
