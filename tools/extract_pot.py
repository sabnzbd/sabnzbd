#!/usr/bin/python -OO
# Copyright 2011-2015 The SABnzbd-Team <team@sabnzbd.org>
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
extract_pot - Extract translatable strings from all PY files
"""

import os
import sys
import re

# Import version.py without the sabnzbd overhead
f = open('sabnzbd/version.py')
code = f.read()
f.close()
exec(code)

# Fixed information for the POT header
HEADER = r'''#
# SABnzbd Translation Template file __TYPE__
# Copyright 2011-2015 The SABnzbd-Team
#   team@sabnzbd.org
#
msgid ""
msgstr ""
"Project-Id-Version: SABnzbd-%s\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\n"
"Last-Translator: shypike@sabnzbd.org\n"
"Language-Team: LANGUAGE <LL@li.org>\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=ASCII\n"
"Content-Transfer-Encoding: 7bit\n"
''' % __version__

PO_DIR = 'po/main'
POE_DIR = 'po/email'
PON_DIR = 'po/nsis'
EMAIL_DIR = 'email'
DOMAIN = 'SABnzbd'
DOMAIN_EMAIL = 'SABemail'
DOMAIN_NSIS = 'SABnsis'
PARMS = '-d %s -p %s -k T -k Ta -k TT -o %s.pot.tmp' % (DOMAIN, PO_DIR, DOMAIN)
FILES = 'SABnzbd.py SABHelper.py SABnzbdDelegate.py sabnzbd/*.py sabnzbd/utils/*.py'

FILE_CACHE = {}


def get_a_line(src, number):
    """ Retrieve line 'number' from file 'src' with caching """
    global FILE_CACHE
    if src not in FILE_CACHE:
        FILE_CACHE[src] = []
        for line in open(src, 'r'):
            FILE_CACHE[src].append(line)
    try:
        return FILE_CACHE[src][number - 1]
    except:
        return ''


RE_LINE = re.compile(r'\s*([^: \t]+)\s*:\s*(\d+)')
RE_CONTEXT = re.compile(r'#:\s*(.*)$')


def get_context(line):
    """ Read context info from source file and append to line.
        input: "#: filepath.py:123 filepath2.py:456"
        output: "#: filepath.py:123 # [context info] # filepath2.py:456 # [context info 2]"
    """
    if not line.startswith('#:'):
        return line

    newlines = []
    for item in line[2:].strip('\r\n').split():
        m = RE_LINE.search(item)
        if m:
            src = m.group(1)
            number = m.group(2)
        else:
            newlines.append(item)
            continue

        srcline = get_a_line(src, int(number)).strip('\r\n')
        context = ''
        m = RE_CONTEXT.search(srcline)
        if m:
            context = m.group(1)
        else:
            if 'logging.error(' in srcline:
                context = 'Error message'
            elif 'logging.warning(' in srcline:
                context = 'Warning message'
        if context:
            newlines.append('%s [%s]' % (item, context))
        else:
            newlines.append(item)

    return '#: ' + ' # '.join(newlines) + '\n'


def add_tmpl_to_pot(prefix, dst):
    """ Append english template to open POT file 'dst' """
    src = open(EMAIL_DIR + '/%s-en.tmpl' % prefix, 'r')
    dst.write('#: email/%s.tmpl:1\n' % prefix)
    dst.write('msgid ""\n')
    for line in src:
        dst.write('"%s"\n' % line.replace('\n', '\\n').replace('"', '\\"'))
    dst.write('msgstr ""\n\n')
    src.close()


if not os.path.exists(PO_DIR):
    os.makedirs(PO_DIR)

# Determine location of PyGetText tool
path, exe = os.path.split(sys.executable)
if os.name == 'nt':
    TOOL = os.path.join(path, r'Tools\i18n\pygettext.py')
else:
    TOOL = os.path.join(path, 'pygettext.py')
if not os.path.exists(TOOL):
    TOOL = 'pygettext'


cmd = '%s %s %s' % (TOOL, PARMS, FILES)
print 'Create POT file'
# print cmd
os.system(cmd)

print 'Post-process the POT file'
src = open('%s/%s.pot.tmp' % (PO_DIR, DOMAIN), 'r')
dst = open('%s/%s.pot' % (PO_DIR, DOMAIN), 'wb')
dst.write(HEADER.replace('__TYPE__', 'MAIN'))
header = True

for line in src:
    if line.startswith('#:'):
        line = line.replace('\\', '/')
        if header:
            dst.write('\n\n')
        header = False
    if header:
        if not ('"POT-Creation-Date:' in line or '"Generated-By:' in line):
            continue
    elif line.startswith('#:'):
        line = get_context(line)
    dst.write(line)

src.close()
dst.close()
os.remove('%s/%s.pot.tmp' % (PO_DIR, DOMAIN))


print 'Create the email POT file'
if not os.path.exists(POE_DIR):
    os.makedirs(POE_DIR)
dst = open(os.path.join(POE_DIR, DOMAIN_EMAIL + '.pot'), 'wb')
dst.write(HEADER.replace('__TYPE__', 'EMAIL'))
add_tmpl_to_pot('email', dst)
add_tmpl_to_pot('rss', dst)
add_tmpl_to_pot('badfetch', dst)
dst.close()


# Create the NSIS POT file
NSIS = 'NSIS_Installer.nsi'
RE_NSIS = re.compile(r'LangString\s+\w+\s+\$\{LANG_ENGLISH\}\s+(".*)', re.I)

print 'Creating the NSIS POT file'
if not os.path.exists(PON_DIR):
    os.makedirs(PON_DIR)
src = open(NSIS, 'r')
dst = open(os.path.join(PON_DIR, DOMAIN_NSIS + '.pot'), 'wb')
dst.write(HEADER.replace('__TYPE__', 'NSIS'))
dst.write('\n')
count = 0
for line in src:
    count += 1
    m = RE_NSIS.search(line)
    if m and 'MsgLangCode' not in line:
        dst.write('#: %s:%s\n' % (NSIS, count))
        text = m.group(1).replace('$\\"', '\\"').replace('$\\', '\\\\')
        dst.write('msgid %s\n' % text)
        dst.write('msgstr ""\n\n')
dst.close()
src.close()
