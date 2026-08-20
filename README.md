# senorinka-posts

せのりんか｜蜜恋占 の X運用システム。

読む順番: `CLAUDE.md`（憲法）→ `RUNBOOK.md`（運用手順）→ `writer_rules.md`（執筆ルール全体）

## 構成

```
CLAUDE.md              ← AIが毎回最初に読む憲法
RUNBOOK.md              ← 運用手順（日次ルーティン7ステップ）
writer_rules.md         ← 執筆ルール(型・NG・チェックリスト)全体
BRAIN.md                ← 判断メモ(数値が貯まり次第更新)
buzz_check.py           ← ドラフト機械検査
scripts/
  fetch_today.py         ← 自分・競合の数字取得(要 SOCIALDATA_API_KEY)
  daily_report.py        ← 日次成績表
  pre_draft_check.py     ← テーマ・型の疲労チェック(API不要)
  upload_to_typefully.py ← 承認済みドラフトの予約投稿アップ(要 TYPEFULLY_API_KEY)
  accounts.json           ← 自分のXハンドル・監視アカウント設定
drafts/                 ← ドラフト(YYYY-MM-DD_HHMM_名前_案.txt)
data/                   ← 日次の数字・競合バズ(JSON)
banks/
  episode_bank.md         ← エピソードバンク(ネタ台帳)
  format_bank.md          ← 型台帳(勝ち型・死に型)
  reference_bank.md       ← 商品解剖DB
```

## 現状

チャットでのドラフト表示・本人による手動投稿までが稼働中。
SocialData / Typefully のAPI接続は未設定（`RUNBOOK.md` 参照）。
