"""把 docs 预处理成 AI 助手的本地检索索引包。

随程序打包，运行时直接加载（assistant_knowledge.py），不联网、不解析 markdown。
文档变动后重新运行本脚本；build_release 打包时会自动调用。

用法：
    python scripts/build_assistant_knowledge.py
    python scripts/build_assistant_knowledge.py --output path/to/index.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.webui import assistant_knowledge as ak


def build(output: Path | None = None) -> Path:
    target = output or ak.INDEX_FILE
    index: dict[str, list[dict]] = {}
    for lang_key in ("zh", "en"):
        chunks: list[dict] = []
        for relative in ak._DOCUMENTS[lang_key]:
            path = ROOT / relative
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            for chunk in ak._parse_markdown(relative, text):
                chunks.append(
                    {
                        "source": chunk.source,
                        "heading": chunk.heading,
                        "text": chunk.text,
                        "tokens": dict(chunk.tokens),
                        "heading_tokens": sorted(chunk.heading_tokens),
                    }
                )
        index[lang_key] = chunks
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v) for v in index.values())
    size_kb = target.stat().st_size / 1024
    print(
        f"assistant knowledge index: {total} chunks "
        f"({len(index['zh'])} zh + {len(index['en'])} en), {size_kb:.1f} KB -> {target}"
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the AI assistant local knowledge index.")
    parser.add_argument("--output", type=Path, default=None, help="Output index file path")
    args = parser.parse_args()
    build(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
