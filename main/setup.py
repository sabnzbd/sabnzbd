#!/usr/bin/env python

import sabnzbd
from distutils.core import setup

# py2exe usage: python setup.py py2exe

import glob
import sys
import os
import os
import tarfile
import re
import subprocess

VERSION_FILE = 'sabnzbd/version.py'

if os.name == 'nt':
    # Patch this for another location
    SvnVersion = r'"c:\Program Files\Subversion\bin\svnversion.exe"'
    SvnRevert =  r'cmd /c "c:\Program Files\Subversion\bin\svn.exe" revert ' + VERSION_FILE
else:
    # SVN is assumed to be on the $PATH
    SvnVersion = 'svnversion'
    SvnRevert = 'svn revert ' + VERSION_FILE

try:
    import py2exe
except ImportError:
    py2exe = None

def PatchVersion(name):
    """ Patch in the SVN baseline number, but only when this is
        an unmodified checkout
    """
    try:
        pipe = subprocess.Popen(SvnVersion, shell=True, stdout=subprocess.PIPE).stdout
        svn = pipe.read().strip(' \t\n\r')
        pipe.close()
    except:
        pass
    
    if not svn:
        print "WARNING: Cannot run %s" % SvnVersion
        svn = 'unknown'

    if not (svn and svn.isdigit()):
        svn = 'unknown'

    try:
        ver = open(VERSION_FILE, 'rb')
        text = ver.read()
        ver.close()
    except:
        print "WARNING: cannot patch " + VERSION_FILE
        return

    regex = re.compile(r'__baseline__\s+=\s+"\w*"')
    text = re.sub(r'__baseline__\s*=\s*"[^"]*"', '__baseline__ = "%s"' % svn, text)
    text = re.sub(r'__version__\s*=\s*"[^"]*"', '__version__ = "%s"' % name, text)
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
            (path, <list-of-file>)
        Always return paths with Unix slashes.
        Skip all SVN elements, .bak .pyc .pyo
    """
    lst = []
    for item in src:
        if item.endswith('/'):
            for root, dirs, files in os.walk(item.rstrip('/\\')):
                path = root.replace('\\', '/')
                if path.find('.svn') < 0 and path.find('_svn') < 0 :
                    flist = []
                    for file in files:
                        if not (file.endswith('.bak') or file.endswith('.pyc') or file.endswith('.pyo')):
                            flist.append(os.path.join(root, file).replace('\\','/'))
                    if flist:
                        lst.append((path, flist))
        else:
            path, name = os.path.split(item)
            items = []
            items.append(name)
            lst.append((path, items))
    return lst


def CreateTar(folder, fname, release):
    """ Create tar.gz file for source distro """
    tar = tarfile.open(fname, "w:gz")

    for root, dirs, files in os.walk(folder):
        for _file in files:
            uroot = root.replace('\\','/')
            if (uroot.find('/win') < 0) and (uroot.find('licenses/Python') < 0):
                path = os.path.join(root, _file)
                fpath = path.replace('srcdist\\', release+'/').replace('\\', '/')
                tarinfo = tar.gettarinfo(path, fpath)
                tarinfo.uid = 0
                tarinfo.gid = 0
                if _file in ('SABnzbd.py', 'Sample-PostProc.sh'):
                    tarinfo.mode = 0755
                else:
                    tarinfo.mode = 0644
                f= open(path, "rb")
                tar.addfile(tarinfo, f)
                f.close()
    tar.close()


print sys.argv[0]

if len(sys.argv) < 2:
    target = None
else:
    target = sys.argv[1]

# Derive release name from path
base, release = os.path.split(os.getcwd())

prod = 'SABnzbd-' + release
Win32ConsoleName = 'SABnzbd-console.exe'
Win32WindowName  = 'SABnzbd.exe'

fileIns = prod + '-win32-setup.exe'
fileBin = prod + '-win32-bin.zip'
fileWSr = prod + '-win32-src.zip'
fileSrc = prod + '-src.tar.gz'

PatchVersion(release)


# List of data elements, directories end with a '/'
data = [ 'README.txt',
         'INSTALL.txt',
         'LICENSE.txt',
         'CHANGELOG.txt',
         'COPYRIGHT.txt',
         'ISSUES.txt',
         'Sample-PostProc.cmd',
         'Sample-PostProc.sh',
         'PKG-INFO',
         'licenses/',
         'interfaces/',
         'win/'
       ]

options = dict(
      name = 'SABnzbd',
      version = release,
      url = 'http://sourceforge.net/projects/sabnzbdplus',
      author = 'ShyPike, sw1tch (original work by Gregor Kaufmann)',
      author_email = 'shypike@users.sourceforge.net',
      description = 'SABnzbd ' + str(sabnzbd.__version__),
      scripts = ['SABnzbd.py'],
      packages = ['sabnzbd', 'sabnzbd.utils', 'sabnzbd.utils.multiauth'],
      platforms = ['posix'],
      license = 'GNU General Public License 2 (GPL2)',
      data_files = PairList(data)

)


if target == 'binary':
    if not py2exe:
        print "Sorry, only works on Windows!"
        exit(1)

    sys.argv[1] = 'py2exe'
    program = [ {'script' : 'SABnzbd.py', 'icon_resources' : [(0, "sabnzbd.ico")] } ]
    options['options'] = {"py2exe": {"bundle_files": 3, "packages": "email,xml,cherrypy.filters,Cheetah", "optimize": 2, "compressed": 0}}
    options['zipfile'] = 'lib/sabnzbd.zip'

    # Generate the console-app
    options['console'] = program
    setup(**options)
    try:
        if os.path.exists("dist/%s" % Win32ConsoleName):
            os.remove("dist/%s" % Win32ConsoleName)
        os.rename("dist/%s" % Win32WindowName, "dist/%s" % Win32ConsoleName)
    except:
        print "Cannot create dist/%s" % Win32ConsoleName
        exit(1)

    # Make sure that the root files are DOS format
    for file in options['data_files'][0][1]:
        os.system("unix2dos --safe dist/%s" % file)
    os.remove('dist/Sample-PostProc.sh')

    # Generate the windowed-app (skip datafiles now)
    del options['console']
    del options['data_files']
    options['windows'] = program
    setup(**options)

    os.system('del dist\*.ini >nul 2>&1')
    os.system('"c:\Program Files\NSIS\makensis.exe" /v3 /DSAB_PRODUCT=%s /DSAB_FILE=%s NSIS_Installer.nsi' % \
              (release, fileIns))


    os.system('if exist %s del /q %s' % (fileBin, fileBin))
    os.rename('dist', prod)
    os.system('zip -9 -r -X %s %s' % (fileBin, prod))
    os.rename(prod, 'dist')
    os.system(SvnRevert)

elif target == 'source':
    # Prepare Source distribution package.
    # Make sure all source files are Unix format
    import shutil

    root = 'srcdist'
    root = os.path.normpath(os.path.abspath(root))
    if not os.path.exists(root):
        os.mkdir(root)

    # Copy the data files
    for set in options['data_files']:
        dest, src = set
        ndir = root + '/' + dest
        ndir = os.path.normpath(os.path.abspath(ndir))
        if not os.path.exists(ndir):
            os.makedirs(ndir)
        for file in src:
            shutil.copy2(file, ndir)
            front, ext = os.path.splitext(file)
            base = os.path.basename(file)
            if ext.lower() in ('.py', '.pl', '.txt', '.html', '.css', '.tmpl', ''):
                os.system("dos2unix --safe %s" % ndir + '/' + base)

    # Copy the script files
    for name in options['scripts']:
        file = os.path.normpath(os.path.abspath(name))
        shutil.copy2(file, root)
        base = os.path.basename(file)
        fullname = os.path.normpath(os.path.abspath(root + '/' + base))
        os.system("dos2unix --safe %s" % fullname)

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
            if ext.lower() not in ('.pyc', '.pyo', '.bak'):
                shutil.copy2(file, dest)
                os.system("dos2unix --safe %s" % fullname)

    # Install CherryPy
    os.chdir(root)
    os.system("unzip -o ../CherryPy-2.3.0.zip")
    os.chdir('..')

    # Prepare the TAR.GZ pacakge
    CreateTar('srcdist', fileSrc, prod)

    # Prepare the ZIP for W32 package
    os.rename('srcdist', prod)
    os.system('if exist %s del /q %s' % (fileWSr, fileWSr))
    # First the text files (unix-->dos)
    os.system('zip -9 -r -X -l %s %s -x */win/* */images/* *licenses/Python*' % (fileWSr, prod))
    # Second the binary files
    os.system('zip -9 -r -X %s %s -i */win/* */images/*' % (fileWSr, prod))
    os.rename(prod, 'srcdist')

    os.system(SvnRevert)
else:
    print 'Usage: setup.py binary|source'

