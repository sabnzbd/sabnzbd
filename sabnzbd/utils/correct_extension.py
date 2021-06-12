#!/usr/bin/python3

""" function to check and find correct extension of a (deobfuscated) file
"""


import sabnzbd.utils.puremagic as puremagic


def all_possible_extensions(file_path: str) -> list:
    """returns a list with all possible extensions for given file_path"""
    extension_list = []
    for i in puremagic.magic_file(file_path):
        extension_list.append(i.extension)
    return extension_list
