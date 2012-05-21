#!/usr/bin/python -OO
# -*- coding: utf-8 -*-
# Copyright 2010-2012 The SABnzbd-Team <team@sabnzbd.org>
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

TOOL = 'msgfmt'
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

LanguageTable = {
    'aa' : ('Afar', 'Afaraf'),
    'af' : ('Afrikaans', 'Afrikaans'),
    'ak' : ('Akan', 'Akan'),
    'sq' : ('Albanian', 'Shqip'),
    'an' : ('Aragonese', 'Aragonés'),
    'ae' : ('Avestan', 'Avesta'),
    'ay' : ('Aymara', 'Aymararu'),
    'bm' : ('Bambara', 'Bamanankan'),
    'eu' : ('Basque', 'Euskara'),
    'bi' : ('Bislama', 'Bislama'),
    'bs' : ('Bosnian', 'Bosanskijezik'),
    'br' : ('Breton', 'Brezhoneg'),
    'ca' : ('Catalan', 'Català'),
    'ch' : ('Chamorro', 'Chamoru'),
    'kw' : ('Cornish', 'Kernewek'),
    'co' : ('Corsican', 'Corsu'),
    'hr' : ('Croatian', 'Hrvatski'),
    'cs' : ('Czech', 'Cesky, ceština'),
    'da' : ('Danish', 'Dansk'),
    'nl' : ('Dutch', 'Nederlands'),
    'en' : ('English', 'English'),
    'eo' : ('Esperanto', 'Esperanto'),
    'et' : ('Estonian', 'Eesti'),
    'fo' : ('Faroese', 'Føroyskt'),
    'fj' : ('Fijian', 'Vosa Vakaviti'),
    'fi' : ('Finnish', 'Suomi'),
    'fr' : ('French', 'Français'),
    'gl' : ('Galician', 'Galego'),
    'de' : ('German', 'Deutsch'),
    'hz' : ('Herero', 'Otjiherero'),
    'ho' : ('Hiri Motu', 'Hiri Motu'),
    'hu' : ('Hungarian', 'Magyar'),
    'id' : ('Indonesian', 'Bahasa Indonesia'),
    'ga' : ('Irish', 'Gaeilge'),
    'io' : ('Ido', 'Ido'),
    'is' : ('Icelandic', 'Íslenska'),
    'it' : ('Italian', 'Italiano'),
    'jv' : ('Javanese', 'BasaJawa'),
    'rw' : ('Kinyarwanda', 'Ikinyarwanda'),
    'kg' : ('Kongo', 'KiKongo'),
    'kj' : ('Kwanyama', 'Kuanyama'),
    'la' : ('Latin', 'Lingua latina'),
    'lb' : ('Luxembourgish', 'Lëtzebuergesch'),
    'lg' : ('Luganda', 'Luganda'),
    'li' : ('Limburgish', 'Limburgs'),
    'ln' : ('Lingala', 'Lingála'),
    'lt' : ('Lithuanian', 'Lietuviukalba'),
    'lv' : ('Latvian', 'Latviešuvaloda'),
    'gv' : ('Manx', 'Gaelg'),
    'mg' : ('Malagasy', 'Malagasy fiteny'),
    'mt' : ('Maltese', 'Malti'),
    'nb' : ('Norwegian', 'Norsk'),  # Bokmål
    'nn' : ('Norwegian', 'Norsk'),  # Nynorsk
    'no' : ('Norwegian', 'Norsk'),
    'oc' : ('Occitan', 'Occitan'),
    'om' : ('Oromo', 'Afaan Oromoo'),
    'pl' : ('Polish', 'Polski'),
    'pt' : ('Portuguese', 'Português'),
    'pt_BR' : ('PortugueseBR', 'Português, Brasil'), # NSIS uses "PortugueseBR"
    'rm' : ('Romansh', 'Rumantsch grischun'),
    'rn' : ('Kirundi', 'kiRundi'),
    'ro' : ('Romanian', 'Româna'),
    'sc' : ('Sardinian', 'Sardu'),
    'se' : ('Northern Sami', 'Davvisámegiella'),
    'sm' : ('Samoan', 'Gagana fa\'a Samoa'),
    'gd' : ('Gaelic', 'Gàidhlig'),
    'sn' : ('Shona', 'Chi Shona'),
    'sk' : ('Slovak', 'Slovencina'),
    'sl' : ('Slovene', 'Slovenšcina'),
    'st' : ('Southern Sotho', 'Sesotho'),
    'es' : ('Spanish', 'Español, castellano'), # NSIS cannot handle "Spanish Castilian"
    'su' : ('Sundanese', 'Basa Sunda'),
    'sw' : ('Swahili', 'Kiswahili'),
    'ss' : ('Swati', 'SiSwati'),
    'sv' : ('Swedish', 'Svenska'),
    'tn' : ('Tswana', 'Setswana'),
    'to' : ('Tonga (Tonga Islands)', 'faka Tonga'),
    'tr' : ('Turkish', 'Türkçe'),
    'ts' : ('Tsonga', 'Xitsonga'),
    'tw' : ('Twi', 'Twi'),
    'ty' : ('Tahitian', 'Reo Tahiti'),
    'wa' : ('Walloon', 'Walon'),
    'cy' : ('Welsh', 'Cymraeg'),
    'wo' : ('Wolof', 'Wollof'),
    'fy' : ('Western Frisian', 'Frysk'),
    'xh' : ('Xhosa', 'isi Xhosa'),
    'yo' : ('Yoruba', 'Yorùbá'),
    'zu' : ('Zulu', 'isi Zulu'),
}

