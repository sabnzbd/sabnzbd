#!/usr/bin/python3 -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
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
import hashlib
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
import pkginfo
import github
from typing import List


VERSION_FILE = "sabnzbd/version.py"
SPEC_FILE = "SABnzbd.spec"

# Also modify these in "SABnzbd.spec"!
extra_files = [
    "README.mkd",
    "INSTALL.txt",
    "LICENSE.txt",
    "GPL2.txt",
    "GPL3.txt",
    "COPYRIGHT.txt",
    "ISSUES.txt",
    "PKG-INFO",
]

extra_folders = [
    "scripts/",
    "licenses/",
    "locale/",
    "email/",
    "interfaces/Glitter/",
    "interfaces/wizard/",
    "interfaces/Config/",
    "scripts/",
    "icons/",
]


# Support functions
def safe_remove(path):
    """Remove file without erros if the file doesn't exist
    Can also handle folders
    """
    if os.path.exists(path):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


def delete_files_glob(name):
    """Delete one file or set of files from wild-card spec"""
    for f in glob.glob(name):
        if os.path.exists(f):
            os.remove(f)


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
        for _ in range(10):
            try:
                urllib.request.urlopen(base_url, timeout=1).read()
                break
            except:
                time.sleep(1)
        else:
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
            print(log_file.read())

        # So we have time to print the file before the directory is removed
        time.sleep(1)


