================================
NOVA 0.4.3 README - Sept 16, 2007
http://sabnzbd.organixdesign.com/

=======
AUTHORS
* Nathan Langlois => complete rewrite of NOVA for version 0.4
* Dana Woodman => original NOVA + concept design
* ShyPike => modified for SABnzbd-0.2.7

============
INTRODUCTION
We view this release very much as a public test. NOVA 0.3 preview 2 returned such a great response that we did not feel it was necessary to provide a final revision, and instead jumped straight to this one. Hope you all enjoy & happy downloading.

===========
WHAT IS NEW
* "Nighttime" concept design (NOTE: Dana hasn't had a chance to go over the new graphic design yet! If you think it looks good now, just you wait.)
* No more iFrames, layout is much more adaptive now
* AJAX Queue Components: Drag & drop sort, Post-processing, Drop, Pause, Verbosity, Sort by average age
* AJAX History Components: Verbosity, Purge
* AJAX refresh rate slider
* AJAX enqueueing of nzbs by report id & URL
* Many structural enhancements to the main statistics
* Standardized Queue & History JSON
* Compatible with multiple browser sessions opened concurrently
* Special care taken in terms of explanations that pop up when hovering items with your cursor
* Not to mention all the good parts from NOVA 0.3p2
* Much much more!

==================
NOVA 0.4.3 UPDATES
Added "Toggle Shutdown" back in + alert box (Windows only)
Queue & History reverted to NOVA v0.3p2 look
Queue Verbosity is now a two-step process:
(1) Toggle Verbosity -ON-
(2) Click the 'v' on an enqueued nzb to see its files
Double-click nzb filename to jump to top of queue
Drag & drop on filename column to sort enqueued nzbs
Queue & History menus no longer get scrunched
Overall % now stays visible on screen
Better labeling in Stats & Queue (more wording/icons for explanation)
"MB downloaded" replaced "MB remaining" in Queue & Stats
Better "broken nzb set" detection
Non-Newzbin nzbs won't show a 'View Report' icon anymore
(Very) minor optimizations - long way to go on this one
Default refresh rate increased to 8 seconds from 4
Current version number now visible in NOVA options

==================
NOVA 0.4.2 UPDATES
* Config & Connections now use Lytebox (pop up over content)
* History verbosity has a new icon to indicate an unzip

==================
NOVA 0.4.1 UPDATES
* Layout settings & Refresh rate now saved
* Fixed 'View Report' (the i icon) sometimes being unclickable
* History verbosity now has a new icon to indicate a join
* Queue verbosity now colored slightly better
* Stats more precise for free space & history

=========
DRAWBACKS
* Only works with Firefox 2+, Safari 3, & Opera 9.5
* Not optimized yet; it's okay, but not great

===
FAQ

Q: Can I contribute?
A: Yes; while we do not have a subversion repository set up, we encourage any suggestions. The good stuff will definitely get added in. Our goal is to turn this into a community project, if that wasn't obvious.

Q: How else can I help?
A: Visit our official site and donate Usenet access.

Q: Can you provide more information?!
A: Yes, stay tuned. Our ultimate goal is to allow for straightforward customization.

==============
SPECIAL THANKS
* Pim for the Dutch translation => http://www.pimspage.nl/
* Prototype Core Team => http://www.prototypejs.org/
* script.aculo.us => http://script.aculo.us/
* Lytebox => http://www.dolem.com/lytebox/
* Nuvola icon set => http://www.icon-king.com/?p=15
* Everyone in the community who left so much valuable feedback - we appreciate it greatly!
