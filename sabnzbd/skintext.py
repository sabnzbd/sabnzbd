#!/usr/bin/python3 -OO
# -*- coding: UTF-8 -*-
# Copyright 2012-2020 The SABnzbd-Team <team@sabnzbd.org>
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
    'post-Propagating'   : TT('Propagation delay'),
    'post-Checking'      : TT('Checking'), #: PP status

    'sch-task'           : TT('Task'), #:  #: Config->Scheduler
    'sch-disable_server' : TT('disable server'), #:  #: Config->Scheduler
    'sch-enable_server'  : TT('enable server'), #:  #: Config->Scheduler

    'sch-speedlimit'     : TT('Speedlimit'), #:  #: Config->Scheduler
    'sch-pause_all'      : TT('Pause All'), #:  #: Config->Scheduler
    'sch-pause_post'     : TT('Pause post-processing'), #:  #: Config->Scheduler
    'sch-resume_post'    : TT('Resume post-processing'), #:  #: Config->Scheduler
    'sch-scan_folder'    : TT('Scan watched folder'), #:  #: Config->Scheduler
    'sch-rss_scan'       : TT('Read RSS feeds'), #:  #: Config->Scheduler
    'sch-remove_failed'  : TT('Remove failed jobs'), #: Config->Scheduler
    'sch-remove_completed': TT('Remove completed jobs'), #: Config->Scheduler
    'sch-pause_all_low'  : TT('Pause low prioirty jobs'), #: Config->Scheduler
    'sch-pause_all_normal':TT('Pause normal prioirty jobs'), #: Config->Scheduler
    'sch-pause_all_high' : TT('Pause high prioirty jobs'), #: Config->Scheduler
    'sch-resume_all_low' : TT('Resume low prioirty jobs'), #: Config->Scheduler
    'sch-resume_all_normal':TT('Resume normal prioirty jobs'), #: Config->Scheduler
    'sch-resume_all_high': TT('Resume high prioirty jobs'), #: Config->Scheduler
    'sch-enable_quota'   : TT('Enable quota management'), #: Config->Scheduler
    'sch-disable_quota'  : TT('Disable quota management'), #: Config->Scheduler
    'sch-pause_cat'      : TT('Pause jobs with category'), #: Config->Scheduler
    'sch-resume_cat'     : TT('Resume jobs with category'), #: Config->Scheduler

    'prowl-off'          : TT('Off'), #: Prowl priority
    'prowl-very-low'     : TT('Very Low'), #: Prowl priority
    'prowl-moderate'     : TT('Moderate'), #: Prowl priority
    'prowl-normal'       : TT('Normal'), #: Prowl priority
    'prowl-high'         : TT('High'), #: Prowl priority
    'prowl-emergency'    : TT('Emergency'), #: Prowl priority

    'pushover-off'       : TT('Off'), #: Prowl priority
    'pushover-low'       : TT('Low'), #: Prowl priority
    'pushover-high'      : TT('High'), #: Prowl priority

# General texts
    'default' : TT('Default'), #: Default value, used in dropdown menus
    'none' : TT('None'), #: No value, used in dropdown menus
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
    'January': TT('January'),
    'February': TT('February'),
    'March': TT('March'),
    'April': TT('April'),
    'May': TT('May'),
    'June': TT('June'),
    'July': TT('July'),
    'August': TT('August'),
    'September': TT('September'),
    'October': TT('October'),
    'November': TT('November'),
    'December': TT('December'),
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
    'notAvailable' : TT('Not available'),
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
    'login' : TT('Log in'),
    'logout' : TT('Log out'),
    'rememberme' : TT('Remember me'),

# General template elements
    'signOn' : TT('The automatic usenet download tool'), #: SABnzbd's theme line
    'button-save' : TT('Save'), #: "Save" button
    'button-saving' : TT('Saving..'),
    'button-failed' : TT('Failed'),
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
    'menu-issues' : TT('Issues'), #: Main menu item
    'menu-donate' : TT('Support the project, Donate!'), #: Main menu item
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
    'cmenu-search' : TT('Search'), #: Main menu item

# Footer
    'ft-download' : TT('Download Dir'), # Used in Footer
    'ft-paused' : TT('PAUSED'), # Used in Footer
    'ft-buffer@2' : TT('Cached %s articles (%s)'), # Used in Footer
    'ft-sysload' : TT('Sysload'), # Used in Footer
    'ft-newRelease@1' : TT('New release %s available at'), # Used in Footer

# Main page
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
    'pp-r' : TT('R'),  #: Post processing pick list: abbreviation for "+Repair"
    'pp-u' : TT('U'),  #: Post processing pick list: abbreviation for "+Unpack"
    'pp-d' : TT('D'),  #: Post processing pick list: abbreviation for "+Delete"
    'pr-force' : TT('Force'), #: Priority pick list
    'pr-normal' : TT('Normal'), #: Priority pick list
    'pr-high' : TT('High'), #: Priority pick list
    'pr-low' : TT('Low'), #: Priority pick list
    'pr-paused' : TT('Paused'), #: Priority pick list
    'pr-stop' : TT('Stop'), #: Priority pick list
    'enterURL' : TT('Enter URL'), #: Add NZB Dialog

