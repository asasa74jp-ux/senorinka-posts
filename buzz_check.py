#!/usr/bin/env python3
"""
buzz_check.py — ドラフトの機械チェック（字数・段数・NG締め・AI感）

使い方:
    python3 buzz_check.py drafts/2026-08-20_0900_senorinka_案.txt

このスクリプトは体裁だけを検査する。内容の良し悪し・ブランド適合性は判断できない。
最終判断は必ず人間が行うこと。
"""

import re
import sys
from pathlib import Path

MAX_COUNT = 280
WARN_THREAD_MIN = 2
WARN_THREAD_MAX = 5
HARD_THREAD_MAX = 6

NG_ENDING_PATTERNS = [
    r"あなたはどう思いますか[?？]\s*$",
    r"どっちだと思いますか[?？]\s*$",
    r"みんなはどう[?？]\s*$",
]

POST_HEADER_RE = re.compile(r"^【投稿(\d+)｜([^】]+)】\s*$")
ANY_HEADER_RE = re.compile(r"^【[^】]+】\s*$")
TWEET_MARK_RE = re.compile(r"^\((\d+)/(\d+)\)\s?(.*)$")


def x_count(text: str) -> int:
    """Xの文字数カウント近似: 半角=1, それ以外(日本語含む)=2として計算。"""
    count = 0
    for ch in text:
        if ord(ch) < 0x3000 and ord(ch) < 128:
            count += 1
        else:
            count += 2
    return count


def split_posts(lines):
    """【投稿N｜型】ヘッダで分割し、{post_no: {"label": str, "body_lines": [...]}} を返す。"""
    posts = {}
    current = None
    for line in lines:
        stripped = line.strip()
        m = POST_HEADER_RE.match(stripped)
        if m:
            current = m.group(1)
            posts[current] = {"label": m.group(2), "body_lines": []}
            continue
        if ANY_HEADER_RE.match(stripped):
            # 【画像メモ】【手動投稿メモ】等、投稿本体ではない後書きセクションの開始。
            # 以降の行が直前の投稿の本文に混入しないよう、取り込みを止める。
            current = None
            continue
        if current is not None:
            posts[current]["body_lines"].append(line)
    return posts


def extract_tweets(body_lines):
    """(n/m) マーカーでツイート単位に分割する。マーカーがなければ全体を1ツイート扱い。"""
    tweets = []
    buf = []
    total = None
    for line in body_lines:
        m = TWEET_MARK_RE.match(line.strip())
        if m:
            if buf:
                tweets.append("\n".join(buf).strip())
                buf = []
            total = int(m.group(2))
            rest = m.group(3)
            if rest:
                buf.append(rest)
        else:
            buf.append(line.rstrip("\n"))
    if buf:
        tweets.append("\n".join(buf).strip())
    return tweets, total


def check_ai_feel(tweets):
    """簡易AI感チェック: 全ツイートが同じ記号の3連箇条書きだけで構成されていないか等。"""
    warnings = []
    bullet_lines = [t for t in tweets if t.count("・") >= 3]
    if bullet_lines and len(bullet_lines) == len(tweets):
        warnings.append("全ツイートが箇条書きのみで構成されています。地の文とのメリハリを確認してください。")
    closers = [t.splitlines()[-1] for t in tweets if t.splitlines()]
    cliche = [c for c in closers if re.search(r"でもあります[。.]?$", c)]
    if len(cliche) >= 3:
        warnings.append("「〜でもあります」締めが3回以上連続しています。表現に変化をつけてください。")
    return warnings


def check_file(path: Path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    posts = split_posts(lines)

    if not posts:
        print(f"[NG] {path}: 【投稿N｜型】の見出しが見つかりません。出力形式を確認してください。")
        return False

    ok = True
    for no, data in sorted(posts.items(), key=lambda kv: int(kv[0])):
        label = data["label"]
        tweets, declared_total = extract_tweets(data["body_lines"])
        tweets = [t for t in tweets if t]
        n = len(tweets)
        print(f"\n投稿{no}｜{label} — {n}ツイート")

        if declared_total is not None and declared_total != n:
            print(f"  [WARN] 連番の宣言({declared_total})と実際のツイート数({n})が一致しません")

        if "投稿5" not in f"投稿{no}" and "誘導" not in label:
            if n and (n < WARN_THREAD_MIN or n > WARN_THREAD_MAX):
                print(f"  [WARN] ツリー段数が{n}です（推奨{WARN_THREAD_MIN}〜{WARN_THREAD_MAX}）")
            if n > HARD_THREAD_MAX:
                print(f"  [NG] ツリー段数が{n}で上限({HARD_THREAD_MAX})を超えています")
                ok = False

        for i, tweet in enumerate(tweets, 1):
            c = x_count(tweet)
            flag = "NG" if c > MAX_COUNT else "OK"
            if flag == "NG":
                ok = False
            print(f"  ({i}/{n}) {c}カウント [{flag}]")

            for pat in NG_ENDING_PATTERNS:
                if re.search(pat, tweet.strip()):
                    print(f"    [WARN] アンケート型の締めが検出されました: 失敗DB #1 に抵触の可能性")

        for w in check_ai_feel(tweets):
            print(f"  [WARN] {w}")

    print("\n※ このチェックは体裁のみを見ています。最終判断は必ず人間が行ってください。")
    return ok


def main():
    if len(sys.argv) < 2:
        print("使い方: python3 buzz_check.py <draftファイルパス>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ファイルが見つかりません: {path}")
        sys.exit(1)

    ok = check_file(path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
