*************************************
*** This is SABnzbd 0.5.0Alpha4   ***
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


**WARNING**   **WARNING**   **WARNING**

This is early-release Alpha software, we know it's still immature.
Use at your own risk.
Don't blame us if your downloads fail.

You are invited to file problem reports on our forum:
http://forums.sabnzbd.org
Board = "Beta Releases"

**WARNING**   **WARNING**   **WARNING**

*******************************************
*** Upgrading from 0.5.0Alphas          ***
*******************************************
Just install the new program over the old one.
You can reuse your queue and history.

*******************************************
*** Upgrading from 0.4.x                ***
*******************************************
Do *not* install the new version over the old one.
Remove old one first or install seperately.
You can re-use your sabnzbd.ini file.
You cannot re-use an unfinished download queue or keep
the download history.
We promise that this is the last time you lose your history.


*******************************************
*** Changes since 0.4.7                 ***
*******************************************
Core Stuff:
* Updated Cherrypy - Among other things, this means you can now use HTTPS for the
  web ui and have a prettier login window if you use a login/pass.
  We have also dropped the need for /sabnzbd/ in the urls you use to access sabnzbd.
  It'll still work with /sabnzbd/, but it will also work without it now.
* New XML Parser - Results in lower memory usage when reading .nzb files, especially large ones.
* File Quick-Check - We can now skip par2 verification altogether in some cases by performing
  a quick-check of file hashes before post-processing.
* New Quick-Start Wizard - If you don't have any servers set, you'll get a neat little
  five-page wizard allowing you to change all the config settings you really need to worry about.
  Stuff like "How should SABnzbd be accessible? Remotely or locally?" and "What's your server address",
  in a step by step manner. Features a button on the server page to test the connection to the news server,
  to make sure you have entered your details correctly.
* Revamped Config System - The configuration backend was overhauled in 0.5.
  Many of the config pages have been changed around to make more sense,
  you can now easily enable/disable servers, and in general all server interaction is much faster than before.
* E-mail Templates - The e-mail system from 0.4.x has been updated to have a full template system,
  allowing you to customize e-mail alerts.
* File Association - .nzb files are now associated with SABnzbd, so you can just double click them
  to load the file into your queue. Currently only Windows is fully supported, however
  you can launch SABnzbd with arguments containing a path, or multiple paths to local nzb/rar/zip files.
* .TS Filejoining - File joining has been improved to allow support for joining multiple .TS files into one file.
* Date Sorting - To compliment series sorting, sorting has now been added for downloads with dates in their names,
  allowing you to place files in daily, monthly, yearly folders with proper naming
* General Sorting - Sorting for general downloads allows users to expand the series sorting into
  other types of downloads. Has support for years in titles allowing files to be placed in folders
  depending on the decade.

The API:
* Totally overhauled for 0.5. Basically, you now have full access to near everything about
  SABnzbd via POST and XML/JSON. See the full docs for more details. Why does this matter?
  It means if you know any programming language and understand how to parse XML/JSON and POST data to an URI,
  then you can write some application which can communicate with SABnzbd almost as easily as a template can.

The Queue & History:
* Per-Item Pause - Now, in addition to being able to pause the whole queue, you can also pause
  individual items in the queue. You can also force downloads to start while the whole queue is paused.
* Priorities - The queue now has four priorities, Normal, High, Low and force.
  Think of this as an easy method to move things around your queue, or to insert things into
  specific areas of your queue. One use case is to set everything to "normal" by default,
  so it works like 0.4.x. However, you can then add a new post or RSS feed as high-priority to have it be
  inserted to the top of the queue, or add one as low-priority to have it inserted at the bottom of the queue
  and keep below normal downloads that are added. Forced items will go straight to the top of the queue,
  and will continue to download even if the queue is paused.
* New History Backend - The history is now stored in a database, so we can handle larger histories better,
  and store more information about downloads.

Skins:
* General Template Changes - Templates have all been updated to support all the neat new features.
  So if you're one of those guys still married to Default, don't worry about missing out on all this new stuff.
* Plush - Complete backend rewrite to work almost exclusively off the API [so it's MUCH faster],
  and a reorganized (and more accessible!) main menu.
* SMPL - Has been reworked to be much faster and friendlier to use.
  The default page now shows the top 5 items from the queue and history.
  The queue and history are also now pages to stop loading a massive number of items.

Bugfixes:
* Sure!
