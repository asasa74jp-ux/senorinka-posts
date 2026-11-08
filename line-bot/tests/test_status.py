import json

import gspread

from bot.status import diagnose


class Src:
    def __init__(self, exc=None):
        self.exc = exc
        self._spreadsheet = None

    @property
    def spreadsheet(self):
        if self.exc:
            raise self.exc

        class WS:
            def __init__(self, t):
                self.title = t

        class SS:
            title = "せのりんかBot 文面"

            def worksheets(self):
                return [WS("設定"), WS("おみくじ")]

        return SS()


KEY = json.dumps({"client_email": "line-bot@p.iam.gserviceaccount.com", "private_key": "SECRETVALUE"})


def setenv(monkeypatch, **env):
    for k in ["LINE_CHANNEL_SECRET", "LINE_CHANNEL_ACCESS_TOKEN", "SPREADSHEET_ID", "GOOGLE_SERVICE_ACCOUNT_JSON"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_all_ok_and_no_secret_shown(monkeypatch):
    setenv(monkeypatch, LINE_CHANNEL_SECRET="s1", LINE_CHANNEL_ACCESS_TOKEN="t1",
           SPREADSHEET_ID="sid", GOOGLE_SERVICE_ACCOUNT_JSON=KEY)
    text = "\n".join(diagnose(Src()))
    assert "結果：すべてOK" in text and "タブ：設定、おみくじ" in text
    for secret in ("SECRETVALUE", "s1", "t1", "sid"):
        assert f"：{secret}" not in text and secret not in text.replace("せのりんか", "")


def test_typo_name_detected(monkeypatch):
    setenv(monkeypatch, LINE_CHANNEL_SECRET="s", LINE_CHANNEL_ACCESS_TOKEN="t",
           SPREADSHEET_ID="x", GOOGLE_SERVICE_ACCOUNT_JSON=KEY, SPREADSHEETID="x")
    monkeypatch.delenv("SPREADSHEET_ID")
    text = "\n".join(diagnose(None))
    assert "×　SPREADSHEET_ID" in text and "SPREADSHEETID" in text


def test_broken_json(monkeypatch):
    setenv(monkeypatch, GOOGLE_SERVICE_ACCOUNT_JSON='{"client_email": "a"')
    assert "鍵の形が正しくありません" in "\n".join(diagnose(Src()))


def test_not_shared(monkeypatch):
    setenv(monkeypatch, LINE_CHANNEL_SECRET="s", LINE_CHANNEL_ACCESS_TOKEN="t",
           SPREADSHEET_ID="x", GOOGLE_SERVICE_ACCOUNT_JSON=KEY)
    text = "\n".join(diagnose(Src(gspread.SpreadsheetNotFound())))
    assert "line-bot@p.iam.gserviceaccount.com が入っていない" in text
