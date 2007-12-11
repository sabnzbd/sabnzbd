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
      url = 'http://sourceforge.net/projects/sabnzbdplus',
      author = 'The ShyPike & Gregor Kaufmann',
      author_email = 'shypike@users.sourceforge.net',
      description = 'SABnzbd ' + str(sabnzbd.__version__),
      scripts = ['SABnzbd.py'],
      packages = ['sabnzbd', 'sabnzbd.utils', 'sabnzbd.utils.multiauth'],
      platforms = ['posix'],
      license = 'GNU General Public License 2 (GPL2)',
      data_files = [('share/doc/SABnzbd-' + sabnzbd.__version__,
                     ['README.txt', 'LICENSE.txt', 'CHANGELOG.txt', 'Sample-PostProc.sh', 'Sample-PostProc.cmd', 'PKG-INFO']),
                    ('share/SABnzbd-' + sabnzbd.__version__ + '/templates',
                             ['interface/Default/README.TXT',
                              'interface/Default/templates/default.css',
                              'interface/Default/templates/history.tmpl',
                              'interface/Default/templates/main.tmpl',
                              'interface/Default/templates/connection_info.tmpl',
                              'interface/Default/templates/config.tmpl',
                              'interface/Default/templates/queue.tmpl',
                              'interface/Default/templates/nzo.tmpl',
                              'interface/Default/templates/config_directories.tmpl',
                              'interface/Default/templates/config_general.tmpl',
                              'interface/Default/templates/config_server.tmpl',
                              'interface/Default/templates/config_switches.tmpl',
                              'interface/Default/templates/config_scheduling.tmpl',
                              'interface/Default/templates/config_rss.tmpl',
                              'interface/Default/templates/static/placeholder.txt',
                              'interface/Default/templates/static/stylesheets/default.css',
                              'interface/Default/templates/static/images/favicon.ico']),
                    ('share/SABnzbd-' + sabnzbd.__version__ + '/templates/static',
                              ['templates/static/placeholder.txt', 'templates/static/placeholder.txt'])])

if py2exe:
    options['data_files'] = [
          ('', ['README.txt', 'LICENSE.txt', 'CHANGELOG.txt', 'Sample-PostProc.sh', 'Sample-PostProc.cmd', 'PKG-INFO']), 
          ('interfaces/Default/README.TXT', ['interfaces/Default/README.TXT']),
          ('interfaces/Default/templates', glob.glob("interfaces/Default/templates/*.tmpl")),
          ('interfaces/Default/templates/static/stylesheets', ['interfaces/Default/templates/static/stylesheets/default.css']),
          ('interfaces/Default/templates/static/images', glob.glob('interfaces/Default/templates/static/images/*.ico')),

          ('interfaces/NOVA_0.3.2', glob.glob("interfaces/NOVA_0.3.2/*.*")),
          ('interfaces/NOVA_0.3.2/templates', glob.glob("interfaces/NOVA_0.3.2/templates/*.*")),
          ('interfaces/NOVA_0.3.2/templates/static', glob.glob("interfaces/NOVA_0.3.2/templates/static/*.*")),
          ('interfaces/NOVA_0.3.2/templates/static/css', glob.glob("interfaces/NOVA_0.3.2/templates/static/css/*.*")),
          ('interfaces/NOVA_0.3.2/templates/static/images', glob.glob("interfaces/NOVA_0.3.2/templates/static/images/*.*")),
          ('interfaces/NOVA_0.3.2/templates/static/js', glob.glob("interfaces/NOVA_0.3.2/templates/static/js/*.*")),

          ('interfaces/NOVA_0.4.5', glob.glob("interfaces/NOVA_0.4.5/*.*")),
          ('interfaces/NOVA_0.4.5/templates', glob.glob("interfaces/NOVA_0.4.5/templates/*.*")),
          ('interfaces/NOVA_0.4.5/templates/static', glob.glob("interfaces/NOVA_0.4.5/templates/static/*.*")),
          ('interfaces/NOVA_0.4.5/templates/static/images', glob.glob("interfaces/NOVA_0.4.5/templates/static/images/*.*")),
          ('interfaces/NOVA_0.4.5/templates/static/javascripts', glob.glob("interfaces/NOVA_0.4.5/templates/static/javascripts/*.*")),
          ('interfaces/NOVA_0.4.5/templates/static/stylesheets', glob.glob("interfaces/NOVA_0.4.5/templates/static/stylesheets/*.*")),

          ('interfaces/Plush', glob.glob("interfaces/Plush/*.*")),
          ('interfaces/Plush/templates', glob.glob("interfaces/Plush/templates/*.*")),
          ('interfaces/Plush/templates/static', glob.glob("interfaces/Plush/templates/static/*.*")),
          ('interfaces/Plush/templates/static/images', glob.glob("interfaces/Plush/templates/static/images/*.*")),
          ('interfaces/Plush/templates/static/javascripts', glob.glob("interfaces/Plush/templates/static/javascripts/*.*")),
          ('interfaces/Plush/templates/static/stylesheets', glob.glob("interfaces/Plush/templates/static/stylesheets/*.*")),

          ('win/par2', ['win/par2/COPYING', 'win/par2/par2.exe', 'win/par2/README', 'win/par2/src/par2cmdline-0.4.tar.gz']),
          ('win/unrar', ['win/unrar/license.txt', 'win/unrar/UnRAR.exe']),
          ('win/unzip', ['win/unzip/LICENSE', 'win/unzip/README', 'win/unzip/README.NT', 'win/unzip/unzip.exe', 'win/unzip/WHERE']),
          ('win/email', glob.glob("win/email/*.*"))
        ]
    options['console'] = ['SABnzbd.py']
    options['options'] = {"py2exe": {"bundle_files": 1, "packages": "xml,cherrypy.filters,Cheetah", "optimize": 2, "compressed": 0}}
    

setup(**options)
