#!/usr/bin/python -OO
# -*- coding: utf-8 -*-
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

"""
sabnzbd.lang - Language support
"""

# This module should be the first non-standard import to
# be done at the top of the application's main file.
# This will ensure that the default language is available
# and the special functions are active.
#
# Required keywords for pygettext.py: -k T -k Ta -k TT
#
# The following pseudo-builtins are provided.
# T()   Unicode translation
# Ta()  Latin-1 translation
# Tx()  Unicode translation of an expression (not a literal string)
# TT()  Dummy translation, use to mark table entries for POT scanning


import gettext, __builtin__
import glob, os, operator, locale
# This module cannot import any application modules!!

__all__ = ['set_locale_info', 'set_language', 'list_languages']

_DOMAIN = ''        # Holds translation domain
_LOCALEDIR = ''     # Holds path to the translation base folder


def set_locale_info(domain, localedir):
    """ Setup the domain and localedir for translations
    """
    global _DOMAIN, _LOCALEDIR
    _DOMAIN = domain
    _LOCALEDIR = localedir


def set_language(language=''):
    """ Activate language, empty language will set default texts.
    """
    # 'codeset' will determine the output of lgettext
    lng = gettext.translation(_DOMAIN, _LOCALEDIR, [language], fallback=True, codeset='latin-1')

    # The unicode flag will make _() return Unicode
    lng.install(unicode=True, names=['lgettext'])
    __builtin__.__dict__['T'] = __builtin__.__dict__['_']           # Unicode
    __builtin__.__dict__['Ta'] = __builtin__.__dict__['lgettext']   # Latin-1
    __builtin__.__dict__['Tx'] = __builtin__.__dict__['_']          # Dynamic translation (unicode)
    __builtin__.__dict__['TT'] = lambda x:x                         # Use in text tables


def list_languages():
    """ Return sorted list of (lang-code, lang-string) pairs,
        representing the available languages.
        When any language file is found, the default tuple ('en', 'English')
        will be included. Otherwise an empty list is returned.
    """
    # Findst find all the MO files.
    # Each folder should also contain a dummy text file giving the language
    # Example:
    #   <localedir>/nl/LC_MESSAGES/SABnzbd.mo
    #   <localedir>/nl/LC_MESSAGES/Nederlands

    lst = []
    for path in glob.glob(os.path.join(_LOCALEDIR, '*')):
        if os.path.isdir(path) and not path.endswith('en'):
            lngname = os.path.basename(path)
            lng = locale.normalize(lngname)
            lng = lng[:lng.find('_')]
            language = LanguageTable.get(lng, (lng, lng))
            language = language[1].decode('utf-8').encode('latin-1')
            lst.append((lng, language))
    if lst:
        lst.append(('en', 'English'))
        return sorted(lst, key=operator.itemgetter(1))
    else:
        return lst


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
    'nb' : ('Norwegian Bokmål', 'Norsk bokmål'),
    'nn' : ('Norwegian Nynorsk', 'Norsk nynorsk'),
    'no' : ('Norwegian', 'Norsk'),
    'oc' : ('Occitan', 'Occitan'),
    'om' : ('Oromo', 'Afaan Oromoo'),
    'pl' : ('Polish', 'Polski'),
    'pt' : ('Portuguese', 'Português'),
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
    'es' : ('Spanish Castilian', 'Español, castellano'),
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

# Setup a safe null-translation
set_language()
