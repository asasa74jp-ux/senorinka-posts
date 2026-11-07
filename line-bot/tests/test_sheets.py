from bot.sheets import ensure_tabs


class FakeWS:
    def __init__(self, title, values=None):
        self.title, self.values = title, values or []

    def get_all_values(self):
        return self.values

    def update(self, values, start, value_input_option=None):
        self.values = [list(map(str, r)) for r in values]

    def append_rows(self, rows, value_input_option=None):
        self.values += [list(map(str, r)) for r in rows]

    def freeze(self, rows):
        pass


class FakeSS:
    def __init__(self, sheets):
        self.sheets = {s.title: s for s in sheets}

    def worksheets(self):
        return list(self.sheets.values())

    def add_worksheet(self, title, rows, cols):
        self.sheets[title] = FakeWS(title)
        return self.sheets[title]


DEFAULTS = {"文面": [{"キー": "a", "文面": "A", "説明": ""}, {"キー": "b", "文面": "B", "説明": ""}]}


def test_creates_missing_tab():
    ss = FakeSS([])
    ensure_tabs(ss, DEFAULTS)
    assert ss.sheets["文面"].values == [["キー", "文面", "説明"], ["a", "A", ""], ["b", "B", ""]]


def test_keeps_edits_and_appends_only_missing_keys():
    ws = FakeWS("文面", [["キー", "文面", "説明"], ["a", "本人が直した文", ""]])
    ensure_tabs(FakeSS([ws]), DEFAULTS)
    assert ws.values == [["キー", "文面", "説明"], ["a", "本人が直した文", ""], ["b", "B", ""]]
