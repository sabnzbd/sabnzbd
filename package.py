#!/usr/bin/env python -OO
#
# Copyright 2008-2012 The SABnzbd-Team <team@sabnzbd.org>
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

from distutils.core import setup

import glob
import sys
import os
import platform
import tarfile
import re
import subprocess
import shutil
import time
try:
    import py2exe
except ImportError:
    py2exe = None
try:
    import py2app
    from setuptools import setup
    OSX_ML = [int(n) for n in platform.mac_ver()[0].split('.')] >= [10, 8, 0]
    OSX_LION = not OSX_ML and [int(n) for n in platform.mac_ver()[0].split('.')] >= [10, 7, 0]
    OSX_SL = not OSX_LION and not OSX_ML
    class WindowsError (): pass
except ImportError:
    py2app = None
    OSX_ML = OSX_LION = OSX_SL = False

VERSION_FILE = 'sabnzbd/version.py'
VERSION_FILEAPP = 'osx/resources/InfoPlist.strings'

my_version = 'unknown'
my_baseline = 'unknown'

def delete_files(name):
    """ Delete one file or set of files from wild-card spec """
    for f in glob.glob(name):
        try:
            if os.path.exists(f):
                os.remove(f)
        except:
            print "Cannot remove file %s" % f
            exit(1)

def CheckPath(name):
    if os.name == 'nt':
        sep = ';'
        ext = '.exe'
    else:
        sep = ':'
        ext = ''

    for path in os.environ['PATH'].split(sep):
        full = os.path.join(path, name+ext)
        if os.path.exists(full):
            return name+ext
    print "Sorry, cannot find %s%s in the path" % (name, ext)
    return None


def PatchVersion(name):
    """ Patch in the Git commit hash, but only when this is
        an unmodified checkout
    """
    global my_version, my_baseline

    commit = ''
    try:
        pipe = subprocess.Popen(GitVersion, shell=True, stdout=subprocess.PIPE).stdout
        for line in pipe.read().split('\n'):
            if 'commit ' in line:
                commit = line.split(' ')[1].strip()
                break
        pipe.close()
    except:
        print 'Cannot run %s' % GitVersion
        exit(1)

    state = ' (not committed)'
    try:
        pipe = subprocess.Popen(GitStatus, shell=True, stdout=subprocess.PIPE).stdout
        for line in pipe.read().split('\n'):
            if 'nothing to commit' in line or 'nothing added to commit' in line:
                state = ''
                break
        pipe.close()
    except:
        print 'Cannot run %s' % GitStatus
        exit(1)

    if not commit:
        print "WARNING: Cannot run %s" % GitVersion
        commit = 'unknown'

    try:
        ver = open(VERSION_FILE, 'rb')
        text = ver.read()
        ver.close()
    except:
        print "WARNING: cannot patch " + VERSION_FILE
        return

    my_baseline = commit + state
    my_version = name

    text = re.sub(r'__baseline__\s*=\s*"[^"]*"', '__baseline__ = "%s"' % my_baseline, text)
    text = re.sub(r'__version__\s*=\s*"[^"]*"', '__version__ = "%s"' % my_version, text)

    try:
        ver = open(VERSION_FILE, 'wb')
        ver.write(text)
        ver.close()
    except:
        print "WARNING: cannot patch " + VERSION_FILE

def PairList(src):
    """ Given a list of files and dirnames,
        return a list of (destn-dir, sourcelist) tuples.
        A file returns (path, [name])
        A dir returns for its root and each of its subdirs
            (path, <list-of-files>)
        Always return paths with Unix slashes.
        Skip all Git elements, .bak .pyc .pyo and *.~*
    """
    lst = []
    for item in src:
        if item.endswith('/'):
            for root, dirs, files in os.walk(item.rstrip('/\\')):
                path = root.replace('\\', '/')
                if path.find('.git') < 0:
                    flist = []
                    for file in files:
                        if not (file.endswith('.bak') or file.endswith('.pyc') or file.endswith('.pyo') or '~' in file):
                            flist.append(os.path.join(root, file).replace('\\','/'))
                    if flist:
                        lst.append((path, flist))
        else:
            path, name = os.path.split(item)
            items = [name]
            lst.append((path, items))
    return lst


