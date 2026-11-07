"""受け取ったメッセージに対して、何を返すかを決める（LINEに依存しない部分）。"""

from __future__ import annotations

import logging
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import timedelta

from .content import Content, ContentStore, split_items
from .records import MemoryRecords, Session, now_jst
from .state import MemoryState

log = logging.getLogger(__name__)

OMIKUJI_MODE = "omikuji"
OMIKUJI_WAIT_SECONDS = 30 * 60  # 「おみくじ」のあと、番号を待つ時間
DIAGNOSIS_SESSION_HOURS = 6  # 診断の途中経過を覚えておく時間
SETTINGS_MAX_AGE = 30  # 受付スイッチ・上限は、30秒以内の最新の値で判断する
ANSWER_MAX_CHARS = 2000
OPEN_VALUES = {"受付中", "受付", "開始", "オン", "on", "はい", "yes"}


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


def is_open(value: str) -> bool:
    return normalize(value).lower() in OPEN_VALUES


def parse_limit(value: str) -> int:
    """受付上限を数値にする。読めない値のときは、受けすぎを防ぐため 0（締め切り扱い）にする。"""
    try:
        return max(int(float(normalize(value))), 0)
    except ValueError:
        log.error("「診断の受付上限」が数字ではありません: %r（締め切り扱いにします）", value)
        return 0


class Router:
    def __init__(self, store: ContentStore, state: MemoryState | None = None, records=None):
        self.store = store
        self.state = state or MemoryState()
        self.records = records if records is not None else MemoryRecords()
        # 受付番号の重複・上限超えを防ぐため、診断の処理は1人ずつ順番に行う
        self._diagnosis_lock = threading.Lock()

    # ---- 入口 ----
    def handle_follow(self, user_id: str) -> list[Reply]:
        """友だち追加（ブロック解除）されたときのあいさつ。"""
        content = self.store.get()
        value = content.setting("あいさつのボタン")
        buttons = [] if normalize(value) == "なし" else split_items(value)
        return [Reply(content.text("あいさつ"), buttons[:13])]

    def handle_text(self, user_id: str, raw_text: str) -> list[Reply]:
        content = self.store.get()
        text = normalize(raw_text)

        # 1. 「おみくじ」「診断」に完全一致したら、何の途中でもそれを始める
        exact_action = next(
            (k.action for k in content.keywords if k.action and k.keyword == text), ""
        )
        if exact_action:
            return self._run_action(exact_action, user_id, content)

        # 2. 診断の途中なら、送られた文は回答として受け取る（キーワード応答より優先）
        try:
            with self._diagnosis_lock:
                session = self._active_session(user_id)
                if session is not None:
                    return self._diagnosis_answer(user_id, text, raw_text, session, content)
        except Exception:  # noqa: BLE001 - シートに書けない等。お客さまには一言返す
            log.exception("診断の処理中にエラーが起きました")
            return [Reply(content.text("診断_エラー"))]

        # 3. おみくじの番号待ちなら、番号として受け取る
        if self.state.get(user_id) == OMIKUJI_MODE:
            replies = self._omikuji_answer(user_id, text, content)
            if replies is not None:
                return replies

        # 4. キーワード応答の表（完全一致を先に、そのあと「含む」を表の上から順に）
        rule = next((k for k in content.keywords if k.keyword == text), None)
        if rule is None:
            rule = next((k for k in content.keywords if k.contains and k.keyword in text), None)
        if rule is not None:
            if rule.action:
                return self._run_action(rule.action, user_id, content)
            if rule.text:
                return [Reply(rule.text, rule.buttons[:13])]

        # 5. どれにも当てはまらないときは返信しない（本人が1対1で返すため）
        return []

    def _run_action(self, action: str, user_id: str, content: Content) -> list[Reply]:
        if action == "おみくじ":
            try:
                with self._diagnosis_lock:
                    self._end_session(user_id)  # 診断の途中でも、おみくじを優先する
            except Exception:  # noqa: BLE001 - 進行状況が消せなくても、おみくじは出す
                log.exception("診断の進行状況を消せませんでした")
            return self._omikuji_start(user_id, content)
        # 診断
        self.state.clear(user_id)
        try:
            with self._diagnosis_lock:
                return self._diagnosis_start(user_id)
        except Exception:  # noqa: BLE001
            log.exception("診断の処理中にエラーが起きました")
            return [Reply(content.text("診断_エラー"))]

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

    # ---- 機能2：簡易・彼の本音診断の受付 ----
    def _active_session(self, user_id: str) -> Session | None:
        session = self.records.get_session(user_id)
        if session is None:
            return None
        if now_jst() - session.updated_at > timedelta(hours=DIAGNOSIS_SESSION_HOURS):
            self.records.delete_session(user_id)
            return None
        return session

    def _end_session(self, user_id: str) -> None:
        if self.records.get_session(user_id) is not None:
            self.records.delete_session(user_id)

    def _closed_reply(self, user_id: str, content: Content) -> list[Reply] | None:
        """受付できない理由があれば、その文面を返す。受付できるなら None。"""
        if not is_open(content.setting("診断の受付", "停止")):
            return [Reply(content.text("診断_受付停止中"))]
        receipts = self.records.list_receipts()
        if any(r.user_id == user_id for r in receipts):
            return [Reply(content.text("診断_受付済み"))]
        if len(receipts) >= parse_limit(content.setting("診断の受付上限", "0")):
            return [Reply(content.text("診断_締め切り"))]
        return None

    def _question_reply(self, content: Content, index: int) -> Reply:
        q = content.questions[index]
        return Reply(q.text, q.choices[:13])

    def _diagnosis_start(self, user_id: str) -> list[Reply]:
        content = self.store.get(max_age=SETTINGS_MAX_AGE)
        self._end_session(user_id)
        closed = self._closed_reply(user_id, content)
        if closed:
            return closed
        if not content.questions:
            log.error("「診断質問」タブに質問がありません")
            return [Reply(content.text("診断_受付停止中"))]
        self.records.save_session(user_id, Session(next_index=0, answers=[]))
        replies = [Reply(content.text("診断_はじめの案内"))] if content.text("診断_はじめの案内") else []
        return replies + [self._question_reply(content, 0)]

    def _diagnosis_answer(self, user_id: str, text: str, raw_text: str, session: Session,
                          content: Content) -> list[Reply]:
        if text == normalize(content.setting("診断の中断キーワード", "やめる")):
            self.records.delete_session(user_id)
            return [Reply(content.text("診断_中断"))]

        answers = session.answers + [raw_text.strip()[:ANSWER_MAX_CHARS]]
        next_index = session.next_index + 1
        if next_index < len(content.questions):
            self.records.save_session(user_id, Session(next_index=next_index, answers=answers))
            return [self._question_reply(content, next_index)]
        return self._diagnosis_finish(user_id, answers)

    def _diagnosis_finish(self, user_id: str, answers: list[str]) -> list[Reply]:
        content = self.store.get(max_age=SETTINGS_MAX_AGE)
        closed = self._closed_reply(user_id, content)  # 答えている間に上限に達した場合など
        if closed:
            self.records.delete_session(user_id)
            return closed

        receipts = self.records.list_receipts()
        number = max((r.number for r in receipts), default=0) + 1
        self.records.append_receipt(number, user_id, answers, now_jst())
        self.records.delete_session(user_id)

        done = content.text("診断_受付完了").replace("{受付番号}", str(number))
        replies = [Reply(done)]
        if content.text("診断_返信の目安"):
            replies.append(Reply(content.text("診断_返信の目安")))
        return replies
