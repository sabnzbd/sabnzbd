=============================================
SABnzbd+ Plush Template README - Nov 28, 2007
Version 1.0.20071128

======
AUTHOR
* Nathan Langlois
* Dana Woodman

============
INTRODUCTION
* SABnzbdPlus 0.2.8 + required

========
BENEFITS
* Faster, more optimized, and more instantaneity than the NOVA template
* Better separation of JavaScript/CSS/HTML - easier to modify

=======
SECRETS
* Click NZB name in "Downloads" to sort files within the NZB set
* Click NZB name in "Finished" to jump to the Newzbin report if applicable

=========
WISH LIST
* IE7 compatibility
* Save Post-Processing options in +NZB 
* Drag & Drop Queue
* AJAX NZB upload
* Helpful hints upon mouse hover

====================
CHANGES 1.0.20071128
* Added layout switcher which stores your preference
* History RSS embedded into page (accessible from URL bar)
* Added Help menu which links to wiki, and narrowed lightbox width
* Config color scheme reverted to SABnzbd default (stands out more)
* Placeholder color scheme for NZBs (WHITE) to demonstrate more emphasis on this data, to be adjusted
* Canned the NZB name drop shadows
* Queue progress bars adapted to be more versatile for any colored background
* SAB+ & Plush version numbers shown upon hover "SABnzbd+ Plush" title

====================
CHANGES 1.0.20071124
* Major Queue Verbosity enhancements
* Various text changes

====================
CHANGES 1.0.20071122
* 0.2.8-only due to Configs
* Completed first phase of Queue Verbosity
* Assorted graphical enhancements
* Padded ETAs 00:00:00
* Top to bottom layout
* Pulled out "Check for Update" for now

===================
CHANGES 1.0pre-1117
* Changed look & icons of Queue & History stats
* Colored MB Left seperator & swapped in new Drop icon upon hover in Queue
* Cleaned up +NZB menu
* NZBs added by Report ID & URL now refresh the Queue immediately
* Fixed General Config settings
* Subtle differences to look of Queue

===================
CHANGES 1.0pre-1116
* Added icons for post-processing options menu (Firefox only)
* Added preliminary idea for a built-in interactive help system
* Fixed floating window close button

===================
CHANGES 1.0pre-1115
* Refresh Rate is saved/restored now
* Page/tab title now changes dynamically
* Added new unrar/unzip icons & favicon
* Fixed icons/"image" text in Opera
* Fixed missing Queue when fetching NZBs off Newzbin
* Fixed tainted drop-shadows on NZB names when using huge font sizes
* Apparently nzbdStatus will work now/soon (standardized JSON)

========================
KNOWN BUGS + RESOLUTIONS

* Post-Processing options in the Downloads keep closing
--- This happens when the Queue reloads
--- Try again or slow the refresh rate

==============
SPECIAL THANKS
* Everyone in the community who left so much valuable feedback
* jQuery
* Interface
* Nuvola
* Greybox
* jsProgressBarHandler
