from bot.content import ContentStore, load_default_tables, parse_content
from bot.records import MemoryRecords
from bot.router import Router


def make(tables=None, open_diagnosis=True):
    tables = tables or load_default_tables()
    if open_diagnosis:
        for row in tables["設定"]:
            if row["項目"] == "診断の受付":
                row["値"] = "受付中"

    class Src:
        def read_tables(self):
            return tables

    return Router(ContentStore(Src(), 300), records=MemoryRecords()), tables


def add_rule(tables, **kw):
    row = {"キーワード": "", "一致方法": "完全一致", "返す文面": "", "ボタン": "", "動作": "", "説明": ""}
    row.update(kw)
    tables["キーワード応答"].append(row)


def test_greeting_with_buttons():
    r, _ = make()
    reply = r.handle_follow("u1")
    assert reply[0].text.startswith("【仮文】友だち追加ありがとうございます")
    assert reply[0].quick_replies == ["おみくじ", "診断"]


def test_greeting_without_buttons():
    tables = load_default_tables()
    for row in tables["設定"]:
        if row["項目"] == "あいさつのボタン":
            row["値"] = "なし"
    r, _ = make(tables)
    assert r.handle_follow("u1")[0].quick_replies == []


def test_text_rule_exact():
    r, _ = make()
    reply = r.handle_text("u1", "プロフィール")
    assert reply[0].text.startswith("【仮文】ここにせのりんかの自己紹介")
    assert reply[0].quick_replies == ["おみくじ"]
    assert r.handle_text("u1", "プロフィールを見たい") == []  # 完全一致なので反応しない


def test_text_rule_contains_and_operator_added_rows():
    tables = load_default_tables()
    add_rule(tables, キーワード="鑑定", 一致方法="含む", 返す文面="鑑定のご案内です")
    add_rule(tables, キーワード="ありがとう", 返す文面="こちらこそ")
    r, _ = make(tables)
    assert r.handle_text("u1", "個別鑑定について知りたいです")[0].text == "鑑定のご案内です"
    assert r.handle_text("u1", "ありがとう")[0].text == "こちらこそ"
    assert r.handle_text("u1", "ありがとうございます") == []


def test_contains_action_rule():
    tables = load_default_tables()
    add_rule(tables, キーワード="おみくじ", 一致方法="含む", 動作="おみくじ")
    r, _ = make(tables)
    assert r.handle_text("u1", "おみくじひきたい")[0].quick_replies[:2] == ["1", "2"]


def test_renamed_trigger_keyword():
    tables = load_default_tables()
    tables["キーワード応答"][0]["キーワード"] = "月夜おみくじ"
    r, _ = make(tables)
    assert r.handle_text("u1", "おみくじ") == []
    assert r.handle_text("u1", "月夜おみくじ")[0].quick_replies


def test_keywords_inside_diagnosis_are_answers():
    tables = load_default_tables()
    add_rule(tables, キーワード="彼", 一致方法="含む", 返す文面="キーワード応答")
    r, _ = make(tables)
    r.handle_text("u1", "診断")
    reply = r.handle_text("u1", "プロフィール")  # キーワードでも診断中は回答
    assert reply[0].text.startswith("【仮文】②")
    r.handle_text("u1", "1週間以内")
    done = r.handle_text("u1", "彼の気持ち")
    assert "受付番号 1番" in done[0].text


def test_unmatched_no_reply():
    r, _ = make()
    assert r.handle_text("u1", "はじめまして、よろしくお願いします") == []


def test_fullwidth_keyword():
    r, _ = make()
    assert r.handle_text("u1", "プロフィール ")[0].text  # 前後の空白は無視


def test_banned_word_warnings():
    tables = load_default_tables()
    tables["文面"][0]["文面"] = "必ず連絡が来ます"
    tables["おみくじ"][2]["本文"] = "絶対に大丈夫"
    add_rule(tables, キーワード="x", 返す文面="今すぐ行動しないと")
    c = parse_content(tables)
    assert any("文面「あいさつ」" in w and "必ず" in w for w in c.warnings)
    assert any("おみくじ 3番の本文" in w for w in c.warnings)
    assert any("キーワード応答「x」" in w for w in c.warnings)


def test_check_results_reported_only_on_change():
    tables = load_default_tables()
    reports = []

    class Src:
        def read_tables(self):
            return tables

        def write_check_results(self, warnings):
            reports.append(list(warnings))

    store = ContentStore(Src(), 0)
    store.get()
    store.get()
    assert reports == [[]]
    tables["文面"][0]["文面"] = "必ず"
    store.get()
    assert len(reports) == 2 and reports[1]
