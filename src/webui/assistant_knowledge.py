"""DiceFrame 公开文档的轻量检索索引。

优先加载随程序打包的预建索引包（scripts/build_assistant_knowledge.py 生成），
不联网、不解析 markdown，秒检索。预建索引不存在时（开发环境）回退到运行时
解析本地 docs。便携版 / 源码发布包通过预建索引获得文档，无需打包原始 docs。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("trpg")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_FILE = Path(__file__).parent / "assistant_knowledge_index.json"
_DOCUMENTS = {
    "zh": (
        "README.md",
        "docs/zh/updates.md",
    ),
    "en": (
        "README_EN.md",
        "docs/en/updates.md",
    ),
}
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_ASCII_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_.:/+-]*", re.IGNORECASE)
_CJK_RE = re.compile(r"[㐀-鿿]+")
_MAX_CHUNK_CHARS = 3600
_DEFAULT_CONTEXT_CHARS = 6_000


@dataclass(frozen=True)
class DocumentChunk:
    source: str
    heading: str
    text: str
    tokens: Counter[str]
    heading_tokens: frozenset[str]


@dataclass(frozen=True)
class KnowledgeResult:
    context: str
    sources: list[dict[str, str]]


_CACHE: dict[str, tuple[str, tuple[DocumentChunk, ...]]] = {}
_CACHE_LOCK = asyncio.Lock()


def _language_key(language: str) -> str:
    return "en" if (language or "").lower().startswith("en") else "zh"


def _tokens(text: str) -> list[str]:
    normalized = text.lower()
    result = _ASCII_WORD_RE.findall(normalized)
    for sequence in _CJK_RE.findall(normalized):
        result.append(sequence)
        if len(sequence) > 1:
            result.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return result


def _split_long_text(text: str, limit: int = _MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    paragraphs = re.split(r"\n{2,}", text)
    parts: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if not paragraph:
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
        while len(paragraph) > limit:
            parts.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        parts.append(current)
    return parts


def _parse_markdown(source: str, text: str) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    headings: list[str] = []
    body: list[str] = []

    def flush() -> None:
        value = "\n".join(body).strip()
        if not value:
            return
        heading = " > ".join(headings) or source
        for part in _split_long_text(value):
            chunks.append(
                DocumentChunk(
                    source=source,
                    heading=heading,
                    text=part,
                    tokens=Counter(_tokens(f"{heading}\n{part}")),
                    heading_tokens=frozenset(_tokens(heading)),
                )
            )

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if not match:
            body.append(line)
            continue
        flush()
        body = []
        level = len(match.group(1))
        title = match.group(2).strip()
        headings = headings[: level - 1]
        headings.append(title)
    flush()
    return chunks


def _load_built_index(lang_key: str) -> tuple[DocumentChunk, ...] | None:
    """加载预建索引包；不存在或损坏返回 None，由调用方回退到运行时解析。"""
    if not INDEX_FILE.exists():
        return None
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    items = data.get(lang_key) if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    chunks: list[DocumentChunk] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        tokens = item.get("tokens")
        heading_tokens = item.get("heading_tokens")
        chunks.append(
            DocumentChunk(
                source=str(item.get("source") or ""),
                heading=str(item.get("heading") or ""),
                text=str(item.get("text") or ""),
                tokens=Counter(tokens if isinstance(tokens, dict) else {}),
                heading_tokens=frozenset(heading_tokens if isinstance(heading_tokens, list) else []),
            )
        )
    return tuple(chunks)


def _build_index_from_local(lang_key: str) -> tuple[DocumentChunk, ...]:
    """兜底：预建索引不存在时（开发环境），运行时解析本地 docs。"""
    chunks: list[DocumentChunk] = []
    for relative in _DOCUMENTS[lang_key]:
        try:
            text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        except OSError:
            continue
        chunks.extend(_parse_markdown(relative, text))
    return tuple(chunks)


def _local_signature(lang_key: str) -> str:
    """本地 docs 内容签名，内容变化才重建索引。"""
    digest = hashlib.sha256()
    for relative in _DOCUMENTS[lang_key]:
        try:
            text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        except OSError:
            text = ""
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


async def _index(language: str) -> tuple[DocumentChunk, ...]:
    lang_key = _language_key(language)
    built = _load_built_index(lang_key)
    if built is not None:
        signature = "built"
    else:
        signature = _local_signature(lang_key)
    cached = _CACHE.get(lang_key)
    if cached and cached[0] == signature:
        return cached[1]
    async with _CACHE_LOCK:
        cached = _CACHE.get(lang_key)
        if cached and cached[0] == signature:
            return cached[1]
        chunks = built if built is not None else _build_index_from_local(lang_key)
        _CACHE[lang_key] = (signature, chunks)
        return chunks


def _score(chunk: DocumentChunk, query_tokens: Counter[str], normalized_query: str) -> float:
    score = 0.0
    for token, query_count in query_tokens.items():
        count = chunk.tokens.get(token, 0)
        if not count:
            continue
        score += query_count * (1.0 + math.log1p(count))
        if token in chunk.heading_tokens:
            score += query_count * 3.5
    compact_query = re.sub(r"\s+", "", normalized_query.lower())
    compact_text = re.sub(r"\s+", "", f"{chunk.heading}\n{chunk.text}".lower())
    if len(compact_query) >= 3 and compact_query in compact_text:
        score += 8.0
    return score


async def search_knowledge(
    query: str,
    language: str,
    *,
    limit: int = 4,
    max_chars: int = _DEFAULT_CONTEXT_CHARS,
) -> KnowledgeResult:
    query_tokens = Counter(_tokens(query))
    if not query_tokens:
        return KnowledgeResult(context="", sources=[])
    scored = [
        (_score(chunk, query_tokens, query), chunk)
        for chunk in await _index(language)
    ]
    scored = [(score, chunk) for score, chunk in scored if score >= 2.0]
    scored.sort(key=lambda item: (-item[0], item[1].source, item[1].heading))

    selected: list[DocumentChunk] = []
    seen: set[tuple[str, str]] = set()
    used_chars = 0
    for _, chunk in scored:
        identity = (chunk.source, chunk.heading)
        if identity in seen:
            continue
        rendered = f"[来源: {chunk.source} > {chunk.heading}]\n{chunk.text}"
        if selected and used_chars + len(rendered) > max_chars:
            continue
        if not selected and len(rendered) > max_chars:
            rendered = rendered[:max_chars]
            chunk = DocumentChunk(
                source=chunk.source,
                heading=chunk.heading,
                text=rendered.split("\n", 1)[-1],
                tokens=chunk.tokens,
                heading_tokens=chunk.heading_tokens,
            )
        selected.append(chunk)
        seen.add(identity)
        used_chars += len(rendered)
        if len(selected) >= limit:
            break

    context_parts = [
        f"[来源: {chunk.source} > {chunk.heading}]\n{chunk.text}"
        for chunk in selected
    ]
    sources = [{"source": chunk.source, "heading": chunk.heading} for chunk in selected]
    return KnowledgeResult(context="\n\n".join(context_parts), sources=sources)