# Queue page
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
    'eta' : TT('ETA'), #: Queue page table column header, "estimated time of arrival"
    'age' : TT('AGE'), #: Queue page table column header, "age of the NZB"
    'button-del' : TT('Del'),  #: Queue page table, "Delete" button
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
    'purgeHistConf' : TT('Delete all completed items from History?'), #: Confirmation popup
    'hideDetails' : TT('Hide details'), #: Button/link hiding History job details
    'showDetails' : TT('Show details'), #: Button/link showing History job details
    'showFailedHis' : TT('Show Failed'), #: Button or link showing only failed History jobs. DON'T MAKE THIS VERY LONG!
    'showAllHis' : TT('Show All'), #: Button or link showing all History jobs
    'completed' : TT('Completed'), #: History: job status
    'size' : TT('Size'), #: History table header
    'status' : TT('Status'), #: History table header
    'purgeFailed' : TT('Purge Failed NZBs'), #: Button to delete all failed jobs in History
    'purgeFailed-Files' : TT('Purge Failed NZBs & Delete Files'), #: Button to delete all failed jobs in History, including files
    'purgeCompl' : TT('Purge Completed NZBs'), #: Button to delete all completed jobs in History
    'purgePage' : TT('Purge NZBs on the current page'), #: Button to delete jobs on current page in History
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
    'explain-forceDisc' : TT('Disconnect all active connections to usenet servers. Connections will be reopened after a few seconds if there are items in the queue.'), #: Status page button text
    'askTestEmail' : TT('This will send a test email to your account.'),
    'link-showLog' : TT('Show Logging'), #: Status page button
    'link-testEmail' : TT('Test Email'), #: Status page button
    'logging' : TT('Logging'), #: Status page selection menu
    'log-errWarn' : TT('Errors/Warning'), #: Status page table header
    'log-info' : TT('+ Info'), #: Status page logging selection value
    'log-debug' : TT('+ Debug'), #: Status page logging selection value
    'connections' : TT('Connections'), #: Status page tab header
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

# Dashboard
    'dashboard-title' : TT('Dashboard'),
    'dashboard-connectionError' : TT('Connection failed!'),
    'dashboard-localIP4' : TT('Local IPv4 address'),
    'dashboard-publicIP4' : TT('Public IPv4 address'),
    'dashboard-IP6' : TT('IPv6 address'),
    'dashboard-NameserverDNS' : TT('Nameserver / DNS Lookup'),
    'dashboard-cpuModel' : TT('CPU Model'),
    'dashboard-systemPerformance' : TT('System Performance (Pystone)'), #: Do not translate Pystone
    'dashboard-downloadDirSpeed' : TT('Download folder speed'),
    'dashboard-completeDirSpeed' : TT('Complete folder speed'),
    'dashboard-writingSpeed' : TT('Writing speed'),
    'dashboard-speedTestFailed' : TT('Could not write. Check that the directory is writable.'),
    'dashboard-internetBandwidth' : TT('Internet Bandwidth'),
    'dashboard-clickToStart' : TT('Click on Repeat test button below to determine'),
    'dashboard-repeatTest' : TT('Repeat test'),
    'dashboard-testDownload' : TT('Test download'),
    'dashboard-testDownload-explain' : TT('Adds a verified test NZB of the specified size, filled with random data. Can be used to verify your setup.'),

# Configuration
    'confgFile' : TT('Config File'),
    'cache' : TT('Used cache'), #: Main config page, how much cache is in use
    'explain-Restart' : TT('This will restart SABnzbd.<br />Use it when you think the program has a stability problem.<br />Downloading will be paused before the restart and resume afterwards.'),
    'explain-needNewLogin' : TT('<br />If authentication is enabled, you will need to login again.'),
    'button-advanced' : TT('Advanced'),
    'button-restart' : TT('Restart'),
    'explain-orphans' : TT('There are orphaned jobs in the download folder.<br />You can choose to delete them (including files) or send them back to the queue.'),
    'button-repair' : TT('Repair'),
    'explain-Repair' : TT('The "Repair" button will restart SABnzbd and do a complete<br />reconstruction of the queue content, preserving already downloaded files.<br />This will modify the queue order.'),
    'confirmWithoutSavingPrompt' : TT('Changes have not been saved, and will be lost.'),
    'explain-sessionExpire': TT('When your IP address changes or SABnzbd is restarted the session will expire.'),
    'opt-enable_unzip' : TT('Enable Unzip'),
    'opt-enable_7zip' : TT('Enable 7zip'),
    'opt-multicore-par2' : TT('Multicore Par2'),
    'explain-nosslcontext' : TT('Secure (SSL) connections from SABnzbd to newsservers and HTTPS websites will be encrypted, however, validating a server\'s identity using its certificates is not possible. OpenSSL 1.0.2 or above and up-to-date local CA certificates are required.'),
    'explain-getpar2mt': TT('Speed up repairs by installing multicore Par2, it is available for many platforms.'),
    'version' : TT('Version'),
    'uptime' : TT('Uptime'),
    'backup' : TT('Backup'), #: Indicates that server is Backup server in Status page
    'readwiki': TT('Read the Wiki Help on this!'),
    'restarting-sab': TT('Restarting SABnzbd...'),