def CreateTar(folder, fname, release):
    """ Create tar.gz file for source distro """
    tar = tarfile.open(fname, "w:gz")

    for root, dirs, files in os.walk(folder):
        for _file in files:
            uroot = root.replace('\\','/')
            if (uroot.find('/win') < 0) and (uroot.find('licenses/Python') < 0) and not _file.endswith('.git'):
                path = os.path.join(root, _file)
                fpath = path.replace('srcdist\\', release+'/').replace('\\', '/')
                tarinfo = tar.gettarinfo(path, fpath)
                tarinfo.uid = 0
                tarinfo.gid = 0
                if _file in ('SABnzbd.py', 'Sample-PostProc.sh', 'make_mo.py', 'msgfmt.py'): # One day add: 'setup.py'
                    # Force Linux/OSX scripts as excutable
                    tarinfo.mode = 0755
                else:
                    tarinfo.mode = 0644
                f= open(path, "rb")
                tar.addfile(tarinfo, f)
                f.close()
    tar.close()

def Dos2Unix(name):
    """ Read file, remove \r and write back """
    base, ext = os.path.splitext(name)
    if ext.lower() not in ('.py', '.txt', '.css', '.js', '.tmpl', '.sh', '.cmd'):
        return

    print name
    try:
        f = open(name, 'rb')
        data = f.read()
        f.close()
    except:
        print "File %s does not exist" % name
        exit(1)
    data = data.replace('\r', '')
    try:
        f = open(name, 'wb')
        f.write(data)
        f.close()
    except:
        print "Cannot write to file %s" % name
        exit(1)


def Unix2Dos(name):
    """ Read file, remove \r, replace \n by \r\n and write back """
    base, ext = os.path.splitext(name)
    if ext.lower() not in ('.py', '.txt', '.css', '.js', '.tmpl', '.sh', '.cmd', '.mkd'):
        return

    print name
    try:
        f = open(name, 'rb')
        data = f.read()
        f.close()
    except:
        print "File %s does not exist" % name
        exit(1)
    data = data.replace('\r', '')
    data = data.replace('\n', '\r\n')
    try:
        f = open(name, 'wb')
        f.write(data)
        f.close()
    except:
        print "Cannot write to file %s" % name
        exit(1)


def rename_file(folder, old, new):
    oldpath = "%s/%s" % (folder, old)
    newpath = "%s/%s" % (folder, new)
    try:
        if os.path.exists(newpath):
            os.remove(newpath)
        os.rename(oldpath, newpath)
    except WindowsError:
        print "Cannot create %s" % newpath
        exit(1)


print sys.argv[0]

Git = CheckPath('git')
ZipCmd = CheckPath('zip')
UnZipCmd = CheckPath('unzip')
if os.name != 'nt':
    PanDoc = CheckPath('pandoc')
else:
    PanDoc = None

if os.name == 'nt':
    msg = 'Requires the standard version of NSIS'
    NSIS = CheckPath('makensis')
    if NSIS:
        log = '%s.log' % NSIS
        os.system('%s >%s' % (NSIS, log))
        if 'Unicode' not in open(log).read():
            msg = ''
        delete_files(log)
    if msg:
        print msg
        exit(1)
else:
    NSIS = '-'

GitRevertApp =  Git + ' checkout -- '
GitRevertVersion =  GitRevertApp + ' ' + VERSION_FILE
GitVersion = Git + ' log -1'
GitStatus = Git + ' status'

if not (Git and ZipCmd and UnZipCmd):
    print 'Missing programs. Need "git", "zip" and "unzip"'
    exit(1)

if len(sys.argv) < 2:
    target = None
else:
    target = sys.argv[1]

