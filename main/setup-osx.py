#!/usr/bin/env python

import sabnzbd
from distutils.core import setup

# OSX py2app usage: python setup.py py2app

try:
	import py2app
	from setuptools import setup
	import glob
except ImportError:
	py2app = None

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
	license = 'GNU General Public License 2 (GPL2)')

if py2app:
	options['data_files'] = ['interfaces','osx/osx',('',glob.glob("osx/ressources/*"))]	      
	options['options'] = {'py2app': {'argv_emulation': True, 'iconfile': 'osx/ressources/sabnzbdplus.icns'}}
	options['app'] = ['SABnzbd.py']
	options['setup_requires'] = ['py2app']    

setup(**options)