# Config->General
    'restartRequired' : TT('Changes will require a SABnzbd restart!'),
    'webServer' : TT('SABnzbd Web Server'),
    'opt-host' : TT('SABnzbd Host'),
    'explain-host' : TT('Host SABnzbd should listen on.'),
    'opt-port' : TT('SABnzbd Port'),
    'explain-port' : TT('Port SABnzbd should listen on.'),
    'opt-web_dir' : TT('Web Interface'),
    'explain-web_dir' : TT('Choose a skin.'),
    'opt-web_username' : TT('SABnzbd Username'),
    'explain-web_username' : TT('Optional authentication username.'),
    'opt-web_password' : TT('SABnzbd Password'),
    'explain-web_password' : TT('Optional authentication password.'),
    'checkSafety' : TT('If the SABnzbd Host or Port is exposed to the internet, your current settings allow full external access to the SABnzbd interface.'),
    'security' : TT('Security'),
    'opt-enable_https' : TT('Enable HTTPS'),
    'opt-notInstalled' : TT('not installed'),
    'explain-enable_https' : TT('Enable accessing the interface from a HTTPS address.'),
    'opt-https_port' : TT('HTTPS Port'),
    'explain-https_port' : TT('If empty, the standard port will only listen to HTTPS.'),
    'opt-https_cert' : TT('HTTPS Certificate'),
    'explain-https_cert' : TT('File name or path to HTTPS Certificate.'),
    'explain-new-cert': TT('Generate new self-signed certificate and key. Requires SABnzbd restart!'),
    'opt-https_key' : TT('HTTPS Key'),
    'explain-https_key' : TT('File name or path to HTTPS Key.'),
    'opt-https_chain' : TT('HTTPS Chain Certifcates'),
    'explain-https_chain' : TT('File name or path to HTTPS Chain.'),
    'tuning' : TT('Tuning'),
    'opt-rss_rate' : TT('RSS Checking Interval'),
    'explain-rss_rate' : TT('Checking interval (in minutes, at least 15). Not active when you use the Scheduler!'),
    'opt-bandwidth_max' : TT('Maximum line speed'),
    'opt-bandwidth_perc' : TT('Percentage of line speed'),
    'explain-bandwidth_perc' : TT('Which percentage of the linespeed should SABnzbd use, e.g. 50'),
    'opt-cache_limitstr' : TT('Article Cache Limit'),
    'explain-cache_limitstr' : TT('Cache articles in memory to reduce disk access.<br /><i>In bytes, optionally follow with K,M,G. For example: "64M" or "128M"</i>'),
    'opt-cleanup_list' : TT('Cleanup List'),
    'explain-cleanup_list' : TT('List of file extensions that should be deleted after download.<br />For example: <b>nfo</b> or <b>nfo, sfv</b>'),
    'opt-history_retention' : TT('History Retention'),
    'explain-history_retention' : TT('Automatically delete completed jobs from History. Beware that Duplicate Detection and some external tools rely on History information.'),
    'history_retention-all' : TT('Keep all jobs'),
    'history_retention-number' : TT('Keep maximum number of completed jobs'),
    'history_retention-days' : TT('Keep completed jobs maximum number of days'),
    'history_retention-none' : TT('Do not keep any completed jobs'),
    'history_retention-limit': TT('Jobs'),
    'button-saveChanges' : TT('Save Changes'),
    'button-restoreDefaults' : TT('Restore Defaults'),
    'explain-restoreDefaults' : TT('Reset'),
    'opt-language' : TT('Language'),
    'explain-language' : TT('Select a web interface language.'),
    'explain-ask-language': TT('Help us translate SABnzbd in your language! <br/>Add untranslated texts or improved existing translations here:'), # Link to sabnzbd.org follows this text
    'opt-apikey' : TT('API Key'),
    'explain-apikey' : TT('This key will give 3rd party programs full access to SABnzbd.'),
    'opt-nzbkey' : TT('NZB Key'),
    'explain-nzbkey' : TT('This key will allow 3rd party programs to add NZBs to SABnzbd.'),
    'button-apikey' : TT('Generate New Key'),
    'explain-qr-code' : TT('API Key QR Code'), #: Explanation for QR code of APIKEY
    'opt-local_ranges' : TT('List of local network ranges'),
    'explain-local_ranges' : TT('All local network addresses start with these prefixes (often "192.168.1.")'),
    'opt-inet_exposure' : TT('External internet access'),
    'explain-inet_exposure' : TT('You can set access rights for systems outside your local network. Requires List of local network ranges to be defined.'),
    'inet-local' : TT('No access'), # Selection value for external access
    'inet-nzb' : TT('Add NZB files '), # Selection value for external access
    'inet-api' : TT('API (no Config)'), # Selection value for external access
    'inet-fullapi' : TT('Full API'), # Selection value for external access
    'inet-ui' : TT('Full Web interface'), # Selection value for external access
    'inet-external_login' : TT('Only external access requires login'), # Selection value for external access