# Filter for retrieving readable language from PO file
RE_LANG = re.compile(r'"Language-Description:\s([^"]+)\\n')

def process_po_folder(domain, folder, extra=''):
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
        ret = os.system('%s %s -o "%s" "%s"' % (TOOL, extra, mo_file, fname))
        if ret != 0:
            print '\nMissing %s. Please install this package first.' % TOOL
            exit(1)

def remove_mo_files():
    """ Remove MO files in locale
    """
    for root, dirs, files in os.walk(MO_DIR, topdown=False):
        for f in files:
            if not f.startswith(DOMAIN):
                os.remove(os.path.join(root, f))

def translate_tmpl(prefix, lng):
    """ Translate template 'prefix' into language 'lng' """
    src = open(EMAIL_DIR + '/%s-en.tmpl' % prefix, 'r')
    data = src.read().decode('utf-8')
    src.close()
    data = _(data).encode('utf-8')
    fp = open('email/%s-%s.tmpl' % (prefix, lng), 'wb')
    if not (-1 < data.find('UTF-8') < 30):
        fp.write('#encoding UTF-8\n')
    fp.write(data)
    fp.close()


def make_templates():
    """ Create email templates
    """
    if not os.path.exists('email'):
        os.makedirs('email')
    for path in glob.glob(os.path.join(MO_DIR, '*')):
        lng = os.path.split(path)[1]
        if lng != 'en':
            print 'Create email template for %s' % lng
            trans = gettext.translation(DOMAIN_E, MO_DIR, [lng], fallback=False, codeset='latin-1')
            # The unicode flag will make _() return Unicode
            trans.install(unicode=True, names=['lgettext'])

            translate_tmpl('email', lng)
            translate_tmpl('rss', lng)
            translate_tmpl('badfetch', lng)

            mo_path = os.path.normpath('%s/%s%s/%s.mo' % (MO_DIR, path, MO_LOCALE, DOMAIN_E))
            if os.path.exists(mo_path):
                os.remove(mo_path)


# Convert Romanian PX files to Latin1 PO files
ro_table = {
    u"\u015f" : u"s", # ș
    u"\u015e" : u"S", # Ș
    u"\u0163" : u"t", # ț
    u"\u0162" : u"T", # Ț
    u"\u0103" : u"ã", # ă
    u"\u0102" : u"Ã", # Ă
    u'\u021b' : u"t", # ț
    u'\u0218' : u"S", # Ș
    u'\u0219' : u"s"  # ș
}

