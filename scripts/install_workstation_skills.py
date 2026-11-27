#!/usr/bin/env python3
"""Install repo-managed skills into a workstation folder without overwriting files."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(".claude/skills"))
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("/workspace/abinath-ai-workstation/skills"),
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if not source.is_dir():
        print(f"Skill source directory does not exist: {source}", file=sys.stderr)
        return 2

    files = sorted(path for path in source.rglob("*") if path.is_file())
    if not files:
        print(f"No skill files found under: {source}", file=sys.stderr)
        return 2

    conflicts: list[Path] = []
    pending: list[tuple[Path, Path]] = []
    for source_file in files:
        relative = source_file.relative_to(source)
        target_file = destination / relative
        if target_file.exists():
            if not target_file.is_file() or target_file.read_bytes() != source_file.read_bytes():
                conflicts.append(target_file)
        else:
            pending.append((source_file, target_file))

    if conflicts:
        print("Refusing to overwrite differing existing files:", file=sys.stderr)
        for path in conflicts:
            print(f"  {path}", file=sys.stderr)
        return 3

    for source_file, target_file in pending:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)

    unchanged = len(files) - len(pending)
    print(f"Installed {len(pending)} new skill files into {destination}")
    print(f"Left {unchanged} identical pre-existing files unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
