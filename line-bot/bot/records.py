"""診断の「受付記録」と「進行状況（途中まで答えた内容）」の保存先。

- SheetRecords : Googleスプレッドシートに保存（本番用）
- MemoryRecords: メモリに保存（シート未接続のときの試運転・テスト用）
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
RECEIPT_TAB = "受付記録"
SESSION_TAB = "進行状況"
RECEIPT_BASE_HEADERS = ["日時", "受付番号", "ユーザーID"]
SESSION_HEADERS = ["ユーザーID", "次の質問", "回答（途中）", "更新日時"]
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_jst() -> datetime:
    return datetime.now(JST)


@dataclass
class Session:
    """診断の途中経過。next_index は「いま答えを待っている質問」の位置（0始まり）。"""

    next_index: int = 0
    answers: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=now_jst)


@dataclass
class Receipt:
    number: int
    user_id: str


class MemoryRecords:
    def __init__(self):
        self.receipts: list[dict] = []
        self.sessions: dict[str, Session] = {}

    def list_receipts(self) -> list[Receipt]:
        return [Receipt(r["受付番号"], r["ユーザーID"]) for r in self.receipts]

    def append_receipt(self, number: int, user_id: str, answers: list[str], at: datetime) -> None:
        self.receipts.append({"日時": at.strftime(TIME_FORMAT), "受付番号": number,
                              "ユーザーID": user_id, "回答": list(answers)})

    def get_session(self, user_id: str) -> Session | None:
        return self.sessions.get(user_id)

    def save_session(self, user_id: str, session: Session) -> None:
        self.sessions[user_id] = session

    def delete_session(self, user_id: str) -> None:
        self.sessions.pop(user_id, None)


class SheetRecords:
    """スプレッドシートの「受付記録」「進行状況」タブを読み書きする。

    進行状況はメモリにも控えを持ち、Botが再起動して控えが消えたときだけシートから読み戻す。
    """

    def __init__(self, sheet_source):
        self._source = sheet_source  # bot.sheets.SheetSource（接続を共有する）
        self._sessions: dict[str, Session | None] = {}
        self._lock = threading.Lock()

    # ---- タブの用意 ----
    def _worksheet(self, title: str, headers: list[str]):
        import gspread

        spreadsheet = self._source.spreadsheet
        try:
            return spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=title, rows=200, cols=max(len(headers), 8))
            ws.update([headers], "A1", value_input_option="RAW")
            ws.freeze(rows=1)
            log.info("タブ「%s」を作成しました", title)
            return ws

    # ---- 受付記録 ----
    def list_receipts(self) -> list[Receipt]:
        ws = self._worksheet(RECEIPT_TAB, RECEIPT_BASE_HEADERS)
        values = ws.get_all_values()
        if len(values) < 2:
            return []
        headers = [h.strip() for h in values[0]]
        try:
            num_col, user_col = headers.index("受付番号"), headers.index("ユーザーID")
        except ValueError:
            log.error("「受付記録」タブの見出し（受付番号・ユーザーID）が見つかりません")
            raise
        receipts = []
        for row in values[1:]:
            number = row[num_col].strip() if num_col < len(row) else ""
            user = row[user_col].strip() if user_col < len(row) else ""
            if not number and not user:
                continue
            try:
                n = int(float(number))
            except ValueError:
                n = 0
            receipts.append(Receipt(n, user))
        return receipts

    def append_receipt(self, number: int, user_id: str, answers: list[str], at: datetime) -> None:
        ws = self._worksheet(RECEIPT_TAB, RECEIPT_BASE_HEADERS)
        headers = ws.row_values(1)
        answer_headers = [f"回答{i + 1}" for i in range(len(answers))]
        missing = [h for h in RECEIPT_BASE_HEADERS + answer_headers if h not in headers]
        if missing:
            headers = headers + missing
            ws.update([headers], "A1", value_input_option="RAW")
        record = {"日時": at.strftime(TIME_FORMAT), "受付番号": number, "ユーザーID": user_id}
        record.update(dict(zip(answer_headers, answers)))
        # RAW で書くので、回答が「=」で始まっても数式として扱われない
        ws.append_row([record.get(h, "") for h in headers], value_input_option="RAW",
                      table_range="A1")

    # ---- 進行状況 ----
    def _find_session_row(self, ws, user_id: str) -> int | None:
        cell = ws.find(user_id, in_column=1)
        return cell.row if cell else None

    def get_session(self, user_id: str) -> Session | None:
        with self._lock:
            if user_id in self._sessions:
                return self._sessions[user_id]
        ws = self._worksheet(SESSION_TAB, SESSION_HEADERS)
        row = self._find_session_row(ws, user_id)
        session = None
        if row:
            values = ws.row_values(row) + ["", "", "", ""]
            try:
                session = Session(
                    next_index=int(values[1]),
                    answers=json.loads(values[2] or "[]"),
                    updated_at=datetime.strptime(values[3], TIME_FORMAT).replace(tzinfo=JST),
                )
            except (ValueError, json.JSONDecodeError):
                log.warning("進行状況の行が読めなかったため、無視します")
        with self._lock:
            self._sessions[user_id] = session
        return session

    def save_session(self, user_id: str, session: Session) -> None:
        with self._lock:
            self._sessions[user_id] = session
        ws = self._worksheet(SESSION_TAB, SESSION_HEADERS)
        values = [user_id, session.next_index, json.dumps(session.answers, ensure_ascii=False),
                  session.updated_at.strftime(TIME_FORMAT)]
        row = self._find_session_row(ws, user_id)
        if row:
            ws.update([values], f"A{row}", value_input_option="RAW")
        else:
            ws.append_row(values, value_input_option="RAW", table_range="A1")

    def delete_session(self, user_id: str) -> None:
        with self._lock:
            self._sessions[user_id] = None
        ws = self._worksheet(SESSION_TAB, SESSION_HEADERS)
        row = self._find_session_row(ws, user_id)
        if row:
            ws.delete_rows(row)
