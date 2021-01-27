#!/usr/bin/python3 -OO
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
extract_pot - Extract translatable strings from all PY files
"""

import os
import sys
import re

# Import version.py without the sabnzbd overhead
with open("sabnzbd/version.py") as version_file:
    exec(version_file.read())

# Fixed information for the POT header
HEADER = (
    r"""#
# SABnzbd Translation Template file __TYPE__
# Copyright 2011-2021 The SABnzbd-Team
#   team@sabnzbd.org
#
msgid ""
msgstr ""
"Project-Id-Version: SABnzbd-%s\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\n"
"Last-Translator: team@sabnzbd.org\n"
"Language-Team: SABnzbd <team@sabnzbd.org>\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"""
    % __version__
)

PO_DIR = "po/main"
POE_DIR = "po/email"
PON_DIR = "po/nsis"
EMAIL_DIR = "email"
DOMAIN = "SABnzbd"
DOMAIN_EMAIL = "SABemail"
DOMAIN_NSIS = "SABnsis"
PARMS = "-d %s -p %s -w500 -k T -k TT -o %s.pot.tmp" % (DOMAIN, PO_DIR, DOMAIN)
FILES = "SABnzbd.py sabnzbd/*.py sabnzbd/utils/*.py"

FILE_CACHE = {}

RE_LINE = re.compile(r"\s*([^: \t]+)\s*:\s*(\d+)")
RE_CONTEXT = re.compile(r"#:\s*(.*)$")


def get_a_line(line_src, number):
    """ Retrieve line 'number' from file 'src' with caching """
    global FILE_CACHE
    if line_src not in FILE_CACHE:
        FILE_CACHE[line_src] = []
        for file_line in open(line_src, "r"):
            FILE_CACHE[line_src].append(file_line)
    try:
        # We include 2 lines extra, since sometimes the "logging.warning"
        # can be on the line above, due to code-formatting
        return "".join(FILE_CACHE[line_src][number - 3 : number])
    except:
        return ""


def get_context(ctx_line):
    """ Read context info from source file and append to line. """
    if not ctx_line.startswith("#:"):
        return ctx_line

    newlines = []
    contexts = []
    for item in ctx_line[2:].strip().split():
        m = RE_LINE.search(item)
        if m:
            line_src = m.group(1)
            number = m.group(2)
        else:
            newlines.append(item)
            continue

        srcline = get_a_line(line_src, int(number)).strip("\r\n")
        context = ""
        m = RE_CONTEXT.search(srcline)
        if m:
            # Context was defined in the source file
            context = m.group(1)
        else:
            if "logging.error(" in srcline:
                context = "Error message"
            elif "logging.warning(" in srcline or "logging.warning_helpful(" in srcline:
                context = "Warning message"

        if context and context not in contexts:
            contexts.append(context)

        # Remove line-number to prevent unnecessary updates of the POT-files
        item = item.split(":")[0]

        # Only add new texts
        if item not in newlines:
            newlines.append(item)

    # Build return value
    return_val = "#: " + ", ".join(newlines) + "\n"
    if contexts:
        # Syntax defined by GNU gettext for context-comments
        return_val = "#. " + " - ".join(contexts) + "\n" + return_val
    return return_val


def add_tmpl_to_pot(prefix, dst_file):
    """ Append english template to open POT file 'dst' """
    with open(EMAIL_DIR + "/%s-en.tmpl" % prefix, "r") as tmpl_src:
        dst_file.write("#: email/%s.tmpl:1\n" % prefix)
        dst_file.write('msgid ""\n')
        for tmpl_line in tmpl_src:
            dst_file.write('"%s"\n' % tmpl_line.replace("\n", "\\n").replace('"', '\\"'))
        dst_file.write('msgstr ""\n\n')


print("Creating POT file")
if not os.path.exists(PO_DIR):
    os.makedirs(PO_DIR)

# Determine location of PyGetText tool
path, py = os.path.split(sys.argv[0])
PYGETTEXT = os.path.abspath(os.path.normpath(os.path.join(path, "pygettext.py")))
cmd = "%s %s %s %s" % (sys.executable, PYGETTEXT, PARMS, FILES)
os.system(cmd)
print("Finished creating POT file")

print("Post-process POT file")
with open("%s/%s.pot.tmp" % (PO_DIR, DOMAIN), "r") as source_pot, open("%s/%s.pot" % (PO_DIR, DOMAIN), "w") as dest_pot:
    dest_pot.write(HEADER.replace("__TYPE__", "MAIN"))
    header = True
    for line in source_pot:
        if line.startswith("#:"):
            line = line.replace("\\", "/")
            if header:
                dest_pot.write("\n")
            header = False
        if header:
            # Skip header generated by pygettext
            continue
        elif line.startswith("#:"):
            line = get_context(line)
        dest_pot.write(line)

os.remove("%s/%s.pot.tmp" % (PO_DIR, DOMAIN))
print("Finished post-process POT file")

print("Creating email POT file")
if not os.path.exists(POE_DIR):
    os.makedirs(POE_DIR)
with open(os.path.join(POE_DIR, DOMAIN_EMAIL + ".pot"), "w") as dst_email:
    dst_email.write(HEADER.replace("__TYPE__", "EMAIL"))
    add_tmpl_to_pot("email", dst_email)
    add_tmpl_to_pot("rss", dst_email)
    add_tmpl_to_pot("badfetch", dst_email)
print("Finished creating email POT file")


# Create the NSIS POT file
NSIS = "builder/win/NSIS_Installer.nsi"
RE_NSIS = re.compile(r'LangString\s+\w+\s+\$\{LANG_ENGLISH\}\s+(".*)', re.I)

if os.path.exists(NSIS):
    print("Creating NSIS POT file")
    if not os.path.exists(PON_DIR):
        os.makedirs(PON_DIR)
    src = open(NSIS, "r")
    dst = open(os.path.join(PON_DIR, DOMAIN_NSIS + ".pot"), "w")
    dst.write(HEADER.replace("__TYPE__", "NSIS"))
    dst.write("\n")
    for line in src:
        m = RE_NSIS.search(line)
        if m and "MsgLangCode" not in line:
            dst.write("#: %s\n" % NSIS)
            text = m.group(1).replace('$\\"', '\\"').replace("$\\", "\\\\")
            dst.write("msgid %s\n" % text)
            dst.write('msgstr ""\n\n')
    dst.close()
    src.close()
    print("Finished creating NSIS POT file")
