#!/usr/bin/python3

""" function to check and find correct extension of a (deobfuscated) file
"""


import puremagic


def all_possible_extensions(file_path: str) -> list:
    """returns a list with all possible extensions for given file_path"""
    extension_list = []
    for i in puremagic.magic_file(file_path):
        extension_list.append(i.extension)
    return extension_list


def extension_matches(file_path: str) -> int:
    import os

    # TBD use SAB's own extension finder
    filename, file_extension = os.path.splitext(file_path)
    file_extension = file_extension.lower()
    return file_extension in all_possible_extensions(file_path)


if __name__ == "__main__":
    import sys

    for i in range(1,len(sys.argv)):
        file_path = sys.argv[i]
        matching_ext = extension_matches(file_path)
        if matching_ext:
            print(True, file_path)
        else:
            print(False, all_possible_extensions(file_path), file_path)
