#!/usr/bin/python3 -OO
# Copyright 2011-2019 The SABnzbd-Team <team@sabnzbd.org>
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
try:
    with open("sabnzbd/version.py") as version_file:
        exec(version_file.read())
except FileNotFoundError:
    with open("../sabnzbd/version.py") as version_file:
        exec(version_file.read())

# Fixed information for the POT header
HEADER = r"""#
    # SABnzbd Translation Template file __TYPE__
    # Copyright 2011-2019 The SABnzbd-Team
    #   team@sabnzbd.org
    #
    msgid ""
    msgstr ""
    "Project-Id-Version: SABnzbd-{}\n"
    "PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\n"
    "Last-Translator: shypike@sabnzbd.org\n"
    "Language-Team: LANGUAGE <LL@li.org>\n"
    "MIME-Version: 1.0\n"
    "Content-Type: text/plain; charset=ASCII\n"
    "Content-Transfer-Encoding: 7bit\n"
    """
HEADER = HEADER.format(__version__)

PO_DIR = "po/main"
POE_DIR = "po/email"
PON_DIR = "po/nsis"
EMAIL_DIR = "email"
DOMAIN = "SABnzbd"
DOMAIN_EMAIL = "SABemail"
DOMAIN_NSIS = "SABnsis"
PARMS = r"-d {} -p {} -w500 -k T -k TT -o {}.pot.tmp".format(DOMAIN, PO_DIR, DOMAIN)
FILES = "SABnzbd.py SABHelper.py SABnzbdDelegate.py sabnzbd/*.py sabnzbd/utils/*.py"

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
        return FILE_CACHE[line_src][number - 1]
    except (OSError, IndexError):
        return ""


def get_context(ctx_line):
    """ Read context info from source file and append to line.
        input: "#: filepath.py:123 filepath2.py:456"
        output: "#: filepath.py:123 # [context info] # filepath2.py:456 # [context info 2]"
    """
    if not ctx_line.startswith("#:"):
        return ctx_line

    newlines = []
    for item in ctx_line[2:].strip("\r\n").split():
        cm = RE_LINE.search(item)
        if cm:
            line_src = cm.group(1)
            number = cm.group(2)
        else:
            newlines.append(item)
            continue

        srcline = get_a_line(line_src, int(number)).strip("\r\n")
        context = ""
        cm = RE_CONTEXT.search(srcline)  # avoid shadowing out of scope variable 'm'
        if cm:
            context = cm.group(1)
        else:
            if "logging.error(" in srcline:
                context = "Error message"
            elif "logging.warning(" in srcline:
                context = "Warning message"
        # Remove line-number
        item = item.split(":")[0]

        if context:
            # Format context
            item = "{} [{}]".format(item, context)

        # Only add new texts
        if item not in newlines:
            newlines.append(item)

    return "#: " + " # ".join(newlines) + "\n"


def add_tmpl_to_pot(prefix, dst_file):
    """ Append english template to open POT file 'dst' """
    tmpl_abs_path = os.path.normpath(os.path.join(project_path, "{}/{}-en.tmpl".format(EMAIL_DIR, prefix)))
    with open(tmpl_abs_path, "r") as tmpl_src:
        dst_file.write("#: email/{}.tmpl:1\n".format(prefix))
        dst_file.write('msgid ""\n')
        for tmpl_line in tmpl_src:
            dst_file.write('"{}"\n'.format(tmpl_line.replace("\n", "\\n").replace('"', '\\"')))
        dst_file.write('msgstr ""\n\n')


print("Creating POT file")
if not os.path.exists(PO_DIR):
    os.makedirs(PO_DIR)

# Determine location of PyGetText tool
path, py = os.path.split(sys.argv[0])
project_path = os.path.split(path)[0]
PYGETTEXT = os.path.abspath(os.path.normpath(os.path.join(path, "pygettext.py")))
FILES = [os.path.normpath(os.path.join(project_path, f)) for f in FILES.split(" ")]
FILES = r" ".join(FILES)
cmd = r"{} {} {} {}".format(sys.executable, PYGETTEXT, PARMS, FILES)
os.system(cmd)
print("Finished creating POT file")

# TODO: Appears to still be a bug in generated POT files. Many nested '#: D # D' appear to be missing a colon.
print("Post-process POT file")
with open("{}/{}.pot.tmp".format(PO_DIR, DOMAIN), "r") as src:
    with open("{}/{}.pot".format(PO_DIR, DOMAIN), "w") as dst:
        dst.write(HEADER.replace("__TYPE__", "MAIN"))
        header = True

        for line in src:
            if line.startswith("#:"):
                line = line.replace("\\", "/")
                if header:
                    dst.write("\n\n")
                header = False
            if header:
                if not ('"POT-Creation-Date:' in line or '"Generated-By:' in line):
                    continue
            elif line.startswith("#:"):
                line = get_context(line)
            dst.write(line)


try:
    os.remove("sabnzbd/{}/{}.pot.tmp".format(PO_DIR, DOMAIN))
except OSError:
    try:
        os.remove("../sabnzbd/{}/{}.pot.tmp".format(PO_DIR, DOMAIN))
    except OSError:
        pass
print("Finished post-process POT file")

print("Creating email POT file")
if not os.path.exists(POE_DIR):
    os.makedirs(POE_DIR)
with open(os.path.join(POE_DIR, "{}.pot".format(DOMAIN_EMAIL)), "w") as dst_email:
    dst_email.write(HEADER.replace("__TYPE__", "EMAIL"))
    add_tmpl_to_pot("email", dst_email)
    add_tmpl_to_pot("rss", dst_email)
    add_tmpl_to_pot("badfetch", dst_email)
print("Finished creating email POT file")


# Create the NSIS POT file
NSIS = "NSIS_Installer.nsi"
RE_NSIS = re.compile(r'LangString\s+\w+\s+\${LANG_ENGLISH\}\s+(".*)', re.I)

if os.path.exists(NSIS):
    print("Creating NSIS POT file")
    if not os.path.exists(PON_DIR):
        os.makedirs(PON_DIR)
    src = open(NSIS, "r")
    dst = open(os.path.join(PON_DIR, "{}.pot".format(DOMAIN_NSIS)), "w")
    dst.write(HEADER.replace("__TYPE__", "NSIS"))
    dst.write("\n")
    for line in src:
        m = RE_NSIS.search(line)
        if m and "MsgLangCode" not in line:
            dst.write("#: {}\n".format(NSIS))
            text = m.group(1).replace('$\\"', '\\"').replace("$\\", "\\\\")
            dst.write("msgid {}\n".format(text))
            dst.write('msgstr ""\n\n')
    dst.close()
    src.close()
    print("Finished creating NSIS POT file")
