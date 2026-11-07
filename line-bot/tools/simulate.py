"""LINEを使わずに、パソコンの画面で会話の流れを試すための道具（開発者向け）。

使い方:  python tools/simulate.py          （診断の受付は「停止」のまま）
        python tools/simulate.py --open   （診断の受付を「受付中」にして試す）
  文面は content/default_content.json から読みます。終わるときは Ctrl+C。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.content import ContentStore, JsonSource  # noqa: E402
from bot.records import MemoryRecords  # noqa: E402
from bot.router import Router  # noqa: E402


class Source(JsonSource):
    def read_tables(self):
        tables = super().read_tables()
        if "--open" in sys.argv:
            for row in tables["設定"]:
                if row["項目"] == "診断の受付":
                    row["値"] = "受付中"
        return tables


records = MemoryRecords()
router = Router(ContentStore(Source(), 0), records=records)
print("（あなた）に続けて文字を入れてください。例: おみくじ")
while True:
    try:
        text = input("（あなた）> ")
    except (EOFError, KeyboardInterrupt):
        print()
        break
    replies = router.handle_text("local-user", text)
    if not replies:
        print("（Bot）※返信なし")
    for r in replies:
        print("（Bot）" + r.text.replace("\n", "\n       "))
        if r.quick_replies:
            print("       [ボタン] " + " / ".join(r.quick_replies))
