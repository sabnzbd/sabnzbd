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

- `python` (We support Python 2.6 and 2.7)
- `python-cheetah`
- `python-configobj`
- `python-feedparser`
- `python-dbus`
- `python-openssl`
- `python-support`
- `python-yenc`
- `par2` (Multi-threaded par2 can be downloaded from [ChuChuSoft](http://chuchusoft.com/par2_tbb/download.html) )
- `unrar` (Make sure you get the "official" non-free version of unrar)
- `unzip`
- `7zip`

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

Our many other command line options are explained in depth [here](http://wiki.sabnzbd.org/command-line-parameters).

## About Our Repo

We're going to be attempting to follow the [gitflow model](http://nvie.com/posts/a-successful-git-branching-model/), so you can consider "master" to be whatever our present stable release build is (presently 0.6.x) and "develop" to be whatever our next build will be (presently 0.7.x). Once we transition from unstable to stable dev builds we'll create release branches, and encourage you to follow along and help us test.
