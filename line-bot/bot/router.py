"""受け取ったメッセージに対して、何を返すかを決める（LINEに依存しない部分）。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .content import Content, ContentStore
from .state import MemoryState

OMIKUJI_MODE = "omikuji"
OMIKUJI_WAIT_SECONDS = 30 * 60  # 「おみくじ」のあと、番号を待つ時間


@dataclass
class Reply:
    text: str
    quick_replies: list[str] = field(default_factory=list)


def normalize(text: str) -> str:
    """全角数字・全角英字などを半角にそろえ、前後の空白を取る。"""
    return unicodedata.normalize("NFKC", text or "").strip()


_NUMBER_RE = re.compile(r"^(\d{1,3})\s*番?$")


def parse_number(text: str) -> int | None:
    m = _NUMBER_RE.match(text)
    return int(m.group(1)) if m else None


class Router:
    def __init__(self, store: ContentStore, state: MemoryState | None = None):
        self.store = store
        self.state = state or MemoryState()

    # ---- 入口 ----
    def handle_text(self, user_id: str, raw_text: str) -> list[Reply]:
        content = self.store.get()
        text = normalize(raw_text)

        if text == normalize(content.setting("おみくじのキーワード", "おみくじ")):
            return self._omikuji_start(user_id, content)

        if self.state.get(user_id) == OMIKUJI_MODE:
            replies = self._omikuji_answer(user_id, text, content)
            if replies is not None:
                return replies

        # どれにも当てはまらないときは返信しない（本人が1対1で返すため）
        return []

    # ---- 機能1：月夜おみくじ ----
    def _omikuji_numbers(self, content: Content) -> list[str]:
        return [str(n) for n in sorted(content.omikuji)][:13]  # LINEのボタンは最大13個

    def _omikuji_start(self, user_id: str, content: Content) -> list[Reply]:
        self.state.set(user_id, OMIKUJI_MODE, OMIKUJI_WAIT_SECONDS)
        return [Reply(content.text("おみくじ_番号の案内"), self._omikuji_numbers(content))]

    def _omikuji_answer(self, user_id: str, text: str, content: Content) -> list[Reply] | None:
        number = parse_number(text)
        if number is None:
            # 数字以外が来たら、おみくじは終わったものとして扱う
            self.state.clear(user_id)
            return None
        entry = content.omikuji.get(number)
        if entry is None:
            return [Reply(content.text("おみくじ_番号が範囲外"), self._omikuji_numbers(content))]

        self.state.clear(user_id)
        heading = (
            content.text("おみくじ_結果の見出し")
            .replace("{番号}", str(entry.number))
            .replace("{結果名}", entry.name)
        )
        parts = [p for p in (heading, entry.body, entry.bridge) if p.strip()]
        return [Reply("\n\n".join(parts))]
