from bot.content import ContentStore, JsonSource, load_default_tables, parse_content
from bot.router import Router
from bot.state import MemoryState

NAMES = ["大結", "結実", "中結", "小結", "再結", "月結", "星結", "待結", "ほどけ結", "新結", "深結", "朝結"]


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make_router(tables=None, clock=None):
    class Src:
        def read_tables(self):
            return tables if tables is not None else load_default_tables()

    return Router(ContentStore(Src(), 300), MemoryState(clock or FakeClock()))


def test_default_has_12_results_in_order():
    content = parse_content(load_default_tables())
    assert [content.omikuji[i].name for i in range(1, 13)] == NAMES


def test_keyword_shows_12_buttons():
    replies = make_router().handle_text("u1", "おみくじ")
    assert len(replies) == 1
    assert replies[0].quick_replies == [str(i) for i in range(1, 13)]


def test_number_is_fixed_to_result():
    for _ in range(3):  # 何度引いても同じ番号は同じ結果
        r = make_router()
        r.handle_text("u1", "おみくじ")
        text = r.handle_text("u1", "9")[0].text
        assert text.startswith("9番　ほどけ結")


def test_fullwidth_and_ban_suffix_accepted():
    r = make_router()
    r.handle_text("u1", "おみくじ")
    assert "12番　朝結" in r.handle_text("u1", "１２番")[0].text


def test_bridge_text_appended_and_blank_bridge_omitted():
    tables = load_default_tables()
    tables["おみくじ"][0]["診断への橋渡し文"] = "診断はこちら"
    tables["おみくじ"][1]["診断への橋渡し文"] = ""
    r = make_router(tables)
    r.handle_text("u1", "おみくじ")
    assert r.handle_text("u1", "1")[0].text.endswith("診断はこちら")
    r.handle_text("u1", "おみくじ")
    assert not r.handle_text("u1", "2")[0].text.endswith("\n")


def test_out_of_range_number_asks_again_and_keeps_waiting():
    r = make_router()
    r.handle_text("u1", "おみくじ")
    replies = r.handle_text("u1", "13")
    assert replies[0].quick_replies  # ボタンを出し直す
    assert "1番" in r.handle_text("u1", "1")[0].text


def test_number_without_omikuji_gets_no_reply():
    assert make_router().handle_text("u1", "3") == []


def test_other_text_cancels_waiting():
    r = make_router()
    r.handle_text("u1", "おみくじ")
    assert r.handle_text("u1", "こんにちは") == []
    assert r.handle_text("u1", "3") == []


def test_waiting_expires_after_30_minutes():
    clock = FakeClock()
    r = make_router(clock=clock)
    r.handle_text("u1", "おみくじ")
    clock.now += 31 * 60
    assert r.handle_text("u1", "3") == []


def test_users_are_independent():
    r = make_router()
    r.handle_text("u1", "おみくじ")
    assert r.handle_text("u2", "3") == []
    assert r.handle_text("u1", "3")


def test_sheet_values_override_defaults_and_blank_falls_back():
    tables = {
        "文面": [{"キー": "おみくじ_番号の案内", "文面": "差し替えた文"},
                {"キー": "おみくじ_番号が範囲外", "文面": ""}],
        "設定": [{"項目": "おみくじのキーワード", "値": "月夜おみくじ"}],
    }
    c = parse_content(tables)
    assert c.text("おみくじ_番号の案内") == "差し替えた文"
    assert c.text("おみくじ_番号が範囲外").startswith("【仮文】")
    assert c.setting("おみくじのキーワード") == "月夜おみくじ"
    assert len(c.omikuji) == 12  # おみくじタブが無ければ既定を使う


def test_store_survives_source_error():
    class Broken:
        def read_tables(self):
            raise RuntimeError("google down")

    content = ContentStore(Broken(), 300).get()
    assert len(content.omikuji) == 12


def test_default_content_has_no_banned_words():
    import json
    from bot.content import DEFAULT_CONTENT_PATH
    text = DEFAULT_CONTENT_PATH.read_text(encoding="utf-8")
    for word in ("必ず", "絶対"):
        assert word not in text
    json.loads(text)
