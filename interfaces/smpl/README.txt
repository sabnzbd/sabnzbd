SMPL - Simple web-iu by switch - switch@sabnzbd.org

SMPL is licenced under the Creative Commons Public Licence.
Please see LICENCE.txt or http://creativecommons.org/licenses/by/3.0/ for more information
------------------------
v1.2

Install Instructions
------------------------
-Go to the General config page in sabnzbd eg 'http://localhost:8080/sabnzbd/config/general/'
-select 'smpl' from the dropdown list under User interface:
-restart sabnzbd to see the new template
-If you notice any weird graphical stuff, press ctrl+f5 on your keyboard to force a refresh of the page without cache



Credits
------------------------
Javascript library - Mochikit http://www.mochikit.com/
Javascript canvas library - Plotkit http://www.liquidx.net/plotkit/
Canvas IE support - Excanvas http://sourceforge.net/projects/excanvas/
Silk icons - http://www.famfamfam.com/lab/icons/silk/


Changelog
------------------------
1.0+1.1
-------------
-Added newzbin config page
-Allow displaying of warnings in connection page
-Added Time-left + Speed/Paused/Idle to the title of the browser tab/window.
-Added: Combined queue+history views
-Fixed: Various stuff

beta4
-------------
-rewritten all javascript
-added ajax form submitting
-added drop down list for a changable refresh rate
-fixed graph updating, now shows correct values and works in IE7
-retrieves info from the new JSON api
-Upgraded to Mochikit 1.4
-removed top progressbar from queue and changed delete link to be an icon.
-redesigned forms to look prettier on firefox2 as well.
-lots of small fixes for various browsers.
-includes links for the latest log downloading, and email testing.
-added the current download below the graph.
-added a simple link at the bottom of the page to function as a version checker.

beta 3.1
-------------
-added purge history and toggle verbosity to history page

beta3
-------------
-Added sort, verbosity and shutdown toggles
-Styled verbosity view
-Changed the way queue stuff submits so it should keep refreshing
-Added 'age' to queue, will try to condense it to show just days
-forced main page forms elements to each be on their own line
-added help pages that link to the wiki like in the default template


TODO:
------------------------
-Make it standards compliant.
