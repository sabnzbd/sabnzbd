#!/usr/bin/python3 -OO
# Copyright 2008-2024 by The SABnzbd-Team (sabnzbd.org)
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

import glob
import platform
import re
import sys
import os
import tempfile
import time
import shutil
import subprocess
import tarfile
import urllib.request
import urllib.error
import configobj
from typing import List

from constants import (
    RELEASE_VERSION,
    VERSION_FILE,
    RELEASE_README,
    RELEASE_NAME,
    RELEASE_BINARY_32,
    RELEASE_BINARY_64,
    RELEASE_INSTALLER,
    ON_GITHUB_ACTIONS,
    RELEASE_THIS,
    RELEASE_SRC,
    EXTRA_FILES,
    EXTRA_FOLDERS,
)


# Support functions
def safe_remove(path):
    """Remove file without errors if the file doesn't exist
    Can also handle folders
    """
    if os.path.exists(path):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


def delete_files_glob(glob_pattern: str, allow_no_matches: bool = False):
    """Delete one file or set of files from wild-card spec.
    We expect to match at least 1 file, to force expected behavior"""
    if files_to_remove := glob.glob(glob_pattern):
        for path in files_to_remove:
            if os.path.exists(path):
                os.remove(path)
    else:
        if not allow_no_matches:
            raise FileNotFoundError(f"No files found that match '{glob_pattern}'")


def run_external_command(command: List[str], print_output: bool = True):
    """Wrapper to ease the use of calling external programs"""
    process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output, _ = process.communicate()
    ret = process.wait()
    if (output and print_output) or ret != 0:
        print(output)
    if ret != 0:
        raise RuntimeError("Command returned non-zero exit code %s!" % ret)
    return output


def run_git_command(parms):
    """Run git command, raise error if it failed"""
    return run_external_command(["git"] + parms)


def patch_version_file(release_name):
    """Patch in the Git commit hash, but only when this is
    an unmodified checkout
    """
    git_output = run_git_command(["log", "-1"])
    for line in git_output.split("\n"):
        if "commit " in line:
            commit = line.split(" ")[1].strip()
            break
    else:
        raise TypeError("Commit hash not found")

    with open(VERSION_FILE, "r") as ver:
        version_file = ver.read()

    version_file = re.sub(r'__baseline__\s*=\s*"[^"]*"', '__baseline__ = "%s"' % commit, version_file)
    version_file = re.sub(r'__version__\s*=\s*"[^"]*"', '__version__ = "%s"' % release_name, version_file)

    with open(VERSION_FILE, "w") as ver:
        ver.write(version_file)


