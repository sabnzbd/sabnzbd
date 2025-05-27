import os
import tarfile

def create_safe_tar(tar_path):
    with tarfile.open(tar_path, "w") as tar:
        info = tarfile.TarInfo(name="bobby_tables.txt")
        info.size = len(b"good content")
        tar.addfile(info)

def create_unsafe_tar(tar_path):
    with tarfile.open(tar_path, "w") as tar:
        # File with relative path traversal
        info = tarfile.TarInfo(name="../../evil.txt")
        info.size = len(b"bad content")
        tar.addfile(info)

def create_unsafe_tar2(tar_path):
    with tarfile.open(tar_path, "w") as tar:
        # File with direct path
        info = tarfile.TarInfo(name="/mnt/evil.txt")
        info.size = len(b"bad content")
        tar.addfile(info)

def main():
    create_safe_tar("testfile.tar")
    create_unsafe_tar("evil.tar")
    create_unsafe_tar2("evil2.tar")

if __name__ == "__main__":
        main()
