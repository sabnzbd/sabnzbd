#!/usr/bin/env python

import sabnzbd
from distutils.core import setup

setup(name = 'SABnzbd',
      version = sabnzbd.__version__,
      url = 'http://sourceforge.net/projects/sabnzbd',
      author = 'Gregor Kaufmann',
      author_email = 'tdian@users.sourceforge.net',
      description = 'SABnzbd-' + str(sabnzbd.__version__),
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
                              'templates/static/placeholder.txt']),
                    ('share/SABnzbd-' + sabnzbd.__version__ + '/templates/static',
                              ['templates/static/placeholder.txt'])])
