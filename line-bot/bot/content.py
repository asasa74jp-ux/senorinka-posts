"""文面・設定の読み込み。

文面と設定は Googleスプレッドシート（なければ content/default_content.json）から読みます。
シートの構成は default_content.json と同じで、タブ名＝JSONのキー、1行目＝見出しです。
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_CONTENT_PATH = Path(__file__).resolve().parent.parent / "content" / "default_content.json"

Tables = dict[str, list[dict]]


def load_default_tables() -> Tables:
    with open(DEFAULT_CONTENT_PATH, encoding="utf-8") as f:
        return json.load(f)


@dataclass
class OmikujiEntry:
    number: int
    name: str
    body: str
    bridge: str


@dataclass
class Question:
    order: int
    text: str
    choices: list[str]


@dataclass
class KeywordRule:
    keyword: str
    contains: bool  # True: 「含む」 / False: 「完全一致」
    text: str
    buttons: list[str]
    action: str  # "" / "おみくじ" / "診断"


ACTIONS = {"おみくじ", "診断"}


def split_items(value: str) -> list[str]:
    """「/」「／」や改行で区切られた項目を、リストにする。"""
    return [c.strip() for c in re.split(r"[/／\n]", value or "") if c.strip()]


@dataclass
class Content:
    settings: dict[str, str] = field(default_factory=dict)
    texts: dict[str, str] = field(default_factory=dict)
    omikuji: dict[int, OmikujiEntry] = field(default_factory=dict)
    questions: list[Question] = field(default_factory=list)
    keywords: list[KeywordRule] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def setting(self, key: str, default: str = "") -> str:
        value = self.settings.get(key, "")
        return value if value != "" else default

    def text(self, key: str) -> str:
        return self.texts.get(key, "")


def _cell(row: dict, key: str) -> str:
    value = row.get(key, "")
    return "" if value is None else str(value).strip()


def _to_int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _key_value(rows: list[dict], key_col: str, value_col: str) -> dict[str, str]:
    result = {}
    for row in rows:
        key = _cell(row, key_col)
        if key:
            result[key] = _cell(row, value_col)
    return result


def parse_content(tables: Tables, defaults: Tables | None = None) -> Content:
    """表データを Content に変換する。シートに無い項目は defaults で補う。"""
    defaults = defaults if defaults is not None else load_default_tables()

    def rows(tab: str) -> list[dict]:
        return tables.get(tab) or []

    settings = _key_value(defaults.get("設定", []), "項目", "値")
    settings.update({k: v for k, v in _key_value(rows("設定"), "項目", "値").items() if v != ""})

    texts = _key_value(defaults.get("文面", []), "キー", "文面")
    texts.update({k: v for k, v in _key_value(rows("文面"), "キー", "文面").items() if v != ""})

    omikuji: dict[int, OmikujiEntry] = {}
    source_rows = rows("おみくじ") or defaults.get("おみくじ", [])
    for row in source_rows:
        number = _to_int(_cell(row, "番号"))
        if number is None:
            continue
        omikuji[number] = OmikujiEntry(
            number=number,
            name=_cell(row, "結果名"),
            body=_cell(row, "本文"),
            bridge=_cell(row, "診断への橋渡し文"),
        )

    questions: list[Question] = []
    source_rows = rows("診断質問") or defaults.get("診断質問", [])
    for i, row in enumerate(source_rows):
        text = _cell(row, "質問文")
        if not text:
            continue
        order = _to_int(_cell(row, "順番"))
        choices = split_items(_cell(row, "選択肢"))
        questions.append(Question(order=order if order is not None else 1000 + i, text=text, choices=choices))
    questions.sort(key=lambda q: q.order)

    import unicodedata

    keywords: list[KeywordRule] = []
    source_rows = rows("キーワード応答") or defaults.get("キーワード応答", [])
    for row in source_rows:
        keyword = unicodedata.normalize("NFKC", _cell(row, "キーワード"))
        if not keyword:
            continue
        action = _cell(row, "動作")
        keywords.append(KeywordRule(
            keyword=keyword,
            contains=_cell(row, "一致方法") == "含む",
            text=_cell(row, "返す文面"),
            buttons=split_items(_cell(row, "ボタン")),
            action=action if action in ACTIONS else "",
        ))

    content = Content(settings=settings, texts=texts, omikuji=omikuji, questions=questions,
                      keywords=keywords)
    content.warnings = find_banned_words(content)
    return content


def find_banned_words(content: Content) -> list[str]:
    """「設定」タブの「使わない言葉」が文面に入っていないか調べる。"""
    words = split_items(content.setting("使わない言葉"))
    places: list[tuple[str, str]] = []
    places += [(f"文面「{k}」", v) for k, v in content.texts.items()]
    for e in content.omikuji.values():
        places += [(f"おみくじ {e.number}番の本文", e.body), (f"おみくじ {e.number}番の橋渡し文", e.bridge)]
    places += [(f"診断質問 {q.order}番", q.text + " " + " ".join(q.choices)) for q in content.questions]
    places += [(f"キーワード応答「{k.keyword}」", k.text + " " + " ".join(k.buttons)) for k in content.keywords]
    found = []
    for place, value in places:
        hits = [w for w in words if w in value]
        if hits:
            found.append(f"{place} に「{'」「'.join(hits)}」が入っています")
    return found


class JsonSource:
    """content/default_content.json（または指定ファイル）から読む。シート未接続時・テスト用。"""

    def __init__(self, path: Path | str = DEFAULT_CONTENT_PATH):
        self.path = Path(path)

    def read_tables(self) -> Tables:
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)


class ContentStore:
    """文面を一定時間キャッシュし、期限が切れたら読み直す。

    読み直しに失敗したときは、前回読めた内容を使い続ける（Botを止めないため）。
    """

    def __init__(self, source, cache_seconds: int = 300):
        self.source = source
        self.cache_seconds = cache_seconds
        self._content: Content | None = None
        self._loaded_at = 0.0
        self._lock = threading.Lock()

    def get(self, max_age: float | None = None) -> Content:
        """文面を返す。max_age（秒）を指定すると、それより古ければ読み直す。"""
        limit = self.cache_seconds if max_age is None else min(max_age, self.cache_seconds)
        with self._lock:
            expired = time.monotonic() - self._loaded_at >= limit
            if self._content is None or expired:
                try:
                    content = parse_content(self.source.read_tables())
                    self._report_warnings(content)
                    self._content = content
                    self._loaded_at = time.monotonic()
                except Exception:  # noqa: BLE001 - シート障害でもBotは動かし続ける
                    log.exception("文面の読み込みに失敗しました")
                    if self._content is None:
                        self._content = parse_content({})  # 仮文で動かす
                    # 失敗時は30秒後にもう一度読みに行く
                    self._loaded_at = time.monotonic() - max(self.cache_seconds - 30, 0)
            return self._content

    def _report_warnings(self, content: Content) -> None:
        previous = self._content.warnings if self._content else None
        if content.warnings == previous:
            return
        for w in content.warnings:
            log.warning("表現チェック: %s", w)
        report = getattr(self.source, "write_check_results", None)
        if report:
            try:
                report(content.warnings)
            except Exception:  # noqa: BLE001
                log.exception("チェック結果をシートに書けませんでした")

    def refresh(self) -> None:
        with self._lock:
            self._loaded_at = 0.0
