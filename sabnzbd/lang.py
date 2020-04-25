#!/usr/bin/python3 -OO
# -*- coding: utf-8 -*-
# Copyright 2011-2020 The SABnzbd-Team <team@sabnzbd.org>
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
# This module cannot import any application modules!!
#
# Required keywords for pygettext.py: -k T -k TT
#
# The following pseudo-builtins are provided.
# T()   Unicode translation
# TT()  Dummy translation, use to mark table entries for POT scanning

import gettext
import builtins
import glob
import os
import locale

__all__ = ["set_locale_info", "set_language", "list_languages"]

_DOMAIN = ""  # Holds translation domain
_LOCALEDIR = ""  # Holds path to the translation base folder


def set_locale_info(domain, localedir):
    """ Setup the domain and localedir for translations """
    global _DOMAIN, _LOCALEDIR
    _DOMAIN = domain
    _LOCALEDIR = localedir


def set_language(language=None):
    """ Activate language, empty language will set default texts. """
    if not language:
        language = ""

    lng = gettext.translation(_DOMAIN, _LOCALEDIR, [language], fallback=True)
    builtins.__dict__["T"] = lng.gettext
    builtins.__dict__["TT"] = lambda x: str(x)  # Use in text tables


def list_languages():
    """ Return sorted list of (lang-code, lang-string) pairs,
        representing the available languages.
        When any language file is found, the default tuple ('en', 'English')
        will be included. Otherwise an empty list is returned.
    """
    # Find all the MO files.
    lst = []
    for path in glob.glob(os.path.join(_LOCALEDIR, "*")):
        if os.path.isdir(path) and not path.endswith("en"):
            lngname = os.path.basename(path)
            lng = locale.normalize(lngname)
            # Example: 'pt_BR.ISO8859-1'
            lng_short = lng[: lng.find("_")]
            lng_full = lng[: lng.find(".")]
            # First try full language string, e.g. 'pt_BR'
            language = LanguageTable.get(lng_full, (lng_full, lng_full))
            if language[0] == lng_full:
                # Full language string not defined: try short form, e.g. 'pt'
                language = LanguageTable.get(lng_short, (lng_short, lng_short))
                lng = lng_short
            else:
                lng = lng_full
            language = language[1]
            lst.append((lng, language))

    lst.append(("en", "English"))
    lst.sort()
    return lst


