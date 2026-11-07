"""せのりんか公式LINE 自動返信Bot（Webサーバーの入口）。

LINEからのWebhookを /callback で受け取り、bot/router.py が決めた返信を送ります。
文面はコードではなく Googleスプレッドシート（未設定なら content/default_content.json）で管理します。
"""

from __future__ import annotations

import logging
import os

from flask import Flask, abort, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessageAction,
    MessagingApi,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import FollowEvent, MessageEvent, TextMessageContent

from bot.content import ContentStore, JsonSource, load_default_tables
from bot.records import MemoryRecords
from bot.router import Reply, Router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("senorinka-bot")


def build_store_and_records():
    cache_seconds = int(os.environ.get("CONTENT_CACHE_SECONDS", "300"))
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "").strip()
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if spreadsheet_id and sa_json:
        from bot.records import SheetRecords
        from bot.sheets import SheetSource

        source = SheetSource(spreadsheet_id, sa_json, list(load_default_tables().keys()))
        log.info("文面・受付記録はGoogleスプレッドシートを使います")
        return ContentStore(source, cache_seconds), SheetRecords(source)
    log.warning("SPREADSHEET_ID が未設定のため、仮文で動きます（受付記録はメモリのみ・再起動で消えます）")
    return ContentStore(JsonSource(), cache_seconds), MemoryRecords()


app = Flask(__name__)
store, records = build_store_and_records()
store.get()  # 起動時に一度読み込む（シートの足りないタブもここで自動作成される）
router = Router(store, records=records)

channel_secret = os.environ.get("LINE_CHANNEL_SECRET", "")
access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
if not channel_secret or not access_token:
    log.warning("LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN が未設定です")
handler = WebhookHandler(channel_secret or "unset")
line_config = Configuration(access_token=access_token)


def to_line_message(reply: Reply) -> TextMessage:
    quick = None
    if reply.quick_replies:
        quick = QuickReply(
            items=[
                QuickReplyItem(action=MessageAction(label=label[:20], text=label))
                for label in reply.quick_replies
            ]
        )
    return TextMessage(text=reply.text[:5000], quickReply=quick)


def send_replies(reply_token: str, replies: list[Reply]) -> None:
    messages = [to_line_message(r) for r in replies if r.text.strip()][:5]  # 1回の返信は最大5通
    if not messages:
        return
    with ApiClient(line_config) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(replyToken=reply_token, messages=messages)
        )


@app.get("/health")
def health():
    """Renderの稼働確認・スリープ防止用。"""
    return "ok"


@app.post("/callback")
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        log.warning("署名が一致しないリクエストを拒否しました")
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event: MessageEvent) -> None:
    user_id = getattr(event.source, "user_id", None) or "unknown"
    try:
        replies = router.handle_text(user_id, event.message.text)
        send_replies(event.reply_token, replies)
    except Exception:  # noqa: BLE001 - 1件の失敗でサーバーを落とさない
        log.exception("メッセージの処理中にエラーが起きました")


@handler.add(FollowEvent)
def on_follow(event: FollowEvent) -> None:
    user_id = getattr(event.source, "user_id", None) or "unknown"
    try:
        send_replies(event.reply_token, router.handle_follow(user_id))
    except Exception:  # noqa: BLE001
        log.exception("あいさつの送信中にエラーが起きました")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