# Config->Folders
    'explain-folderConfig' : TT('<em>NOTE:</em> Folders will be created automatically when Saving. You may use absolute paths to save outside of the default folders.'),
    'userFolders' : TT('User Folders'),
    'browse-folder' : TT('Browse'),
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
    'opt-script_dir' : TT('Scripts Folder'),
    'explain-script_dir' : TT('Folder containing user scripts.'),
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
    'opt-enable_all_par' : TT('Download all par2 files'),
    'explain-enable_all_par' : TT('This prevents multiple repair runs by downloading all par2 files when needed.'),
    'opt-enable_recursive' : TT('Enable recursive unpacking'),
    'explain-enable_recursive' : TT('Unpack archives (rar, zip, 7z) within archives.'),
    'opt-flat_unpack' : TT('Ignore any folders inside archives'),
    'explain-flat_unpack' : TT('All files will go into a single folder.'),
    'opt-top_only' : TT('Only Get Articles for Top of Queue'),
    'explain-top_only' : TT('Enable for less memory usage. Disable to prevent slow jobs from blocking the queue.'),
    'opt-safe_postproc' : TT('Post-Process Only Verified Jobs'),
    'explain-safe_postproc' : TT('Only perform post-processing on jobs that passed all PAR2 checks.'),
    'opt-pause_on_pwrar' : TT('Action when encrypted RAR is downloaded'),
    'explain-pause_on_pwrar' : TT('In case of "Pause", you\'ll need to set a password and resume the job.'),
    'opt-no_dupes' : TT('Detect Duplicate Downloads'),
    'explain-no_dupes' : TT('Detect identical NZB files (based on items in your History or files in .nzb Backup Folder)'),
    'opt-no_series_dupes' : TT('Detect duplicate episodes in series'),
    'explain-no_series_dupes' : TT('Detect identical episodes in series (based on "name/season/episode" of items in your History)'),
    'opt-series_propercheck' : TT('Allow proper releases'),
    'explain-series_propercheck' : TT('Bypass series duplicate detection if PROPER, REAL or REPACK is detected in the download name'),
    'nodupes-off' : TT('Off'), #: Three way switch for duplicates
    'nodupes-ignore' : TT('Discard'), #: Four way switch for duplicates
    'nodupes-pause' : TT('Pause'), #: Four way switch for duplicates
    'nodupes-fail' : TT('Fail job (move to History)'), #: Four way switch for duplicates
    'nodupes-tag' : TT('Tag job'), #: Four way switch for duplicates
    'abort' : TT('Abort'), #: Three way switch for encrypted posts
    'opt-action_on_unwanted_extensions' : TT('Action when unwanted extension detected'),
    'explain-action_on_unwanted_extensions' : TT('Action when an unwanted extension is detected in RAR files'),
    'opt-unwanted_extensions' : TT('Unwanted extensions'),
    'explain-unwanted_extensions' : TT('List all unwanted extensions. For example: <b>exe</b> or <b>exe, com</b>'),
    'opt-sfv_check' : TT('Enable SFV-based checks'),
    'explain-sfv_check' : TT('Do an extra verification based on SFV files.'),
    'opt-script_can_fail' : TT('User script can flag job as failed'),
    'explain-script_can_fail' : TT('When the user script returns a non-zero exit code, the job will be flagged as failed.'),
    'opt-new_nzb_on_failure' : TT('On failure, try alternative NZB'),
    'explain-new_nzb_on_failure' : TT('Some servers provide an alternative NZB when a download fails.'),
    'opt-enable_meta' : TT('Use tags from indexer'),
    'explain-enable_meta' : TT('When sorting, use tags from indexer for title, season, episode, etc. Otherwise all naming is derived from the NZB name.'),
    'opt-folder_rename' : TT('Enable folder rename'),
    'explain-folder_rename' : TT('Use temporary names during post processing. Disable when your system doesn\'t handle that properly.'),
    'opt-pre_script' : TT('Pre-queue user script'),
    'explain-pre_script' : TT('Used before an NZB enters the queue.'),
    'opt-par_option' : TT('Extra PAR2 Parameters'),
    'explain-par_option' : TT('Read the Wiki Help on this!'),
    'opt-nice' : TT('Nice Parameters'),
    'explain-nice' : TT('Read the Wiki Help on this!'),
    'opt-ionice' : TT('IONice Parameters'),
    'explain-ionice' : TT('Read the Wiki Help on this!'),
    'opt-win_process_prio' : TT('External process priority'),
    'explain-win_process_prio' : TT('Read the Wiki Help on this!'),
    'win_process_prio-high' : TT('High'),
    'win_process_prio-normal' : TT('Normal'),
    'win_process_prio-low' : TT('Low'),
    'win_process_prio-idle' : TT('Idle'),
    'opt-auto_disconnect' : TT('Disconnect on Empty Queue'),
    'explain-auto_disconnect' : TT('Disconnect from Usenet server(s) when queue is empty or paused.'),
    'opt-auto_sort' : TT('Sort by Age'),
    'explain-auto_sort' : TT('Automatically sort items by (average) age.'),
    'opt-direct_unpack' : TT('Direct Unpack'),
    'explain-direct_unpack' : TT('Jobs will start unpacking during the downloading to reduce post-processing time. Only works for jobs that do not need repair.'),
    'opt-propagation_delay' : TT('Propagation delay'),
    'explain-propagation_delay' : TT('Posts will be paused untill they are at least this age. Setting job priority to Force will skip the delay.'),
    'opt-check_new_rel' : TT('Check for New Release'),
    'explain-check_new_rel' : TT('Weekly check for new SABnzbd release.'),
    'also-test' : TT('Also test releases'), #: Pick list for weekly test for new releases
    'opt-replace_spaces' : TT('Replace Spaces in Foldername'),
    'explain-replace_spaces' : TT('Replace spaces with underscores in folder names.'),
    'opt-replace_dots' : TT('Replace dots in Foldername'),
    'explain-replace_dots' : TT('Replace dots with spaces in folder names.'),
    'opt-sanitize_safe' : TT('Make Windows compatible'),
    'explain-sanitize_safe' : TT('For servers: make sure names are compatible with Windows.'),
    'opt-auto_browser' : TT('Launch Browser on Startup'),
    'explain-auto_browser' : TT('Launch the default web browser when starting SABnzbd.'),
    'opt-pause_on_post_processing' : TT('Pause Downloading During Post-Processing'),
    'explain-pause_on_post_processing' : TT('Pauses downloading at the start of post processing and resumes when finished.'),
    'opt-ignore_samples' : TT('Ignore Samples'),
    'explain-ignore_samples' : TT('Filter out sample files (e.g. video samples).'),
    'igsam-del' : TT('Delete after download'),
    'opt-enable_https_verification' : TT('HTTPS certificate verification'),
    'explain-enable_https_verification' : TT('Verify certificates when connecting to indexers and RSS-sources using HTTPS.'),
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
    'opt-ssl_ciphers' : TT('SSL Ciphers'),
    'explain-ssl_ciphers' : TT('Increase performance by forcing a lower SSL encryption strength.'),
    'opt-max_art_tries' : TT('Maximum retries'),
    'explain-max_art_tries' : TT('Maximum number of retries per server'),
    'opt-fail_hopeless_jobs' : TT('Abort jobs that cannot be completed'),
    'explain-fail_hopeless_jobs' : TT('When during download it becomes clear that too much data is missing, abort the job'),
    'opt-rating_enable' : TT('Enable Indexer Integration'),
    'explain-rating_enable' : TT('Indexers can supply rating information when a job is added and SABnzbd can report to the indexer if a job couldn\'t be completed.'),
    'opt-rating_api_key' : TT('API Key'),
    'explain-rating_api_key' : TT('This key provides identity to indexer. Check your profile on the indexer\'s website.'),
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
    'opt-load_balancing' : TT('Server IP address selection'),
    'no-load-balancing' : TT('First IP address'),
    'load-balancing' : TT('Randomly selected IP address'),
    'load-balancing-happy-eyeballs' : TT('Quickest IP address, preferring IPv6'),
    'explain-load_balancing' : TT('Useful if a newsserver has more than one IPv4/IPv6 address'),

