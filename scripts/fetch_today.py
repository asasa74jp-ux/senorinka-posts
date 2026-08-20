#!/usr/bin/env python3
"""
fetch_today.py — 自分の数字＋競合の数字を取得し data/YYYY-MM-DD.json に保存する

前提:
- 環境変数 SOCIALDATA_API_KEY が設定されていること
- このセッション/環境のネットワークポリシーで api.socialdata.tools への通信が許可されていること
- scripts/accounts.json に own_handle（せのりんかのXアカウント）と watch_handles（監視アカウント）を設定しておくこと

**注意**: このスクリプトのエンドポイント・レスポンス構造は、ネットワーク制限のため
SocialData公式ドキュメント(https://docs.socialdata.tools)を直接確認できない状態で、
検索結果から得られた仕様（2026年8月時点）をもとに書いている。
初回実行時にエラーが出た場合は、公式ドキュメントと突き合わせて調整すること。

- 認証: `Authorization: Bearer {API_KEY}`
- ユーザー情報: GET https://api.socialdata.tools/twitter/user/{username}
- ツイート取得: GET https://api.socialdata.tools/twitter/user/{user_id}/tweets
- 課金: ツイート1件ごとに従量課金（$0.0002/件）。監視アカウント数・取得件数に注意
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests が必要です: pip install requests")
    sys.exit(1)

API_BASE = "https://api.socialdata.tools"
JST = timezone(timedelta(hours=9))

ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_FILE = ROOT / "scripts" / "accounts.json"
DATA_DIR = ROOT / "data"


def get_api_key() -> str:
    key = os.environ.get("SOCIALDATA_API_KEY")
    if not key:
        print("環境変数 SOCIALDATA_API_KEY が設定されていません。")
        print("RUNBOOK.md の「接続を有効にする手順」を参照してください。")
        sys.exit(1)
    return key


def headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def get_user_id(username: str, api_key: str) -> dict:
    url = f"{API_BASE}/twitter/user/{username}"
    r = requests.get(url, headers=headers(api_key), timeout=30)
    r.raise_for_status()
    return r.json()


def get_recent_tweets(user_id: str, api_key: str) -> list:
    url = f"{API_BASE}/twitter/user/{user_id}/tweets"
    r = requests.get(url, headers=headers(api_key), timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("tweets", data.get("data", []))


def fetch_account(username: str, api_key: str) -> dict:
    profile = get_user_id(username, api_key)
    user_id = profile.get("id") or profile.get("id_str")
    if not user_id:
        return {"username": username, "error": "user_id取得失敗", "profile": profile}
    tweets = get_recent_tweets(str(user_id), api_key)
    return {
        "username": username,
        "user_id": user_id,
        "followers_count": profile.get("followers_count"),
        "tweets": tweets,
    }


def main():
    api_key = get_api_key()

    if not ACCOUNTS_FILE.exists():
        print(f"{ACCOUNTS_FILE} が見つかりません。own_handle と watch_handles を設定してください。")
        sys.exit(1)

    accounts = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    own_handle = accounts.get("own_handle", "")
    watch_handles = accounts.get("watch_handles", [])

    if not own_handle or own_handle.startswith("REPLACE_WITH"):
        print("scripts/accounts.json の own_handle を実際のXハンドルに設定してください。")
        sys.exit(1)

    result = {"fetched_at": datetime.now(JST).isoformat(), "own": None, "watch": []}

    print(f"自分のアカウント({own_handle})を取得中...")
    result["own"] = fetch_account(own_handle, api_key)

    for h in watch_handles:
        print(f"監視アカウント({h})を取得中...")
        try:
            result["watch"].append(fetch_account(h, api_key))
        except requests.HTTPError as e:
            print(f"  [WARN] {h} の取得に失敗しました: {e}")

    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"{datetime.now(JST).strftime('%Y-%m-%d')}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"保存しました: {out_path}")


if __name__ == "__main__":
    main()
