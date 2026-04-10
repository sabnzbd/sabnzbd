#!/usr/bin/python3 -OO
# -*- coding: utf-8 -*-
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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
make_mo - Compile PO files to MO files
"""

import concurrent.futures
import gettext
import glob
import os
import re
import sys

import msgfmt

PO_DIR = "po/main"
PO_EMAIL_DIR = "po/email"
PO_NSIS_DIR = "po/nsis"
MO_DIR = "locale"
EMAIL_DIR = "email"

DOMAIN = "SABnzbd"
DOMAIN_EMAIL = "SABemail"
DOMAIN_NSIS = "SABnsis"

NSIS = "builder/win/NSIS_Installer.nsi"

# Maps locale codes to NSIS MUI_LANGUAGE names (only languages with active translations).
# To add a new language:
#  * Add the locale code here with the matching MUI_LANGUAGE name
#  * Add the corresponding !insertmacro MUI_LANGUAGE line in NSIS_Installer.nsi
#  * Create po/nsis/<locale>.po.
#  * Available MUI language names are listed in the NSIS source:
#    https://github.com/NSIS-Dev/nsis/tree/master/Contrib/Language%20files

NSIS_LANGUAGE_NAMES = {
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "es": "Spanish",
    "fi": "Finnish",
    "fr": "French",
    "he": "Hebrew",
    "it": "Italian",
    "nb": "Norwegian",
    "nl": "Dutch",
    "pl": "Polish",
    "pt_BR": "PortugueseBR",
    "ro": "Romanian",
    "ru": "Russian",
    "sr": "Serbian",
    "sv": "Swedish",
    "tr": "Turkish",
    "zh_CN": "SimpChinese",
}

RE_NSIS = re.compile(r'^(\s*LangString\s+)(\w+)(\s+\$\{LANG_)(\w+)\}\s+(".*)', re.I)


def _compile_po_file(po_file, mo_file):
    """Compile a single PO file to MO — runs in a worker process"""
    msgfmt.MESSAGES = {}
    try:
        msgfmt.make(po_file, mo_file)
        return True
    except SystemExit:
        return False


def process_po_folder(domain, folder):
    """Compile all PO files in folder to MO files in parallel"""
    po_files, mo_files = [], []
    for po_file in glob.glob(os.path.join(folder, "*.po")):
        name = os.path.splitext(os.path.basename(po_file))[0]
        mo_path = os.path.join(MO_DIR, name, "LC_MESSAGES")
        os.makedirs(mo_path, exist_ok=True)
        mo_file = os.path.join(mo_path, f"{domain}.mo")
        print(f"Compile {mo_file}")
        po_files.append(po_file)
        mo_files.append(mo_file)

    with concurrent.futures.ProcessPoolExecutor() as executor:
        if not all(executor.map(_compile_po_file, po_files, mo_files)):
            sys.exit(1)


def translate_tmpl(trans, prefix, lng):
    """Write a translated copy of an email template"""
    src = os.path.join(EMAIL_DIR, f"{prefix}-en.tmpl")
    dst = os.path.join(EMAIL_DIR, f"{prefix}-{lng}.tmpl")
    with open(src, encoding="utf-8") as fp:
        data = trans.gettext(fp.read())
    with open(dst, "w", encoding="utf-8") as fp:
        if not -1 < data.find("UTF-8") < 30:
            fp.write("#encoding UTF-8\n")
        fp.write(data)


def make_templates():
    """Create translated email templates for all available languages"""
    os.makedirs(EMAIL_DIR, exist_ok=True)
    for lng in os.listdir(MO_DIR):
        if lng == "en" or not os.path.exists(os.path.join(PO_EMAIL_DIR, f"{lng}.po")):
            continue
        print(f"Create email template for {lng}")
        trans = gettext.translation(DOMAIN_EMAIL, MO_DIR, [lng], fallback=False)
        for prefix in ("email", "rss", "badfetch"):
            translate_tmpl(trans, prefix, lng)
        # Remove the email MO file — only needed for template generation
        mo_file = os.path.join(MO_DIR, lng, "LC_MESSAGES", f"{DOMAIN_EMAIL}.mo")
        if os.path.exists(mo_file):
            os.remove(mo_file)


def remove_mo_files():
    """Remove any remaining non-main MO files from locale"""
    for mo_file in glob.glob(os.path.join(MO_DIR, "**", "*.mo"), recursive=True):
        if not os.path.splitext(os.path.basename(mo_file))[0].startswith(DOMAIN):
            os.remove(mo_file)


def patch_nsis():
    """Patch translations into the NSIS installer script"""
    languages = [e.name for e in os.scandir(MO_DIR) if e.is_dir()]
    languages.sort()

    # Pre-load all NSIS translations once
    nsis_translations = {
        lcode: gettext.translation(DOMAIN_NSIS, MO_DIR, [lcode], fallback=False) for lcode in languages
    }

    output_lines = []
    with open(NSIS, encoding="utf-8-sig") as src:
        for line in src:
            if not (m := RE_NSIS.search(line)):
                output_lines.append(line)
                continue

            leader, item, rest = m.group(1), m.group(2), m.group(3)
            langname = m.group(4).upper()
            text = m.group(5).strip('"\n')

            # Drop previously generated non-English langstrings; they will be regenerated below
            if langname != "ENGLISH":
                continue

            # Write back the English line, then append a translation for each language
            output_lines.append(line)
            text = text.replace('$\\"', '"').replace("$\\", "\\")
            for lcode in languages:
                if lcode == "en":
                    continue
                if lcode not in NSIS_LANGUAGE_NAMES:
                    raise RuntimeWarning(f"Unsupported language {lcode}! Check NSIS_LANGUAGE_NAMES how to add.")

                lng_name = NSIS_LANGUAGE_NAMES[lcode].upper()
                if item == "MsgLangCode":
                    # The language code will be stored in the registry
                    text_trans = lcode
                else:
                    text_trans = nsis_translations[lcode].gettext(text)
                    text_trans = text_trans.replace("\r", "").replace("\n", "\\r\\n")
                    text_trans = text_trans.replace("\\", "$\\").replace('"', '$\\"')
                output_lines.append(f'{leader}{item}{rest}{lng_name}}} "{text_trans}"\n')

    # Write with UTF-8 BOM so NSIS picks up the translations correctly
    with open(NSIS, "w", encoding="utf-8") as dst:
        dst.write("\ufeff")
        dst.writelines(output_lines)


def main():
    if not os.path.exists("po"):
        raise RuntimeError("Make sure to run from root directory of SABnzbd")

    print("Email MO files")
    process_po_folder(DOMAIN_EMAIL, PO_EMAIL_DIR)
    print("Create email templates from MO files")
    make_templates()

    print("Main program MO files")
    process_po_folder(DOMAIN, PO_DIR)

    if os.path.exists(NSIS):
        print("NSIS MO files")
        process_po_folder(DOMAIN_NSIS, PO_NSIS_DIR)
        print("Patch NSIS script")
        patch_nsis()

    print("Remove temporary MO files")
    remove_mo_files()


if __name__ == "__main__":
    main()
