import base64
import hashlib
import hmac
import json
import os

os.environ["LINE_CHANNEL_SECRET"] = "test-secret"
os.environ["LINE_CHANNEL_ACCESS_TOKEN"] = "test-token"
os.environ.pop("SPREADSHEET_ID", None)

import app as bot_app  # noqa: E402


def signed_post(client, text, user="Uabc"):
    body = json.dumps({
        "destination": "x",
        "events": [{
            "type": "message", "mode": "active", "timestamp": 0,
            "webhookEventId": "e1", "deliveryContext": {"isRedelivery": False},
            "replyToken": "rtok",
            "source": {"type": "user", "userId": user},
            "message": {"type": "text", "id": "1", "quoteToken": "q", "text": text},
        }],
    }, ensure_ascii=False)
    sig = base64.b64encode(hmac.new(b"test-secret", body.encode(), hashlib.sha256).digest()).decode()
    return client.post("/callback", data=body.encode(), headers={"X-Line-Signature": sig,
                                                                   "Content-Type": "application/json"})


def test_flow_through_webhook(monkeypatch):
    sent = []
    monkeypatch.setattr(bot_app.MessagingApi, "reply_message", lambda self, req: sent.append(req))
    client = bot_app.app.test_client()

    assert signed_post(client, "おみくじ").status_code == 200
    assert len(sent[-1].messages[0].quick_reply.items) == 12
    assert signed_post(client, "1").status_code == 200
    assert sent[-1].messages[0].text.startswith("1番　大結")
    n = len(sent)
    signed_post(client, "こんにちは")
    assert len(sent) == n  # 無返信


def test_bad_signature_rejected():
    client = bot_app.app.test_client()
    r = client.post("/callback", data=b"{}", headers={"X-Line-Signature": "bad"})
    assert r.status_code == 400


def test_health():
    assert bot_app.app.test_client().get("/health").data == b"ok"