if target not in ('source', 'binary', 'installer', 'app'):
    print 'Usage: package.py binary|installer|source|app'
    exit(1)

# Derive release name from path
base, release = os.path.split(os.getcwd())

prod = 'SABnzbd-' + release
Win32ServiceName = 'SABnzbd-service.exe'
Win32ServiceHelpName = 'SABnzbd-helper.exe'
Win32ConsoleName = 'SABnzbd-console.exe'
Win32WindowName  = 'SABnzbd.exe'
Win32HelperName  = 'SABHelper.exe'
Win32TempName    = 'SABnzbd-windows.exe'

fileIns = prod + '-win32-setup.exe'
fileBin = prod + '-win32-bin.zip'
fileSrc = prod + '-src.tar.gz'
fileDmg_ml = prod + '-osx-mountainlion.dmg'
fileDmg_lion = prod + '-osx-lion.dmg'
fileDmg_sl = prod + '-osx-snowleopard.dmg'
fileOSr = prod + '-osx-src.tar.gz'
fileImg = prod + '.sparseimage'
if OSX_SL:   postfix = 'sl'
if OSX_LION: postfix = 'lion'
if OSX_ML:   postfix = 'ml'

PatchVersion(release)


# List of data elements, directories end with a '/'
data_files = [
         'ABOUT.txt',
         'README.mkd',
         'INSTALL.txt',
         'GPL2.txt',
         'GPL3.txt',
         'CHANGELOG.txt',
         'COPYRIGHT.txt',
         'ISSUES.txt',
         'Sample-PostProc.cmd',
         'Sample-PostProc.sh',
         'PKG-INFO',
         'licenses/',
         'locale/',
         'email/',
         'interfaces/Classic/',
         'interfaces/smpl/',
         'interfaces/Plush/',
         'interfaces/Mobile/',
         'interfaces/wizard/',
         'interfaces/Config/',
         'win/par2/',
         'win/unzip/',
         'win/unrar/',
         'icons/'
       ]

options = dict(
      name = 'SABnzbd',
      version = release,
      url = 'http://sourceforge.net/projects/sabnzbdplus',
      author = 'The SABnzbd-Team',
      author_email = 'team@sabnzbd.org',
      scripts = ['SABnzbd.py', 'SABHelper.py'], # One day, add  'setup.py'
      packages = ['sabnzbd', 'sabnzbd.utils', 'util'],
      platforms = ['posix'],
      license = 'GNU General Public License 2 (GPL2) or later',
      data_files = []

)


