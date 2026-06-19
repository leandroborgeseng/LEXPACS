#!/usr/bin/env python3
"""Política E5: manter 7 backups diários + 4 semanais (mais recente de cada dia/semana)."""
from __future__ import annotations

import os
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")


def parse_stamp(name: str) -> datetime | None:
    try:
        return datetime.strptime(name, "%Y-%m-%d_%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def apply_retention(
    backup_root: Path,
    *,
    daily_count: int = 7,
    weekly_count: int = 4,
) -> list[str]:
    if not backup_root.is_dir():
        return []

    entries: list[tuple[datetime, Path]] = []
    for child in backup_root.iterdir():
        if child.is_dir() and STAMP_RE.match(child.name):
            stamp = parse_stamp(child.name)
            if stamp:
                entries.append((stamp, child))

    if not entries:
        return []

    entries.sort(key=lambda item: item[0], reverse=True)
    now = datetime.now(timezone.utc)
    keep: set[Path] = set()

    by_day: dict = {}
    for stamp, path in entries:
        day = stamp.date()
        if day not in by_day or stamp > by_day[day][0]:
            by_day[day] = (stamp, path)

    for day in sorted(by_day.keys(), reverse=True)[:daily_count]:
        keep.add(by_day[day][1])

    daily_cutoff = (now - timedelta(days=daily_count)).date()
    by_week: dict = defaultdict(lambda: None)
    for stamp, path in entries:
        if path in keep or stamp.date() >= daily_cutoff:
            continue
        week = stamp.isocalendar()[:2]
        current = by_week[week]
        if current is None or stamp > current[0]:
            by_week[week] = (stamp, path)

    for _, (_, path) in sorted(by_week.values(), key=lambda item: item[0], reverse=True)[:weekly_count]:
        keep.add(path)

    removed: list[str] = []
    for _, path in entries:
        if path in keep:
            continue
        print(f"Retenção: removendo {path.name}")
        shutil.rmtree(path)
        removed.append(path.name)

    kept_names = sorted(p.name for p in keep)
    print(
        f"Retenção: {len(kept_names)} mantido(s) "
        f"({daily_count} diários + {weekly_count} semanais), {len(removed)} removido(s)"
    )
    return removed


def main() -> int:
    backup_root = Path(sys.argv[1] if len(sys.argv) > 1 else "./backups")
    daily = int(os.environ.get("BACKUP_RETENTION_DAILY", "7"))
    weekly = int(os.environ.get("BACKUP_RETENTION_WEEKLY", "4"))
    apply_retention(backup_root, daily_count=daily, weekly_count=weekly)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