# Config->Server
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
    'explain-ssl' : TT('Secure connection to server'), #: Server SSL tickbox
    'opt-ssl_verify' : TT('Certificate verification'),
    'explain-ssl_verify' : TT('Minimal: when SSL is enabled, verify the identity of the server using its certificates. Strict: verify and enforce matching hostname.'),
    'ssl_verify-disabled' : TT('Disabled'),
    'ssl_verify-normal' : TT('Minimal'),
    'ssl_verify-strict' : TT('Strict'),
    'srv-priority' : TT('Priority'), #: Server priority
    'explain-svrprio' : TT('0 is highest priority, 100 is the lowest priority'), #: Explain server priority
    'srv-optional' : TT('Optional'), #: Server optional tickbox
    'explain-optional' : TT('For unreliable servers, will be ignored longer in case of failures'), #: Explain server optional tickbox
    'srv-enable' : TT('Enable'), #: Enable server tickbox
    'button-addServer' : TT('Add Server'), #: Button: Add server
    'button-delServer' : TT('Remove Server'), #: Button: Remove server
    'button-testServer' : TT('Test Server'), #: Button: Test server
    'button-clrServer' : TT('Clear Counters'), #: Button: Clear server's byte counters
    'srv-testing' : TT('Testing server details...'),
    'srv-bandwidth' : TT('Bandwidth'),
    'srv-send_group' : TT('Send Group'),
    'srv-explain-send_group' : TT('Send group command before requesting articles.'),
    'srv-notes' : TT('Personal notes'),

# Config->Scheduling
    'addSchedule' : TT('Add Schedule'), #:Config->Scheduling
    'sch-frequency' : TT('Frequency'), #:Config->Scheduling
    'sch-action' : TT('Action'), #:Config->Scheduling
    'sch-arguments' : TT('Arguments'), #:Config->Scheduling
    'button-addSchedule' : TT('Add Schedule'), #:Config->Scheduling
    'currentSchedules' : TT('Current Schedules'), #:Config->Scheduling
    'sch-resume' : TT('Resume'), #:Config->Scheduling
    'sch-pause' : TT('Pause'), #:Config->Scheduling
    'sch-shutdown' : TT('Shutdown'), #:Config->Scheduling
    'sch-restart' : TT('Restart'), #:Config->Scheduling

# Config->RSS
    'explain-RSS' : TT('The checkbox next to the feed name should be ticked for the feed to be enabled and be automatically checked for new items.<br />When a feed is added, it will only pick up new items and not anything already in the RSS feed unless you press "Force Download".'),
    'feed' : TT('Feed'), #: Config->RSS, tab header
    'addMultipleFeeds' : TT('Seperate multiple URLs by a comma'), #: Config->RSS, placeholder (cannot be too long)
    'button-preFeed' : TT('Read Feed'),#: Config->RSS button
    'button-forceFeed' : TT('Force Download'),#: Config->RSS button
    'rss-order' : TT('Order'), #: Config->RSS table column header
    'rss-type' : TT('Type'), #: Config->RSS table column header
    'rss-filter' : TT('Filter'), #: Config->RSS table column header
    'rss-accept' : TT('Accept'), #: Config->RSS filter-type selection menu
    'rss-reject' : TT('Reject'), #: Config->RSS filter-type selection menu
    'rss-must' : TT('Requires'), #: Config->RSS filter-type selection menu
    'rss-mustcat' : TT('RequiresCat'), #: Config->RSS filter-type selection menu
    'rss-atleast' : TT('At least'), #: Config->RSS filter-type selection menu
    'rss-atmost' : TT('At most'), #: Config->RSS filter-type selection menu
    'rss-from' : TT('From SxxEyy'), #: Config->RSS filter-type selection menu "From Season/Episode"
    'rss-from-show' : TT('From Show SxxEyy'), #: Config->RSS filter-type selection menu "From Show Season/Episode"
    'rss-matched' : TT('Matched'), #: Config->RSS section header
    'rss-notMatched' : TT('Not Matched'), #: Config->RSS section header
    'rss-done' : TT('Downloaded'), #: Config->RSS section header
    'rss-added' : TT('Added NZB'), #: Config->RSS after adding to queue
    'link-download' : TT('Download'), #: Config->RSS button "download item"
    'button-rssNow' : TT('Read All Feeds Now'), #: Config->RSS button

