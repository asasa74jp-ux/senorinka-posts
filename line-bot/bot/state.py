"""ユーザーごとの「いま何の途中か」を覚えておく。

おみくじの番号待ちは短時間の状態なので、メモリに置く（Botが再起動したら
「おみくじ」と送り直してもらえば済む）。
"""

from __future__ import annotations

import threading
import time


class MemoryState:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._data: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def set(self, user_id: str, mode: str, ttl_seconds: int) -> None:
        with self._lock:
            self._data[user_id] = (mode, self._clock() + ttl_seconds)

    def get(self, user_id: str) -> str | None:
        with self._lock:
            item = self._data.get(user_id)
            if item is None:
                return None
            mode, expires = item
            if self._clock() >= expires:
                del self._data[user_id]
                return None
            return mode

    def clear(self, user_id: str) -> None:
        with self._lock:
            self._data.pop(user_id, None)
