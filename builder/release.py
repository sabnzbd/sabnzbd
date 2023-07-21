#!/usr/bin/python3 -OO
# Copyright 2008-2017 The SABnzbd-Team (sabnzbd.org)
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

import hashlib
import json
import os
import re
import shutil
import xml.etree.ElementTree as ET

import github
import praw

from constants import (
    RELEASE_VERSION,
    PRERELEASE,
    RELEASE_SRC,
    RELEASE_BINARY_32,
    RELEASE_BINARY_64,
    RELEASE_INSTALLER,
    RELEASE_MACOS,
    RELEASE_README,
    RELEASE_THIS,
    RELEASE_TITLE,
    APPDATA_FILE,
)

# Verify we have all assets
files_to_check = (
    RELEASE_SRC,
    RELEASE_BINARY_32,
    RELEASE_BINARY_64,
    RELEASE_INSTALLER,
    RELEASE_MACOS,
    RELEASE_README,
)
for file_to_check in files_to_check:
    if not os.path.exists(file_to_check):
        raise RuntimeError("Not all release files are present!")
print("All release files are present")

# Verify that appdata file is updated
if not PRERELEASE:
    if not isinstance(ET.parse(APPDATA_FILE).find(f"./releases/release[@version='{RELEASE_VERSION}']"), ET.Element):
        raise RuntimeError(f"Could not find {RELEASE_VERSION} in {APPDATA_FILE}")

# Calculate hashes for Synology release
with open(RELEASE_SRC, "rb") as inp_file:
    source_data = inp_file.read()

print("---- Synology spksrc digest hashes ---- ")
print(RELEASE_SRC, "SHA1", hashlib.sha1(source_data).hexdigest())
print(RELEASE_SRC, "SHA256", hashlib.sha256(source_data).hexdigest())
print(RELEASE_SRC, "MD5", hashlib.md5(source_data).hexdigest())
print("----")

# Check if tagged as release and check for token
gh_token = os.environ.get("AUTOMATION_GITHUB_TOKEN", "")
if RELEASE_THIS and gh_token:
    gh_obj = github.Github(gh_token)
    gh_repo = gh_obj.get_repo("sabnzbd/sabnzbd")

    # Read the release notes
    with open(RELEASE_README, "r") as readme_file:
        readme_data = readme_file.read()

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
            prerelease=PRERELEASE,
        )

    # Fetch existing assets, as overwriting is not allowed by GitHub
    gh_assets = gh_release.get_assets()

    # Upload the assets
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
                prerelease=PRERELEASE,
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
        if PRERELEASE:
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
        update_pr = gh_repo_web.create_pull(
            title="Release %s" % RELEASE_VERSION,
            base="master",
            body="Automated update of release files",
            head=RELEASE_VERSION,
        )

        # Merge pull-request
        print("Merging pull request in sabnzbd/sabnzbd.github.io for the update")
        update_pr.merge(merge_method="squash")

    # Only with GitHub success we proceed to Reddit
    if reddit_token := os.environ.get("REDDIT_TOKEN", ""):
        # Token format (without whitespace):
        # {
        #     "client_id":"XXX",
        #     "client_secret":"XXX",
        #     "user_agent":"SABnzbd release script",
        #     "username":"Safihre",
        #     "password":"XXX"
        # }
        credentials = json.loads(reddit_token)
        reddit = praw.Reddit(**credentials)

        subreddit_sabnzbd = reddit.subreddit("sabnzbd")
        subreddit_usenet = reddit.subreddit("usenet")

        # Read the release notes
        with open(RELEASE_README, "r") as readme_file:
            readme_lines = readme_file.readlines()

        # Put the download link after the title
        readme_lines[2] = "## https://sabnzbd.org/downloads\n"

        # Use the header in the readme as title
        title = readme_lines[0]
        release_notes_text = "".join(readme_lines[2:])

        # Only stable releases to r/usenet
        if not PRERELEASE:
            print("Posting release notes to Reddit: r/usenet")
            submission = subreddit_usenet.submit(title, selftext=release_notes_text)

            # Cross-post to r/SABnzbd
            print("Cross-posting release notes to Reddit: r/sabnzbd")
            submission.crosspost(subreddit_sabnzbd)
        else:
            # Post always to r/SABnzbd
            print("Posting release notes to Reddit: r/sabnzbd")
            subreddit_sabnzbd.submit(title, selftext=release_notes_text)

    else:
        print("Missing REDDIT_TOKEN")

else:
    print("To push release to GitHub, first tag the commit.")
    print("Or missing the AUTOMATION_GITHUB_TOKEN, cannot push to GitHub without it.")