# Config->Notifications
    'opt-email_endjob' : TT('Email Notification On Job Completion'),
    'email-never' : TT('Never'), #: When to send email
    'email-always' : TT('Always'),  #: When to send email
    'email-errorOnly' : TT('Error-only'),  #: When to send email
    'opt-email_full' : TT('Disk Full Notifications'),
    'explain-email_full' : TT('Send email when disk is full and SABnzbd is paused.'),
    'opt-email_rss' : TT('Send RSS notifications'),
    'explain-email_rss' : TT('Send email when an RSS feed adds jobs to the queue.'),
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
    'notifications-notesent': TT('Notification Sent!'),
    'opt-ntfosd_enable' : TT('Enable NotifyOSD'), #: Don't translate "NotifyOSD"
    'opt-ncenter_enable' : TT('Notification Center'),
    'opt-acenter_enable' : TT('Enable Windows Notifications'),
    'testNotify' : TT('Test Notification'),
    'section-NC' : TT('Notification Center'), #: Header for OSX Notfication Center section
    'section-AC' : TT('Windows Notifications'),
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
    'opt-pushover_emergency_retry' : TT('Emergency retry'), #: Pushover settings
    'explain-pushover_emergency_retry' : TT('How often (in seconds) the same notification will be sent'), #: Pushover settings
    'opt-pushover_emergency_expire' : TT('Emergency expire'), #: Pushover settings
    'explain-pushover_emergency_expire' : TT('How many seconds your notification will continue to be retried'), #: Pushover settings
    'section-Pushbullet' : TT('Pushbullet'), #: Header for Pushbullet notification section
    'opt-pushbullet_enable' : TT('Enable Pushbullet notifications'), #: Pushbullet settings
    'explain-pushbullet_enable' : TT('Requires a Pushbullet account'), #: Pushbulletsettings
    'opt-pushbullet_apikey' : TT('Personal API key'), #: Pushbullet settings
    'explain-pushbullet_apikey' : TT('Your personal Pushbullet API key (required)'), #: Pushbullet settings
    'opt-pushbullet_device' : TT('Device'), #: Pushbullet settings
    'explain-pushbullet_device' : TT('Device to which message should be sent'), #: Pushbullet settings
    'section-NScript' : TT('Notification Script'), #: Header for Notification Script notification section
    'opt-nscript_enable' : TT('Enable notification script'), #: Notification Script settings
    'opt-nscript_script' : TT('Script'), #: Notification Script settings
    'opt-nscript_parameters' : TT('Parameters'), #: Notification Script settings
    'explain-nscript_enable' : TT('Executes a custom script'), #: Notification Scriptsettings
    'explain-nscript_script' : TT('Which script should we execute for notification?'), #: Notification Scriptsettings
    'explain-nscript_parameters' : TT('Read the Wiki Help on this!'), #: Notification Script settings

# Config->Cat
    'explain-catTags' : TT('Indexers can supply a category inside the NZB which SABnzbd will try to match to the categories defined below. Additionally, you can add terms to "Indexer Categories / Groups" to match more categories. Use commas to separate terms. Wildcards in the terms are supported. <br>More information can be found on the Wiki.'),
    'explain-catTags2' : TT('Ending the path with an asterisk * will prevent creation of job folders.'),
    'explain-relFolder' : TT('Relative folders are based on'),
    'catFolderPath' : TT('Folder/Path'),
    'catTags' : TT('Indexer Categories / Groups'),
    'button-delCat' : TT('X'), #: Small delete button

# Config->Sorting
    'seriesSorting' : TT('Series Sorting'),
    'opt-tvsort' : TT('Enable TV Sorting'),
    'sort-legenda' : TT('Pattern Key'),
    'button-clear' : TT('Clear'),
    'button-evalFeed' : TT('Apply filters'),
    'presetSort' : TT('Presets'),
    'example' : TT('Example'),
    'movieSort' : TT('Movie Sorting'),
    'opt-movieSort' : TT('Enable Movie Sorting'),
    'opt-movieExtra' : TT('Keep loose downloads in extra folders'),
    'affectedCat' : TT('Affected Categories'),
    'sort-meaning' : TT('Meaning'),
    'sort-pattern' : TT('Pattern'),
    'sort-result' : TT('Result'),
    'button-Season1x05' : TT('1x05 Season Folder'),
    'button-SeasonS01E05' : TT('S01E05 Season Folder'),
    'button-Ep1x05' : TT('1x05 Episode Folder'),
    'button-EpS01E05' : TT('S01E05 Episode Folder'),
    'button-FileLikeFolder' : TT('Job Name as Filename'),
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
    'orgJobname' : TT('Original Job Name'),
    'lowercase' : TT('Lower Case'),
    'TEXT' : TT('TEXT'),
    'text' : TT('text'),
    'sort-File' : TT('file'),
    'sortString' : TT('Sort String'),
    'multiPartLabel' : TT('Multi-part label'),
    'button-inFolders' : TT('In folders'),
    'button-noFolders' : TT('No folders'),
    'dateSorting' : TT('Date Sorting'),
    'opt-dateSort' : TT('Enable Date Sorting'),
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