if target == 'app':
    if not platform.system() == 'Darwin':
        print "Sorry, only works on Apple OSX!"
        os.system(GitRevertVersion)
        exit(1)

    if not PanDoc:
        print "Sorry, requires pandoc in the $PATH"
        os.system(GitRevertVersion)
        exit(1)

    # Check which Python flavour
    apple_py = 'ActiveState' not in sys.copyright

    options['description'] = 'SABnzbd ' + str(my_version)

    # Remove previous build result
    os.system('rm -rf dist/ build/')

    # Create MO files
    os.system('python ./tools/make_mo.py')

    # build SABnzbd.py
    sys.argv[1] = 'py2app'

    APP = ['SABnzbd.py']
    DATA_FILES = ['interfaces', 'locale', 'email', ('', glob.glob("osx/resources/*"))]

    NZBFILE = dict(
            CFBundleTypeExtensions = [ "nzb" ],
            CFBundleTypeIconFile = 'nzbfile.icns',
            CFBundleTypeMIMETypes = [ "text/nzb" ],
            CFBundleTypeName = 'NZB File',
            CFBundleTypeRole = 'Viewer',
            LSTypeIsPackage = 0,
            NSPersistentStoreTypeKey = 'Binary',
    )
    OPTIONS = {'argv_emulation': not apple_py,
               'iconfile': 'osx/resources/sabnzbdplus.icns',
               'plist': {
                   'NSUIElement':1,
                   'CFBundleShortVersionString':release,
                   'NSHumanReadableCopyright':'The SABnzbd-Team',
                   'CFBundleIdentifier':'org.sabnzbd.team',
                   'CFBundleDocumentTypes':[NZBFILE],
                   },
               'packages': "email,xml,Cheetah",
               'excludes': ["pywin", "pywin.debugger", "pywin.debugger.dbgcon", "pywin.dialogs",
                            "pywin.dialogs.list", "Tkconstants", "Tkinter", "tcl"]
              }

    setup(
        app=APP,
        data_files=DATA_FILES,
        options={'py2app': OPTIONS },
        setup_requires=['py2app'],
    )

    # Remove 64bit code
    if not OSX_SL:
        os.system("mv dist/SABnzbd.app dist/SABnzbd.app.temp")
        os.system("ditto --arch i386 --arch ppc dist/SABnzbd.app.temp dist/SABnzbd.app/")
        os.system("rm -rf dist/SABnzbd.app.temp")

    # Create a symlink for Mavericks compatibility
    if not OSX_SL:
        cdir = os.getcwd()
        os.chdir('dist/SABnzbd.app/Contents/Frameworks/Python.framework/Versions')
        if os.path.exists('2.7') and not os.path.exists('Current'):
            os.system('ln -s 2.7 Current')
        os.chdir(cdir)

    # copy unrar & par2 binary
    os.system("mkdir dist/SABnzbd.app/Contents/Resources/osx>/dev/null")
    os.system("mkdir dist/SABnzbd.app/Contents/Resources/osx/par2>/dev/null")
    os.system("cp -pR osx/par2/ dist/SABnzbd.app/Contents/Resources/osx/par2>/dev/null")
    os.system("mkdir dist/SABnzbd.app/Contents/Resources/osx/unrar>/dev/null")
    os.system("cp -pR osx/unrar/license.txt dist/SABnzbd.app/Contents/Resources/osx/unrar/ >/dev/null")
    if OSX_SL:
        os.system("cp -pR osx/unrar/unrar-ppc dist/SABnzbd.app/Contents/Resources/osx/unrar/ >/dev/null")
    os.system("cp -pR osx/unrar/unrar dist/SABnzbd.app/Contents/Resources/osx/unrar/ >/dev/null")
    os.system("cp icons/sabnzbd.ico dist/SABnzbd.app/Contents/Resources >/dev/null")
    os.system("pandoc -f markdown -t rtf -s -o dist/SABnzbd.app/Contents/Resources/Credits.rtf README.mkd >/dev/null")
    os.system("find dist/SABnzbd.app -name .git | xargs rm -rf")

    # Remove source files to prevent re-compilation, which would invalidate signing
    py_ver = '%s.%s' % (sys.version_info[0], sys.version_info[1])
    os.system("find dist/SABnzbd.app/Contents/Resources/lib/python%s/Cheetah -name '*.py' | xargs rm" % py_ver)
    os.system("find dist/SABnzbd.app/Contents/Resources/lib/python%s/xml -name '*.py' | xargs rm" % py_ver)
    os.system('rm dist/SABnzbd.app/Contents/Resources/site.py 2>/dev/null')

    # Add the SabNotifier app
    if OSX_ML and os.path.exists(os.path.join(os.environ['HOME'], 'sabnotifier/SABnzbd.app')):
        os.system("cp -pR $HOME/sabnotifier/SABnzbd.app dist/SABnzbd.app/Contents/Resources/")

    # Add License files
    os.mkdir("dist/SABnzbd.app/Contents/Resources/licenses/")
    os.system("cp -p licenses/*.txt dist/SABnzbd.app/Contents/Resources/licenses/")
    os.system("cp -p *.txt dist/SABnzbd.app/Contents/Resources/licenses/")

    os.system("sleep 5")

    # Sign if possible
    authority = os.environ.get('SIGNING_AUTH')
    if authority:
        os.system('codesign --deep -f -i "org.sabnzbd.SABnzbd" -s "%s" "dist/SABnzbd.app"' % authority)
        
    # Archive result to share, if present
    dest_path = os.environ.get('SHARE')
    if dest_path and os.path.exists(dest_path):
        cpio_path = os.path.join(dest_path, prod) + '-' + postfix + '.cpio'
        print 'Create CPIO file %s' % cpio_path
        delete_files(cpio_path)
        os.system('ditto -c -z dist/ "%s"' % cpio_path)
    else:
        print 'No SHARE variable set, build result not copied'

    if OSX_ML:
        print 'Create src %s' % fileOSr
        delete_files(fileOSr)
        os.system('tar -czf "%s" --exclude ".git*" --exclude "sab*.zip" --exclude "SAB*.tar.gz" --exclude "*.cmd" --exclude "*.pyc" '
                  '--exclude "*.sparseimage*" --exclude "dist" --exclude "build" --exclude "*.nsi" --exclude "win" --exclude "*.dmg" '
                  './ >/dev/null' % os.path.join(dest_path, fileOSr) )

    os.system(GitRevertApp + VERSION_FILEAPP)
    os.system(GitRevertApp + VERSION_FILE)


