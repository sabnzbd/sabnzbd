#!/usr/bin/python3

""" function to check and find correct extension of a (deobfuscated) file
Note: extension always contains a leading dot
"""


import puremagic
import os
import sys
import re
from typing import List
from sabnzbd.filesystem import get_ext


# common extension from https://www.computerhope.com/issues/ch001789.htm
POPULAR_EXT = (
    "3g2",
    "3gp",
    "7z",
    "ai",
    "aif",
    "apk",
    "arj",
    "asp",
    "aspx",
    "avi",
    "bak",
    "bat",
    "bin",
    "bmp",
    "c",
    "cab",
    "cda",
    "cer",
    "cfg",
    "cfm",
    "cgi",
    "cgi",
    "cgi",
    "class",
    "com",
    "cpl",
    "cpp",
    "cs",
    "css",
    "csv",
    "cur",
    "dat",
    "db",
    "dbf",
    "deb",
    "dll",
    "dmg",
    "dmp",
    "doc",
    "docx",
    "drv",
    "email",
    "eml",
    "emlx",
    "exe",
    "flv",
    "fnt",
    "fon",
    "gadget",
    "gif",
    "h",
    "h264",
    "htm",
    "html",
    "icns",
    "ico",
    "ico",
    "ini",
    "iso",
    "jar",
    "java",
    "jpeg",
    "jpg",
    "js",
    "jsp",
    "key",
    "lnk",
    "log",
    "m4v",
    "mdb",
    "mid",
    "midi",
    "mkv",
    "mov",
    "mp3",
    "mp4",
    "mpa",
    "mpeg",
    "mpg",
    "msg",
    "msi",
    "msi",
    "odp",
    "ods",
    "odt",
    "oft",
    "ogg",
    "ost",
    "otf",
    "part",
    "pdf",
    "php",
    "php",
    "pkg",
    "pl",
    "pl",
    "pl",
    "png",
    "pps",
    "ppt",
    "pptx",
    "ps",
    "psd",
    "pst",
    "py",
    "py",
    "py",
    "rar",
    "rm",
    "rpm",
    "rss",
    "rtf",
    "sav",
    "sh",
    "sql",
    "svg",
    "swf",
    "swift",
    "sys",
    "tar",
    "tar",
    "gz",
    "tex",
    "tif",
    "tiff",
    "tmp",
    "toast",
    "ttf",
    "txt",
    "vb",
    "vcd",
    "vcf",
    "vob",
    "wav",
    "wma",
    "wmv",
    "wpd",
    "wpl",
    "wsf",
    "xhtml",
    "xls",
    "xlsm",
    "xlsx",
    "z",
    "zip",
)

DOWNLOAD_EXT = (
    "ass",
    "avi",
    "bat",
    "bdmv",
    "bin",
    "bup",
    "cbr",
    "cbz",
    "clpi",
    "crx",
    "db",
    "diz",
    "djvu",
    "docx",
    "epub",
    "exe",
    "flac",
    "gif",
    "gz",
    "htm",
    "html",
    "icns",
    "ico",
    "idx",
    "ifo",
    "img",
    "inf",
    "info",
    "ini",
    "iso",
    "jpg",
    "log",
    "m2ts",
    "m3u",
    "m4a",
    "mkv",
    "mp3",
    "mp4",
    "mpls",
    "mx",
    "nfo",
    "nib",
    "nzb",
    "otf",
    "par2",
    "part",
    "pdf",
    "pem",
    "php",
    "plist",
    "png",
    "py",
    "rar",
    "releaseinfo",
    "rev",
    "sfv",
    "sh",
    "srr",
    "srs",
    "srt",
    "strings",
    "sub",
    "sup",
    "sys",
    "tif",
    "ttf",
    "txt",
    "url",
    "vob",
    "website",
    "wmv",
    "xpi",
)

# Combine to one tuple, with unique entries:
ALL_EXT = tuple(set(POPULAR_EXT + DOWNLOAD_EXT))
# Prepend a dot to each extension, because we work with a leading dot in extensions
ALL_EXT = tuple(["." + i for i in ALL_EXT])

# Match old-style multi-rar extensions
SIMPLE_RAR_RE = re.compile(r"\.r\d\d\d?$", re.I)


def has_popular_extension(file_path: str) -> bool:
    """returns boolean if the extension of file_path is a popular, well-known extension"""
    file_extension = get_ext(file_path)
    return file_extension in ALL_EXT or SIMPLE_RAR_RE.match(file_extension)


def all_possible_extensions(file_path: str) -> List[str]:
    """returns a list with all possible extensions (with leading dot) for given file_path as reported by puremagic"""
    extension_list = []
    for i in puremagic.magic_file(file_path):
        extension_list.append(i.extension)
    return extension_list


def what_is_most_likely_extension(file_path: str) -> str:
    """Returns most_likely extension, with a leading dot"""
    for possible_extension in all_possible_extensions(file_path):
        # let's see if technically-suggested extension by puremagic is also likely IRL
        if possible_extension in ALL_EXT:
            # Yes, looks likely
            return possible_extension

    # Check if text or NZB, as puremagic is not good at that.
    try:
        # Only read the start, don't need the whole file
        with open(file_path, "r") as inp_file:
            txt = inp_file.read(200).lower()

        # Yes, a text file ... so let's check if it's even an NZB:
        if "!doctype nzb public" in txt or "<nzb xmlns=" in txt:
            # yes, contains NZB signals:
            return ".nzb"
        else:
            return ".txt"
    except UnicodeDecodeError:
        # not txt (and not nzb)
        pass

    # no popular extension found, so just trust puremagic and return the first extension (if any)
    try:
        return all_possible_extensions(file_path)[0]
    except IndexError:
        return ""


if __name__ == "__main__":
    privacy = False

    # parse all parameters on CLI as files to be ext-checked
    for i in range(1, len(sys.argv)):
        if sys.argv[i] == "-p":
            # privacy, please ... so only print last 10 chars of a file
            privacy = True
            continue

        file_path = sys.argv[i]

        if privacy:
            to_be_printed = file_path[-10:]
        else:
            to_be_printed = file_path

        if has_popular_extension(file_path):
            # a common extension, so let's see what puremagic says, so that we can learn
            filename, file_extension = os.path.splitext(file_path)
            file_extension = file_extension[1:].lower()

            print(
                "IRL-ext",
                file_extension,
                "most_likely",
                what_is_most_likely_extension(file_path),
                "puremagic",
                all_possible_extensions(file_path),
            )
