SABnzbd - The automated Usenet download tool
============================================

This Unicode release is not compatible with 0.7.x queues!

There is also an issue with upgrading of the "sabnzbd.ini" file.
Make sure that you have a backup!

Saved queues may not be compatible after updates.

----

SABnzbd is an Open Source Binary Newsreader written in Python.

It's totally free, incredibly easy to use, and works practically everywhere.

SABnzbd makes Usenet as simple and streamlined as possible by automating everything we can. All you have to do is add an .nzb. SABnzbd takes over from there, where it will be automatically downloaded, verified, repaired, extracted and filed away with zero human interaction.

If you want to know more you can head over to our website: http://sabnzbd.org.

## Resolving Dependencies

SABnzbd has a good deal of dependencies you'll need before you can get running. If you've previously run SABnzbd from one of the various Linux packages floating around (Ubuntu, Debian, Fedora, etc), then you likely already have all the needed dependencies. If not, here's what you're looking for:

- `python` (only 2.7.x and higher, but not 3.x.x)
- `python-cheetah`
- `python-support`
- `par2` (Multi-threaded par2 installation guide can be found [here](https://forums.sabnzbd.org/viewtopic.php?f=16&t=18793#p99702))
- `unrar` (Make sure you get the "official" non-free version of unrar)

Optional:

- `python-cryptography`
- `python-yenc`
- `python-dbus` (enable option to Shutdown/Restart/Standby PC on queue finish)
- `7zip`
- `unzip`

Your package manager should supply these. If not, we've got links in our more in-depth [installation guide](https://github.com/sabnzbd/sabnzbd/blob/master/INSTALL.txt).

## Running SABnzbd from source

Once you've sorted out all the dependencies, simply run:

```
python SABnzbd.py
```

Or, if you want to run in the background:

```
python SABnzbd.py -d -f /path/to/sabnzbd.ini
```

If you want multi-language support, run:

```
python tools/make_mo.py
```

Our many other command line options are explained in depth [here](https://sabnzbd.org/wiki/advanced/command-line-parameters).

## About Our Repo

The workflow we use, is a simplified form of "GitFlow".
Basically:
- "master" contains only stable releases (which have been merged to "master")
- "develop" is the target for integration
- "1.0.x" is a release and maintenance branch for 1.0.x: 1.0.0 -> 1.0.1 -> 1.0.2
- "1.1.x" is a release and maintenance branch for 1.1.x: 1.1.0 -> 1.1.1 -> 1.1.2
- "feature/my_feature" is a temporary feature branch
- "hotfix/my_hotfix is an optional temporary branch for bugfix(es)

Condtions:
- Merging of a stable release into "master" will be simple: the release branch is always right.
- "master" is not merged back to "develop"
- "develop" is not re-based on "master".
- Release branches branch from "develop" only.
- Bugfixes created specifically for a release branch are done there (because they are specific, they're not cherry-picked to "develop").
- Bugfixes done on "develop" may be cherry-picked to a release branch.
- We will not release a 1.0.2 if a 1.1.0 has already been released.
