#!/usr/bin/python -OO
# -*- coding: UTF-8 -*-
# Copyright 2012-2015 The SABnzbd-Team <team@sabnzbd.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
sabnzbd.skintext - Language strings used in the templates
"""

SKIN_TEXT = {

# Special texts
    'stage-download'     : TT('Download'), #: Queue status "download"
    'stage-repair'       : TT('Repair'), #: PP phase "repair"
    'stage-filejoin'     : TT('Join files'), #: PP phase "filejoin"
    'stage-unpack'       : TT('Unpack'), #: PP phase "unpack"
    'stage-script'       : TT('Script'), #: PP phase "script"
    'stage-source'       : TT('Source'), #: PP Source of the NZB (path or URL)
    'stage-servers'      : TT('Servers'), #: PP Distribution over servers
    'stage-fail'         : TT('Failure'), #: PP Failure message

    'post-Completed'     : TT('Completed'), #: PP status
    'post-Failed'        : TT('Failed'), #: PP status
    'post-Queued'        : TT('Waiting'), #: Queue and PP status
    'post-Paused'        : TT('Paused'), #: PP status
    'post-Repairing'     : TT('Repairing...'), #: PP status
    'post-Extracting'    : TT('Extracting...'), #: PP status
    'post-Moving'        : TT('Moving...'), #: PP status
    'post-Running'       : TT('Running script...'), #: PP status
    'post-Fetching'      : TT('Fetching extra blocks...'), #: PP status
    'post-QuickCheck'    : TT('Quick Check...'), #: PP status
    'post-Verifying'     : TT('Verifying...'), #: PP status
    'post-Downloading'   : TT('Downloading'), #: Pseudo-PP status, in reality used for Queue-status
    'post-Grabbing'      : TT('Get NZB'), #: Pseudo-PP status, in reality used for Grabbing status
    'post-Checking'      : TT('Checking'), #: PP status

    'sch-frequency'      : TT('Frequency'), #:  #: Config->Scheduler
    'sch-action'         : TT('Action'), #:  #: Config->Scheduler
    'sch-arguments'      : TT('Arguments'), #:  #: Config->Scheduler
    'sch-task'           : TT('Task'), #:  #: Config->Scheduler
    'sch-disable_server' : TT('disable server'), #:  #: Config->Scheduler
    'sch-enable_server'  : TT('enable server'), #:  #: Config->Scheduler
    'sch-resume'         : TT('Resume'), #:  #: Config->Scheduler
    'sch-pause'          : TT('Pause'), #:  #: Config->Scheduler
    'sch-shutdown'       : TT('Shutdown'), #:  #: Config->Scheduler
    'sch-restart'        : TT('Restart'), #:  #: Config->Scheduler
    'sch-speedlimit'     : TT('Speedlimit'), #:  #: Config->Scheduler
    'sch-pause_all'      : TT('Pause All'), #:  #: Config->Scheduler
    'sch-pause_post'     : TT('Pause post-processing'), #:  #: Config->Scheduler
    'sch-resume_post'    : TT('Resume post-processing'), #:  #: Config->Scheduler
    'sch-scan_folder'    : TT('Scan watched folder'), #:  #: Config->Scheduler
    'sch-rss_scan'       : TT('Read RSS feeds'), #:  #: Config->Scheduler
    'sch-remove_failed'  : TT('Remove failed jobs'), #: Config->Scheduler
    'sch-pause_all_low'  : TT('Pause low prioirty jobs'), #: Config->Scheduler
    'sch-pause_all_normal':TT('Pause normal prioirty jobs'), #: Config->Scheduler
    'sch-pause_all_high' : TT('Pause high prioirty jobs'), #: Config->Scheduler
    'sch-resume_all_low' : TT('Resume low prioirty jobs'), #: Config->Scheduler
    'sch-resume_all_normal':TT('Resume normal prioirty jobs'), #: Config->Scheduler
    'sch-resume_all_high': TT('Resume high prioirty jobs'), #: Config->Scheduler
    'sch-enable_quota'   : TT('Enable quota management'), #: Config->Scheduler
    'sch-disable_quota'  : TT('Disable quota management'), #: Config->Scheduler

    'prowl-off'          : TT('Off'), #: Prowl priority
    'prowl-very-low'     : TT('Very Low'), #: Prowl priority
    'prowl-moderate'     : TT('Moderate'), #: Prowl priority
    'prowl-normal'       : TT('Normal'), #: Prowl priority
    'prowl-high'         : TT('High'), #: Prowl priority
    'prowl-emergency'    : TT('Emergency'), #: Prowl priority

    'pushover-off'       : TT('Off'), #: Prowl priority
    'pushover-low'       : TT('Low'), #: Prowl priority
    'pushover-high'      : TT('High'), #: Prowl priority
    'pushover-confirm'   : TT('Confirm'), #: Prowl priority

# General texts
    'default' : TT('Default'), #: Default value, used in dropdown menus
    'none' : TT('None'), #: No value, used in dropdown menus
    'KBs' : TT('KB/s'), #: Speed indicator kilobytes/sec
    'MB' : TT('MB'), #: Megabytes
    'GB' : TT('GB'), #: Gigabytes
    'B' : TT('B'), #: Bytes (used as postfix, as in "GB", "TB")
    'hour' : TT('hour'), #: One hour
    'hours' : TT('hours'), #: Multiple hours
    'minute' : TT('min'), #: One minute
    'minutes' : TT('mins'), #: Multiple minutes
    'second' : TT('sec'), #: One second
    'seconds' : TT('seconds'), #: Multiple seconds
    'day' : TT('day'),
    'days' : TT('days'),
    'week' : TT('week'),
    'month' : TT('Month'),
    'year' : TT('Year'),
    'daily' : TT('Daily'),
    'monday' : TT('Monday'),
    'tuesday' : TT('Tuesday'),
    'wednesday' : TT('Wednesday'),
    'thursday' : TT('Thursday'),
    'friday' : TT('Friday'),
    'saturday' : TT('Saturday'),
    'sunday' : TT('Sunday'),
    'day-of-month' : TT('Day of month'),
    'thisWeek' : TT('This week'),
    'thisMonth' : TT('This month'),
    'today' : TT('Today'),
    'total' : TT('Total'),
    'on' : TT('on'),
    'off' : TT('off'),
    'parameters' : TT('Parameters'), #: Config: startup parameters of SABnzbd
    'pythonVersion' : TT('Python Version'),
    'homePage' : TT('Home page'), #: Home page of the SABnzbd project
    'source' : TT('Source'), #: Where to find the SABnzbd sourcecode
    'or' : TT('or'), #: Used in "IRC or IRC-Webaccess"
    'host' : TT('Host'),
    'comment' : TT('Comment'),
    'send' : TT('Send'),
    'cancel' : TT('Cancel'),
    'other' : TT('Other'),
    'report' : TT('Report'),
    'video' : TT('Video'),
    'audio' : TT('Audio'),
    'notUsed' : TT('Not used'),
    'orLess' : TT('or less'),

# General template elements
    'signOn' : TT('The automatic usenet download tool'), #: SABnzbd's theme line
    'button-save' : TT('Save'), #: "Save" button
    'queued' : TT('Queued'), #: "Queued" used to show amount of jobs
    'button-back' : TT('Back'), #: Generic "Back" button
    'button-x' : TT('X'), #: Generic "Delete" button, short form
    'confirm' : TT('Are you sure?'), #: Used in confirmation popups
    'delFiles' : TT('Delete all downloaded files?'),  #: Used in confirmation popups

# Header
    'menu-home' : TT('Home'), #: Main menu item
    'menu-queue' : TT('Queue'), #: Main menu item
    'menu-history' : TT('History'), #: Main menu item
    'menu-config' : TT('Config'), #: Main menu item
    'menu-cons' : TT('Status'), #: Main menu item
    'menu-help' : TT('Help'), #: Main menu item
    'menu-wiki' : TT('Wiki'), #: Main menu item
    'menu-forums' : TT('Forum'), #: Main menu item
    'menu-irc' : TT('IRC'), #: Main menu item
    'cmenu-general' : TT('General'), #: Main menu item
    'cmenu-folders' : TT('Folders'), #: Main menu item
    'cmenu-switches' : TT('Switches'), #: Main menu item
    'cmenu-servers' : TT('Servers'), #: Main menu item
    'cmenu-scheduling' : TT('Scheduling'), #: Main menu item
    'cmenu-rss' : TT('RSS'), #: Main menu item
    'cmenu-notif' : TT('Notifications'), #: Main menu item
    'cmenu-email' : TT('Email'), #: Main menu item
    'cmenu-cat' : TT('Categories'), #: Main menu item
    'cmenu-sorting' : TT('Sorting'), #: Main menu item
    'cmenu-special' : TT('Special'), #: Main menu item

# Footer
    'ft-download' : TT('Download Dir'), # Used in Footer
    'ft-complete' : TT('Complete Dir'), # Used in Footer
    'ft-speed' : TT('Download speed'), # Used in Footer
    'ft-queued' : TT('Queued'), # Used in Footer
    'ft-paused' : TT('PAUSED'), # Used in Footer
    'ft-buffer@2' : TT('Cached %s articles (%s)'), # Used in Footer
    'ft-sysload' : TT('Sysload'), # Used in Footer
    'ft-warning' : TT('WARNINGS'), # Used in Footer
    'ft-newRelease@1' : TT('New release %s available at'), # Used in Footer

# Main page
    'addNewJobs' : TT('Add new downloads'),
    'shutdownOK?' : TT('Are you sure you want to shutdown SABnzbd?'),
    'link-shutdown' : TT('Shutdown'), #: Shutdown SABnzbd
    'link-pause' : TT('Pause'), #: Pause downloading
    'link-resume' : TT('Resume'), #: Resume downloading
    'button-add' : TT('Add'), #: Add NZB to queue (button)
    'add' : TT('Add'),  #: Add NZB to queue (header)
    'addFile' : TT('Add File'), #: Add NZB file to queue (header
    'category' : TT('Category'), #: Job category
    'pp' : TT('Processing'),
    'script' : TT('Script'),
    'priority' : TT('Priority'),
    'pp-none' : TT('Download'), #: Post processing pick list
    'pp-repair' : TT('+Repair'), #: Post processing pick list
    'pp-unpack' : TT('+Unpack'), #: Post processing pick list
    'pp-delete' : TT('+Delete'), #: Post processing pick list
    'pp-n' : TT('&nbsp;'),  #: Part of Post processing pick list: abbreviation for "Download"
    'pp-r' : TT('R'),  #: Post processing pick list: abbreviation for "+Repair"
    'pp-u' : TT('U'),  #: Post processing pick list: abbreviation for "+Unpack"
    'pp-d' : TT('D'),  #: Post processing pick list: abbreviation for "+Delete"
    'pr-force' : TT('Force'), #: Priority pick list
    'pr-repair' : TT('Repair'), #: Priority pick list
    'pr-normal' : TT('Normal'), #: Priority pick list
    'pr-high' : TT('High'), #: Priority pick list
    'pr-low' : TT('Low'), #: Priority pick list
    'pr-paused' : TT('Paused'), #: Priority pick list
    'pr-stop' : TT('Stop'), #: Priority pick list
    'enterURL' : TT('Enter URL'), #: Add NZB Dialog
    'enterID' : TT('&nbsp;or Report ID'), #: Add NZB Dialog

# Queue page
    'link-sortByName' : TT('Sort by name'), #: Queue page button
    'link-sortByAge' : TT('Sort by age'), #: Queue page button
    'link-sortBySize' : TT('Sort by size'), #: Queue page button
    'link-hideFiles' : TT('Hide files'), #: Queue page button
    'link-showFiles' : TT('Show files'), #: Queue page button
    'onQueueFinish' : TT('On queue finish'),  #: Queue page selection menu
    'shutdownPc' : TT('Shutdown PC'), #: Queue page end-of-queue action
    'standbyPc' : TT('Standby PC'), #: Queue page end-of-queue action
    'hibernatePc' : TT('Hibernate PC'), #: Queue page end-of-queue action
    'shutdownSab' : TT('Shutdown SABnzbd'), #: Queue page end-of-queue action
    'speedLimit' : TT('Speed Limit'), #: Queue page selection menu or entry box
    'pauseFor' : TT('Pause for'), #: Queue page button or entry box
    'mode' : TT('Processing'), #: Queue page table column header
    'order' : TT('Order'), #: Queue page table column header
    'name' : TT('Name'), #: Queue page table column header
    'remainTotal' : TT('Remain/Total'), #: Queue page table column header
    'eta' : TT('ETA'), #: Queue page table column header, "estimated time of arrival"
    'age' : TT('AGE'), #: Queue page table column header, "age of the NZB"
    'button-del' : TT('Del'),  #: Queue page table, "Delete" button
    'button-resume' : TT('Resume'), #: Queue page button
    'button-pause' : TT('Pause'), #: Queue page button
    'button-retry' : TT('Retry'), #: Queue page button
    'eoq-actions' : TT('Actions'), #: Queue end-of-queue selection box
    'eoq-scripts' : TT('Scripts'), #: Queue page table, script selection menu
    'purgeQueue' : TT('Purge Queue'), #: Queue page button
    'purgeQueueConf' : TT('Delete all items from the queue?'), #: Confirmation popup
    'purgeNZBs' : TT('Purge NZBs'), #: Queue page button
    'purgeNZBs-Files' : TT('Purge NZBs & Delete Files'), #: Queue page button
    'retryQueue' : TT('Retry all failed jobs'), #: Retry all failed jobs dialog box
    'removeNZB' : TT('Remove NZB'), #: Queue page button
    'removeNZB-Files' : TT('Remove NZB & Delete Files'), #: Queue page button
    'AofB' : TT('of'), #: Queue page, as in "4G *of* 10G"
    'missingArt': TT('Missing articles'), #: Caption for missing articles in Queue
    'quota-left' : TT('Quota left'), #: Remaining quota (displayed in Queue)
    'manual' : TT('manual'), #: Manual reset of quota
    'link-resetQuota' : TT('Reset Quota now'),

# History page
    'purgeHist' : TT('Purge History'), #: History page button
    'purgeHistFailed' : TT('Purge Failed History'), #: History page button
    'purgeHistConf' : TT('Delete all completed items from History?'), #: Confirmation popup
    'purgeHistFailedConf' : TT('Delete all failed items from History?'), #: Confirmation popup
    'hideDetails' : TT('Hide details'), #: Button/link hiding History job details
    'showDetails' : TT('Show details'), #: Button/link showing History job details
    'sizeHist' : TT('History Size'), #: History: amount of downloaded data
    'showFailedHis' : TT('Show Failed'), #: Button or link showing only failed History jobs. DON'T MAKE THIS VERY LONG!
    'showAllHis' : TT('Show All'), #: Button or link showing all History jobs
    'completed' : TT('Completed'), #: History: job status
    'size' : TT('Size'), #: History table header
    'status' : TT('Status'), #: History table header
    'purgeFailed' : TT('Purge Failed NZBs'), #: Button to delete all failed jobs in History
    'purgeFailed-Files' : TT('Purge Failed NZBs & Delete Files'), #: Button to delete all failed jobs in History, including files
    'purgeCompl' : TT('Purge Completed NZBs'), #: Button to delete all completed jobs in History
    'opt-extra-NZB' : TT('Optional Supplemental NZB'), #: Button to add NZB to failed job in History
    'msg-path' : TT('Path'), #: Path as displayed in History details
    'link-retryAll' : TT('Retry all failed'), #: Retry all failed jobs in History
    'retryNZBs' : TT('Retry All'), #: Retry all button for Retry All Failed Jobs
    'spam' : TT('Virus/spam'),
    'encrypted' : TT('Passworded'),
    'expired' : TT('Out of retention'),
    'otherProblem' : TT('Other problem'),

# Connections page
    'link-forceDisc' : TT('Force Disconnect'), #: Status page button
    'askTestEmail' : TT('This will send a test email to your account.'),
    'link-showLog' : TT('Show Logging'), #: Status page button
    'link-showWeblog' : TT('Show Weblogging'), #: Status page button
    'link-testEmail' : TT('Test Email'), #: Status page button
    'logging' : TT('Logging'), #: Status page selection menu
    'log-errWarn' : TT('Errors/Warning'), #: Status page table header
    'log-info' : TT('+ Info'), #: Status page logging selection value
    'log-debug' : TT('+ Debug'), #: Status page logging selection value
    'connections' : TT('Connections'), #: Status page tab header
    'thread' : TT('Thread'), #: Status page, server threads
    'emailResult' : TT('Email Test Result'), #: Status page, title for email test result
    'lastWarnings' : TT('Latest Warnings'), #: Status page, table header
    'clearWarnings' : TT('clear'),  #: Status page button
    'server-blocked' : TT('Unblock'), #: Status page button
    'article-id' : TT('Article identifier'), #: Status page, article identifier
    'file-set' : TT('File set'), #: Status page, par-set that article belongs to
    'warn-when' : TT('When'), #: Status page, table column header, when error occured
    'warn-type' : TT('Type'), #: Status page, table column header, type of message
    'warning' : TT('Warning'), #: Status page, table column header, actual message
    'warnings' : TT('Warnings'), #: Footer: indicator of warnings
    'enabled' : TT('Enabled'), #: Status page, indicator that server is enabled

# Configuration
    'configuration' : TT('Configuration'),
    'confgFile' : TT('Config File'),
    'cache' : TT('Used cache'), #: Main config page, how much cache is in use
    'explain-Restart' : TT('This will restart SABnzbd.<br />Use it when you think the program has a stability problem.<br />Downloading will be paused before the restart and resume afterwards.'),
    'button-restart' : TT('Restart'),
    'explain-orphans' : TT('There are orphaned jobs in the download folder.<br />You can choose to delete them (including files) or send them back to the queue.'),
    'button-repair' : TT('Repair'),
    'explain-Repair' : TT('The "Repair" button will restart SABnzbd and do a complete<br />reconstruction of the queue content, preserving already downloaded files.<br />This will modify the queue order.'),
    #'explain-Shutdown' : TT('This will end the SABnzbd process. <br />You will be unable to access SABnzbd and no downloading will take place until the service is started again.'),
    'version' : TT('Version'),
    'uptime' : TT('Uptime'),
    'backup' : TT('Backup'), #: Indicates that server is Backup server in Status page
    'oznzb' : TT('OZnzb'),

# Config->General
    'generalConfig' : TT('General configuration'),
    'restartRequired' : TT('Changes will require a SABnzbd restart!'),
    'webServer' : TT('SABnzbd Web Server'),
    'opt-host' : TT('SABnzbd Host'),
    'explain-host' : TT('Host SABnzbd should listen on.'),
    'opt-port' : TT('SABnzbd Port'),
    'explain-port' : TT('Port SABnzbd should listen on.'),
    'opt-web_dir' : TT('Web Interface'),
    'explain-web_dir' : TT('Choose a skin.'),
    'opt-web_dir2' : TT('Secondary Web Interface'),
    'explain-web_dir2' : TT('Activate an alternative skin.'),
    'webAuth' : TT('Web server authentication'),
    'opt-web_username' : TT('SABnzbd Username'),
    'explain-web_username' : TT('Optional authentication username.'),
    'opt-web_password' : TT('SABnzbd Password'),
    'explain-web_password' : TT('Optional authentication password.'),
    'httpsSupport' : TT('HTTPS Support'),
    'opt-enable_https' : TT('Enable HTTPS'),
    'opt-notInstalled' : TT('not installed'),
    'explain-enable_https' : TT('Enable accessing the interface from a HTTPS address.'),
    'opt-https_port' : TT('HTTPS Port'),
    'explain-https_port' : TT('If empty, the standard port will only listen to HTTPS.'),
    'opt-https_cert' : TT('HTTPS Certificate'),
    'explain-https_cert' : TT('File name or path to HTTPS Certificate.'),
    'opt-https_key' : TT('HTTPS Key'),
    'explain-https_key' : TT('File name or path to HTTPS Key.'),
    'opt-https_chain' : TT('HTTPS Chain Certifcates'),
    'explain-https_chain' : TT('File name or path to HTTPS Chain.'),
    'tuning' : TT('Tuning'),
    'opt-refresh_rate' : TT('Queue auto refresh interval:'),
    'explain-refresh_rate' : TT('Refresh interval of the queue web-interface page(sec, 0= none).'),
    'opt-rss_rate' : TT('RSS Checking Interval'),
    'explain-rss_rate' : TT('Checking interval (in minutes, at least 15). Not active when you use the Scheduler!'),
    'opt-bandwidth_max' : TT('Maximum line speed'),
    'explain-bandwidth_max' : TT('Highest possible linespeed in Bytes/second, e.g. 2M.'),
    'opt-bandwidth_perc' : TT('Percentage of line speed'),
    'explain-bandwidth_perc' : TT('Which percentage of the linespeed should SABnzbd use, e.g. 50'),
    'opt-cache_limitstr' : TT('Article Cache Limit'),
    'explain-cache_limitstr' : TT('Cache articles in memory to reduce disk access.<br /><i>In bytes, optionally follow with K,M,G. For example: "64M" or "128M"</i>'),
    'opt-cleanup_list' : TT('Cleanup List'),
    'explain-cleanup_list' : TT('List of file extensions that should be deleted after download.<br />For example: <b>nfo</b> or <b>nfo, sfv</b>'),
    'button-saveChanges' : TT('Save Changes'),
    'opt-language' : TT('Language'),
    'explain-language' : TT('Select a web interface language.'),
    'opt-apikey' : TT('API Key'),
    'explain-apikey' : TT('This key will give 3rd party programs full access to SABnzbd.'),
    'opt-nzbkey' : TT('NZB Key'),
    'explain-nzbkey' : TT('This key will allow 3rd party programs to add NZBs to SABnzbd.'),
    'button-apikey' : TT('Generate New Key'),
    'opt-disableApikey' : TT('Disable API-key'),
    'explain-disableApikey' : TT('Do not require the API key.'),
    'explain-disableApikeyWarn' : TT('USE AT YOUR OWN RISK!'),
    'qr-code' : TT('QR Code'), #: Button to show QR code of APIKEY
    'explain-qr-code' : TT('API Key QR Code'), #: Explanation for QR code of APIKEY
    'opt-local_ranges' : TT('List of local network ranges'),
    'explain-local_ranges' : TT('All local network addresses start with these prefixes (often "192.168.1.")'),
    'opt-inet_exposure' : TT('External internet access'),
    'explain-inet_exposure' : TT('You can set access rights for systems outside your local network'),
    'inet-local' : TT('No access'), # Selection value for external access
    'inet-nzb' : TT('Add NZB files '), # Selection value for external access
    'inet-api' : TT('API (no Config)'), # Selection value for external access
    'inet-fullapi' : TT('Full API'), # Selection value for external access
    'inet-ui' : TT('Full Web interface'), # Selection value for external access

# Config->Folders
    'folderConfig' : TT('Folder configuration'),
    'explain-folderConfig' : TT('<em>NOTE:</em> Folders will be created automatically when Saving. You may use absolute paths to save outside of the default folders.'),
    'userFolders' : TT('User Folders'),
    'in' : TT('In'),
    'opt-download_dir' : TT('Temporary Download Folder'),
    'explain-download_dir' : TT('Location to store unprocessed downloads.<br /><i>Can only be changed when queue is empty.</i>'),
    'opt-download_free' : TT('Minimum Free Space for Temporary Download Folder'),
    'explain-download_free' : TT('Auto-pause when free space is beneath this value.<br /><i>In bytes, optionally follow with K,M,G,T. For example: "800M" or "8G"</i>'),
    'opt-complete_dir' : TT('Completed Download Folder'),
    'explain-complete_dir' : TT('Location to store finished, fully processed downloads.<br /><i>Can be overruled by user-defined categories.</i>'),
    'opt-permissions' : TT('Permissions for completed downloads'),
    'explain-permissions' : TT('Set permissions pattern for completed files/folders.<br /><i>In octal notation. For example: "755" or "777"</i>'),
    'opt-dirscan_dir' : TT('Watched Folder'),
    'explain-dirscan_dir' : TT('Folder to monitor for .nzb files.<br /><i>Also scans .zip .rar and .tar.gz archives for .nzb files.</i>'),
    'opt-dirscan_speed' : TT('Watched Folder Scan Speed'),
    'explain-dirscan_speed' : TT('Number of seconds between scans for .nzb files.'),
    'opt-script_dir' : TT('Post-Processing Scripts Folder'),
    'explain-script_dir' : TT('Folder containing user scripts for post-processing.'),
    'opt-email_dir' : TT('Email Templates Folder'),
    'explain-email_dir' : TT('Folder containing user-defined email templates.'),
    'opt-password_file' : TT('Password file'),
    'explain-password_file' : TT('File containing all passwords to be tried on encrypted RAR files.'),
    'systemFolders' : TT('System Folders'),
    'opt-admin_dir' : TT('Administrative Folder'),
    'explain-admin_dir1' : TT('Location for queue admin and history database.<br /><i>Can only be changed when queue is empty.</i>'),
    'explain-admin_dir2' : TT('<i>Data will <b>not</b> be moved. Requires SABnzbd restart!</i>'),
    'opt-log_dir' : TT('Log Folder'),
    'explain-log_dir' : TT('Location of log files for SABnzbd.<br /><i>Requires SABnzbd restart!</i>'),
    'opt-nzb_backup_dir' : TT('.nzb Backup Folder'),
    'explain-nzb_backup_dir' : TT('Location where .nzb files will be stored.'),
    'base-folder' : TT('Default Base Folder'),

# Config->Switches
    'switchesConfig' : TT('Switches configuration'),
    'processingSwitches' : TT('Processing Switches'),
    'opt-quick_check' : TT('Enable Quick Check'),
    'explain-quick_check' : TT('Skip par2 checking when files are 100% valid.'),
    'opt-enable_all_par' : TT('Download all par2 files'),
    'explain-enable_all_par' : TT('This prevents multiple repair runs. QuickCheck on: download all par2 files when needed. QuickCheck off: always download all par2 files.'),
    'opt-enable_unrar' : TT('Enable Unrar'),
    'explain-enable_unrar' : TT('Enable built-in unrar functionality.'),
    'opt-enable_unzip' : TT('Enable Unzip'),
    'explain-enable_unzip' : TT('Enable built-in unzip functionality.'),
    'opt-enable_7zip' : TT('Enable 7zip'),
    'explain-enable_7zip' : TT('Enable built-in 7zip functionality.'),
    'opt-enable_recursive' : TT('Enable recursive unpacking'),
    'explain-enable_recursive' : TT('Unpack archives (rar, zip, 7z) within archives.'),
    'opt-flat_unpack' : TT('Ignore any folders inside archives'),
    'explain-flat_unpack' : TT('All files will go into a single folder.'),
    'opt-enable_filejoin' : TT('Enable Filejoin'),
    'explain-enable_filejoin' : TT('Join files ending in .001, .002 etc. into one file.'),
    'opt-enable_tsjoin' : TT('Enable TS Joining'),
    'explain-ts_join' : TT('Join files ending in .001.ts, .002.ts etc. into one file.'),
    'opt-enable_par_cleanup' : TT('Enable Par Cleanup'),
    'explain-enable_par_cleanup' : TT('Cleanup par files (if verifiying/repairing succeded).'),
    'opt-overwrite_files' : TT('When unpacking, overwrite existing files'),
    'explain-overwrite_files' : TT('This will overwrite existing files instead of creating an alternative name.'),
    'opt-top_only' : TT('Only Get Articles for Top of Queue'),
    'explain-top_only' : TT('Enable for less memory usage. Disable to prevent slow jobs from blocking the queue.'),
    'opt-safe_postproc' : TT('Post-Process Only Verified Jobs'),
    'explain-safe_postproc' : TT('Only perform post-processing on jobs that passed all PAR2 checks.'),
    'opt-pause_on_pwrar' : TT('Action when encrypted RAR is downloaded'),
    'explain-pause_on_pwrar' : TT('In case of "Pause", you\'ll need to set a password and resume the job.'),
    'opt-no_dupes' : TT('Detect Duplicate Downloads'),
    'explain-no_dupes' : TT('Detect identical NZB files (based on NZB content)'),
    'opt-no_series_dupes' : TT('Detect duplicate episodes in series'),
    'explain-no_series_dupes' : TT('Detect identical episodes in series (based on "name/season/episode")'),
    'nodupes-off' : TT('Off'), #: Three way switch for duplicates
    'nodupes-ignore' : TT('Discard'), #: Three way switch for duplicates
    'nodupes-pause' : TT('Pause'), #: Three way switch for duplicates
    'abort' : TT('Abort'), #: Three way switch for encrypted posts
    'opt-action_on_unwanted_extensions' : TT('Action when unwanted extension detected'),
    'explain-action_on_unwanted_extensions' : TT('Action when an unwanted extension is detected in RAR files'),
    'opt-unwanted_extensions' : TT('Unwanted extensions'),
    'explain-unwanted_extensions' : TT('List all unwanted extensions. For example: <b>exe</b> or <b>exe, com</b>'),
    'opt-sfv_check' : TT('Enable SFV-based checks'),
    'explain-sfv_check' : TT('Do an extra verification based on SFV files.'),
    'opt-unpack_check' : TT('Check result of unpacking'),
    'explain-unpack_check' : TT('Check result of unpacking (needs to be off for some file systems).'),
    'opt-script_can_fail' : TT('User script can flag job as failed'),
    'explain-script_can_fail' : TT('When the user script returns a non-zero exit code, the job will be flagged as failed.'),
    'opt-enable_meta' : TT('Use tags from indexer'),
    'explain-enable_meta' : TT('Use tags from indexer for title, season, episode, etc. Otherwise all naming is derived from the NZB name.'),
    'opt-folder_rename' : TT('Enable folder rename'),
    'explain-folder_rename' : TT('Use temporary names during post processing. Disable when your system doesn\'t handle that properly.'),
    'opt-dirscan_opts' : TT('Default Post-Processing'),
    'explain-dirscan_opts' : TT('Used when no post-processing is defined by the category.'),
    'opt-dirscan_script' : TT('Default User Script'),
    'explain-dirscan_script' : TT('Used when no user script is defined by the category.'),
    'opt-pre_script' : TT('Pre-queue user script'),
    'explain-pre_script' : TT('Used before an NZB enters the queue.'),
    'opt-dirscan_priority' : TT('Default Priority'),
    'explain-dirscan_priority' : TT('Used when no priority is defined by the category.'),
    'opt-par2_multicore' : TT('Enable MultiCore Par2'),
    'explain-par2_multicore' : TT('Read the Wiki Help on this!'),
    'opt-par_option' : TT('Extra PAR2 Parameters'),
    'explain-par_option' : TT('Read the Wiki Help on this!'),
    'opt-nice' : TT('Nice Parameters'),
    'explain-nice' : TT('Read the Wiki Help on this!'),
    'opt-ionice' : TT('IONice Parameters'),
    'explain-ionice' : TT('Read the Wiki Help on this!'),
    'otherSwitches' : TT('Other Switches'),
    'opt-auto_disconnect' : TT('Disconnect on Empty Queue'),
    'explain-auto_disconnect' : TT('Disconnect from Usenet server(s) when queue is empty or paused.'),
    'opt-auto_sort' : TT('Sort by Age'),
    'explain-auto_sort' : TT('Automatically sort items by (average) age.'),
    'opt-check_new_rel' : TT('Check for New Release'),
    'explain-check_new_rel' : TT('Weekly check for new SABnzbd release.'),
    'also-test' : TT('Also test releases'), #: Pick list for weekly test for new releases
    'opt-replace_spaces' : TT('Replace Spaces in Foldername'),
    'explain-replace_spaces' : TT('Replace spaces with underscores in folder names.'),
    'opt-replace_dots' : TT('Replace dots in Foldername'),
    'explain-replace_dots' : TT('Replace dots with spaces in folder names.'),
    'opt-replace_illegal' : TT('Replace Illegal Characters in Folder Names'),
    'explain-replace_illegal' : TT('Replace illegal characters in folder names by equivalents (otherwise remove).'),
    'opt-sanitize_safe' : TT('Make Windows compatible'),
    'explain-sanitize_safe' : TT('For servers: make sure names are compatible with Windows.'),
    'opt-auto_browser' : TT('Launch Browser on Startup'),
    'explain-auto_browser' : TT('Launch the default web browser when starting SABnzbd.'),
    'opt-pause_on_post_processing' : TT('Pause Downloading During Post-Processing'),
    'explain-pause_on_post_processing' : TT('Pauses downloading at the start of post processing and resumes when finished.'),
    'opt-ignore_samples' : TT('Ignore Samples'),
    'explain-ignore_samples' : TT('Filter out sample files (e.g. video samples).'),
    'igsam-off' : TT('Off'),
    'igsam-del' : TT('Delete after download'),
    'igsam-not' : TT('Do not download'),
    'opt-ampm' : TT('Use 12 hour clock (AM/PM)'),
    'explain-ampm' : TT('Show times in AM/PM notation (does not affect scheduler).'),
    'swtag-general' : TT('General'),
    'swtag-server' : TT('Server'),
    'swtag-queue' : TT('Queue'),
    'swtag-pp' : TT('Post processing'),
    'swtag-naming' : TT('Naming'),
    'swtag-quota' : TT('Quota'),
    'swtag-indexing' : TT('Indexing'),
    'opt-quota_size' : TT('Size'), #: Size of the download quota
    'explain-quota_size' : TT('How much can be downloaded this month (K/M/G)'),
    'opt-quota_day' : TT('Reset day'), #: Reset day of the download quota
    'explain-quota_day' : TT('On which day of the month or week (1=Monday) does your ISP reset the quota? (Optionally with hh:mm)'),
    'opt-quota_resume' : TT('Auto resume'), #: Auto-resume download on the reset day
    'explain-quota_resume' : TT('Should downloading resume after the quota is reset?'),
    'opt-quota_period' : TT('Quota period'), #: Does the quota get reset every day, week or month?
    'explain-quota_period' : TT('Does the quota get reset each day, week or month?'),
    'opt-pre_check' : TT('Check before download'),
    'explain-pre_check' : TT('Try to predict successful completion before actual download (slower!)'),
    'opt-max_art_tries' : TT('Maximum retries'),
    'explain-max_art_tries' : TT('Maximum number of retries per server'),
    'opt-max_art_opt' : TT('Only for optional servers'),
    'explain-max_art_opt' : TT('Apply maximum retries only to optional servers'),
    'opt-fail_hopeless' : TT('Abort jobs that cannot be completed'),
    'explain-fail_hopeless' : TT('When during download it becomes clear that too much data is missing, abort the job'),
    'opt-rating_enable' : TT('Enable OZnzb Integration'),
    'explain-rating_enable' : TT('Enhanced functionality including ratings and extra status information is available when connected to OZnzb indexer.'),
    'opt-rating_api_key' : TT('Site API Key'),
    'explain-rating_api_key' : TT('This key provides identity to indexer. Refer to https://www.oznzb.com/profile.'),
    'tip-rating_api_key' : TT('Refer to https://www.oznzb.com/profile'),
    'opt-rating_feedback' : TT('Automatic Feedback'),
    'explain-rating_feedback' : TT('Send automatically calculated validation results for downloads to indexer.'),
    'opt-rating_filter_enable' : TT('Enable Filtering'),
    'explain-rating_filter_enable' : TT('Action downloads according to filtering rules.'),
    'opt-rating_filter_abort_if' : TT('Abort If'),
    'opt-rating_filter_pause_if' : TT('Else Pause If'),
    'opt-rating_filter_video' : TT('Video rating'),
    'opt-rating_filter_audio' : TT('Audio rating'),
    'opt-rating_filter_passworded' : TT('Passworded'),
    'opt-rating_filter_spam' : TT('Spam'),
    'opt-rating_filter_confirmed' : TT('Confirmed'),
    'opt-rating_filter_downvoted' : TT('More thumbs down than up'),
    'opt-rating_filter_keywords' : TT('Title keywords'),
    'explain-rating_filter_keywords' : TT('Comma separated list'),

# Config->Server
    'configServer' : TT('Server configuration'), #: Caption
    'defServer' : TT('Server definition'), # Caption
    'addServer' : TT('Add Server'), #: Caption
    'srv-displayname' : TT('Server description'), #: User defined name for server
    'srv-host' : TT('Host'), #: Server hostname or IP
    'srv-port' : TT('Port'), #: Server port
    'srv-username' : TT('Username'), #: Server username
    'srv-password' : TT('Password'), #: Server password
    'srv-timeout' : TT('Timeout'), #: Server timeout
    'srv-connections' : TT('Connections'), #: Server: amount of connections
    'srv-retention' : TT('Retention time'), #: Server's retention time in days
    'srv-ssl' : TT('SSL'), #: Server SSL tickbox
    'srv-priority' : TT('Priority'), #: Server priority
    'explain-svrprio' : TT('0 is highest priority, 100 is the lowest priority'), #: Explain server priority
    'srv-optional' : TT('Optional'), #: Server optional tickbox
    'srv-enable' : TT('Enable'), #: Enable server tickbox
    'srv-ssl_type' : TT('SSL type'),
    'srv-explain-ssl_type' : TT('Use TLS1 unless your provider requires otherwise!'),
    'button-addServer' : TT('Add Server'), #: Button: Add server
    'button-delServer' : TT('Remove Server'), #: Button: Remove server
    'button-testServer' : TT('Test Server'), #: Button: Test server
    'button-clrServer' : TT('Clear Counters'), #: Button: Clear server's byte counters
    'srv-testing' : TT('Testing server details...'),
    'srv-testHint' : TT('Click below to test.'),
    'srv-bandwidth' : TT('Bandwidth'),
    'srv-send_group' : TT('Send Group'),
    'srv-explain-send_group' : TT('Send group command before requesting articles.'),
    'srv-categories' : TT('Categories'),
    'srv-explain-categories' : TT('Only use this server for these categories.'),
    'srv-notes' : TT('Personal notes'),

# Config->Scheduling
    'configSchedule' : TT('Scheduling configuration'), #:Config->Scheduling
    'addSchedule' : TT('Add Schedule'), #:Config->Scheduling
    'sch-frequency' : TT('Frequency'), #:Config->Scheduling
    'sch-action' : TT('Action'), #:Config->Scheduling
    'sch-arguments' : TT('Arguments'), #:Config->Scheduling
    'button-addSchedule' : TT('Add Schedule'), #:Config->Scheduling
    'button-delSchedule' : TT('Remove'), #:Config->Scheduling
    'currentSchedules' : TT('Current Schedules'), #:Config->Scheduling
    'sch-resume' : TT('Resume'), #:Config->Scheduling
    'sch-pause' : TT('Pause'), #:Config->Scheduling
    'sch-shutdown' : TT('Shutdown'), #:Config->Scheduling
    'sch-restart' : TT('Restart'), #:Config->Scheduling

# Config->RSS
    'configRSS' : TT('RSS Configuration'),
    'newFeedURI' : TT('New Feed URL'),
    'explain-RSS' : TT('The checkbox next to the feed name should be ticked for the feed to be enabled and be automatically checked for new items.<br />When a feed is added, it will only pick up new items and not anything already in the RSS feed unless you press "Force Download".'),
    'feed' : TT('Feed'), #: Config->RSS, tab header
    'addFeed' : TT('Add Feed'), #: Config->RSS button
    'button-delFeed' : TT('Delete Feed'),#: Config->RSS button
    'button-preFeed' : TT('Read Feed'),#: Config->RSS button
    'button-forceFeed' : TT('Force Download'),#: Config->RSS button
    'rss-order' : TT('Order'), #: Config->RSS table column header
    'rss-type' : TT('Type'), #: Config->RSS table column header
    'rss-filter' : TT('Filter'), #: Config->RSS table column header
    'rss-skip' : TT('Skip'), #: Config->RSS table column header
    'rss-accept' : TT('Accept'), #: Config->RSS filter-type selection menu
    'rss-reject' : TT('Reject'), #: Config->RSS filter-type selection menu
    'rss-must' : TT('Requires'), #: Config->RSS filter-type selection menu
    'rss-mustcat' : TT('RequiresCat'), #: Config->RSS filter-type selection menu
    'rss-atleast' : TT('At least'), #: Config->RSS filter-type selection menu
    'rss-atmost' : TT('At most'), #: Config->RSS filter-type selection menu
    'rss-from' : TT('From SxxEyy'), #: Config->RSS filter-type selection menu "From Season/Episode"
    'rss-delFilter' : TT('X'), #: Config->RSS button "Delete filter"
    'rss-matched' : TT('Matched'), #: Config->RSS section header
    'rss-notMatched' : TT('Not Matched'), #: Config->RSS section header
    'rss-done' : TT('Downloaded'), #: Config->RSS section header
    'link-download' : TT('Download'), #: Config->RSS button "download item"
    'tableFeeds' : TT('Feeds'), #: Tab title for Config->Feeds
    'button-rssNow' : TT('Read All Feeds Now'), #: Config->RSS button
    'feedSettings' : TT('Settings'), #: Tab title for Config->Feeds
    'filters' : TT('Filters'), #: Tab title for Config->Feeds

# Config->Notifications
    'configEmail' : TT('Notifications'), #: Main Config page
    'emailOptions' : TT('Email Options'), #: Section header
    'opt-email_endjob' : TT('Email Notification On Job Completion'),
    'email-never' : TT('Never'), #: When to send email
    'email-always' : TT('Always'),  #: When to send email
    'email-errorOnly' : TT('Error-only'),  #: When to send email
    'opt-email_full' : TT('Disk Full Notifications'),
    'explain-email_full' : TT('Send email when disk is full and SABnzbd is paused.'),
    'opt-email_rss' : TT('Send RSS notifications'),
    'explain-email_rss' : TT('Send email when an RSS feed adds jobs to the queue.'),
    'emailAccount' : TT('Email Account Settings'),
    'opt-email_server' : TT('SMTP Server'),
    'explain-email_server' : TT('Set your ISP\'s server for outgoing email.'),
    'opt-email_to' : TT('Email Recipient'),
    'explain-email_to' : TT('Email address to send the email to.'),
    'opt-email_from' : TT('Email Sender'),
    'explain-email_from' : TT('Who should we say sent the email?'),
    'opt-email_account' : TT('OPTIONAL Account Username'),
    'explain-email_account' : TT('For authenticated email, account name.'),
    'opt-email_pwd' : TT('OPTIONAL Account Password'),
    'explain-email_pwd' : TT('For authenticated email, password.'),
    'growlSettings' : TT('Growl'), #: Header Growl section
    'opt-growl_enable' : TT('Enable Growl'), #: Don't translate "Growl"
    'explain-growl_enable' : TT('Send notifications to Growl'), #: Don't translate "Growl"
    'opt-growl_server' : TT('Server address'), #: Address of Growl server
    'explain-growl_server' : TT('Only use for remote Growl server (host:port)'), #: Don't translate "Growl"
    'opt-growl_password' : TT('Server password'), #: Growl server password
    'explain-growl_password' : TT('Optional password for Growl server'), #: Don't translate "Growl"
    'opt-ntfosd_enable' : TT('Enable NotifyOSD'), #: Don't translate "NotifyOSD"
    'explain-ntfosd_enable' : TT('Send notifications to NotifyOSD'), #: Don't translate "NotifyOSD"
    'opt-ncenter_enable' : TT('Notification Center'),
    'explain-ncenter_enable' : TT('Send notifications to Notification Center'),
    'opt-notify_classes' : TT('Notification classes'),
    'explain-notify_classes' : TT('Enable classes of messages to be reported (none, one or multiple)'),
    'testNotify' : TT('Test Notification'),
    'section-NC' : TT('Notification Center'), #: Header for OSX Notfication Center section
    'section-OSD' : TT('NotifyOSD'), #: Header for Ubuntu's NotifyOSD notifications section
    'section-Prowl' : TT('Prowl'), #: Header for Prowl notification section
    'opt-prowl_enable' : TT('Enable Prowl notifications'), #: Prowl settings
    'explain-prowl_enable' : TT('Requires a Prowl account'), #: Prowl settings
    'opt-prowl_apikey' : TT('API key for Prowl'), #: Prowl settings
    'explain-prowl_apikey' : TT('Personal API key for Prowl (required)'), #: Prowl settings

    'section-Pushover' : TT('Pushover'), #: Header for Pushover notification section
    'opt-pushover_enable' : TT('Enable Pushover notifications'), #: Pushover settings
    'explain-pushover_enable' : TT('Requires a Pushover account'), #: Pushoversettings
    'opt-pushover_token' : TT('Application Token'), #: Pushover settings
    'explain-pushover_token' : TT('Application token (required)'), #: Pushover settings
    'opt-pushover_userkey' : TT('User Key'), #: Pushover settings
    'explain-pushover_userkey' : TT('User Key (required)'), #: Pushover settings
    'opt-pushover_device' : TT('Device(s)'), #: Pushover settings
    'explain-pushover_device' : TT('Device(s) to which message should be sent'), #: Pushover settings

    'section-Pushbullet' : TT('Pushbullet'), #: Header for Pushbullet notification section
    'opt-pushbullet_enable' : TT('Enable Pushbullet notifications'), #: Pushbullet settings
    'explain-pushbullet_enable' : TT('Requires a Pushbullet account'), #: Pushbulletsettings
    'opt-pushbullet_apikey' : TT('Personal API key'), #: Pushbullet settings
    'explain-pushbullet_apikey' : TT('Your personal Pushbullet API key (required)'), #: Pushbullet settings
    'opt-pushbullet_device' : TT('Device'), #: Pushbullet settings
    'explain-pushbullet_device' : TT('Device to which message should be sent'), #: Pushbullet settings

# Config->Cat
    'configCat' : TT('User-defined categories'),
    'explain-configCat' : TT('Defines post-processing and storage.'),
    'explain-catTags' : TT('Use the "Groups / Indexer tags" column to map groups and tags to your categories.<br/>Wildcards are supported. Use commas to separate terms.'),
    'explain-catTags2' : TT('Ending the path with an asterisk * will prevent creation of job folders.'),
    'explain-relFolder' : TT('Relative folders are based on'),
    'catFolderPath' : TT('Folder/Path'),
    'catTags' : TT('Groups / Indexer tags'),
    'button-delCat' : TT('X'), #: Small delete button

# Config->Sorting
    'configSort' : TT('Sorting configuration'),
    'seriesSorting' : TT('Series Sorting'),
    'opt-tvsort' : TT('Enable TV Sorting'),
    'explain-tvsort' : TT('Enable sorting and renaming of episodes.'),
    'sort-legenda' : TT('Pattern Key'),
    'button-clear' : TT('Clear'),
    'presetSort' : TT('Presets'),
    'example' : TT('Example'),
    'genericSort' : TT('Generic Sorting'),
    'opt-movieSort' : TT('Enable Movie Sorting'),
    'explain-movieSort' : TT('Enable generic sorting and renaming of files.'),
    'opt-movieExtra' : TT('Keep loose downloads in extra folders'),
    'explain-movieExtra' : TT('Enable if downloads are not put in their own folders.'),
    'affectedCat' : TT('Affected Categories'),
    'sort-meaning' : TT('Meaning'),
    'sort-pattern' : TT('Pattern'),
    'sort-result' : TT('Result'),
    'button-Season1x05' : TT('1x05 Season Folder'),
    'button-SeasonS01E05' : TT('S01E05 Season Folder'),
    'button-Ep1x05' : TT('1x05 Episode Folder'),
    'button-EpS01E05' : TT('S01E05 Episode Folder'),
    'sort-title' : TT('Title'),
    'movie-sp-name' : TT('Movie Name'),
    'movie-dot-name' : TT('Movie.Name'),
    'movie-us-name' : TT('Movie_Name'),
    'show-name' : TT('Show Name'),
    'show-sp-name' : TT('Show Name'),
    'show-dot-name' : TT('Show.Name'),
    'show-us-name' : TT('Show_Name'),
    'show-seasonNum' : TT('Season Number'),
    'show-epNum' : TT('Episode Number'),
    'ep-name' : TT('Episode Name'),
    'ep-sp-name' : TT('Episode Name'),
    'ep-dot-name' : TT('Episode.Name'),
    'ep-us-name' : TT('Episode_Name'),
    'fileExt' : TT('File Extension'),
    'extension' : TT('Extension'),
    'partNumber' : TT('Part Number'),
    'decade' : TT('Decade'),
    'orgFilename' : TT('Original Filename'),
    'orgDirname' : TT('Original Foldername'),
    'lowercase' : TT('Lower Case'),
    'TEXT' : TT('TEXT'),
    'text' : TT('text'),
    'sort-File' : TT('file'),
    'sort-Folder' : TT('folder'),
    'sortString' : TT('Sort String'),
    'multiPartLabel' : TT('Multi-part label'),
    'button-inFolders' : TT('In folders'),
    'button-noFolders' : TT('No folders'),
    'dateSorting' : TT('Date Sorting'),
    'opt-dateSort' : TT('Enable Date Sorting'),
    'explain-dateSort' : TT('Enable sorting and renaming of date named files.'),
    'button-ShowNameF' : TT('Show Name folder'),
    'button-YMF' : TT('Year-Month Folders'),
    'button-DailyF' : TT('Daily Folders'),
    'case-adjusted' : TT('case-adjusted'), #: Note for title expression in Sorting that does case adjustment
    'sortResult' : TT('Processed Result'),

# Config->Special
    'explain-special' : TT('Rarely used options. For their meaning and explanation, click on the Help button to go to the Wiki page.<br>'
                           'Don\'t change these without checking the Wiki first, as some have serious side-effects.<br>'
                           'The default values are between parentheses.'),
    'sptag-boolean' : TT('Switches'),
    'sptag-entries' : TT('Values'),

# NZO
    'nzoDetails' : TT('Edit NZB Details'), #: Job details page
    'nzoName' : TT('Name'), #: Job details page
    'nzo-delete' : TT('Delete'), #: Job details page, delete button
    'nzo-top' : TT('Top'), #: Job details page, move file to top
    'nzo-up' : TT('Up'),  #: Job details page, move file one place up
    'nzo-down' : TT('Down'), #: Job details page, move file one place down
    'nzo-bottom' : TT('Bottom'),  #: Job details page, move file to bottom
    'nzo-all' : TT('All'),  #: Job details page, select all files
    'nzo-none' : TT('None'), #: Job details page, select no files
    'nzo-invert' : TT('Invert'), #: Job details page, invert file selection
    'nzo-filename' : TT('Filename'), #: Job details page, filename column header
    'nzo-subject' : TT('Subject'),  #: Job details page, subject column header
    'nzo-age' : TT('Age'), #: Job details page, file age column header
    'nzo-selection' : TT('Selection'), #: Job details page, section header
    'nzo-action' : TT('Action'), #: Job details page, section header


#OSX Menu
    'Mobile-confirm-delete' : TT('Are you sure you want to delete'),
    'Mobile-button-refresh' : TT('Refresh'),
    'Mobile-warnings' : TT('Warnings'),
    'Mobile-button-options' : TT('Options'),
    'Mobile-page' : TT('Page'),
    'Mobile-button-prev' : TT('Prev'),
    'Mobile-button-next' : TT('Next'),
    'Mobile-button-first' : TT('First'),
    'Mobile-button-last' : TT('Last'),
    'Mobile-button-close' : TT('Close'),
    'Mobile-button-pauseInterval' : TT('Set Pause Interval'),
    'Mobile-sort' : TT('Sort'),
    'Mobile-confirm-purgeQ' : TT('Purge the Queue?'),
    'Mobile-button-purgeQ' : TT('Purge Queue'),
    'Mobile-pauseInterval' : TT('Pause Interval'),
    'Mobile-pause5m' : TT('Pause for 5 minutes'),
    'Mobile-pause15m' : TT('Pause for 15 minutes'),
    'Mobile-pause30m' : TT('Pause for 30 minutes'),
    'Mobile-pause1h' : TT('Pause for 1 hour'),
    'Mobile-pause3h' : TT('Pause for 3 hours'),
    'Mobile-pause6h' : TT('Pause for 6 hours'),
    'Mobile-pause12h' : TT('Pause for 12 hours'),
    'Mobile-pause24h' : TT('Pause for 24 hours'),
    'Mobile-sortAgeAsc' : TT('Sort by Age <small>Oldest&rarr;Newest</small>'),
    'Mobile-sortAgeDesc' : TT('Sort by Age <small>Newest&rarr;Oldest</small>'),
    'Mobile-sortNameAsc' : TT('Sort by Name <small>A&rarr;Z</small>'),
    'Mobile-sortNameDesc' : TT('Sort by Name <small>Z&rarr;A</small>'),
    'Mobile-sortSizeAsc' : TT('Sort by Size <small>Smallest&rarr;Largest</small>'),
    'Mobile-sortSizeDesc' : TT('Sort by Size <small>Largest&rarr;Smallest</small>'),
    'Mobile-rename' : TT('Rename'),
    'Mobile-left' : TT('Left'),
    'Mobile-confirm-purgeH' : TT('Purge the History?'),
    'Mobile-button-purgeH' : TT('Purge History'),

#Glitter skin
    'Glitter-addNZB' : TT('Add NZB'),
    'Glitter-pause5m' : TT('Pause for 5 minutes'),
    'Glitter-pause15m' : TT('Pause for 15 minutes'),
    'Glitter-pause30m' : TT('Pause for 30 minutes'),
    'Glitter-pause1h' : TT('Pause for 1 hour'),
    'Glitter-pause3h' : TT('Pause for 3 hours'),
    'Glitter-pause6h' : TT('Pause for 6 hours'),
    'Glitter-setMaxLinespeed' : TT('Set maximum line speed in configuration'),
    'Glitter-left' : TT('left'),
    'Glitter-quota' : TT('quota'),
    'Glitter-free' : TT('Free Space'),
    'Glitter-search' : TT('Search'),
    'Glitter-multiOperations' : TT('Multi-Operations'),
    'Glitter-multiSelect' : TT('Hold shift key to select a range'),
    'Glitter-checkAll' : TT('Check all'),
    'Glitter-configure' : TT('SABnzbd settings'),
    'Glitter-restartSab' : TT('Restart SABnzbd'),
    'Glitter-onFinish' : TT('On queue finish'),
    'Glitter-clearAction' : TT('Clear action'),
    'Glitter-statusInterfaceOptions' : TT('Status and interface options'),
    'Glitter-dragAndDrop' : TT('Or drag and drop files in the window!'),
    'Glitter-storage' : TT('Storage'),
    'Glitter-today' : TT('Today'),
    'Glitter-thisMonth' : TT('This month'),
    'Glitter-total' : TT('Total'),
    'Glitter-lostConnection' : TT('Lost connection to SABnzbd..'),
    'Glitter-afterRestart' : TT('In case of SABnzbd restart this screen will disappear automatically!'),
    'Glitter-refresh' : TT('Refresh'),
    'Glitter-disabled' : TT('Disabled'),
    'Glitter-interfaceOptions' : TT('Web Interface').title(),
    'Glitter-interfaceRefresh' : TT('Refresh rate'),
    'Glitter-queueItemLimit' : TT('Queue item limit'),
    'Glitter-historyItemLimit' : TT('History item limit'),
    'Glitter-dateFormat' : TT('Date format'),
    'Glitter-page' : TT('page'),
    'Glitter-everything' : TT('Everything'),
    'Glitter-loading' : TT('Loading'),
    'Glitter-connectionError' : TT('Connection failed!'),
    'Glitter-localIP4' : TT('Local IPv4 address'),
    'Glitter-publicIP4' : TT('Public IPv4 address'),
    'Glitter-IP6' : TT('IPv6 address'),
    'Glitter-NameserverDNS' : TT('Nameserver / DNS Lookup'),
    'Glitter-downloadDirSpeed' : TT('Download folder speed'),
    'Glitter-completeDirSpeed' : TT('Complete folder speed'),
    'Glitter-repeatTest' : TT('Repeat test'),
    'Glitter-articles' : TT('articles'),
    'Glitter-repairQueue' : TT('Queue repair'),
    'Glitter-showActiveConnections' : TT('Show active connections'),
    'Glitter-unblockServer' : TT('Unblock'),
    'Glitter-orphanedJobs' : TT('Orphaned jobs'),
    'Glitter-backToQueue' : TT('Send back to queue'),
    'Glitter-purgeOrphaned' : TT('Delete All'),
    'Glitter-deleteJobAndFolders' : TT('Remove NZB & Delete Files'),
    'Glitter-addFromURL' : TT('Fetch NZB from URL'),
    'Glitter-addFromFile' : TT('Upload NZB'),
    'Glitter-addnzbFilename' : TT('Optionally specify a filename'),
    'Glitter-nzbFormats' : TT('Formats: .nzb, .rar, .zip, .gz, .bz2'),
    'Glitter-unpackPassword' : TT('Password for unpacking'),
    'Glitter-submit' : TT('Submit'),
    'Glitter-openInfoURL' : TT('Open Informational URL'),
    'Glitter-sendThanks' : TT('Submitted. Thank you!'),
    'Glitter-noSelect' : TT('Nothing selected!'),
    'Glitter-removeSelected' : TT('Remove all selected files'),
    'Glitter-toggleCompletedFiles' : TT('Hide/show completed files'),
    'Glitter-retryJob' : TT('Retry'),
    'Glitter-scriptLog' : TT('View Script Log').title(),
    'Glitter-clearHistory' : TT('Purge History').title(),
    'Glitter-confirmClearWarnings' : TT('Are you sure?'),
    'Glitter-confirmClearDownloads' : TT('Are you sure?'),
    'Glitter-confirmClear1Download' : TT('Are you sure?'),
    'Glitter-grabbing' : TT('Grabbing NZB...'),
    'Glitter-updateAvailable' : TT('Update Available!'),
    'Glitter-sortAgeAsc' : TT('Sort by Age <small>Oldest&rarr;Newest</small>'),
    'Glitter-sortAgeDesc' : TT('Sort by Age <small>Newest&rarr;Oldest</small>'),
    'Glitter-sortNameAsc' : TT('Sort by Name <small>A&rarr;Z</small>'),
    'Glitter-sortNameDesc' : TT('Sort by Name <small>Z&rarr;A</small>'),
    'Glitter-sortSizeAsc' : TT('Sort by Size <small>Smallest&rarr;Largest</small>'),
    'Glitter-sortSizeDesc' : TT('Sort by Size <small>Largest&rarr;Smallest</small>'),

#Plush skin
    'Plush-confirmWithoutSavingPrompt' : TT('Changes have not been saved, and will be lost.'),
    'Plush-cmenu-scheduling' : TT('Scheduling'),
    'Plush-confirm' : TT('Are you sure?'),
    'Plush-openSourceURL' : TT('Open Source URL'),
    'Plush-openInfoURL' : TT('Open Informational URL'),
    'Plush-path' : TT('Path'),
    'Plush-storage' : TT('Storage'),
    'Plush-viewScriptLog' : TT('View Script Log'),
    'Plush-prev' : TT('Prev'),
    'Plush-next' : TT('Next'),
    'Plush-confirmPurgeH' : TT('Purge the History?'),
    'Plush-enableJavascript' : TT('You must enable JavaScript for Plush to function!'),
    'Plush-addnzb' : TT('Add NZB'),
    'Plush-button-refresh' : TT('Refresh'),
    'Plush-options' : TT('Options'),
    'Plush-plushoptions' : TT('Plush Options'),
    'Plush-updateAvailable' : TT('Update Available!'),
    'Plush-pause5m' : TT('Pause for 5 minutes'),
    'Plush-pause15m' : TT('Pause for 15 minutes'),
    'Plush-pause30m' : TT('Pause for 30 minutes'),
    'Plush-pause1h' : TT('Pause for 1 hour'),
    'Plush-pause3h' : TT('Pause for 3 hours'),
    'Plush-pause6h' : TT('Pause for 6 hours'),
    'Plush-pauseForPrompt' : TT('Pause for how many minutes?'),
    'Plush-pauseFor' : TT('Pause for...'),
    'Plush-multiOperations' : TT('Multi-Operations'),
    'Plush-topMenu' : TT('Top Menu'),
    'Plush-onQueueFinish' : TT('On Finish'),
    'Plush-sort' : TT('Sort'),
    'Plush-sortAgeAsc' : TT('Sort by Age <small>(Oldest&rarr;Newest)</small>'),
    'Plush-sortAgeDesc' : TT('Sort by Age <small>(Newest&rarr;Oldest)</small>'),
    'Plush-sortNameAsc' : TT('Sort by Name <small>(A&rarr;Z)</small>'),
    'Plush-sortNameDesc' : TT('Sort by Name <small>(Z&rarr;A)</small>'),
    'Plush-sortSizeAsc' : TT('Sort by Size <small>(Smallest&rarr;Largest)</small>'),
    'Plush-sortSizeDesc' : TT('Sort by Size <small>(Largest&rarr;Smallest)</small>'),
    'Plush-confirmPurgeQ' : TT('Purge the Queue?'),
    'Plush-confirmRetryQ' : TT('Retry all failed jobs in History?'),
    'Plush-purge' : TT('Purge'),
    'Plush-left' : TT('left'),
    'Plush-maxSpeed' : TT('Max Speed'), #: Used in speed menu. Split in two lines if too long.
    'Plush-nzo-range' : TT('Range'),
    'Plush-reset' : TT('Reset'),
    'Plush-applySelected' : TT('Apply to Selected'),
    'Plush-page' : TT('page'),
    'Plush-everything' : TT('Everything'),
    'Plush-disabled' : TT('Disabled'),
    'Plush-refreshRate' : TT('Refresh Rate'),
    'Plush-containerWidth' : TT('Container Width'),
    'Plush-confirmDeleteQueue' : TT('Confirm Queue Deletions'),
    'Plush-confirmDeleteHistory' : TT('Confirm History Deletions'),
    'Plush-explain-blockRefresh' : TT('This will prevent refreshing content when your mouse cursor is hovering over the queue.'),
    'Plush-blockRefresh' : TT('Block Refreshes on Hover'),
    'Plush-fetch' : TT('Fetch'), #: Fetch from URL button in "Add NZB" dialog box
    'Plush-upload' : TT('Upload'), #: Upload button in "Add NZB" dialog box
    'Plush-uploadTip' : TT('Upload: .nzb .rar .zip .gz, .bz2'),
    'Plush-addnzb-filename' : TT('Optionally specify a filename'),
    'Plush-progress' : TT('Progress'),
    'Plush-remaining' : TT('Remaining'),
    'Plush-notEnoughSpace' : TT('Not enough disk space to complete downloads!'),
    'Plush-freeSpace' : TT('Free Space'),
    'Plush-freeSpaceTemp' : TT('Free (Temp)'),
    'Plush-idle' : TT('IDLE'),
    'Plush-downloads' : TT('Downloads'),
    'Plush-tab-repair' : TT('Queue repair'),
    'Plush-rss-delete' : TT('Delete'),
    'Plush-rss-actions' : TT('Actions'),
    'Plush-explain-rssActions' : TT('<strong>Read Feed</strong> will get the current feed content. <strong>Force Download</strong> will download all matching NZBs now.'),


#smpl skin
    'smpl-hourmin' : TT('Hour:Min'),
    'smpl-purgehist' : TT('Delete Completed'),
    'smpl-purgefailhistOK?' : TT('Delete the all failed items from the history?'),
    'smpl-purgefailhist' : TT('Delete Failed'),
    'smpl-retryAllJobs?' : TT('Retry all failed jobs?'),
    'smpl-retryAll' : TT('Retry all'), #: Link in SMPL for "Retry all failed jobs"
    'smpl-links' : TT('Links'),
    'smpl-size' : TT('Size'),
    'smpl-path' : TT('Path'),
    'smpl-numresults@3' : TT('Showing %s to %s out of %s results'),
    'smpl-noresult' : TT('No results'),
    'smpl-oneresult' : TT('Showing one result'),
    'smpl-first' : TT('First'),
    'smpl-previous' : TT('Prev'),
    'smpl-next' : TT('Next'),
    'smpl-last' : TT('Last'),
    'smpl-pauseForPrompt' : TT('Pause for how many minutes?'),
    'smpl-paused' : TT('Paused'),
    'smpl-downloading' : TT('Downloading'),
    'smpl-idle' : TT('Idle'),
    'smpl-emailsent' : TT('Email Sent!'),
    'smpl-notesent' : TT('Notification Sent!'),
    'smpl-saving' : TT('Saving..'),
    'smpl-saved' : TT('Saved'),
    'smpl-failed' : TT('Failed'),
    'smpl-speed' : TT('Speed'),
    'smpl-toggleadd' : TT('Toggle Add NZB'),
    'smpl-dualView1' : TT('DualView1'),
    'smpl-dualView2' : TT('DualView2'),
    'smpl-warnings' : TT('Warnings'),
    'smpl-custom' : TT('Custom'),
    'smpl-restartOK?' : TT('Are you sure you want to restart SABnzbd?'),
    'smpl-refreshr' : TT('Refresh rate'),
    'smpl-purgeQueue' : TT('Delete All'),
    'smpl-hideEdit' : TT('Hide Edit Options'),
    'smpl-showEdit' : TT('Show Edit Options'),
    'smpl-edit' : TT('Edit'),
    'smpl-progress' : TT('Progress'),
    'smpl-timeleft' : TT('Timeleft'),
    'smpl-age' : TT('Age'),

#Wizard
    'wizard-quickstart' :  TT('SABnzbd Quick-Start Wizard'),
    'wizard-version' :  TT('SABnzbd Version'),
    'wizard-previous' :  TT('Previous'), #: Button to go to previous Wizard page
    'wizard-next' :  TT('Next'), #: Button to go to next Wizard page
    'wizard-access' :  TT('Access'), #: Wizard step in which the web server is set
    'wizard-access-anypc' :  TT('I want SABnzbd to be viewable by any pc on my network.'),
    'wizard-access-mypc' :  TT('I want SABnzbd to be viewable from my pc only.'),
    'wizard-access-pass' :  TT('Password protect access to SABnzbd (recommended)'),
    'wizard-access-https' :  TT('Enable HTTPS access to SABnzbd.'),
    'wizard-misc' :  TT('Misc'), #: Wizard step
    'wizard-misc-browser' :  TT('Launch my internet browser with the SABnzbd page when the program starts.'),
    'wizard-server' :  TT('Server Details'),
    'wizard-explain-server' :  TT('Please enter in the details of your primary usenet provider.'),
    'wizard-server-help' :  TT('Help'), #: Wizard help link
    'wizard-server-help1' :  TT('In order to download from usenet you will require access to a provider. Your ISP may provide you with access, however a premium provider is recommended.'),
    'wizard-server-help2' :  TT('Don\'t have a usenet provider? We recommend trying %s.'),
    'wizard-server-con-explain' :  TT('The number of connections allowed by your provider'),
    'wizard-server-con-eg' : TT('E.g. 8 or 20'), #: Wizard: examples of amount of connections
    'wizard-server-ssl-explain' :  TT('Select only if your provider allows SSL connections.'),
    'wizard-server-text' :  TT('Click to test the entered details.'),
    'wizard-server-required' :  TT('This field is required.'),
    'wizard-server-number' :  TT('Please enter a whole number.'),
    'wizard-optional' :  TT('Optional'), #: As in "this item is optional"
    'wizard-example' :  TT('E.g.'), #: Abbreviation for "for example"
    'wizard-button-testServer' :  TT('Test Server'), #: Wizard step
    'wizard-restarting' :  TT('Restarting SABnzbd...'), #: Wizard step
    'wizard-complete' :  TT('Setup is now complete!'), #: Wizard step
    'wizard-tip1' :  TT('SABnzbd will now be running in the background.'), #: Wizard tip
    'wizard-tip2' :  TT('Closing any browser windows/tabs will NOT close SABnzbd.'), #: Wizard tip
    'wizard-tip3' :  TT('After SABnzbd has finished restarting you will be able to access it at the following location: %s'), #: Wizard tip
    'wizard-tip4' :  TT('It is recommended you right click and bookmark this location and use this bookmark to access SABnzbd when it is running in the background.'), #: Wizard tip
    'wizard-tip-wiki' :  TT('Further help can be found on our'), #: Will be appended with a wiki-link, adjust word order accordingly
    'wizard-goto' :  TT('Go to SABnzbd'), #: Wizard step
    'wizard-step-one' :  TT('Step One'), #: Wizard step
    'wizard-step-two' :  TT('Step Two'), #: Wizard step
    'wizard-step-three' :  TT('Step Three'), #: Wizard step
    'wizard-step-four' :  TT('Step Four'), #: Wizard step
    'wizard-step-five' :  TT('Step Five'), #: Wizard step
    'wizard-port-eg' : TT('E.g. 119 or 563 for SSL'), #: Wizard port number examples
    'wizard-exit' : TT('Exit SABnzbd'), #: Wizard EXIT button on first page
    'wizard-start' : TT('Start Wizard'), #: Wizard START button on first page
    'wizard-bandwidth-explain' : TT('When your ISP speed is 10 Mbits/sec, enter here 1M'), #: Wizard explain relation bits/sec bytes/sec
    'wizard-bandwidth-error' : TT('Enter a speed (e.g. 5M)'), #: Wizard tell user to enter a max bandwidth

#Special
    'yourRights' : TT('''
SABnzbd comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it under certain conditions.
It is licensed under the GNU GENERAL PUBLIC LICENSE Version 2 or (at your option) any later version.
''')
    }
