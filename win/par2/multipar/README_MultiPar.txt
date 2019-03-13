
Restore damaged or lost files with PAR recovery files.

MultiPar (set of PAR clients and GUI)

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

[ Introduction ]

 MultiPar was made as an alternative to QuickPar.
The GUI is similar to QuickPar by getting agreement from Peter Clements.
While it looks like a multi-lingual version of QuickPar,
there are some good features; Unicode characters, directory-tree,
faster repairing, smaller recovery files, batch scripting, and so on.

[ Feature ]

 MultiPar supports both PAR 1.0 and PAR 2.0 specifications.
See "http://parchive.sourceforge.net/" for details of Parchive.
MultiPar uses UTF-8 or UTF-16 to treat filenames with non-ASCII characters.
While MultiPar and par2_tbb can treat sub-directory and UTF-8 filename,
QuickPar and other PAR2 clients cannot treat them.
Almost all PAR2 clients don't support UTF-16 filename and comment.
Be careful to use those special features.

[ System requirement ]

 MultiPar requires a PC with Windows XP or later (Windows Vista, 7, 8, 10, etc).


/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

[ Failure, Fault or Mistake ]

 Use this application at your own risk, because I might miss something.
If you find something odd behavior, report the incident to me.
Some examples like output-log, screen-shot, file name, file size, your PC spec,
and detailes (when / where / what / how) are helpful to solve problems.
Please contain them as possible as you can.
Then, I will fix it at next version.

[ Security risk ]

 You should treat PAR files in a same security level as their source files. 
When you have secret data on some files and encrypt them, 
you must create PAR files from their encrypted files. 
If you create PAR files from non-encrypted files,
others may know how is the original secret data.
Even when there is no enough redundancy to recover it completely,
their PAR files may reveal useful information for a spy.

 Parchive doesn't prevent an intended modification. 
Recovering with unknown PAR files is same as copying unknown files on your PC. 
The reliability of recovered files depends on their PAR files. 
PAR clients may modify original valid files into something invalid files, 
when PAR files were modified by a malicious cracker. 
For example, if someone created PAR files from his modified source files, 
the PAR files will damage your complete source files.

[ PAR 3.0 is not finished yet ]

 PAR 3.0 in MultiPar is implemented only for personal testing purpose.
Because I modify its algorithm and format sometimes while writing the proposal,
current samples won't be compatible with future PAR 3.0 specifications.
Don't send current PAR3 files to others, who may not have the same version.

 Currently sample PAR3 isn't available, while the specification is being updated.


/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

[ How to install or uninstall with installer package ]

 Double click setup file ( MultiPar129_setup.exe or something like this name ),
and follow the installer dialog.
At version up, if you want to use previous setting, overwrite install is possible.
Before overwrite install, you should un-check "Integrate MultiPar into Shell".
You may need to re-start OS after overwrite install or uninstall rarely.
To install under "Program Files" directory on Windows Vista/7/8,
you must start the installer with administrative privileges by selecting
"Run as administrator" on right-click menu.

 You can uninstall through the Windows OS's Control Panel,
or double click unins000.exe in a folder which MultiPar was installed.
Because uninstaller does not delete setting files or newly put files,
you may delete them by yourself.

 When you have used installer package, you should not move install folder.
Or else, you will fail to uninstall later.

[ Installation for multiple users by installer package ]

 If multiple users may log-on a PC, the administrator can install MultiPar for everyone.
By installing with administrative privileges, installer made Start Menu icon,
Desktop icon, and File association will be available for all users.
When he installed under "Program Files" directory, each user keeps individual setting.
When he installed in another folder, all users share same setting.
In either case, user made icons and association are available for the user only.


[ How to install with archive version ]

 Unpack compressed file ( MultiPar129.zip or something like this name ) in a folder.
MultiPar.exe is the interface of MultiPar.

 You can create short-cut icon or send-to link at Option window later.
If you associate PAR file extensions ".par" or ".par2" with MultiPar,
de-associate them from other application like QuickPar at first.

[ How to un-install with archive version ]

 If you associate PAR file with MultiPar, de-associate them from this.
Delete all files in the install folder, in which you extract files.
If you installed MultiPar under "Program Files" directory,
setting data was saved in MultiPar folder under "Application Data" directory,
so you need to delete the folder.

 When you integrated MultiPar into shell at Option window,
you must clear the check before un-install.
If you have deleted MultiPar.exe already, you can un-install the DLL manually.
Open "Command Prompt" and change directory to MultiPar's folder,
then type "RegSvr32.exe /u MultiParShlExt.dll" to remove shell extension.
You cannot delete "MultiParShlExt.dll", while it is used by OS or Explorer.
You may log-off and log-on again to OS before deleting the file. 

[ How to change installed folder of archive version ]

 Move files in the install folder.
If you associated PAR file with MultiPar, de-associate once, and associate again.
If you want to use same setting at another PC, copy the setting file "MultiPar.ini".
If you move MultiPar into "Program Files" directory,
setting data is saved in MultiPar folder under "Application Data" directory,
so you need to move "MultiPar.ini" into the folder, too.


/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

[ License ]

 MultiPar consists of PAR clients and GUI to control them.
They are written by Yutaka Sawada.
Though console applications are open source (PAR clients are GPL),
GUI application is closed source.
Some article are available at my web site.
(URL: "http://hp.vector.co.jp/authors/VA021385/")
If you want source code, contact with me by e-mail.


/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */

[ Support ]

 Because I cannot connect to the Internet so often, I may check mails once a week.
Please wait very long to receive my mail reply.
There is a web-forum for MultiPar users.
(URL: "http://www.livebusinesschat.com/smf/index.php?board=396.0")
Even when I cannot reply your question, other users may help.

 My name is Yutaka Sawada.
E-mail address is "tenfon (at mark) outlook.jp".
Or "multipar (at mark) outlook.jp" for PayPal usage and
"tenfon (at mark) users.sourceforge.net" for SourceForge users.
Because they use a same mail-box, don't send duplicate mails.
Though e-mail address had been "ten_fon (at mark) mail.goo.ne.jp" ago,
the mail service ended at March 2014, so don't send to there.
The (at mark) is format to avoid junk mails, and replace it with "@".

 I get many spam mails from oversea.
If an e-mail is detected as junk mail or suspicious,
mail server may delete it automatically, and I won't see it.
When you never get reply, you may ask at a web-forum.


[ Link ]

 I use Vector 's author page to introduce MultiPar.
(URL: "http://hp.vector.co.jp/authors/VA021385/")
Because there is another official download page,
(URL: "http://www.vector.co.jp/soft/dl/winnt/util/se460801.html")
using direct link to files on the page isn't preferable.
When you write a link on somewhere, please don't include filename.