#Glitter skin
    'Glitter-addNZB' : TT('Add NZB'),
    'Glitter-pause5m' : TT('Pause for 5 minutes'),
    'Glitter-pause15m' : TT('Pause for 15 minutes'),
    'Glitter-pause30m' : TT('Pause for 30 minutes'),
    'Glitter-pause1h' : TT('Pause for 1 hour'),
    'Glitter-pause3h' : TT('Pause for 3 hours'),
    'Glitter-pause6h' : TT('Pause for 6 hours'),
    'Glitter-setMaxLinespeed' : TT('You must set a maximum bandwidth before you can set a bandwidth limit'),
    'Glitter-left' : TT('left'),
    'Glitter-free' : TT('Free Space'),
    'Glitter-freeTemp' : TT('Temp Folder'),
    'Glitter-search' : TT('Search'),
    'Glitter-multiOperations' : TT('Multi-Operations'),
    'Glitter-multiSelect' : TT('Hold shift key to select a range'),
    'Glitter-checkAll' : TT('Check all'),
    'Glitter-restartSab' : TT('Restart SABnzbd'),
    'Glitter-onFinish' : TT('On queue finish'),
    'Glitter-statusInterfaceOptions' : TT('Status and interface options'),
    'Glitter-dragAndDrop' : TT('Or drag and drop files in the window!'),
    'Glitter-today' : TT('Today'),
    'Glitter-thisMonth' : TT('This month'),
    'Glitter-total' : TT('Total'),
    'Glitter-lostConnection' : TT('Lost connection to SABnzbd..'),
    'Glitter-afterRestart' : TT('In case of SABnzbd restart this screen will disappear automatically!'),
    'Glitter-disabled' : TT('Disabled'),
    'Glitter-warning' : TT('WARNING:'),
    'Glitter-encrypted' : TT('ENCRYPTED'),
    'Glitter-incomplete' : TT('INCOMPLETE'),
    'Glitter-duplicate' : TT('DUPLICATE'),
    'Glitter-unwanted' : TT('UNWANTED'),
    'Glitter-tooLarge' : TT('TOO LARGE'),
    'Glitter-filtered' : TT('FILTERED'),
    'Glitter-waitSec' : TT('WAIT %s sec'),
    'Glitter-error' : TT('ERROR:'),
    'Glitter-fetch' : TT('Fetch'),
    'Glitter-interfaceOptions' : TT('Web Interface'),
    'Glitter-interfaceRefresh' : TT('Refresh rate'),
    'Glitter-useGlobalOptions' : TT('Use global interface settings'),
    'Glitter-queueItemLimit' : TT('Queue item limit'),
    'Glitter-historyItemLimit' : TT('History item limit'),
    'Glitter-dateFormat' : TT('Date format'),
    'Glitter-showExtraQueueColumn' : TT('Extra queue column'),
    'Glitter-showExtraHistoryColumn' : TT('Extra history column'),
    'Glitter-page' : TT('page'),
    'Glitter-loading' : TT('Loading'),
    'Glitter-articles' : TT('articles'),
    'Glitter-rename' : TT('Rename'),
    'Glitter-repairQueue' : TT('Queue repair'),
    'Glitter-showActiveConnections' : TT('Show active connections'),
    'Glitter-unblockServer' : TT('Unblock'),
    'Glitter-orphanedJobs' : TT('Orphaned jobs'),
    'Glitter-backToQueue' : TT('Send back to queue'),
    'Glitter-purgeOrphaned' : TT('Delete All'),
    'Glitter-retryAllOrphaned' : TT('Retry all'),
    'Glitter-deleteJobAndFolders' : TT('Remove NZB & Delete Files'),
    'Glitter-addFromURL' : TT('Fetch NZB from URL'),
    'Glitter-addFromFile' : TT('Upload NZB'),
    'Glitter-chooseFile' : TT('Browse'),
    'Glitter-addnzbFilename' : TT('Optionally specify a filename'),
    'Glitter-submit' : TT('Submit'),
    'Glitter-openInfoURL' : TT('Open Informational URL'),
    'Glitter-sendThanks' : TT('Submitted. Thank you!'),
    'Glitter-noSelect' : TT('Nothing selected!'),
    'Glitter-removeSelected' : TT('Remove all selected files'),
    'Glitter-toggleCompletedFiles' : TT('Hide/show completed files'),
    'Glitter-top' : TT('Top'),
    'Glitter-bottom' : TT('Bottom'),
    'Glitter-retryJob' : TT('Retry'),
    'Glitter-more' : TT('More'),
    'Glitter-scriptLog' : TT('View Script Log'),
    'Glitter-clearHistory' : TT('Purge History'),
    'Glitter-confirmClearWarnings' : TT('Are you sure?'),
    'Glitter-confirmClearDownloads' : TT('Are you sure?'),
    'Glitter-confirmClear1Download' : TT('Are you sure?'),
    'Glitter-updateAvailable' : TT('Update Available!'),
    'Glitter-noLocalStorage' : TT('LocalStorage (cookies) are disabled in your browser, interface settings will be lost after you close the browser!'), #: Don't translate LocalStorage
    'Glitter-glitterTips' : TT('Glitter has some (new) features you might like!'),
    'Glitter-custom' : TT('Custom'),
    'Glitter-displayCompact' : TT('Compact layout'),
    'Glitter-displayTabbed' : TT('Tabbed layout <br/>(separate queue and history)'),
    'Glitter-speed' : TT('Speed'),
    'Glitter-confirmDeleteQueue' : TT('Confirm Queue Deletions'),
    'Glitter-confirmDeleteHistory' : TT('Confirm History Deletions'),
    'Glitter-pausePrompt': TT('How long or untill when do you want to pause? (in English!)'),
    'Glitter-pausePromptFail': TT('Sorry, we could not interpret that. Try again.'),
    'Glitter-pauseFor' : TT('Pause for...'),
    'Glitter-refresh' : TT('Refresh'),
    'Glitter-logText' : TT('All usernames, passwords and API-keys are automatically removed from the log and the included copy of your settings.'),
    'Glitter-sortAgeAsc' : TT('Sort by Age <small>Oldest&rarr;Newest</small>'),
    'Glitter-sortAgeDesc' : TT('Sort by Age <small>Newest&rarr;Oldest</small>'),
    'Glitter-sortNameAsc' : TT('Sort by Name <small>A&rarr;Z</small>'),
    'Glitter-sortNameDesc' : TT('Sort by Name <small>Z&rarr;A</small>'),
    'Glitter-sortSizeAsc' : TT('Sort by Size <small>Smallest&rarr;Largest</small>'),
    'Glitter-sortSizeDesc' : TT('Sort by Size <small>Largest&rarr;Smallest</small>'),
    'Glitter-notification-uploading' : TT('Uploading'), # Notification window
    'Glitter-notification-disconnect' : TT('Forcing disconnect'), # Notification window
    'Glitter-notification-removing1' : TT('Removing job'), # Notification window
    'Glitter-notification-removing' : TT('Removing jobs'), # Notification window
    'Glitter-notification-shutdown' : TT('Shutting down'), # Notification window

