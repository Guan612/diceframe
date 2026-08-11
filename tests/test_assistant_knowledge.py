from __future__ import annotations

import os

import pytest

from src.webui import assistant_knowledge


@pytest.fixture
def knowledge_docs(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    guide = tmp_path / "docs" / "GUIDE_CN.md"
    guide.write_text(
        "# 用户指南\n\n## API 配置\n在设置页面填写模型地址、模型名和 API Key。\n\n"
        "## 插件\n在插件商店安装插件。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(assistant_knowledge, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(assistant_knowledge, "_DOCUMENTS", {
        "zh": ("docs/GUIDE_CN.md",),
        "en": ("docs/GUIDE_CN.md",),
    })
    monkeypatch.setattr(assistant_knowledge, "_CACHE", {})
    monkeypatch.setattr(assistant_knowledge, "INDEX_FILE", tmp_path / "nonexistent.json")
    return guide


@pytest.mark.asyncio
async def test_search_returns_relevant_chunk_and_source(knowledge_docs):
    result = await assistant_knowledge.search_knowledge("怎么配置 API", "zh-CN")
    assert "填写模型地址" in result.context
    assert result.sources == [{"source": "docs/GUIDE_CN.md", "heading": "用户指南 > API 配置"}]


@pytest.mark.asyncio
async def test_index_refreshes_after_document_change(knowledge_docs):
    first = await assistant_knowledge.search_knowledge("插件怎么安装", "zh-CN")
    assert "插件商店" in first.context

    knowledge_docs.write_text(
        "# 用户指南\n\n## 插件\n新版说明：从插件页上传 dfplugin。\n",
        encoding="utf-8",
    )
    stat = knowledge_docs.stat()
    os.utime(knowledge_docs, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    second = await assistant_knowledge.search_knowledge("插件怎么安装", "zh-CN")
    assert "新版说明" in second.context
    assert "插件商店" not in second.context


@pytest.mark.asyncio
async def test_unrelated_query_returns_no_context(knowledge_docs):
    result = await assistant_knowledge.search_knowledge("量子物理光谱", "zh-CN")
    assert result.context == ""
    assert result.sources == []
