## Repo layout

- Entry points & metadata  
  - `SABnzbd.py`: starts the app.  
  - `README.md` / `README.mkd`: release notes and overview.  
  - `requirements.txt`: runtime deps.

- Core application package `sabnzbd/`  
  - Download engine: `downloader.py` (main loop), `newswrapper.py` (NNTP connections), `urlgrabber.py`, `nzbqueue.py` (queue), `nzbparser.py` (parse NZB), `assembler.py` (writes decoded parts), `decoder.py` (yEnc/UU decode), `articlecache.py` (in-memory/on-disk cache).  
  - Post-processing: `newsunpack.py`, `postproc.py`, `directunpacker.py`, `sorting.py`, `deobfuscate_filenames.py`.  
  - Config/constants/utilities: `cfg.py`, `config.py`, `constants.py`, `misc.py`, `filesystem.py`, `encoding.py`, `lang.py`, `scheduler.py`, `notifier.py`, `emailer.py`, `rss.py`.  
  - UI plumbing: `interface.py`, `skintext.py`, `version.py`, platform helpers (`macosmenu.py`, `sabtray*.py`).  
  - Subpackages: `sabnzbd/nzb/` (NZB model objects), `sabnzbd/utils/` (helpers).

- Web interfaces & assets  
  - `interfaces/Glitter`, `interfaces/Config`, `interfaces/wizard`: HTML/JS/CSS skins.  
  - `icons/`: tray/web icons.  
  - `locale/`, `po/`, `tools/`: translation sources and helper scripts (`make_mo.py`, etc.).

- Testing & samples  
  - `tests/`: pytest suite plus `data/` fixtures and `test_utils/`.  
  - `scripts/`: sample post-processing hooks (`Sample-PostProc.*`).  

- Packaging/build  
  - `builder/`: platform build scripts (DMG/EXE specs, `package.py`, `release.py`).  
  - Platform folders `win/`, `macos/`, `linux/`, `snap/`: installer or platform-specific assets.  
  - `admin/`, `builder/constants.py`, `licenses/`: release and licensing support files.

- Documentation
  - Documentation website source is stored in the `sabnzbd.github.io` repo.
  - This repo is most likely located 1 level up from the root folder of this repo.
  - Documentation is split per SABnzbd version, in the `wiki` folder.
