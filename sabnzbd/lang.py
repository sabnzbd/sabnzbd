#!/usr/bin/python3 -OO
# -*- coding: utf-8 -*-
# Copyright 2011-2021 The SABnzbd-Team <team@sabnzbd.org>
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

__all__ = ["set_locale_info", "set_language", "list_languages", "is_rtl"]

_DOMAIN = ""  # Holds translation domain
_LOCALEDIR = ""  # Holds path to the translation base folder


def set_locale_info(domain, localedir):
    """Setup the domain and localedir for translations"""
    global _DOMAIN, _LOCALEDIR
    _DOMAIN = domain
    _LOCALEDIR = localedir


def set_language(language=None):
    """Activate language, empty language will set default texts."""
    if not language:
        language = ""

    lng = gettext.translation(_DOMAIN, _LOCALEDIR, [language], fallback=True)
    builtins.__dict__["T"] = lng.gettext
    builtins.__dict__["TT"] = lambda x: str(x)  # Use in text tables


def list_languages():
    """Return sorted list of (lang-code, lang-string) pairs,
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


def is_rtl(lang):
    return LanguageTable.get(lang, "en")[3]


# English name, native name, code page, right-to-left
LanguageTable = {
    "aa": ("Afar", "Afaraf", 0, False),
    "af": ("Afrikaans", "Afrikaans", 0, False),
    "ak": ("Akan", "Akan", 0, False),
    "sq": ("Albanian", "Shqip", 0, False),
    "an": ("Aragonese", "Aragonés", 0, False),
    "ae": ("Avestan", "Avesta", 0, False),
    "ay": ("Aymara", "Aymararu", 0, False),
    "bm": ("Bambara", "Bamanankan", 0, False),
    "eu": ("Basque", "Euskara", 0, False),
    "bi": ("Bislama", "Bislama", 0, False),
    "bs": ("Bosnian", "Bosanskijezik", 0, False),
    "br": ("Breton", "Brezhoneg", 0, False),
    "ca": ("Catalan", "Català", 0, False),
    "ch": ("Chamorro", "Chamoru", 0, False),
    "kw": ("Cornish", "Kernewek", 0, False),
    "co": ("Corsican", "Corsu", 0, False),
    "hr": ("Croatian", "Hrvatski", 0, False),
    "cs": ("Czech", "Cesky, ceština", 0, False),
    "da": ("Danish", "Dansk", 0, False),
    "nl": ("Dutch", "Nederlands", 0, False),
    "en": ("English", "English", 0, False),
    "eo": ("Esperanto", "Esperanto", 0, False),
    "et": ("Estonian", "Eesti", 0, False),
    "fo": ("Faroese", "Føroyskt", 0, False),
    "fj": ("Fijian", "Vosa Vakaviti", 0, False),
    "fi": ("Finnish", "Suomi", 0, False),
    "fr": ("French", "Français", 0, False),
    "gl": ("Galician", "Galego", 0, False),
    "de": ("German", "Deutsch", 0, False),
    "he": ("Hebrew", "עִבְרִית‎", 1255, True),
    "hz": ("Herero", "Otjiherero", 0, False),
    "ho": ("Hiri Motu", "Hiri Motu", 0, False),
    "hu": ("Hungarian", "Magyar", 0, False),
    "id": ("Indonesian", "Bahasa Indonesia", 0, False),
    "ga": ("Irish", "Gaeilge", 0, False),
    "io": ("Ido", "Ido", 0, False),
    "is": ("Icelandic", "Íslenska", 0, False),
    "it": ("Italian", "Italiano", 0, False),
    "jv": ("Javanese", "BasaJawa", 0, False),
    "rw": ("Kinyarwanda", "Ikinyarwanda", 0, False),
    "kg": ("Kongo", "KiKongo", 0, False),
    "kj": ("Kwanyama", "Kuanyama", 0, False),
    "la": ("Latin", "Lingua latina", 0, False),
    "lb": ("Luxembourgish", "Lëtzebuergesch", 0, False),
    "lg": ("Luganda", "Luganda", 0, False),
    "li": ("Limburgish", "Limburgs", 0, False),
    "ln": ("Lingala", "Lingála", 0, False),
    "lt": ("Lithuanian", "Lietuviukalba", 0, False),
    "lv": ("Latvian", "Latviešuvaloda", 0, False),
    "gv": ("Manx", "Gaelg", 0, False),
    "mg": ("Malagasy", "Malagasy fiteny", 0, False),
    "mt": ("Maltese", "Malti", 0, False),
    "nb": ("Norwegian Bokmål", "Norsk bokmål", 0, False),
    "nn": ("Norwegian Nynorsk", "Norsk nynorsk", 0, False),
    "no": ("Norwegian", "Norsk", 0, False),
    "oc": ("Occitan", "Occitan", 0, False),
    "om": ("Oromo", "Afaan Oromoo", 0, False),
    "pl": ("Polish", "Polski", 0, False),
    "pt": ("Portuguese", "Português", 0, False),
    "pt_BR": ("Portuguese Brazillian", "Português Brasileiro", 0, False),
    "rm": ("Romansh", "Rumantsch grischun", 0, False),
    "rn": ("Kirundi", "kiRundi", 0, False),
    "ro": ("Romanian", "Româna", 1250, False),
    "sc": ("Sardinian", "Sardu", 0, False),
    "se": ("Northern Sami", "Davvisámegiella", 0, False),
    "sm": ("Samoan", "Gagana fa'a Samoa", 0, False),
    "gd": ("Gaelic", "Gàidhlig", 0, False),
    "ru": ("Russian", "русский язык", 1251, False),
    "sr": ("Serbian", "српски", 1251, False),
    "sn": ("Shona", "Chi Shona", 0, False),
    "sk": ("Slovak", "Slovencina", 0, False),
    "sl": ("Slovene", "Slovenšcina", 0, False),
    "st": ("Southern Sotho", "Sesotho", 0, False),
    "es": ("Spanish Castilian", "Español, castellano", 0, False),
    "su": ("Sundanese", "Basa Sunda", 0, False),
    "sw": ("Swahili", "Kiswahili", 0, False),
    "ss": ("Swati", "SiSwati", 0, False),
    "sv": ("Swedish", "Svenska", 0, False),
    "tn": ("Tswana", "Setswana", 0, False),
    "to": ("Tonga (Tonga Islands)", "faka Tonga", 0, False),
    "tr": ("Turkish", "Türkçe", 0, False),
    "ts": ("Tsonga", "Xitsonga", 0, False),
    "tw": ("Twi", "Twi", 0, False),
    "ty": ("Tahitian", "Reo Tahiti", 0, False),
    "wa": ("Walloon", "Walon", 0, False),
    "cy": ("Welsh", "Cymraeg", 0, False),
    "wo": ("Wolof", "Wollof", 0, False),
    "fy": ("Western Frisian", "Frysk", 0, False),
    "xh": ("Xhosa", "isi Xhosa", 0, False),
    "yo": ("Yoruba", "Yorùbá", 0, False),
    "zu": ("Zulu", "isi Zulu", 0, False),
    "zh_CN": ("SimpChinese", "简体中文", 936, False),
}

# Setup a safe null-translation
set_language()