elif target in ('binary', 'installer'):
    if not py2exe:
        print "Sorry, only works on Windows!"
        os.system(GitRevertVersion)
        exit(1)

    # Create MO files
    os.system('tools\\make_mo.py all')

    options['data_files'] = PairList(data_files)
    options['description'] = 'SABnzbd ' + str(my_version)

    sys.argv[1] = 'py2exe'
    program = [ {'script' : 'SABnzbd.py', 'icon_resources' : [(0, "icons/sabnzbd.ico")] } ]
    options['options'] = {"py2exe":
                              {
                                "bundle_files": 3,
                                "packages": "email,xml,Cheetah,win32file",
                                "excludes": ["pywin", "pywin.debugger", "pywin.debugger.dbgcon", "pywin.dialogs",
                                             "pywin.dialogs.list", "Tkconstants", "Tkinter", "tcl"],
                                "optimize": 2,
                                "compressed": 0
                              }
                         }
    options['zipfile'] = 'lib/sabnzbd.zip'

    options['scripts'] = ['SABnzbd.py']

    ############################
    # Generate the console-app
    options['console'] = program
    setup(**options)
    rename_file('dist', Win32WindowName, Win32ConsoleName)


    # Make sure that all TXT and CMD files are DOS format
    for tup in options['data_files']:
        for file in tup[1]:
            name, ext = os.path.splitext(file)
            if ext.lower() in ('.txt', '.cmd', '.mkd'):
                Unix2Dos("dist/%s" % file)
    delete_files('dist/Sample-PostProc.sh')
    delete_files('dist/PKG-INFO')

    delete_files('*.ini')

    ############################
    # Generate the windowed-app
    options['windows'] = program
    del options['data_files']
    del options['console']
    setup(**options)
    rename_file('dist', Win32WindowName, Win32TempName)


    ############################
    # Generate the service-app
    options['service'] = [{'modules':["SABnzbd"], 'cmdline_style':'custom'}]
    del options['windows']
    setup(**options)
    rename_file('dist', Win32WindowName, Win32ServiceName)

    # Give the Windows app its proper name
    rename_file('dist', Win32TempName, Win32WindowName)


    ############################
    # Generate the Helper service-app
    options['scripts'] = ['SABHelper.py']
    options['zipfile'] = 'lib/sabhelper.zip'
    options['service'] = [{'modules':["SABHelper"], 'cmdline_style':'custom'}]
    options['packages'] = ['util']
    options['data_files'] = []
    options['options']['py2exe']['packages'] = "win32file"

    setup(**options)
    rename_file('dist', Win32HelperName, Win32ServiceHelpName)


    ############################
    # Remove unwanted system DLL files that Py2Exe copies when running on Win7
    delete_files(r'dist\lib\API-MS-Win-*.dll')
    delete_files(r'dist\lib\MSWSOCK.DLL')
    delete_files(r'dist\lib\POWRPROF.DLL')
    delete_files(r'dist\lib\KERNELBASE.dll')

    ############################
    # Remove .git residue
    delete_files(r'dist\interfaces\Config\.git')

    ############################
    # Copy Curl if needed
    if sys.version_info < (2, 6):
        # Curl for Python 2.5
        os.system(r'unzip -o win\curl\curl.zip -d dist\lib')

    ############################
    # Fix icon issue with NZB association
    os.system(r'copy dist\icons\nzb.ico dist')

    ############################
    # Rename MKD file
    rename_file('dist', 'README.mkd', 'README.txt')

    ############################
    if target == 'installer':
        delete_files(fileIns)
        os.system('makensis.exe /v3 /DSAB_PRODUCT=%s /DSAB_VERSION=%s /DSAB_FILE=%s NSIS_Installer.nsi.tmp' % \
                  (prod, release, fileIns))
        delete_files('NSIS_Installer.nsi.tmp')
        if not os.path.exists(fileIns):
            print 'Fatal error creating %s' % fileIns
            exit(1)

    delete_files(fileBin)
    os.rename('dist', prod)
    os.system('zip -9 -r -X %s %s' % (fileBin, prod))
    time.sleep(1.0)
    os.rename(prod, 'dist')

    os.system(GitRevertVersion)

    ############################
    # Check for uncompressed sqlite3.dll
    if os.path.getsize('dist/lib/sqlite3.dll') < 400000L:
        print
        print '>>>> WARNING: compressed version of sqlite3.dll detected, use uncompressed version!!'
        print