# Convert Polish PX files to Latin1 PO files
pl_table = {
    u"\u0104" : u"A", # Ą
    u"\u0106" : u"C", # Ć
    u"\u0118" : u"E", # Ę
    u"\u0141" : u"L", # Ł
    u"\u013B" : u"L", # Ł
    u"\u0143" : u"N", # Ń
    #u"\u00D3" : u"O", # Ó
    u"\u015A" : u"S", # Ś
    u"\u0179" : u"Z", # Ź
    u"\u017B" : u"Z", # Ż
    u"\u0105" : u"a", # ą
    u"\u0107" : u"c", # ć
    u"\u0119" : u"e", # ę
    u"\u0142" : u"l", # ł
    u"\u0144" : u"n", # ń
    #u"\u00F3" : u"o", # ó
    u"\u015B" : u"s", # ś
    u"\u017A" : u"z", # ź
    u"\u017C" : u"z"  # ż
}

def fix_ro():
    """ Convert ro.px files to ro.po files with only Latin1
    """
    for section in ('main', 'email', 'nsis'):
        f = open('po/%s/ro.px' % section, 'rb')
        data = f.read().decode('utf-8')
        f.close()

        for ch in ro_table:
            data = data.replace(ch, ro_table[ch])

        f = open('po/%s/ro.po' % section, 'wb')
        f.write(data.encode('utf-8'))
        f.close()
        try:
            lnum = 0
            for line in data.split('\n'):
                lnum += 1
                line.encode('latin-1')
        except:
            print line.encode('utf-8')
            print 'WARNING: line %d in file po/%s/ro.po is not Latin-1' % (lnum, section)
            exit(1)

def fix_pl():
    """ Convert pl.px files to pl.po files with only Latin1
    """
    for section in ('main', 'email', 'nsis'):
        f = open('po/%s/pl.px' % section, 'rb')
        data = f.read().decode('utf-8')
        f.close()

        for ch in pl_table:
            data = data.replace(ch, pl_table[ch])

        f = open('po/%s/pl.po' % section, 'wb')
        f.write(data.encode('utf-8'))
        f.close()
        try:
            lnum = 0
            for line in data.split('\n'):
                lnum += 1
                line.encode('latin-1')
        except:
            print line.encode('utf-8')
            print 'WARNING: line %d in file po/%s/pl.po is not Latin-1' % (lnum, section)
            exit(1)


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
                    lng = LanguageTable.get(lcode)
                    if lng and lcode != 'en':
                        lng = lng[0].decode('utf-8').encode('latin-1').upper()
                        trans = gettext.translation(DOMAIN_N, MO_DIR, [lcode], fallback=False, codeset='latin-1')
                        # The unicode flag will make _() return Unicode
                        trans.install(unicode=True, names=['lgettext'])
                        trans = lgettext(text)
                        trans = trans.replace('\r', '').replace('\n', '\\r\\n')
                        trans = trans.replace('\\', '$\\').replace('"', '$\\"')
                        line = '%s%s} "%s"\n' % (leader, lng, trans)
                        new.append(line)
                    elif lng is None:
                        print 'Warning: unsupported language %s (%s), add to table in this script' % (langname, lcode)
        else:
            new.append(line)
    src.close()

    dst = open(NSIS+'.tmp', 'w')
    for line in new:
        dst.write(line)
    dst.close()


# Determine location of MsgFmt tool
path, py = os.path.split(sys.argv[0])
tl = os.path.abspath(os.path.normpath(os.path.join(path, 'msgfmt.py')))
if os.path.exists(tl):
    if os.name == 'nt':
        TOOL = 'python "%s"' % tl
    else:
        TOOL = '"%s"' % tl

# Fix up Romanian and Polish texts
fix_ro()
fix_pl()

if len(sys.argv) > 1 and sys.argv[1] == 'all':
    print 'NSIS MO file'
    process_po_folder(DOMAIN_N, PON_DIR)

    print "Patch NSIS script"
    patch_nsis()

print 'Email MO files'
process_po_folder(DOMAIN_E, POE_DIR)

print "Create email templates from MO files"
make_templates()


print 'Main program MO files'
# -n option added to remove all newlines from the translations
process_po_folder(DOMAIN, PO_DIR, '-n')

print "Remove temporary templates"
remove_mo_files()
