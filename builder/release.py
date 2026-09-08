#!/usr/bin/python3 -OO
# Copyright 2008-2026 by The SABnzbd-Team (sabnzbd.org)
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

import json
import os
import re

import github
import praw
import requests

from common import (
    RELEASE_VERSION,
    PRERELEASE,
    RELEASE_SRC,
    RELEASE_WIN_BIN_X64,
    RELEASE_WIN_BIN_ARM64,
    RELEASE_WIN_INSTALLER,
    RELEASE_MACOS,
    RELEASE_README,
    RELEASE_THIS,
    RELEASE_TITLE,
    pe_has_authenticode_signature,
)

# Verify we have all assets
files_to_check = (
    RELEASE_SRC,
    RELEASE_WIN_BIN_X64,
    RELEASE_WIN_BIN_ARM64,
    RELEASE_WIN_INSTALLER,
    RELEASE_MACOS,
    RELEASE_README,
)
for file_to_check in files_to_check:
    if not os.path.exists(file_to_check):
        raise RuntimeError("Release file %s is missing!" % file_to_check)
print("All release files are present")

# When releasing, the Windows installer must be signed
if RELEASE_THIS:
    if not pe_has_authenticode_signature(RELEASE_WIN_INSTALLER):
        raise RuntimeError("%s is not signed!" % RELEASE_WIN_INSTALLER)
    print("%s has an Authenticode signature" % RELEASE_WIN_INSTALLER)

# Check if tagged as release and check for token
gh_token = os.environ.get("AUTOMATION_GITHUB_TOKEN", "")
if RELEASE_THIS and gh_token:
    gh_obj = github.Github(auth=github.Auth.Token(gh_token))
    gh_repo = gh_obj.get_repo("sabnzbd/sabnzbd")

    # Read the release notes (reused for the Reddit post below)
    with open(RELEASE_README, "r") as readme_file:
        readme_data = readme_file.read()

    # Find the existing release for this tag, or create a fresh draft
    try:
        gh_release = gh_repo.get_release(RELEASE_VERSION)
        print("Found existing release %s" % gh_release.name)
    except github.UnknownObjectException:
        print("Creating GitHub release SABnzbd %s" % RELEASE_VERSION)
        gh_release = gh_repo.create_git_release(
            tag=RELEASE_VERSION,
            name=RELEASE_TITLE,
            message=readme_data,
            draft=True,
            prerelease=PRERELEASE,
        )

    # Overwriting an asset isn't allowed by GitHub, so delete any that already exist
    existing_assets = {asset.name: asset for asset in gh_release.get_assets()}
    for file_to_upload in files_to_check:
        if file_to_upload in existing_assets:
            print("Removing existing asset %s" % file_to_upload)
            existing_assets[file_to_upload].delete_asset()
        print("Uploading %s to release %s" % (file_to_upload, gh_release.name))
        gh_release.upload_asset(file_to_upload)

    # Publish the release once all assets are attached
    uploaded_assets = {asset.name for asset in gh_release.get_assets()}
    if set(files_to_check).issubset(uploaded_assets):
        print("All assets present, releasing %s" % RELEASE_VERSION)
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

    # Trigger the Docker image build at linuxserver.io
    # Branch "develop" builds the pre-releases, "master" the stable releases
    if linuxserver_token := os.environ.get("LINUXSERVER_WEBHOOK_TOKEN", ""):
        linuxserver_branch = "develop" if PRERELEASE else "master"
        print("Triggering linuxserver.io Docker build for branch %s" % linuxserver_branch)
        requests.post(
            "https://ci.linuxserver.io/generic-webhook-trigger/invoke?sabnzbd",
            headers={"Authorization": "Bearer %s" % linuxserver_token},
            json={"branch": linuxserver_branch},
            timeout=30,
        ).raise_for_status()
    else:
        print("Missing LINUXSERVER_WEBHOOK_TOKEN")

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

        # Reuse the release notes read earlier, split into lines
        readme_lines = readme_data.splitlines(keepends=True)

        # Put the download link after the title
        readme_lines[2] = "## https://sabnzbd.org/downloads\n\n"

        # Use the header in the readme as title
        title = readme_lines[0]
        release_notes_text = "".join(readme_lines[2:])
        print("Posting release notes to Reddit")

        # Only stable releases to r/usenet
        if not PRERELEASE:
            # Get correct flair-id (required by r/usenet)
            for flair in subreddit_usenet.flair.link_templates.user_selectable():
                if flair["flair_text"] == "News":
                    print("Posting to r/usenet")
                    submission = subreddit_usenet.submit(
                        title, selftext=release_notes_text, flair_id=flair["flair_template_id"]
                    )
                    break
            else:
                raise ValueError("Could not locate flair_text for posting to r/usenet")

        # Post always to r/SABnzbd
        print("Posting to r/sabnzbd")
        subreddit_sabnzbd.submit(title, selftext=release_notes_text)

    else:
        print("Missing REDDIT_TOKEN")

    # Push release notes to Discord via an incoming webhook
    # Separate channels for testing (pre-release) and stable, both are required
    discord_webhook_testing = os.environ.get("DISCORD_WEBHOOK_TESTING", "")
    discord_webhook_stable = os.environ.get("DISCORD_WEBHOOK_STABLE", "")
    if discord_webhook_testing and discord_webhook_stable:
        discord_webhook = discord_webhook_testing if PRERELEASE else discord_webhook_stable
        print("Posting release notes to Discord")
        # Reuse the release notes read earlier: line 0 is the title header
        discord_lines = readme_data.splitlines(keepends=True)
        discord_title = discord_lines[0].lstrip("# ").strip()
        discord_body = "".join(discord_lines[2:])[:4096]
        requests.post(
            discord_webhook,
            json={
                "embeds": [
                    {
                        "title": discord_title,
                        "url": gh_release.html_url,
                        "description": discord_body,
                        "color": 0xFFA500 if PRERELEASE else 0x00A550,
                    }
                ]
            },
            timeout=30,
        ).raise_for_status()
    else:
        print("Missing DISCORD_WEBHOOK_TESTING and/or DISCORD_WEBHOOK_STABLE")

else:
    print("To push release to GitHub, first tag the commit.")
    print("Or missing the AUTOMATION_GITHUB_TOKEN, cannot push to GitHub without it.")
