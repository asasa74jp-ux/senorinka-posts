#!/usr/bin/env python3
"""
upload_to_typefully.py — 承認済みドラフトをTypefullyに予約投稿としてアップする

**前提（絶対に飛ばさないこと）**:
- 本文を人間（本人）が全文確認し、明示的に承認していること（RUNBOOK.md の「承認について」参照）
- 環境変数 TYPEFULLY_API_KEY が設定されていること
- 環境変数 TYPEFULLY_SOCIAL_SET_ID が設定されていること（Typefully側でXアカウントを紐付けた social set のID）
- このセッション/環境のネットワークポリシーで api.typefully.com への通信が許可されていること

**2026-08-22 修正**: 当初 `schedule_date` というv1相当のフィールド名で実装していたが、
実際のv2 APIでは `publish_at` が正しいフィールド名だった（WebSearchで確認）。
`publish_at` は省略可能で、省略すると「予約なしの下書き」としてTypefully側に作成され、
自動公開されない（"planned"止まり）。ISO8601日時、"now"、"next-free-slot" のいずれかを渡すと
そのタイミングで公開される。

- 認証: `Authorization: Bearer {API_KEY}`
- エンドポイント: POST https://api.typefully.com/v2/social-sets/{social_set_id}/drafts
- ボディ例（予約する場合）:
    {
      "platforms": {
        "x": {
          "enabled": true,
          "posts": [{"text": "..."}, {"text": "..."}]
        }
      },
      "publish_at": "2026-08-21T09:00:00+09:00"
    }
  ボディ例（下書きのみ・自動公開しない場合）: 上記から "publish_at" キー自体を省く

使い方:
    予約あり: python3 scripts/upload_to_typefully.py drafts/2026-08-21_0900_senorinka_案.txt --post 1 --at 2026-08-21T09:00:00+09:00 --confirm-approved
    下書きのみ（自動公開なし・接続テスト用）: python3 scripts/upload_to_typefully.py drafts/2026-08-21_0900_senorinka_案.txt --post 1 --draft-only --confirm-approved
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
    parser.add_argument(
        "--at",
        help="予約日時 (ISO8601, 例: 2026-08-21T09:00:00+09:00 / \"now\" / \"next-free-slot\")。"
        "省略した場合は --draft-only が必須で、公開予約なしの下書きとして作成する。",
    )
    parser.add_argument(
        "--draft-only",
        action="store_true",
        help="publish_atを付けず、自動公開されない下書きとして作成する（接続テスト・内容確認用）",
    )
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

    if not args.at and not args.draft_only:
        print("[STOP] --at か --draft-only のどちらかを指定してください。")
        sys.exit(1)
    if args.at and args.draft_only:
        print("[STOP] --at と --draft-only は同時に指定できません。")
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
    }
    if args.at:
        body["publish_at"] = args.at

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
