"""Googleスプレッドシートとの接続。

- 起動時に、足りないタブ・足りない行を仮文で自動追加する（運用者が空のシートを用意するだけで済むように）。
- 既に入っている行は上書きしない（運用者が直した文面を消さないため）。
"""

from __future__ import annotations

import json
import logging

import gspread

from .content import Tables, load_default_tables

log = logging.getLogger(__name__)


def open_spreadsheet(spreadsheet_id: str, service_account_json: str) -> gspread.Spreadsheet:
    client = gspread.service_account_from_dict(json.loads(service_account_json))
    return client.open_by_key(spreadsheet_id)


def ensure_tabs(spreadsheet: gspread.Spreadsheet, defaults: Tables | None = None) -> None:
    """タブが無ければ作り、1列目（キー）がシートに無い行を末尾に足す。"""
    defaults = defaults if defaults is not None else load_default_tables()
    existing = {ws.title: ws for ws in spreadsheet.worksheets()}

    for tab, rows in defaults.items():
        if not rows:
            continue
        headers = list(rows[0].keys())
        ws = existing.get(tab)
        if ws is None:
            ws = spreadsheet.add_worksheet(title=tab, rows=max(len(rows) + 50, 100), cols=len(headers))
            values = [headers] + [[row.get(h, "") for h in headers] for row in rows]
            ws.update(values, "A1", value_input_option="RAW")
            ws.freeze(rows=1)
            log.info("タブ「%s」を作成しました", tab)
            continue

        current = ws.get_all_values()
        if not current or not any(current[0]):
            values = [headers] + [[row.get(h, "") for h in headers] for row in rows]
            ws.update(values, "A1", value_input_option="RAW")
            continue

        sheet_headers = current[0]
        present_keys = {str(r[0]).strip() for r in current[1:] if r}
        missing = [row for row in rows if str(row[headers[0]]).strip() not in present_keys]
        if missing:
            ws.append_rows(
                [[row.get(h, "") for h in sheet_headers] for row in missing],
                value_input_option="RAW",
            )
            log.info("タブ「%s」に %d 行を追加しました", tab, len(missing))


class SheetSource:
    """スプレッドシートの各タブを表データとして読む。

    接続は最初に読むときに行い、失敗したら次の読み込みでやり直す
    （起動時にGoogle側が一時的に不調でも、復旧すれば自動でつながるように）。
    """

    def __init__(self, spreadsheet_id: str, service_account_json: str, tabs: list[str]):
        self.spreadsheet_id = spreadsheet_id
        self.service_account_json = service_account_json
        self.tabs = tabs
        self._spreadsheet: gspread.Spreadsheet | None = None

    @property
    def spreadsheet(self) -> gspread.Spreadsheet:
        if self._spreadsheet is None:
            spreadsheet = open_spreadsheet(self.spreadsheet_id, self.service_account_json)
            ensure_tabs(spreadsheet)
            self._spreadsheet = spreadsheet
        return self._spreadsheet

    def read_tables(self) -> Tables:
        tables: Tables = {}
        for tab in self.tabs:
            try:
                ws = self.spreadsheet.worksheet(tab)
            except gspread.WorksheetNotFound:
                continue
            values = ws.get_all_values()
            if not values:
                continue
            headers = [h.strip() for h in values[0]]
            tables[tab] = [dict(zip(headers, row)) for row in values[1:] if any(c.strip() for c in row)]
        return tables