if __name__ == "__main__":
    # Was any option supplied?
    if len(sys.argv) < 2:
        raise TypeError("Please specify what to do")

    # Make sure we are in the src folder
    if not os.path.exists("builder"):
        raise FileNotFoundError("Run from the main SABnzbd source folder: python builder/package.py")

    # Extract version info
    RELEASE_VERSION = pkginfo.Develop(".").version

    # Check if we have the needed certificates
    try:
        import certifi
    except ImportError:
        raise FileNotFoundError("Need certifi module")

    # Define release name
    RELEASE_NAME = "SABnzbd-%s" % RELEASE_VERSION
    RELEASE_TITLE = "SABnzbd %s" % RELEASE_VERSION
    RELEASE_SRC = RELEASE_NAME + "-src.tar.gz"
    RELEASE_BINARY_32 = RELEASE_NAME + "-win32-bin.zip"
    RELEASE_BINARY_64 = RELEASE_NAME + "-win64-bin.zip"
    RELEASE_INSTALLER = RELEASE_NAME + "-win-setup.exe"
    RELEASE_MACOS = RELEASE_NAME + "-osx.dmg"
    RELEASE_README = "README.mkd"

    # Patch release file
    patch_version_file(RELEASE_VERSION)

    # To draft a release or not to draft a release?
    ON_GITHUB_ACTIONS = os.environ.get("CI", False)
    RELEASE_THIS = "refs/tags/" in os.environ.get("GITHUB_REF", "")

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
    shutil.copyfile("builder/%s" % SPEC_FILE, SPEC_FILE)

    if "binary" in sys.argv or "installer" in sys.argv:
        # Must be run on Windows
        if sys.platform != "win32":
            raise RuntimeError("Binary should be created on Windows")

        # Check what architecture we are on
        RELEASE_BINARY = RELEASE_BINARY_32
        if platform.architecture()[0] == "64bit":
            RELEASE_BINARY = RELEASE_BINARY_64

        # Remove any leftovers
        safe_remove(RELEASE_BINARY)

        # Run PyInstaller and check output
        run_external_command([sys.executable, "-O", "-m", "PyInstaller", "SABnzbd.spec"])

        shutil.copytree("dist/SABnzbd-console", "dist/SABnzbd", dirs_exist_ok=True)
        safe_remove("dist/SABnzbd-console")

        # Remove unwanted DLL's
        delete_files_glob("dist/SABnzbd/api-ms-win*.dll")
        delete_files_glob("dist/SABnzbd/mfc140u.dll")
        delete_files_glob("dist/SABnzbd/ucrtbase.dll")

        # Remove other files we don't need
        delete_files_glob("dist/SABnzbd/PKG-INFO")
        delete_files_glob("dist/SABnzbd/win32ui.pyd")
        delete_files_glob("dist/SABnzbd/winxpgui.pyd")

        if "installer" in sys.argv:
            # Needs to be run on 64 bit
            if RELEASE_BINARY != RELEASE_BINARY_64:
                raise RuntimeError("Installer should be created on 64bit Python")

            # Compile NSIS translations
            safe_remove("NSIS_Installer.nsi")
            safe_remove("NSIS_Installer.nsi.tmp")
            shutil.copyfile("builder/win/NSIS_Installer.nsi", "NSIS_Installer.nsi")
            run_external_command([sys.executable, "tools/make_mo.py", "nsis"])

            # Remove 32bit external executables
            delete_files_glob("dist/SABnzbd/win/par2/multipar/par2j.exe")
            delete_files_glob("dist/SABnzbd/win/unrar/UnRAR.exe")

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
                "osx/par2/par2-sl64",
                "osx/par2/arm64/par2",
                "osx/par2/arm64/libomp.dylib",
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
        extra_folders.extend(["sabnzbd/", "po/", "linux/", "tools/", "tests/"])
        extra_files.extend(["SABnzbd.py", "requirements.txt"])

        # Copy all folders and files to the new folder
        for source_folder in extra_folders:
            shutil.copytree(source_folder, os.path.join(src_folder, source_folder), dirs_exist_ok=True)

        # Copy all files
        for source_file in extra_files:
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

        # Calculate hashes for Synology release
        with open(RELEASE_SRC, "rb") as inp_file:
            source_data = inp_file.read()

        print("----")
        print(RELEASE_SRC, "SHA1", hashlib.sha1(source_data).hexdigest())
        print(RELEASE_SRC, "SHA256", hashlib.sha256(source_data).hexdigest())
        print(RELEASE_SRC, "MD5", hashlib.md5(source_data).hexdigest())
        print("----")

    # Release to github
    if "release" in sys.argv:
        # Check if tagged as release and check for token
        gh_token = os.environ.get("AUTOMATION_GITHUB_TOKEN", "")
        if RELEASE_THIS and gh_token:
            gh_obj = github.Github(gh_token)
            gh_repo = gh_obj.get_repo("sabnzbd/sabnzbd")

            # Read the release notes
            with open(RELEASE_README, "r") as readme_file:
                readme_data = readme_file.read()

            # Pre-releases are longer than 6 characters (e.g. 3.1.0Beta1 vs 3.1.0, but also 3.0.11)
            prerelease = len(RELEASE_VERSION) > 5

            # We have to manually check if we already created this release
            for release in gh_repo.get_releases():
                if release.tag_name == RELEASE_VERSION:
                    gh_release = release
                    print("Found existing release %s" % gh_release.title)
                    break
            else:
                # Did not find it, so create the release, use the GitHub tag we got as input
                print("Creating GitHub release SABnzbd %s" % RELEASE_VERSION)
                gh_release = gh_repo.create_git_release(
                    tag=RELEASE_VERSION,
                    name=RELEASE_TITLE,
                    message=readme_data,
                    draft=True,
                    prerelease=prerelease,
                )

            # Fetch existing assets, as overwriting is not allowed by GitHub
            gh_assets = gh_release.get_assets()

            # Upload the assets
            files_to_check = (
                RELEASE_SRC,
                RELEASE_BINARY_32,
                RELEASE_BINARY_64,
                RELEASE_INSTALLER,
                RELEASE_MACOS,
                RELEASE_README,
            )
            for file_to_check in files_to_check:
                if os.path.exists(file_to_check):
                    # Check if this file was previously uploaded
                    if gh_assets.totalCount:
                        for gh_asset in gh_assets:
                            if gh_asset.name == file_to_check:
                                print("Removing existing asset %s " % gh_asset.name)
                                gh_asset.delete_asset()
                    # Upload the new one
                    print("Uploading %s to release %s" % (file_to_check, gh_release.title))
                    gh_release.upload_asset(file_to_check)

            # Check if we now have all files
            gh_new_assets = gh_release.get_assets()
            if gh_new_assets.totalCount:
                all_assets = [gh_asset.name for gh_asset in gh_new_assets]

                # Check if we have all files, using set-comparison
                if set(files_to_check) == set(all_assets):
                    print("All assets present, releasing %s" % RELEASE_VERSION)
                    # Publish release
                    gh_release.update_release(
                        tag_name=RELEASE_VERSION,
                        name=RELEASE_TITLE,
                        message=readme_data,
                        draft=False,
                        prerelease=prerelease,
                    )

            # Update the website
            gh_repo_web = gh_obj.get_repo("sabnzbd/sabnzbd.github.io")
            # Check if the branch already exists, only create one if it doesn't
            skip_website_update = False
            try:
                gh_repo_web.get_branch(RELEASE_VERSION)
                print("Branch %s on sabnzbd/sabnzbd.github.io already exists, skipping update" % RELEASE_VERSION)
                skip_website_update = True
            except github.GithubException:
                # Create a new branch to have the changes
                sb = gh_repo_web.get_branch("master")
                print("Creating branch %s on sabnzbd/sabnzbd.github.io" % RELEASE_VERSION)
                new_branch = gh_repo_web.create_git_ref(ref="refs/heads/" + RELEASE_VERSION, sha=sb.commit.sha)

            # Update the files
            if not skip_website_update:
                # We need bytes version to interact with GitHub
                RELEASE_VERSION_BYTES = RELEASE_VERSION.encode()

                # Get all the version files
                latest_txt = gh_repo_web.get_contents("latest.txt")
                latest_txt_items = latest_txt.decoded_content.split()
                new_latest_txt_items = latest_txt_items[:2]
                config_yml = gh_repo_web.get_contents("_config.yml")
                if prerelease:
                    # If it's a pre-release, we append to current version in latest.txt
                    new_latest_txt_items.extend([RELEASE_VERSION_BYTES, latest_txt_items[1]])
                    # And replace in _config.yml
                    new_config_yml = re.sub(
                        b"latest_testing: '[^']*'",
                        b"latest_testing: '%s'" % RELEASE_VERSION_BYTES,
                        config_yml.decoded_content,
                    )
                else:
                    # New stable release, replace the version
                    new_latest_txt_items[0] = RELEASE_VERSION_BYTES
                    # And replace in _config.yml
                    new_config_yml = re.sub(
                        b"latest_testing: '[^']*'",
                        b"latest_testing: ''",
                        config_yml.decoded_content,
                    )
                    new_config_yml = re.sub(
                        b"latest_stable: '[^']*'",
                        b"latest_stable: '%s'" % RELEASE_VERSION_BYTES,
                        new_config_yml,
                    )
                    # Also update the wiki-settings, these only use x.x notation
                    new_config_yml = re.sub(
                        b"wiki_version: '[^']*'",
                        b"wiki_version: '%s'" % RELEASE_VERSION_BYTES[:3],
                        new_config_yml,
                    )

                # Update the files
                print("Updating latest.txt")
                gh_repo_web.update_file(
                    "latest.txt",
                    "Release %s: latest.txt" % RELEASE_VERSION,
                    b"\n".join(new_latest_txt_items),
                    latest_txt.sha,
                    RELEASE_VERSION,
                )
                print("Updating _config.yml")
                gh_repo_web.update_file(
                    "_config.yml",
                    "Release %s: _config.yml" % RELEASE_VERSION,
                    new_config_yml,
                    config_yml.sha,
                    RELEASE_VERSION,
                )

                # Create pull-request
                print("Creating pull request in sabnzbd/sabnzbd.github.io for the update")
                gh_repo_web.create_pull(
                    title=RELEASE_VERSION,
                    base="master",
                    body="Automated update of release files",
                    head=RELEASE_VERSION,
                )
        else:
            print("To push release to GitHub, first tag the commit.")
            print("Or missing the AUTOMATION_GITHUB_TOKEN, cannot push to GitHub without it.")

    # Reset!
    run_git_command(["reset", "--hard"])
    run_git_command(["clean", "-f"])
