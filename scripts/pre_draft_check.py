#!/usr/bin/env python3
"""
pre_draft_check.py — テーマ・型の疲労チェック

drafts/ 配下の過去ドラフトを読み、直近14日で使った型・テーマを一覧表示する。
失敗DB #7（同じ型の連発は2週間で反応が落ちる）のセルフチェック用。
SocialData API不要。ローカルの drafts/ だけで動く。

ファイル名の想定: drafts/YYYY-MM-DD_*.txt
"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = ROOT / "drafts"

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_")
THEME_RE = re.compile(r"【今日のテーマ】\s*\n(.+)")
POST_HEADER_RE = re.compile(r"【投稿\d+｜([^】]+)】")


def file_date(path: Path):
    m = DATE_RE.match(path.name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def main():
    window_days = int(sys.argv[1]) if len(sys.argv) > 1 else 14

    if not DRAFTS_DIR.exists() or not any(DRAFTS_DIR.glob("*.txt")):
        print(f"{DRAFTS_DIR} にドラフトがまだありません。初回はチェック対象なしです。")
        return

    cutoff = datetime.now().date() - timedelta(days=window_days)
    used_types = []
    used_themes = []

    for path in sorted(DRAFTS_DIR.glob("*.txt")):
        d = file_date(path)
        if d is None or d < cutoff:
            continue
        text = path.read_text(encoding="utf-8")
        theme_m = THEME_RE.search(text)
        if theme_m:
            used_themes.append((d, theme_m.group(1).strip()))
        for label in POST_HEADER_RE.findall(text):
            used_types.append((d, label.strip()))

    print(f"=== 直近{window_days}日の使用履歴（{cutoff}以降） ===\n")

    print("【使用済みテーマ】")
    if used_themes:
        for d, theme in used_themes:
            print(f"  {d}: {theme}")
    else:
        print("  なし")

    print("\n【使用済みの型（投稿見出しラベル）】")
    if used_types:
        for d, label in used_types:
            print(f"  {d}: {label}")
        print("\n  → 上記の型は直近14日以内に使用済みです。writer_rules.md の9型のうち、")
        print("     ここに出ていない型を優先して選んでください（失敗DB #7）。")
    else:
        print("  なし")


if __name__ == "__main__":
    main()