LanguageTable = {
    "aa": ("Afar", "Afaraf", 0),
    "af": ("Afrikaans", "Afrikaans", 0),
    "ak": ("Akan", "Akan", 0),
    "sq": ("Albanian", "Shqip", 0),
    "an": ("Aragonese", "Aragonés", 0),
    "ae": ("Avestan", "Avesta", 0),
    "ay": ("Aymara", "Aymararu", 0),
    "bm": ("Bambara", "Bamanankan", 0),
    "eu": ("Basque", "Euskara", 0),
    "bi": ("Bislama", "Bislama", 0),
    "bs": ("Bosnian", "Bosanskijezik", 0),
    "br": ("Breton", "Brezhoneg", 0),
    "ca": ("Catalan", "Català", 0),
    "ch": ("Chamorro", "Chamoru", 0),
    "kw": ("Cornish", "Kernewek", 0),
    "co": ("Corsican", "Corsu", 0),
    "hr": ("Croatian", "Hrvatski", 0),
    "cs": ("Czech", "Cesky, ceština", 0),
    "da": ("Danish", "Dansk", 0),
    "nl": ("Dutch", "Nederlands", 0),
    "en": ("English", "English", 0),
    "eo": ("Esperanto", "Esperanto", 0),
    "et": ("Estonian", "Eesti", 0),
    "fo": ("Faroese", "Føroyskt", 0),
    "fj": ("Fijian", "Vosa Vakaviti", 0),
    "fi": ("Finnish", "Suomi", 0),
    "fr": ("French", "Français", 0),
    "gl": ("Galician", "Galego", 0),
    "de": ("German", "Deutsch", 0),
    "he": ("Hebrew", "עִבְרִית‎", 1255),
    "hz": ("Herero", "Otjiherero", 0),
    "ho": ("Hiri Motu", "Hiri Motu", 0),
    "hu": ("Hungarian", "Magyar", 0),
    "id": ("Indonesian", "Bahasa Indonesia", 0),
    "ga": ("Irish", "Gaeilge", 0),
    "io": ("Ido", "Ido", 0),
    "is": ("Icelandic", "Íslenska", 0),
    "it": ("Italian", "Italiano", 0),
    "jv": ("Javanese", "BasaJawa", 0),
    "rw": ("Kinyarwanda", "Ikinyarwanda", 0),
    "kg": ("Kongo", "KiKongo", 0),
    "kj": ("Kwanyama", "Kuanyama", 0),
    "la": ("Latin", "Lingua latina", 0),
    "lb": ("Luxembourgish", "Lëtzebuergesch", 0),
    "lg": ("Luganda", "Luganda", 0),
    "li": ("Limburgish", "Limburgs", 0),
    "ln": ("Lingala", "Lingála", 0),
    "lt": ("Lithuanian", "Lietuviukalba", 0),
    "lv": ("Latvian", "Latviešuvaloda", 0),
    "gv": ("Manx", "Gaelg", 0),
    "mg": ("Malagasy", "Malagasy fiteny", 0),
    "mt": ("Maltese", "Malti", 0),
    "nb": ("Norwegian Bokmål", "Norsk bokmål", 0),
    "nn": ("Norwegian Nynorsk", "Norsk nynorsk", 0),
    "no": ("Norwegian", "Norsk", 0),
    "oc": ("Occitan", "Occitan", 0),
    "om": ("Oromo", "Afaan Oromoo", 0),
    "pl": ("Polish", "Polski", 0),
    "pt": ("Portuguese", "Português", 0),
    "pt_BR": ("Portuguese Brazillian", "Português Brasileiro", 0),
    "rm": ("Romansh", "Rumantsch grischun", 0),
    "rn": ("Kirundi", "kiRundi", 0),
    "ro": ("Romanian", "Româna", 1250),
    "sc": ("Sardinian", "Sardu", 0),
    "se": ("Northern Sami", "Davvisámegiella", 0),
    "sm": ("Samoan", "Gagana fa'a Samoa", 0),
    "gd": ("Gaelic", "Gàidhlig", 0),
    "ru": ("Russian", "русский язык", 1251),
    "sr": ("Serbian", "српски", 1251),
    "sn": ("Shona", "Chi Shona", 0),
    "sk": ("Slovak", "Slovencina", 0),
    "sl": ("Slovene", "Slovenšcina", 0),
    "st": ("Southern Sotho", "Sesotho", 0),
    "es": ("Spanish Castilian", "Español, castellano", 0),
    "su": ("Sundanese", "Basa Sunda", 0),
    "sw": ("Swahili", "Kiswahili", 0),
    "ss": ("Swati", "SiSwati", 0),
    "sv": ("Swedish", "Svenska", 0),
    "tn": ("Tswana", "Setswana", 0),
    "to": ("Tonga (Tonga Islands)", "faka Tonga", 0),
    "tr": ("Turkish", "Türkçe", 0),
    "ts": ("Tsonga", "Xitsonga", 0),
    "tw": ("Twi", "Twi", 0),
    "ty": ("Tahitian", "Reo Tahiti", 0),
    "wa": ("Walloon", "Walon", 0),
    "cy": ("Welsh", "Cymraeg", 0),
    "wo": ("Wolof", "Wollof", 0),
    "fy": ("Western Frisian", "Frysk", 0),
    "xh": ("Xhosa", "isi Xhosa", 0),
    "yo": ("Yoruba", "Yorùbá", 0),
    "zu": ("Zulu", "isi Zulu", 0),
    "zh_CN": ("SimpChinese", "简体中文", 936),
}

# Setup a safe null-translation
set_language()
