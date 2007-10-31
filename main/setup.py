#!/usr/bin/env python

import sabnzbd
from distutils.core import setup

# py2exe usage: python setup.py py2exe

try:
    import py2exe
    import glob
except ImportError:
    py2exe = None

options = dict(
    name = 'SABnzbd',
      version = sabnzbd.__version__,
      url = 'http://sourceforge.net/projects/sabnzbd',
      author = 'Gregor Kaufmann & The ShyPike',
      author_email = 'shypike@users.sourceforge.net',
      description = 'SABnzbd ' + str(sabnzbd.__version__),
      scripts = ['SABnzbd.py'],
      packages = ['sabnzbd', 'sabnzbd.utils', 'sabnzbd.utils.multiauth'],
      platforms = ['posix'],
      license = 'GNU General Public License 2 (GPL2)',
      data_files = [('share/doc/SABnzbd-' + sabnzbd.__version__,
                     ['SABnzbd.ini.sample', 'README.txt', 'LICENSE.txt',
                      'TODO.txt', 'CHANGELOG.txt', 'UPGRADE.txt']),
                    ('share/SABnzbd-' + sabnzbd.__version__ + '/templates',
                             ['templates/default.css', 'templates/history.tmpl',
                              'templates/main.tmpl',
			      'templates/connection_info.tmpl',
                              'templates/config.tmpl',
			      'templates/queue.tmpl',
                              'templates/nzo.tmpl',
                              'templates/config_directories.tmpl',
                              'templates/config_general.tmpl',
                              'templates/config_server.tmpl',
                              'templates/config_switches.tmpl',
                              'templates/config_scheduling.tmpl',
                              'templates/config_rss.tmpl',
                              'templates/static/placeholder.txt',
							  'templates/static/favicon.ico']),
                    ('share/SABnzbd-' + sabnzbd.__version__ + '/templates/static',
                              ['templates/static/placeholder.txt', 'templates/static/placeholder.txt'])])

if py2exe:
    options['data_files'] = [
          ('', ['SABnzbd.ini', 'README.txt', 'LICENSE.txt', 'TODO.txt', 'CHANGELOG.txt', 'UPGRADE.txt']), 
          ('templates', glob.glob("templates/*.tmpl")),
          ('templates', ['templates/default.css']),
          ('templates/static', glob.glob('templates/static/*.ico')),
          ('downloads', []),
          ('downloads/Incomplete', []),
          ('downloads/Complete', []),
          ('NZB_backups', []),
          ('NZB_blackhole', []),
          ('logs', []),
          ('cache', []),
          ('par2', ['win/par2/COPYING', 'win/par2/par2.exe', 'win/par2/README', 'win/par2/src/par2cmdline-0.4.tar.gz']),
          ('unrar', ['win/unrar/license.txt', 'win/unrar/UnRAR.exe']),
          ('unzip', ['win/unzip/LICENSE', 'win/unzip/README', 'win/unzip/README.NT', 'win/unzip/unzip.exe', 'win/unzip/WHERE']),
          ('email', glob.glob("win/email/*.*"))
        ]
    options['console'] = ['SABnzbd.py']
    options['options'] = {"py2exe": {"bundle_files": 1, "packages": "xml,cherrypy.filters,Cheetah", "optimize": 2, "compressed": 0}}
    

setup(**options)