else:
    # Prepare Source distribution package.
    # Make sure all source files are Unix format
    import shutil

    # Create MO files
    os.system('python tools/make_mo.py all')

    root = 'srcdist'
    root = os.path.normpath(os.path.abspath(root))
    if not os.path.exists(root):
        os.mkdir(root)

    # Set data files
    data_files.extend(['po/', 'cherrypy/', 'gntp/', 'solaris/'])
    options['data_files'] = PairList(data_files)
    options['data_files'].append(('tools', ['tools/make_mo.py', 'tools/msgfmt.py']))

    # Copy the data files
    for set in options['data_files']:
        dest, src = set
        ndir = root + '/' + dest
        ndir = os.path.normpath(os.path.abspath(ndir))
        if not os.path.exists(ndir):
            os.makedirs(ndir)
        for file in src:
            shutil.copy2(file, ndir)
            Dos2Unix(ndir + '/' + os.path.basename(file))

    # Copy the script files
    for name in options['scripts']:
        file = os.path.normpath(os.path.abspath(name))
        shutil.copy2(file, root)
        base = os.path.basename(file)
        fullname = os.path.normpath(os.path.abspath(root + '/' + base))
        Dos2Unix(fullname)

    # Copy all content of the packages (but skip backups and pre-compiled stuff)
    for unit in options['packages']:
        unitpath = unit.replace('.','/')
        dest = os.path.normpath(os.path.abspath(root + '/' + unitpath))
        if not os.path.exists(dest):
            os.makedirs(dest)
        for name in glob.glob("%s/*.*" % unitpath):
            file = os.path.normpath(os.path.abspath(name))
            front, ext = os.path.splitext(file)
            base = os.path.basename(file)
            fullname = os.path.normpath(os.path.abspath(dest + '/' + base))
            if (ext.lower() not in ('.pyc', '.pyo', '.bak')) and '~' not in ext:
                shutil.copy2(file, dest)
                Dos2Unix(fullname)

    ############################
    # Rename MKD file
    rename_file(root, 'README.mkd', 'README.txt')

    os.chdir(root)
    os.chdir('..')

    # Prepare the TAR.GZ pacakge
    CreateTar('srcdist', fileSrc, prod)

    os.system(GitRevertVersion)
