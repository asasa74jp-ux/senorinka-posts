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

CHECK_TAB = "チェック結果"


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
        """文面用のタブをまとめて読む（Googleへの問い合わせは2回だけ）。"""
        spreadsheet = self.spreadsheet
        titles = {ws.title for ws in spreadsheet.worksheets()}
        tabs = [t for t in self.tabs if t in titles]
        if not tabs:
            return {}
        # タブ名に記号が入っていても読めるように、'タブ名' の形で指定する
        result = spreadsheet.values_batch_get([f"'{t}'" for t in tabs])
        tables: Tables = {}
        for tab, value_range in zip(tabs, result.get("valueRanges", [])):
            values = value_range.get("values", [])
            if not values:
                continue
            headers = [h.strip() for h in values[0]]
            tables[tab] = [
                dict(zip(headers, row)) for row in values[1:] if any(str(c).strip() for c in row)
            ]
        return tables

    def write_check_results(self, warnings: list[str]) -> None:
        """表現チェックの結果を「チェック結果」タブに書く（運用者が確認できるように）。"""
        spreadsheet = self.spreadsheet
        try:
            ws = spreadsheet.worksheet(CHECK_TAB)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title=CHECK_TAB, rows=100, cols=2)
        from datetime import datetime, timedelta, timezone

        stamp = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
        lines = warnings or ["問題は見つかりませんでした"]
        ws.clear()
        ws.update([["確認日時", "内容"]] + [[stamp, line] for line in lines], "A1",
                  value_input_option="RAW")
