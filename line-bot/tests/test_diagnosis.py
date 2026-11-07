from datetime import timedelta

import pytest

from bot import records as records_mod
from bot.content import ContentStore, load_default_tables
from bot.records import MemoryRecords
from bot.router import Router


def make(settings=None, tables=None):
    tables = tables or load_default_tables()
    rows = {r["項目"]: r for r in tables["設定"]}
    for k, v in {"診断の受付": "受付中", **(settings or {})}.items():
        rows[k]["値"] = v

    class Src:
        def read_tables(self):
            return tables

    recs = MemoryRecords()
    return Router(ContentStore(Src(), 300), records=recs), recs, tables


def answer_all(r, user="u1"):
    out = [r.handle_text(user, "診断")]
    for a in ["片思い", "1か月以内", "彼の気持ちが知りたい"]:
        out.append(r.handle_text(user, a))
    return out


def test_switch_off_by_default():
    tables = load_default_tables()

    class Src:
        def read_tables(self):
            return tables

    r = Router(ContentStore(Src(), 300), records=MemoryRecords())
    reply = r.handle_text("u1", "診断")
    assert reply[0].text.startswith("【仮文】ただいま診断の受付はお休み")
    assert r.handle_text("u1", "片思い") == []  # 受付は始まっていない


def test_full_flow_and_record():
    r, recs, _ = make()
    start, a1, a2, done = answer_all(r)
    assert len(start) == 2 and start[1].text.startswith("今、彼とは")
    assert "片思い" in start[1].quick_replies
    assert a1[0].text.startswith("最後に連絡を") and a1[0].quick_replies
    assert a2[0].text.startswith("いちばん知りたい") and a2[0].quick_replies == []
    assert "受付番号 1番で承りました" in done[0].text
    assert "数日以内" in done[1].text
    rec = recs.receipts[0]
    assert rec["受付番号"] == 1 and rec["ユーザーID"] == "u1"
    assert rec["回答"] == ["片思い", "1か月以内", "彼の気持ちが知りたい"]
    assert recs.sessions == {}


def test_numbers_increase():
    r, recs, _ = make()
    answer_all(r, "u1")
    done = answer_all(r, "u2")[-1]
    assert "受付番号 2番" in done[0].text


def test_duplicate_blocked():
    r, recs, _ = make()
    answer_all(r, "u1")
    reply = r.handle_text("u1", "診断")
    assert "すでにお受けしています" in reply[0].text
    assert len(recs.receipts) == 1


def test_limit_reached_at_start():
    r, recs, _ = make({"診断の受付上限": "2"})
    answer_all(r, "u1")
    answer_all(r, "u2")
    reply = r.handle_text("u3", "診断")
    assert "締め切りました" in reply[0].text
    assert r.handle_text("u3", "片思い") == []


def test_limit_reached_while_answering():
    r, recs, _ = make({"診断の受付上限": "1"})
    r.handle_text("u1", "診断")
    r.handle_text("u2", "診断")
    for a in "abc":
        r.handle_text("u1", a)
    r.handle_text("u2", "a")
    r.handle_text("u2", "b")
    last = r.handle_text("u2", "c")
    assert "締め切りました" in last[0].text
    assert len(recs.receipts) == 1


def test_default_limit_is_20():
    r, recs, _ = make()
    for i in range(20):
        answer_all(r, f"u{i}")
    assert "締め切りました" in r.handle_text("x", "診断")[0].text
    assert len(recs.receipts) == 20


def test_invalid_limit_closes():
    r, _, _ = make({"診断の受付上限": "にじゅう"})
    assert "締め切りました" in r.handle_text("u1", "診断")[0].text


def test_fullwidth_limit_ok():
    r, _, _ = make({"診断の受付上限": "２０"})
    assert len(r.handle_text("u1", "診断")) == 2


def test_cancel():
    r, recs, _ = make()
    r.handle_text("u1", "診断")
    r.handle_text("u1", "片思い")
    assert "中断しました" in r.handle_text("u1", "やめる")[0].text
    assert recs.sessions == {} and recs.receipts == []
    assert r.handle_text("u1", "1か月以内") == []


def test_restart_with_keyword():
    r, recs, _ = make()
    r.handle_text("u1", "診断")
    r.handle_text("u1", "片思い")
    again = r.handle_text("u1", "診断")
    assert again[1].text.startswith("今、彼とは")
    assert recs.sessions["u1"].answers == []


def test_omikuji_interrupts_diagnosis():
    r, recs, _ = make()
    r.handle_text("u1", "診断")
    reply = r.handle_text("u1", "おみくじ")
    assert reply[0].quick_replies[0] == "1"
    assert "u1" not in recs.sessions
    assert r.handle_text("u1", "3")[0].text.startswith("3番")


def test_numbers_during_diagnosis_are_answers_not_omikuji():
    r, recs, _ = make()
    r.handle_text("u1", "おみくじ")
    r.handle_text("u1", "診断")  # おみくじ待ちは解除
    reply = r.handle_text("u1", "3")
    assert reply[0].text.startswith("最後に連絡を")


def test_session_expires(monkeypatch):
    r, recs, _ = make()
    r.handle_text("u1", "診断")
    real_now = records_mod.now_jst
    monkeypatch.setattr("bot.router.now_jst", lambda: real_now() + timedelta(hours=7))
    assert r.handle_text("u1", "片思い") == []
    assert "u1" not in recs.sessions


def test_question_sheet_edit_changes_count():
    tables = load_default_tables()
    tables["診断質問"] = [
        {"順番": "2", "質問文": "二問目", "選択肢": "", "説明": ""},
        {"順番": "1", "質問文": "一問目", "選択肢": "A／B\nC", "説明": ""},
    ]
    r, recs, _ = make(tables=tables)
    start = r.handle_text("u1", "診断")
    assert start[1].text == "一問目" and start[1].quick_replies == ["A", "B", "C"]
    assert r.handle_text("u1", "A")[0].text == "二問目"
    assert "受付番号 1番" in r.handle_text("u1", "x")[0].text
    assert recs.receipts[0]["回答"] == ["A", "x"]


def test_switch_change_reflected_within_30_seconds():
    tables = load_default_tables()

    class Src:
        def read_tables(self):
            return tables

    store = ContentStore(Src(), 300)
    r = Router(store, records=MemoryRecords())
    assert "お休み" in r.handle_text("u1", "診断")[0].text
    for row in tables["設定"]:
        if row["項目"] == "診断の受付":
            row["値"] = "受付中"
    store._loaded_at -= 31  # 31秒たったことにする
    assert len(r.handle_text("u1", "診断")) == 2


def test_record_failure_returns_error_text():
    r, recs, _ = make()

    def boom(*a, **k):
        raise RuntimeError("sheet down")

    recs.list_receipts = boom
    reply = r.handle_text("u1", "診断")
    assert "うまく進みませんでした" in reply[0].text


@pytest.mark.parametrize("value", ["停止", "", "オフ", "受付終了"])
def test_switch_off_values(value):
    r, _, _ = make({"診断の受付": value})
    assert "お休み" in r.handle_text("u1", "診断")[0].text
