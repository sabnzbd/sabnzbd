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
import platform
import re
import sys
import os
import time
import shutil
import subprocess
import tarfile
import pkginfo
import github
from distutils.dir_util import copy_tree


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
    "interfaces/Plush/",
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
    """ Delete one file or set of files from wild-card spec """
    for f in glob.glob(name):
        if os.path.exists(f):
            os.remove(f)


def run_external_command(command):
    """ Wrapper to ease the use of calling external programs """
    process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output, _ = process.communicate()
    ret = process.wait()
    if output:
        print(output)
    if ret != 0:
        raise RuntimeError("Command returned non-zero exit code %s!" % ret)
    return output


def run_git_command(parms):
    """ Run git command, raise error if it failed """
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
    RELEASE_THIS = "draft release" in run_git_command(["log", "-1", "--pretty=format:%b"])

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

        # Use special distutils function to merge the main and console directories
        copy_tree("dist/SABnzbd-console", "dist/SABnzbd")
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
        os.rename("dist/SABnzbd", RELEASE_NAME)

        # Create the archive
        run_external_command(["win/7zip/7za.exe", "a", RELEASE_BINARY, RELEASE_NAME])

    if "app" in sys.argv:
        # Must be run on macOS
        if sys.platform != "darwin":
            raise RuntimeError("App should be created on macOS")

        # Who will sign and notarize this?
        authority = os.environ.get("SIGNING_AUTH")
        notarization_user = os.environ.get("NOTARIZATION_USER")
        notarization_pass = os.environ.get("NOTARIZATION_PASS")

        # Run PyInstaller and check output
        run_external_command([sys.executable, "-O", "-m", "PyInstaller", "SABnzbd.spec"])

        # Only continue if we can sign
        if authority:
            files_to_sign = [
                "dist/SABnzbd.app/Contents/MacOS/osx/par2/par2-sl64",
                "dist/SABnzbd.app/Contents/MacOS/osx/7zip/7za",
                "dist/SABnzbd.app/Contents/MacOS/osx/unrar/unrar",
                "dist/SABnzbd.app/Contents/MacOS/SABnzbd",
                "dist/SABnzbd.app",
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
                        "-i",
                        "org.sabnzbd.sabnzbd",
                        "-s",
                        authority,
                        file_to_sign,
                    ],
                )
                print("Signed %s!" % file_to_sign)

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
                upload_process = run_external_command(
                    [
                        "xcrun",
                        "altool",
                        "--notarize-app",
                        "-t",
                        "osx",
                        "-f",
                        notarization_zip,
                        "--primary-bundle-id",
                        "org.sabnzbd.sabnzbd",
                        "-u",
                        notarization_user,
                        "-p",
                        notarization_pass,
                    ],
                )

                # Extract the notarization ID
                m = re.match(".*RequestUUID = (.*?)\n", upload_process, re.S)
                if not m:
                    raise RuntimeError("No UUID created")
                uuid = m.group(1)

                print("Checking notarization of UUID: %s (every 30 seconds)" % uuid)
                notarization_in_progress = True
                while notarization_in_progress:
                    time.sleep(30)
                    check_status = run_external_command(
                        [
                            "xcrun",
                            "altool",
                            "--notarization-info",
                            uuid,
                            "-u",
                            notarization_user,
                            "-p",
                            notarization_pass,
                        ],
                    )
                    notarization_in_progress = "Status: in progress" in check_status

                # Check if success
                if "Status: success" not in check_status:
                    raise RuntimeError("Failed to notarize..")

                # Staple the notarization!
                print("Approved! Stapling the result to the app")
                run_external_command(["xcrun", "stapler", "staple", "dist/SABnzbd.app"])
            elif notarization_user and notarization_pass:
                print("Notarization skipped, add 'draft release' to the commit message trigger notarization!")
            else:
                print("Notarization skipped, NOTARIZATION_USER or NOTARIZATION_PASS missing.")
        else:
            print("Signing skipped, missing SIGNING_AUTH.")

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
            copy_tree(source_folder, os.path.join(src_folder, source_folder))

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
            print("To push release to GitHub, add 'draft release' to the commit message.")
            print("Or missing the AUTOMATION_GITHUB_TOKEN, cannot push to GitHub without it.")

    # Reset!
    run_git_command(["reset", "--hard"])
    run_git_command(["clean", "-f"])
