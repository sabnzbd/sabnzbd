# -*- mode: python -*-
import os
import re
import sys

from PyInstaller.building.api import EXE, COLLECT, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.building.osx import BUNDLE
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

from builder.constants import EXTRA_FILES, EXTRA_FOLDERS, RELEASE_VERSION

# Add extra files in the PyInstaller-spec
extra_pyinstaller_files = []

# Add hidden imports
extra_hiddenimports = ["Cheetah.DummyTransaction", "cheroot.ssl.builtin", "certifi"]
extra_hiddenimports.extend(collect_submodules("apprise"))
extra_hiddenimports.extend(collect_submodules("babelfish.converters"))
extra_hiddenimports.extend(collect_submodules("guessit.data"))

# Add platform specific stuff
if sys.platform == "darwin":
    extra_hiddenimports.extend(["objc", "PyObjCTools"])
    # macOS folders
    EXTRA_FOLDERS += ["osx/par2/", "osx/unrar/", "osx/7zip/"]
    # Add NZB-icon file
    extra_pyinstaller_files.append(("builder/osx/image/nzbfile.icns", "."))
    # Version information is set differently on macOS
    version_info = None
else:
    # Build would fail on non-Windows
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo,
        FixedFileInfo,
        StringFileInfo,
        StringTable,
        StringStruct,
        VarFileInfo,
        VarStruct,
    )

    # Windows
    extra_hiddenimports.extend(["win32timezone", "winrt.windows.foundation.collections"])
    EXTRA_FOLDERS += ["win/multipar/", "win/par2/", "win/unrar/", "win/7zip/"]
    EXTRA_FILES += ["portable.cmd"]

    # Parse the version info
    version_regexed = re.search(r"(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)", RELEASE_VERSION)
    version_tuple = (int(version_regexed.group(1)), int(version_regexed.group(2)), int(version_regexed.group(3)), 0)

    # Detailed instructions are in the PyInstaller documentation
    # We don't include the alpha/beta/rc in the counters
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=version_tuple,
            prodvers=version_tuple,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("Comments", f"SABnzbd {RELEASE_VERSION}"),
                            StringStruct("CompanyName", "The SABnzbd-Team"),
                            StringStruct("FileDescription", f"SABnzbd {RELEASE_VERSION}"),
                            StringStruct("FileVersion", RELEASE_VERSION),
                            StringStruct("LegalCopyright", "The SABnzbd-Team"),
                            StringStruct("ProductName", f"SABnzbd {RELEASE_VERSION}"),
                            StringStruct("ProductVersion", RELEASE_VERSION),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

# Process the extra-files and folders
for file_item in EXTRA_FILES:
    extra_pyinstaller_files.append((file_item, "."))
for folder_item in EXTRA_FOLDERS:
    extra_pyinstaller_files.append((folder_item, folder_item))

# Add babelfish data files
extra_pyinstaller_files.extend(collect_data_files("babelfish"))
extra_pyinstaller_files.extend(collect_data_files("guessit"))
extra_pyinstaller_files.extend(collect_data_files("apprise"))

pyi_analysis = Analysis(
    ["SABnzbd.py"],
    datas=extra_pyinstaller_files,
    hiddenimports=extra_hiddenimports,
    excludes=["ujson", "FixTk", "tcl", "tk", "_tkinter", "tkinter", "Tkinter", "pydoc", "pydoc_data.topics"],
    module_collection_mode={"apprise.plugins": "py"},
)

pyz = PYZ(pyi_analysis.pure, pyi_analysis.zipped_data)

codesign_identity = os.environ.get("SIGNING_AUTH")
if not codesign_identity:
    # PyInstaller needs specifically None, not just an empty value
    codesign_identity = None

# macOS specific parameters are ignored on other platforms
exe = EXE(
    pyz,
    pyi_analysis.scripts,
    [],
    exclude_binaries=True,
    name="SABnzbd",
    console=False,
    append_pkg=False,
    icon="icons/sabnzbd.ico",
    contents_directory=".",
    version=version_info,
    target_arch="universal2",
    entitlements_file="builder/osx/entitlements.plist",
    codesign_identity=codesign_identity,
)

coll = COLLECT(exe, pyi_analysis.binaries, pyi_analysis.zipfiles, pyi_analysis.datas, name="SABnzbd")

# We need to run again for the console-app
if sys.platform == "win32":
    # Enable console=True for this one
    console_exe = EXE(
        pyz,
        pyi_analysis.scripts,
        [],
        exclude_binaries=True,
        name="SABnzbd-console",
        append_pkg=False,
        icon="icons/sabnzbd.ico",
        contents_directory=".",
        version=version_info,
    )

    console_coll = COLLECT(
        console_exe,
        pyi_analysis.binaries,
        pyi_analysis.zipfiles,
        pyi_analysis.datas,
        name="SABnzbd-console",
    )

# Build the APP on macOS
if sys.platform == "darwin":
    info_plist = {
        "NSUIElement": 1,
        "NSPrincipalClass": "NSApplication",
        "CFBundleShortVersionString": RELEASE_VERSION,
        "NSHumanReadableCopyright": "The SABnzbd-Team",
        "CFBundleIdentifier": "org.sabnzbd.sabnzbd",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeExtensions": ["nzb"],
                "CFBundleTypeIconFile": "nzbfile.icns",
                "CFBundleTypeMIMETypes": ["text/nzb"],
                "CFBundleTypeName": "NZB File",
                "CFBundleTypeRole": "Viewer",
                "LSTypeIsPackage": 0,
                "NSPersistentStoreTypeKey": "Binary",
            }
        ],
        "LSMinimumSystemVersion": "10.9",
        "LSEnvironment": {"LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"},
    }

    app = BUNDLE(
        coll,
        name="SABnzbd.app",
        icon="builder/osx/image/sabnzbdplus.icns",
        bundle_identifier="org.sabnzbd.sabnzbd",
        info_plist=info_plist,
    )
