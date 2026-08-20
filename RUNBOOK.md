# RUNBOOK — 運用手順

## 現状のステータス

| 項目 | 状態 |
| --- | --- |
| ドラフト生成（チャット表示） | 稼働中 |
| SocialData API（自分・競合の数値取得） | 未接続（APIキー未設定＋このセッションのネットワークポリシーが api.socialdata.tools への通信を拒否） |
| Typefully API（予約投稿アップロード） | 未接続（APIキー未設定＋このセッションのネットワークポリシーが api.typefully.com への通信を拒否） |

未接続の間は、①〜③・⑤〜⑥を省略し、④の提案（ドラフト作成）→⑦の人間承認→**本人が手動でXにコピペ投稿**、という運用になる。

## 接続を有効にする手順（本人がやること）

1. SocialData（https://socialdata.tools）でアカウント作成しAPIキーを取得する
2. Typefully（https://typefully.com）でアカウント作成しAPIキーを取得する（無料枠あり）
3. このプロジェクトが動いているClaude Code on the webの環境設定（Web UI）で、
   - ネットワークポリシーに `api.socialdata.tools` と `api.typefully.com` への通信を許可する項目を追加する
   - 環境変数 `SOCIALDATA_API_KEY` と `TYPEFULLY_API_KEY` を設定する（**絶対にAPIキーをgitにコミットしない・チャットに貼らない**。環境変数として設定する）
4. 設定後、次回のセッションでこのRunbookの手順①〜⑦がフルで動くようになる

## 日次ルーティン（7ステップ）

```
① fetch      python3 scripts/fetch_today.py     … 自分の数字+競合の数字を取得（SOCIALDATA_API_KEY必須）
② report     python3 scripts/daily_report.py    … 成績表を出す(合格線・型別スコア・競合TOP)
③ check      python3 scripts/pre_draft_check.py … テーマ疲労・強ワードのクールダウンを確認（APIなしでも drafts/ の履歴だけで動く）
④ 提案       writer_rules.md に沿って5本のドラフトを作成し、チャットに全文表示する
⑤ ドラフト    決まった案を drafts/YYYY-MM-DD_HHMM_名前_案.txt に保存する
⑥ 検査       python3 buzz_check.py drafts/<ファイル>  … 機械チェック(字数・段数・NG・AI感)
⑦ 承認→アップ 本文全文を人間（本人）が見て明示的に承認する。
              承認後、APIが接続済みなら python3 scripts/upload_to_typefully.py drafts/<ファイル> で予約アップ。
              未接続なら、このままチャットからコピペして本人が手動投稿する。
```

## 承認について（重要）

- 「いいね」「OK」だけでなく、投稿の**全文を提示した上での承認**を得ること。概要だけの承認でアップロードに進まない。
- Typefully接続後は、承認された時点から予約時刻の公開までは自動で進み、公開の瞬間に人の目は入らない。これは本人が明示的に合意した運用（2026年8月時点）。
