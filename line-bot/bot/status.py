"""運用者向けの「接続チェック」ページ（/status）の中身。

ブラウザで開くだけで、環境変数とGoogleスプレッドシートの接続状態を日本語で確認できる。
鍵の値そのものは決して表示しない（「入っているか」と、公開しても問題のない情報だけ）。
"""

from __future__ import annotations

import json
import os

REQUIRED = [
    "LINE_CHANNEL_SECRET",
    "LINE_CHANNEL_ACCESS_TOKEN",
    "SPREADSHEET_ID",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
]
WATCH_WORDS = ("LINE", "CHANNEL", "TOKEN", "SECRET", "SPREAD", "SHEET", "GOOGLE", "SERVICE", "JSON")


def _api_error_message(exc) -> tuple[int | None, str]:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    message = ""
    try:
        message = response.json()["error"]["message"]
    except Exception:  # noqa: BLE001
        message = str(exc)
    return status, message[:300]


def diagnose(source) -> list[str]:
    lines = ["■ 接続チェック", ""]
    ok = True

    # 1. 環境変数
    lines.append("【1】Renderの環境変数")
    for name in REQUIRED:
        value = os.environ.get(name, "")
        if value.strip():
            lines.append(f"  OK　{name}：入っています")
        else:
            ok = False
            lines.append(f"  ×　{name}：見つかりません（名前の打ち間違い、または値が空）")
    similar = sorted(
        k for k in os.environ
        if k not in REQUIRED and any(w in k.upper() for w in WATCH_WORDS)
        and not k.startswith(("RENDER", "PYTHON", "GUNICORN"))
    )
    if similar:
        lines.append("  ※ 似た名前の環境変数があります（打ち間違いかもしれません）：" + "、".join(similar))
    lines.append("")

    # 2. Googleの鍵（JSON）
    lines.append("【2】Googleの鍵（GOOGLE_SERVICE_ACCOUNT_JSON）")
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    email = ""
    if not raw:
        lines.append("  ×　入っていません")
        ok = False
    else:
        try:
            info = json.loads(raw)
            email = info.get("client_email", "")
            if not email or "private_key" not in info:
                raise ValueError
            lines.append("  OK　鍵の形は正しいです")
            lines.append(f"  Botのメールアドレス：{email}")
            lines.append("  （スプレッドシートの「共有」に、このアドレスが「編集者」で入っている必要があります）")
        except ValueError:
            ok = False
            lines.append("  ×　鍵の形が正しくありません。JSONファイルの中身を、最初の { から最後の } まで")
            lines.append("     まるごと貼り直してください（途中で切れている・余分な文字が付いている可能性）")
    lines.append("")

    # 3. スプレッドシート
    lines.append("【3】スプレッドシートとの接続")
    if source is None:
        lines.append("  ×　SPREADSHEET_ID か GOOGLE_SERVICE_ACCOUNT_JSON が無いため、シートを見に行っていません")
        lines.append("     （いまは仮文で動いています）")
        ok = False
    elif email:
        try:
            import gspread

            source._spreadsheet = None  # つなぎ直して、足りないタブも作る
            spreadsheet = source.spreadsheet
            titles = [ws.title for ws in spreadsheet.worksheets()]
            lines.append(f"  OK　シート「{spreadsheet.title}」につながりました")
            lines.append("  タブ：" + "、".join(titles))
        except gspread.SpreadsheetNotFound:
            ok = False
            lines.append("  ×　シートが見つかりません。次のどちらかです：")
            lines.append(f"     ・シートの「共有」に {email} が入っていない")
            lines.append("     ・SPREADSHEET_ID が違う（URLの /d/ と /edit の間の文字列だけを入れる）")
        except gspread.exceptions.APIError as exc:
            ok = False
            status, message = _api_error_message(exc)
            lines.append(f"  ×　Googleからエラーが返りました（{status}）")
            lower = message.lower()
            if "has not been used" in lower or "disabled" in lower:
                lines.append("     → Google Sheets API が有効になっていません。")
                lines.append("       Google Cloud で、鍵を作ったのと同じプロジェクトを選び、")
                lines.append("       「APIとサービス」→「ライブラリ」→ Google Sheets API →「有効にする」")
            elif status == 403:
                lines.append(f"     → シートの「共有」に {email} を「編集者」で追加してください")
            elif status == 404:
                lines.append("     → SPREADSHEET_ID が違う可能性があります")
            lines.append(f"     （Googleのメッセージ：{message}）")
        except Exception as exc:  # noqa: BLE001
            ok = False
            lines.append(f"  ×　接続できませんでした：{type(exc).__name__}")
    lines.append("")

    lines.insert(1, "結果：すべてOKです" if ok else "結果：×の項目を直してください（直したら、このページを開き直すだけでOK）")
    return lines
