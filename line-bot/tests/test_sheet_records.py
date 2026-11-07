from datetime import datetime

import gspread

from bot.records import JST, Session, SheetRecords


class Cell:
    def __init__(self, row):
        self.row = row


class FakeWS:
    def __init__(self, title):
        self.title, self.values = title, []

    def update(self, values, start, value_input_option=None):
        row = int(start[1:]) - 1
        for i, r in enumerate(values):
            while len(self.values) <= row + i:
                self.values.append([])
            self.values[row + i] = [str(v) for v in r]

    def row_values(self, n):
        return list(self.values[n - 1]) if n <= len(self.values) else []

    def get_all_values(self):
        return [list(r) for r in self.values]

    def append_row(self, values, value_input_option=None, table_range=None):
        assert value_input_option == "RAW"
        self.values.append([str(v) for v in values])

    def find(self, query, in_column=None):
        for i, r in enumerate(self.values):
            if r and r[in_column - 1] == query:
                return Cell(i + 1)
        return None

    def delete_rows(self, n):
        del self.values[n - 1]

    def freeze(self, rows):
        pass


class FakeSS:
    def __init__(self):
        self.tabs = {}

    def worksheet(self, title):
        if title not in self.tabs:
            raise gspread.WorksheetNotFound(title)
        return self.tabs[title]

    def add_worksheet(self, title, rows, cols):
        self.tabs[title] = FakeWS(title)
        return self.tabs[title]


class Src:
    def __init__(self):
        self.spreadsheet = FakeSS()


def test_receipts_written_and_read():
    src = Src()
    rec = SheetRecords(src)
    assert rec.list_receipts() == []
    at = datetime(2026, 11, 19, 21, 5, 0, tzinfo=JST)
    rec.append_receipt(1, "Uaaa", ["片思い", "1か月以内", "=HYPERLINK(\"x\")"], at)
    ws = src.spreadsheet.tabs["受付記録"]
    assert ws.values[0] == ["日時", "受付番号", "ユーザーID", "回答1", "回答2", "回答3"]
    assert ws.values[1] == ["2026-11-19 21:05:00", "1", "Uaaa", "片思い", "1か月以内", "=HYPERLINK(\"x\")"]
    got = rec.list_receipts()
    assert got[0].number == 1 and got[0].user_id == "Uaaa"


def test_receipts_respect_reordered_columns_and_blank_rows():
    src = Src()
    ws = src.spreadsheet.add_worksheet("受付記録", 1, 1)
    ws.values = [["受付番号", "メモ", "ユーザーID", "日時"], ["5", "テスト", "U1", "x"], ["", "", "", ""]]
    rec = SheetRecords(src)
    assert [(r.number, r.user_id) for r in rec.list_receipts()] == [(5, "U1")]
    rec.append_receipt(6, "U2", ["a"], datetime(2026, 1, 1, tzinfo=JST))
    assert ws.values[0] == ["受付番号", "メモ", "ユーザーID", "日時", "回答1"]
    assert ws.values[-1] == ["6", "", "U2", "2026-01-01 00:00:00", "a"]


def test_session_roundtrip_survives_restart():
    src = Src()
    rec = SheetRecords(src)
    assert rec.get_session("U1") is None
    rec.save_session("U1", Session(next_index=1, answers=["片思い"]))
    rec.save_session("U1", Session(next_index=2, answers=["片思い", "1週間以内"]))
    ws = src.spreadsheet.tabs["進行状況"]
    assert len(ws.values) == 2  # 同じ人は1行を上書き

    restarted = SheetRecords(src)  # メモリの控えが消えた状態
    s = restarted.get_session("U1")
    assert s.next_index == 2 and s.answers == ["片思い", "1週間以内"]
    restarted.delete_session("U1")
    assert len(ws.values) == 1
    assert SheetRecords(src).get_session("U1") is None