def test_sab_binary(binary_path: str):
    """Wrapper to have a simple start-up test for the binary"""
    with tempfile.TemporaryDirectory() as config_dir:
        sabnzbd_process = subprocess.Popen(
            [binary_path, "--browser", "0", "--logging", "2", "--config", config_dir],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        # Wait for SAB to respond
        base_url = "http://127.0.0.1:8080/"
        for _ in range(30):
            try:
                urllib.request.urlopen(base_url, timeout=1).read()
                break
            except:
                time.sleep(1)
        else:
            # Print console output and give some time to print
            print(sabnzbd_process.stdout.read())
            time.sleep(1)
            raise urllib.error.URLError("Could not connect to SABnzbd")

        # Open a number of API calls and pages, to see if we are really up
        pages_to_test = [
            "",
            "wizard",
            "config",
            "config/server",
            "config/categories",
            "config/scheduling",
            "config/rss",
            "config/general",
            "config/folders",
            "config/switches",
            "config/sorting",
            "config/notify",
            "config/special",
            "api?mode=version",
        ]
        for url in pages_to_test:
            print("Testing: %s%s" % (base_url, url))
            if b"500 Internal Server Error" in urllib.request.urlopen(base_url + url, timeout=1).read():
                raise RuntimeError("Crash in %s" % url)

        # Parse API-key so we can do a graceful shutdown
        sab_config = configobj.ConfigObj(os.path.join(config_dir, "sabnzbd.ini"))
        urllib.request.urlopen(base_url + "shutdown/?apikey=" + sab_config["misc"]["api_key"], timeout=10)
        sabnzbd_process.wait()

        # Print logs for verification
        with open(os.path.join(config_dir, "logs", "sabnzbd.log"), "r") as log_file:
            # Wait after printing so the output is nicely displayed in case of problems
            print(log_text := log_file.read())
            time.sleep(5)

            # Make sure no extra errors/warnings were reported
            if "ERROR" in log_text or "WARNING" in log_text:
                raise RuntimeError("Warning or error reported during execution")


if __name__ == "__main__":
    # Was any option supplied?
    if len(sys.argv) < 2:
        raise TypeError("Please specify what to do")

    # Make sure we are in the src folder
    if not os.path.exists("builder"):
        raise FileNotFoundError("Run from the main SABnzbd source folder: python builder/package.py")

    # Check if we have the needed certificates
    try:
        import certifi
    except ImportError:
        raise FileNotFoundError("Need certifi module")

    # Patch release file
    patch_version_file(RELEASE_VERSION)

    # Rename release notes file
    safe_remove("README.txt")
    shutil.copyfile(RELEASE_README, "README.txt")

    # Compile translations
    if not os.path.exists("locale"):
        run_external_command([sys.executable, "tools/make_mo.py"])

        # Check again if translations exist, fail otherwise
        if not os.path.exists("locale"):
            raise FileNotFoundError("Failed to compile language files")

    # Make sure we remove any existing build-folders
    safe_remove("build")
    safe_remove("dist")
    safe_remove(RELEASE_NAME)

    # Copy the specification
    shutil.copyfile("builder/SABnzbd.spec", "SABnzbd.spec")

    if "binary" in sys.argv or "installer" in sys.argv:
        # Must be run on Windows
        if sys.platform != "win32":
            raise RuntimeError("Binary should be created on Windows")

        # Check what architecture we are on
        RELEASE_BINARY = RELEASE_BINARY_32
        BUILDING_64BIT = False
        if platform.architecture()[0] == "64bit":
            RELEASE_BINARY = RELEASE_BINARY_64
            BUILDING_64BIT = True

        # Remove any leftovers
        safe_remove(RELEASE_BINARY)

        # Run PyInstaller and check output
        run_external_command([sys.executable, "-O", "-m", "PyInstaller", "SABnzbd.spec"])

        shutil.copytree("dist/SABnzbd-console", "dist/SABnzbd", dirs_exist_ok=True)
        safe_remove("dist/SABnzbd-console")

        # Remove unwanted DLL's
        shutil.rmtree("dist/SABnzbd/Pythonwin")
        if BUILDING_64BIT:
            # These are only present on 64bit (Python 3.9+)
            delete_files_glob("dist/SABnzbd/api-ms-win*.dll", allow_no_matches=True)
            delete_files_glob("dist/SABnzbd/ucrtbase.dll", allow_no_matches=True)

            # Remove 32bit external executables
            delete_files_glob("dist/SABnzbd/win/par2/par2.exe")
            delete_files_glob("dist/SABnzbd/win/multipar/par2j.exe")
            delete_files_glob("dist/SABnzbd/win/unrar/UnRAR.exe")

        if "installer" in sys.argv:
            # Needs to be run on 64 bit
            if not BUILDING_64BIT:
                raise RuntimeError("Installer should be created on 64bit Python")

            # Compile NSIS translations
            safe_remove("NSIS_Installer.nsi")
            safe_remove("NSIS_Installer.nsi.tmp")
            shutil.copyfile("builder/win/NSIS_Installer.nsi", "NSIS_Installer.nsi")
            run_external_command([sys.executable, "tools/make_mo.py", "nsis"])

            # Run NSIS to build installer
            run_external_command(
                [
                    "makensis.exe",
                    "/V3",
                    "/DSAB_PRODUCT=%s" % RELEASE_NAME,
                    "/DSAB_VERSION=%s" % RELEASE_VERSION,
                    "/DSAB_FILE=%s" % RELEASE_INSTALLER,
                    "NSIS_Installer.nsi.tmp",
                ]
            )

        # Rename the folder
        shutil.copytree("dist/SABnzbd", RELEASE_NAME)

        # Create the archive
        run_external_command(["win/7zip/7za.exe", "a", RELEASE_BINARY, RELEASE_NAME])

        # Test the release, as the very last step to not mess with any release code
        test_sab_binary("dist/SABnzbd/SABnzbd.exe")

    if "app" in sys.argv:
        # Must be run on macOS
        if sys.platform != "darwin":
            raise RuntimeError("App should be created on macOS")

        # Who will sign and notarize this?
        authority = os.environ.get("SIGNING_AUTH")
        notarization_user = os.environ.get("NOTARIZATION_USER")
        notarization_pass = os.environ.get("NOTARIZATION_PASS")

        # We need to sign all the included binaries before packaging them
        # Otherwise the signature of the main application becomes invalid
        if authority:
            files_to_sign = [
                "osx/par2/par2-turbo",
                "osx/par2/arm64/par2-turbo",
                "osx/unrar/unrar",
                "osx/unrar/arm64/unrar",
                "osx/7zip/7zz",
            ]
            for file_to_sign in files_to_sign:
                print("Signing %s with hardended runtime" % file_to_sign)
                run_external_command(
                    [
                        "codesign",
                        "--deep",
                        "--force",
                        "--timestamp",
                        "--options",
                        "runtime",
                        "--entitlements",
                        "builder/osx/entitlements.plist",
                        "-s",
                        authority,
                        file_to_sign,
                    ],
                    print_output=False,
                )
                print("Signed %s!" % file_to_sign)

        # Run PyInstaller and check output
        run_external_command([sys.executable, "-O", "-m", "PyInstaller", "SABnzbd.spec"])

        # Make sure we created a fully universal2 release when releasing or during CI
        if RELEASE_THIS or ON_GITHUB_ACTIONS:
            for bin_to_check in glob.glob("dist/SABnzbd.app/Contents/MacOS/**/*.so", recursive=True):
                print("Checking if binary is universal2: %s" % bin_to_check)
                file_output = run_external_command(["file", bin_to_check], print_output=False)
                # Make sure we have both arm64 and x86
                if not ("x86_64" in file_output and "arm64" in file_output):
                    raise RuntimeError("Non-universal2 binary found!")

        # Only continue if we can sign
        if authority:
            # We use PyInstaller to sign the main SABnzbd executable and the SABnzbd.app
            files_already_signed = [
                "dist/SABnzbd.app/Contents/MacOS/SABnzbd",
                "dist/SABnzbd.app",
            ]
            for file_to_check in files_already_signed:
                print("Checking signature of %s" % file_to_check)
                sign_result = run_external_command(
                    [
                        "codesign",
                        "-dv",
                        "-r-",
                        file_to_check,
                    ],
                    print_output=False,
                ) + run_external_command(
                    [
                        "codesign",
                        "--verify",
                        "--deep",
                        file_to_check,
                    ],
                    print_output=False,
                )
                if authority not in sign_result or "adhoc" in sign_result or "invalid" in sign_result:
                    raise RuntimeError("Signature of %s seems invalid!" % file_to_check)

            # Only notarize for real builds that we want to deploy
            if notarization_user and notarization_pass and RELEASE_THIS:
                # Prepare zip to upload to notarization service
                print("Creating zip to send to Apple notarization service")
                # We need to use ditto, otherwise the signature gets lost!
                notarization_zip = RELEASE_NAME + ".zip"
                run_external_command(
                    ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", "dist/SABnzbd.app", notarization_zip]
                )

                # Upload to Apple
                print("Sending zip to Apple notarization service")
                upload_result = run_external_command(
                    [
                        "xcrun",
                        "notarytool",
                        "submit",
                        notarization_zip,
                        "--apple-id",
                        notarization_user,
                        "--team-id",
                        authority,
                        "--password",
                        notarization_pass,
                        "--wait",
                    ],
                )

                # Check if success
                if "status: accepted" not in upload_result.lower():
                    raise RuntimeError("Failed to notarize..")

                # Staple the notarization!
                print("Approved! Stapling the result to the app")
                run_external_command(["xcrun", "stapler", "staple", "dist/SABnzbd.app"])
            elif notarization_user and notarization_pass:
                print("Notarization skipped, tag commit to trigger notarization!")
            else:
                print("Notarization skipped, NOTARIZATION_USER or NOTARIZATION_PASS missing.")
        else:
            print("Signing skipped, missing SIGNING_AUTH.")

        # Test the release, as the very last step to not mess with any release code
        test_sab_binary("dist/SABnzbd.app/Contents/MacOS/SABnzbd")

    if "source" in sys.argv:
        # Prepare Source distribution package.
        # We assume the sources are freshly cloned from the repo
        # Make sure all source files are Unix format
        src_folder = "srcdist"
        safe_remove(src_folder)
        os.mkdir(src_folder)

        # Remove any leftovers
        safe_remove(RELEASE_SRC)

        # Add extra files and folders need for source dist
        EXTRA_FOLDERS.extend(["sabnzbd/", "po/", "linux/", "tools/", "tests/"])
        EXTRA_FILES.extend(["SABnzbd.py", "requirements.txt"])

        # Copy all folders and files to the new folder
        for source_folder in EXTRA_FOLDERS:
            shutil.copytree(source_folder, os.path.join(src_folder, source_folder), dirs_exist_ok=True)

        # Copy all files
        for source_file in EXTRA_FILES:
            shutil.copyfile(source_file, os.path.join(src_folder, source_file))

        # Make sure all line-endings are correct
        for input_filename in glob.glob("%s/**/*.*" % src_folder, recursive=True):
            base, ext = os.path.splitext(input_filename)
            if ext.lower() not in (".py", ".txt", ".css", ".js", ".tmpl", ".sh", ".cmd"):
                continue
            print(input_filename)

            with open(input_filename, "rb") as input_data:
                data = input_data.read()
            data = data.replace(b"\r", b"")
            with open(input_filename, "wb") as output_data:
                output_data.write(data)

        # Create tar.gz file for source distro
        with tarfile.open(RELEASE_SRC, "w:gz") as tar_output:
            for root, dirs, files in os.walk(src_folder):
                for _file in files:
                    input_path = os.path.join(root, _file)
                    if sys.platform == "win32":
                        tar_path = input_path.replace("srcdist\\", RELEASE_NAME + "/").replace("\\", "/")
                    else:
                        tar_path = input_path.replace("srcdist/", RELEASE_NAME + "/")
                    tarinfo = tar_output.gettarinfo(input_path, tar_path)
                    tarinfo.uid = 0
                    tarinfo.gid = 0
                    if _file in ("SABnzbd.py", "Sample-PostProc.sh", "make_mo.py", "msgfmt.py"):
                        # Force Linux/OSX scripts as executable
                        tarinfo.mode = 0o755
                    else:
                        tarinfo.mode = 0o644

                    with open(input_path, "rb") as f:
                        tar_output.addfile(tarinfo, f)

        # Remove source folder
        safe_remove(src_folder)

    # Reset!
    run_git_command(["reset", "--hard"])
    run_git_command(["clean", "-f"])
