#!/usr/bin/python -OO
# Copyright 2010 The SABnzbd-Team <team@sabnzbd.org>
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

# Compile PO files to MO files

import glob
import os
import re
import sys
import gettext

PO_DIR = 'po/main'
POE_DIR = 'po/email'
PON_DIR = 'po/nsis'
MO_DIR = 'locale'
EMAIL_DIR = 'email'

MO_LOCALE = '/LC_MESSAGES'
DOMAIN = 'SABnzbd'
DOMAIN_E = 'SABemail'
DOMAIN_N = 'SABnsis'
LANG_MARKER = 'language.txt'
NSIS= 'NSIS_Installer.nsi'

LNG_TABLE = { # NSIS requires full English names for the languages
    'da' : 'DANISH',
    'de' : 'GERMAN',
    'fr' : 'FRENCH',
    'nl' : 'DUTCH',
    'no' : 'NORSE',
    'sv' : 'SWEDISH',
    'en' : ''
}

# Determine location of PyGetText tool
path, exe = os.path.split(sys.executable)
if os.name == 'nt':
    TOOL = os.path.join(path, r'Tools\i18n\msgfmt.py')
else:
    TOOL = os.path.join(path, 'msgfmt.py')
if not os.path.exists(TOOL):
    TOOL = 'msgfmt'


# Filter for retrieving readable language from PO file
RE_LANG = re.compile(r'"Language-Description:\s([^"]+)\\n')

def process_po_folder(domain, folder):
    """ Process each PO file in folder
    """
    for fname in glob.glob(os.path.join(folder, '*.po')):
        podir, basename = os.path.split(fname)
        name, ext = os.path.splitext(basename)
        mo_path = os.path.normpath('%s/%s%s' % (MO_DIR, name, MO_LOCALE))
        mo_name = '%s.mo' % domain
        if not os.path.exists(mo_path):
            os.makedirs(mo_path)

        # Create the MO file
        mo_file = os.path.join(mo_path, mo_name)
        print 'Compile %s' % mo_file
        os.system('%s -o %s %s' % (TOOL, mo_file, fname))

        # Determine language's pretty name
        language = ''
        fp = open(fname, 'r')
        for line in fp:
            m = RE_LANG.search(line)
            if m:
                language = m.group(1)
                break
        fp.close()

        # Create the readable name file
        if language:
            mo_file = os.path.join(mo_path, LANG_MARKER)
            fp = open(mo_file, 'wb')
            fp.write('%s\n' % language)
            fp.close()


def make_templates():
    """ Create email templates
    """
    if not os.path.exists('email'):
        os.makedirs('email')
    for path in glob.glob(os.path.join(MO_DIR, '*')):
        lng = os.path.split(path)[1]
        print 'Create email template for %s' % lng
        trans = gettext.translation(DOMAIN_E, MO_DIR, [lng], fallback=False, codeset='latin-1')
        # The unicode flag will make _() return Unicode
        trans.install(unicode=True, names=['lgettext'])

        src = open(EMAIL_DIR + '/email-en.tmpl', 'r')
        data = src.read().decode('utf-8')
        src.close()
        data = _(data).encode('utf-8')
        fp = open('email/email-%s.tmpl' % lng, 'wb')
        fp.write(data)
        fp.close()

        src = open(EMAIL_DIR + '/rss-en.tmpl', 'r')
        data = src.read().decode('utf-8')
        src.close()
        data = _(data).encode('utf-8')
        fp = open('email/rss-%s.tmpl' % lng, 'wb')
        fp.write(data)
        fp.close()
        mo_path = os.path.normpath('%s/%s%s/%s.mo' % (MO_DIR, path, MO_LOCALE, DOMAIN_E))
        if os.path.exists(mo_path):
            os.remove(mo_path)


def patch_nsis():
    """ Patch translation into the NSIS script
    """
    RE_NSIS = re.compile(r'^(\s*LangString\s+\w+\s+\$\{LANG_)(\w+)\}\s+(".*)', re.I)
    languages = [os.path.split(path)[1] for path in glob.glob(os.path.join(MO_DIR, '*'))]

    src = open(NSIS, 'r')
    new = []
    for line in src:
        m = RE_NSIS.search(line)
        if m:
            leader = m.group(1)
            langname = m.group(2).upper()
            text = m.group(3).strip('"\n')
            if langname == 'ENGLISH':
                # Write back old content
                new.append(line)
                # Replace silly $\ construction with just a \
                text = text.replace('$\\"', '"').replace('$\\', '\\')
                for lcode in languages:
                    lng = LNG_TABLE.get(lcode)
                    if lng:
                        trans = gettext.translation(DOMAIN_N, MO_DIR, [lcode], fallback=False, codeset='latin-1')
                        # The unicode flag will make _() return Unicode
                        trans.install(unicode=True, names=['lgettext'])
                        trans = lgettext(text)
                        trans = trans.replace('\\', '$\\').replace('"', '$\\"')
                        line = '%s%s "%s"\n' % (leader, lng, trans)
                        new.append(line)
                    elif lng is None:
                        print 'Warning: unsupported language %s, add to table in this script' % langname
        else:
            new.append(line)
    src.close()

    dst = open(NSIS, 'w')
    for line in new:
        dst.write(line)
    dst.close()


print 'Email MO files'
process_po_folder(DOMAIN_E, POE_DIR)

print 'NSIS MO file'
process_po_folder(DOMAIN_N, PON_DIR)

print 'Main program MO files'
process_po_folder(DOMAIN, PO_DIR)

print "Create email templates from MO files"
make_templates()

print "Patch NSIS script"
patch_nsis()

