SABnzbd - The automated Usenet download tool
============================================

[![Average time to resolve an issue](https://isitmaintained.com/badge/resolution/sabnzbd/sabnzbd.svg)](https://isitmaintained.com/project/sabnzbd/sabnzbd "Average time to resolve an issue")
[![Travis CI](https://travis-ci.org/sabnzbd/sabnzbd.svg?branch=develop)](https://travis-ci.org/sabnzbd/sabnzbd)
[![AppVeryor](https://ci.appveyor.com/api/projects/status/github/sabnzbd/sabnzbd?svg=true&branch=develop)](https://ci.appveyor.com/project/Safihre/sabnzbd)
[![Snap Status](https://build.snapcraft.io/badge/sabnzbd/sabnzbd.svg)](https://snapcraft.io/sabnzbd)
[![License](https://img.shields.io/badge/license-GPL%20v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

SABnzbd is an Open Source Binary Newsreader written in Python.

It's totally free, easy to use, and works practically everywhere.
SABnzbd makes Usenet as simple and streamlined as possible by automating everything we can. All you have to do is add an `.nzb`. SABnzbd takes over from there, where it will be automatically downloaded, verified, repaired, extracted and filed away with zero human interaction.
SABnzbd offers an easy setup wizard and has self-analysis tools to verify your setup.

If you want to know more you can head over to our website: https://sabnzbd.org.

## Resolving Dependencies

SABnzbd has a few dependencies you'll need before you can get running. If you've previously run SABnzbd from one of the various Linux packages, then you likely already have all the needed dependencies. If not, here's what you're looking for:

- `python` (Python 3.5 and higher, often called `python3`)
- Python modules listed in `requirements.txt`
- `par2` (Multi-threaded par2 installation guide can be found [here](https://sabnzbd.org/wiki/installation/multicore-par2))
- `unrar` (make sure you get the "official" non-free version of unrar)

Optional:
- See `requirements.txt`

Your package manager should supply these. If not, we've got links in our [installation guide](https://github.com/sabnzbd/sabnzbd/blob/master/INSTALL.txt).

## Running SABnzbd from source

Once you've sorted out all the dependencies, simply run:

```
python3 -OO SABnzbd.py
```

Or, if you want to run in the background:

```
python3 -OO SABnzbd.py -d -f /path/to/sabnzbd.ini
```

If you want multi-language support, run:

```
python3 tools/make_mo.py
```

Our many other command line options are explained in depth [here](https://sabnzbd.org/wiki/advanced/command-line-parameters).

## About Our Repo

The workflow we use, is a simplified form of "GitFlow".
Basically:
- `master` contains only stable releases (which have been merged to `master`) and is intended for end-users.
- `develop` is the target for integration and is **not** intended for end-users.
- `1.1.x` is a release and maintenance branch for 1.1.x (1.1.0 -> 1.1.1 -> 1.1.2) and is **not** intended for end-users.
- `feature/my_feature` is a temporary feature branch based on `develop`.
- `bugfix/my_bugfix` is an optional temporary branch for bugfix(es) based on `develop`.

Conditions:
- Merging of a stable release into `master` will be simple: the release branch is always right.
- `master` is not merged back to `develop`.
- `develop` is not re-based on `master`.
- Release branches branch from `develop` only.
- Bugfixes created specifically for a release branch are done there (because they are specific, they're not cherry-picked to `develop`).
- Bugfixes done on `develop` may be cherry-picked to a release branch.
- We will not release a 1.0.2 if a 1.1.0 has already been released.