#Plush skin
    'Plush-confirmWithoutSavingPrompt' : TT('Changes have not been saved, and will be lost.'),
    'Plush-confirm' : TT('Are you sure?'),
    'Plush-openInfoURL' : TT('Open Informational URL'),
    'Plush-viewScriptLog' : TT('View Script Log'),
    'Plush-prev' : TT('Prev'),
    'Plush-next' : TT('Next'),
    'Plush-confirmPurgeH' : TT('Purge the History?'),
    'Plush-enableJavascript' : TT('You must enable JavaScript for Plush to function!'),
    'Plush-addnzb' : TT('Add NZB'),
    'Plush-button-refresh' : TT('Refresh'),
    'Plush-options' : TT('Options'),
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

#Wizard
    'wizard-quickstart' :  TT('SABnzbd Quick-Start Wizard'),
    'wizard-version' :  TT('SABnzbd Version'),
    'wizard-previous' :  TT('Previous'), #: Button to go to previous Wizard page
    'wizard-next' :  TT('Next'), #: Button to go to next Wizard page
    'wizard-server' :  TT('Server Details'),
    'wizard-explain-server' :  TT('Please enter in the details of your primary usenet provider.'),
    'wizard-server-con-explain' :  TT('The number of connections allowed by your provider'),
    'wizard-server-con-eg' : TT('E.g. 8 or 20'), #: Wizard: examples of amount of connections
    'wizard-server-ssl-explain' :  TT('Select only if your provider allows SSL connections.'),
    'wizard-server-text' :  TT('Click to test the entered details.'),
    'wizard-example' :  TT('E.g.'), #: Abbreviation for "for example"
    'wizard-button-testServer' :  TT('Test Server'), #: Wizard step
    'wizard-complete' :  TT('Setup is now complete!'), #: Wizard step
    'wizard-tip1' :  TT('SABnzbd will now be running in the background.'), #: Wizard tip
    'wizard-tip2' :  TT('Closing any browser windows/tabs will NOT close SABnzbd.'), #: Wizard tip
    'wizard-tip4' :  TT('It is recommended you right click and bookmark this location and use this bookmark to access SABnzbd when it is running in the background.'), #: Wizard tip
    'wizard-tip-wiki' :  TT('Further help can be found on our'), #: Will be appended with a wiki-link, adjust word order accordingly
    'wizard-goto' :  TT('Go to SABnzbd'), #: Wizard step
    'wizard-exit' : TT('Exit SABnzbd'), #: Wizard EXIT button on first page
    'wizard-start' : TT('Start Wizard'), #: Wizard START button on first page

#Special
    'yourRights' : TT('''
SABnzbd comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it under certain conditions.
It is licensed under the GNU GENERAL PUBLIC LICENSE Version 2 or (at your option) any later version.
'''),
    'wizard-ad-1': TT('In order to download from usenet you will require access to a provider. Your ISP may provide you with access, however a premium provider is recommended.'),
    'wizard-ad-2': TT('Don\'t have a usenet provider? We recommend trying %s.'),
    }
