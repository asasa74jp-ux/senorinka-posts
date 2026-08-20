#!/usr/bin/env python3
"""
daily_report.py — data/*.json をもとに簡易成績表を出す

前提: fetch_today.py で data/YYYY-MM-DD.json が生成されていること
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def load_recent(days: int = 3):
    files = sorted(DATA_DIR.glob("*.json"))[-days:]
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def tweet_views(tweet: dict) -> int:
    for key in ("view_count", "views", "views_count"):
        if key in tweet:
            return tweet[key] or 0
    return 0


def summarize_account(account: dict):
    if not account or "tweets" not in account:
        return None
    followers = account.get("followers_count") or 0
    tweets = account.get("tweets") or []
    if not tweets:
        return {"username": account.get("username"), "followers": followers, "count": 0}
    views = [tweet_views(t) for t in tweets]
    views.sort()
    median = views[len(views) // 2] if views else 0
    pass_line = followers * 2
    passed = sum(1 for v in views if v >= pass_line)
    return {
        "username": account.get("username"),
        "followers": followers,
        "count": len(tweets),
        "median_views": median,
        "pass_line": pass_line,
        "passed": passed,
    }


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    snapshots = load_recent(days)
    if not snapshots:
        print(f"{DATA_DIR} にデータがありません。先に fetch_today.py を実行してください。")
        sys.exit(1)

    latest = snapshots[-1]
    print(f"=== 成績表（{latest.get('fetched_at', '不明')} 時点） ===\n")

    own = summarize_account(latest.get("own"))
    if own:
        print(f"【自分: @{own['username']}】")
        print(f"  フォロワー: {own['followers']}")
        print(f"  直近投稿数: {own['count']}")
        if own.get("count"):
            print(f"  中央値views: {own['median_views']} / 合格ライン(フォロワー×2): {own['pass_line']}")
            print(f"  合格本数: {own['passed']}/{own['count']}")
        print()

    print("【監視アカウントTOP】")
    watch_summaries = [summarize_account(a) for a in latest.get("watch", [])]
    watch_summaries = [w for w in watch_summaries if w and w.get("count")]
    watch_summaries.sort(key=lambda w: w["median_views"], reverse=True)
    for w in watch_summaries[:5]:
        print(f"  @{w['username']}: 中央値views {w['median_views']} (フォロワー {w['followers']})")

    print("\n=== 失敗DBリマインド（writer_rules.md より） ===")
    print("1. アンケート型の締めは避ける")
    print("6. 暦注・タイムリー投稿は当日中に出す")
    print("7. 同じ型の連発は2週間で反応が落ちる")
    print("9. 大バズ進行中は新弾を被せない")


if __name__ == "__main__":
    main()
