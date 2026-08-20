#!/usr/bin/env python3
"""
upload_to_typefully.py — 承認済みドラフトをTypefullyに予約投稿としてアップする

**前提（絶対に飛ばさないこと）**:
- 本文を人間（本人）が全文確認し、明示的に承認していること（RUNBOOK.md の「承認について」参照）
- 環境変数 TYPEFULLY_API_KEY が設定されていること
- 環境変数 TYPEFULLY_SOCIAL_SET_ID が設定されていること（Typefully側でXアカウントを紐付けた social set のID）
- このセッション/環境のネットワークポリシーで api.typefully.com への通信が許可されていること

**注意**: ネットワーク制限のためTypefully公式ドキュメント(https://typefully.com/docs/api)を
直接確認できない状態で、検索結果から得られた仕様（2026年8月時点、API v2）をもとに書いている。
初回実行時にエラーが出た場合は、公式ドキュメントと突き合わせて調整すること。

- 認証: `Authorization: Bearer {API_KEY}`
- エンドポイント: POST https://api.typefully.com/v2/social-sets/{social_set_id}/drafts
- ボディ例:
    {
      "platforms": {
        "x": {
          "enabled": true,
          "posts": [{"text": "..."}, {"text": "..."}]
        }
      },
      "schedule_date": "2026-08-21T09:00:00+09:00"
    }

使い方:
    python3 scripts/upload_to_typefully.py drafts/2026-08-21_0900_senorinka_案.txt --post 1 --at 2026-08-21T09:00:00+09:00
    （--post で 【投稿N｜...】 のNを指定。1本ずつアップする想定）
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests が必要です: pip install requests")
    sys.exit(1)

API_BASE = "https://api.typefully.com"

POST_HEADER_RE = re.compile(r"^【投稿(\d+)｜([^】]+)】\s*$")
TWEET_MARK_RE = re.compile(r"^\((\d+)/(\d+)\)\s?(.*)$")


def get_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(f"環境変数 {name} が設定されていません。RUNBOOK.md を参照してください。")
        sys.exit(1)
    return val


def extract_post(text: str, post_no: str):
    lines = text.splitlines()
    body = []
    capture = False
    for line in lines:
        m = POST_HEADER_RE.match(line.strip())
        if m:
            capture = m.group(1) == post_no
            continue
        if line.strip().startswith("【") and capture:
            break
        if capture:
            body.append(line)

    tweets = []
    buf = []
    for line in body:
        m = TWEET_MARK_RE.match(line.strip())
        if m:
            if buf:
                tweets.append("\n".join(buf).strip())
                buf = []
            rest = m.group(3)
            if rest:
                buf.append(rest)
        else:
            buf.append(line.rstrip("\n"))
    if buf:
        tweets.append("\n".join(buf).strip())
    return [t for t in tweets if t]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("draft_path")
    parser.add_argument("--post", required=True, help="アップする投稿番号（【投稿N】のN）")
    parser.add_argument("--at", required=True, help="予約日時 (ISO8601, 例: 2026-08-21T09:00:00+09:00)")
    parser.add_argument(
        "--confirm-approved",
        action="store_true",
        help="本人が本文を全文確認し承認済みであることを明示するフラグ（必須）",
    )
    args = parser.parse_args()

    if not args.confirm_approved:
        print("[STOP] --confirm-approved フラグがありません。")
        print("本人が本文全文を確認・承認するまで、このスクリプトは実行しないでください。")
        sys.exit(1)

    path = Path(args.draft_path)
    if not path.exists():
        print(f"ファイルが見つかりません: {path}")
        sys.exit(1)

    tweets = extract_post(path.read_text(encoding="utf-8"), args.post)
    if not tweets:
        print(f"投稿{args.post} の本文が見つかりませんでした。")
        sys.exit(1)

    print(f"投稿{args.post}（{len(tweets)}ツイート）をアップします:")
    for i, t in enumerate(tweets, 1):
        print(f"--- ({i}/{len(tweets)}) ---\n{t}\n")

    api_key = get_env("TYPEFULLY_API_KEY")
    social_set_id = get_env("TYPEFULLY_SOCIAL_SET_ID")

    body = {
        "platforms": {
            "x": {
                "enabled": True,
                "posts": [{"text": t} for t in tweets],
            }
        },
        "schedule_date": args.at,
    }

    url = f"{API_BASE}/v2/social-sets/{social_set_id}/drafts"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps(body),
        timeout=30,
    )

    if r.status_code >= 400:
        print(f"[NG] アップロード失敗: {r.status_code} {r.text}")
        sys.exit(1)

    print("[OK] Typefullyに予約アップしました。")
    print(r.json())


if __name__ == "__main__":
    main()
