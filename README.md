SABnzbd - The automated Usenet download tool
============================================

[![AppVeryor](https://ci.appveyor.com/api/projects/status/github/sabnzbd/sabnzbd?svg=true&branch=master)]()
[![Travis CI](https://travis-ci.org/sabnzbd/sabnzbd.svg?branch=master)](https://travis-ci.org/sabnzbd/sabnzbd)

SABnzbd is an Open Source Binary Newsreader written in Python.

It's totally free, incredibly easy to use, and works practically everywhere.
SABnzbd makes Usenet as simple and streamlined as possible by automating everything we can. All you have to do is add an `.nzb`. SABnzbd takes over from there, where it will be automatically downloaded, verified, repaired, extracted and filed away with zero human interaction.
If you want to know more you can head over to our website: https://sabnzbd.org.

## Resolving Dependencies

SABnzbd has a good deal of dependencies you'll need before you can get running. If you've previously run SABnzbd from one of the various Linux packages, then you likely already have all the needed dependencies. If not, here's what you're looking for:

- `python` (only 2.7.x and higher, but not 3.x.x)
- `python-cheetah`
- `par2` (Multi-threaded par2 installation guide can be found [here](https://sabnzbd.org/wiki/installation/multicore-par2))
- `unrar` (Make sure you get the "official" non-free version of unrar)
- `sabyenc` (installation guide can be found [here](https://sabnzbd.org/sabyenc))

Optional:
- `python-cryptography` (enables certificate generation and detection of encrypted RAR-files during download)
- `python-dbus` (enable option to Shutdown/Restart/Standby PC on queue finish)
- `7zip`

Your package manager should supply these. If not, we've got links in our more in-depth [installation guide](https://github.com/sabnzbd/sabnzbd/blob/master/INSTALL.txt).

## Running SABnzbd from source

Once you've sorted out all the dependencies, simply run:

```
python -OO SABnzbd.py
```

Or, if you want to run in the background:

```
python -OO SABnzbd.py -d -f /path/to/sabnzbd.ini
```

If you want multi-language support, run:

```
python tools/make_mo.py
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
