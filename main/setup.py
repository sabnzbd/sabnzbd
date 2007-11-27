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
                     ['README.txt', 'LICENSE.txt', 'CHANGELOG.txt']),
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
                              'templates/static/stylesheets/default.css',
                              'templates/static/images/favicon.ico']),
                    ('share/SABnzbd-' + sabnzbd.__version__ + '/templates/static',
                              ['templates/static/placeholder.txt', 'templates/static/placeholder.txt'])])

if py2exe:
    options['data_files'] = [
          ('', ['README.txt', 'LICENSE.txt', 'CHANGELOG.txt']), 
          ('templates', glob.glob("templates/*.tmpl")),
          ('templates/static/stylesheets', ['templates/static/stylesheets/default.css']),
          ('templates/static/images', glob.glob('templates/static/images/*.ico')),
          ('NOVA_0.3.2', glob.glob("NOVA_0.3.2/*.*")),
          ('NOVA_0.3.2/templates', glob.glob("NOVA_0.3.2/templates/*.*")),
          ('NOVA_0.3.2/templates/static', glob.glob("NOVA_0.3.2/templates/static/*.*")),
          ('NOVA_0.3.2/templates/static/css', glob.glob("NOVA_0.3.2/templates/static/css/*.*")),
          ('NOVA_0.3.2/templates/static/images', glob.glob("NOVA_0.3.2/templates/static/images/*.*")),
          ('NOVA_0.3.2/templates/static/js', glob.glob("NOVA_0.3.2/templates/static/js/*.*")),
          ('NOVA_0.4.5', glob.glob("NOVA_0.4.5/*.*")),
          ('NOVA_0.4.5/templates', glob.glob("NOVA_0.4.5/templates/*.*")),
          ('NOVA_0.4.5/templates/static', glob.glob("NOVA_0.4.5/templates/static/*.*")),
          ('NOVA_0.4.5/templates/static/images', glob.glob("NOVA_0.4.5/templates/static/images/*.*")),
          ('NOVA_0.4.5/templates/static/javascripts', glob.glob("NOVA_0.4.5/templates/static/javascripts/*.*")),
          ('NOVA_0.4.5/templates/static/stylesheets', glob.glob("NOVA_0.4.5/templates/static/stylesheets/*.*")),
          ('win/par2', ['win/par2/COPYING', 'win/par2/par2.exe', 'win/par2/README', 'win/par2/src/par2cmdline-0.4.tar.gz']),
          ('win/unrar', ['win/unrar/license.txt', 'win/unrar/UnRAR.exe']),
          ('win/unzip', ['win/unzip/LICENSE', 'win/unzip/README', 'win/unzip/README.NT', 'win/unzip/unzip.exe', 'win/unzip/WHERE']),
          ('win/email', glob.glob("win/email/*.*"))
        ]
    options['console'] = ['SABnzbd.py']
    options['options'] = {"py2exe": {"bundle_files": 1, "packages": "xml,cherrypy.filters,Cheetah", "optimize": 2, "compressed": 0}}
    

setup(**options)
