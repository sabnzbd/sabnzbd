#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

"""
po_to_json - Export untranslated strings from PO files to JSON and merge translations back.

This utility is intended for AI-assisted translation workflows:
- Export untranslated PO entries into a small JSON payload.
- Let an AI (or human) fill the `translation` fields.
- Merge the JSON back into PO files.

Quick usage:
1) Export:
   python tools/po_to_json.py --mode export --po-dir po/main --languages cs --output tools/cs.json
2) Fill `translation` values in the JSON.
3) Dry-run merge:
   python tools/po_to_json.py --mode merge --input tools/cs.json --languages cs --dry-run
4) Apply merge:
   python tools/po_to_json.py --mode merge --input tools/cs.json --languages cs

Guidance for (AI) translators:
Before filling the `translation` fields, read the existing translations in the
same target `.po` file and use them as the primary style reference. Each JSON
entry includes its `file` so you know which `.po` to consult. Match the existing
translations of that language, specifically:
- Tone and formality (for example, Dutch uses the informal "je").
- Established terminology and word choices already used for recurring terms
  (for example, in Dutch a "job" is translated as "download").
- Reuse existing phrasings for concepts that already appear (for example, the
  Dutch "map voor voltooide downloads" for the completed-download folder).
- Keep formatting intact: placeholders (%s, %d, %f), HTML tags (<br />, <b>),
  and URLs must be preserved exactly as in the `msgid`.
The goal is consistency with the existing translation, not a literal,
word-for-word conversion.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polib


def export_untranslated(po_root: Path, output_path: Path, selected_languages: set[str] | None) -> None:
    entries: list[dict] = []
    for po_file in sorted(po_root.rglob("*.po")):
        language = po_file.stem
        if selected_languages is not None and language not in selected_languages:
            continue
        po_data = polib.pofile(str(po_file))
        for entry in po_data:
            if entry.msgstr != "":
                continue
            entries.append(
                {
                    "file": po_file.as_posix(),
                    "msgid": entry.msgid,
                    "translation": None,
                    "comment": entry.tcomment or None,
                }
            )

    payload = {"entries": entries}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} untranslated entries to {output_path.as_posix()}")


def merge_translations(input_path: Path, dry_run: bool, selected_languages: set[str] | None) -> None:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError("Invalid JSON format: missing 'entries' list")

    updates_by_file: dict[Path, list[dict]] = {}
    for item in entries:
        po_file = Path(item.get("file", ""))
        if not po_file:
            continue
        language = po_file.stem
        if selected_languages is not None and language not in selected_languages:
            continue
        updates_by_file.setdefault(po_file, []).append(item)

    files_touched = 0
    entries_updated = 0
    entries_skipped = 0

    for po_file, updates in sorted(updates_by_file.items()):
        if not po_file.exists():
            entries_skipped += len(updates)
            continue
        po_data = polib.pofile(str(po_file))
        index = {}
        for entry in po_data:
            index[(entry.msgctxt, entry.msgid)] = entry
        file_updated = False

        for item in updates:
            key = (item.get("msgctxt"), item.get("msgid", ""))
            entry = index.get(key)
            if entry is None:
                entries_skipped += 1
                continue

            translation = item.get("translation")
            if isinstance(translation, str) and translation != entry.msgstr:
                entry.msgstr = translation
                entries_updated += 1
                file_updated = True
            else:
                entries_skipped += 1

        if file_updated:
            files_touched += 1
            if not dry_run:
                po_data.save(str(po_file))

    mode_suffix = " (dry-run)" if dry_run else ""
    print(
        f"Merged translations{mode_suffix}: "
        f"{entries_updated} updated, "
        f"{entries_skipped} skipped, "
        f"{files_touched} files touched"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export untranslated PO entries to JSON and merge translations back (for AI-assisted translation workflows)"
    )
    parser.add_argument("--mode", choices=("export", "merge"), default="export")
    parser.add_argument("--po-dir", default="po", help="Root directory containing .po files")
    parser.add_argument("--output", default="tools/untranslated_po.json", help="Output JSON path for export mode")
    parser.add_argument("--input", default="tools/untranslated_po.json", help="Input JSON path for merge mode")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--languages", nargs="+", default=None, help="Only process specific languages")
    args = parser.parse_args()

    if not Path("po").exists():
        raise RuntimeError("Make sure to run from root directory of SABnzbd")

    selected_languages = None
    if args.languages:
        selected_languages = {language.strip() for language in args.languages if language.strip()}

    if args.mode == "export":
        po_root = Path(args.po_dir)
        if not po_root.exists():
            raise RuntimeError(f"PO directory does not exist: {po_root}")
        export_untranslated(
            po_root=po_root,
            output_path=Path(args.output),
            selected_languages=selected_languages,
        )
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            raise RuntimeError(f"Input JSON does not exist: {input_path}")
        merge_translations(input_path=input_path, dry_run=args.dry_run, selected_languages=selected_languages)


if __name__ == "__main__":
    main()
