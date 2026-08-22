# RUNBOOK — 運用手順

## 現状のステータス

| 項目 | 状態 |
| --- | --- |
| ドラフト生成（チャット表示） | 稼働中 |
| SocialData API（自分・競合の数値取得） | 接続済み（2026-08-22 疎通確認。`SOCIALDATA_API_KEY` 設定済み・api.socialdata.tools 通信可） |
| Typefully API（予約投稿アップロード） | 接続済み（2026-08-22 疎通確認。social set: 327587 / @senorinka） |

接続済みなので、日次ルーティン①〜⑦をフルで回せる。⑦の**人間による全文承認は接続後も省略しない**（「承認について」参照）。
※ Typefullyの公式ドキュメント(https://typefully.com/docs/api)自体はネットワークポリシー外のため閲覧不可。
　 API仕様は `scripts/upload_to_typefully.py` のdocstringに実測ベースで記録している。

## 接続設定（完了済み・再設定が必要になったとき用）

Claude Code on the web の環境設定（Web UI）で、以下が設定されている。

- ネットワークポリシーの許可リスト: `api.socialdata.tools` / `api.typefully.com`
- 環境変数: `SOCIALDATA_API_KEY` / `TYPEFULLY_API_KEY` / `TYPEFULLY_SOCIAL_SET_ID`
  （**絶対にAPIキーをgitにコミットしない・チャットに貼らない**。環境変数として設定する）

接続確認のしかた（キーは表示せずステータスだけ見る）:

```
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $TYPEFULLY_API_KEY" \
  https://api.typefully.com/v2/social-sets
```

200 が返れば接続OK。401/403ならキー、000や403 CONNECTならネットワークポリシー側を疑う。

## 日次ルーティン（8ステップ）

```
① fetch      python3 scripts/fetch_today.py     … 自分の数字+競合の数字を取得（SOCIALDATA_API_KEY必須）
①.5 analyze  data/YYYY-MM-DD.json の監視アカウント投稿から、閲覧数上位1〜3本をAI(Claude)が読んで
              構造・テクニックを抽出し、banks/format_bank.md の「外部の型メモ」に書き足す。
              「個人情報・誹謗中傷の禁止」「権威づけは実績ベースのみ」等の安全ルールは通常の反映プロセスと同様に適用する。
              明確に新しい型だと判断できるものは writer_rules.md の構文パターンに正式追加してよいが、
              その場合はこのステップ内で完結させず、本人にチャットで一言報告してから追加する
② report     python3 scripts/daily_report.py    … 成績表を出す(合格線・型別スコア・競合TOP)
③ check      python3 scripts/pre_draft_check.py … テーマ疲労・強ワードのクールダウンを確認（APIなしでも drafts/ の履歴だけで動く）
④ 提案       writer_rules.md に沿って5本のドラフトを作成し、チャットに全文表示する
⑤ ドラフト    決まった案を drafts/YYYY-MM-DD_HHMM_名前_案.txt に保存する
⑥ 検査       python3 buzz_check.py drafts/<ファイル>  … 機械チェック(字数・段数・NG・AI感)
⑦ 承認→アップ 本文全文を人間（本人）が見て明示的に承認する。
              承認後、python3 scripts/upload_to_typefully.py drafts/<ファイル> --post N --at <ISO8601> --confirm-approved で予約アップ。
              （--confirm-approved は本人の全文承認が取れている場合だけ付ける。手動投稿に切り替えてもよい）
```

**①.5について**: これは`fetch_today.py`が返す生データ（投稿本文＋数値）をAIが毎回読んで判断するステップで、Pythonスクリプトでは自動化していない（構文の解析は数値処理ではなく読解・判断が必要なため）。SocialData API接続後は①のデータを使ってこのステップを回せる（本人がポストを貼ってくれた場合の手動分析も引き続き有効）。

## 承認について（重要）

- 「いいね」「OK」だけでなく、投稿の**全文を提示した上での承認**を得ること。概要だけの承認でアップロードに進まない。
- Typefully接続後は、承認された時点から予約時刻の公開までは自動で進み、公開の瞬間に人の目は入らない。これは本人が明示的に合意した運用（2026年8月時点）。
