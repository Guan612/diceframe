"""P2-N：前后端契约快照——后端关键端点返回的顶层字段必须被前端 types.ts 显式声明。

防止"后端加字段、前端漏改"导致的静默 undefined 漂移（types.ts 的 index signature
会让 TS 永不报错，契约测试兜住）。纯静态比对，不依赖运行环境。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _backend_return_top_keys(path: Path, func_name: str) -> list[str]:
    """提取后端 async 函数末尾 `return { ... }` 块里的顶层 dict key。

    限定在函数体内（下一个顶层 async def 之前），并取最后一个 return 块，
    避免早退 return 与嵌套 dict 的 key 混入。
    """
    text = path.read_text(encoding="utf-8")
    start = text.find(f"async def {func_name}")
    if start == -1:
        raise AssertionError(f"未找到后端函数 {func_name}")
    body_end = text.find("\nasync def ", start + 1)
    if body_end == -1:
        body_end = len(text)
    ret = text.rfind("return {", start, body_end)
    assert ret != -1, f"{func_name} 无 return dict"
    depth = 0
    keys: list[str] = []
    i = ret + len("return {")
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        elif ch == '"' and depth == 0:
            m = re.match(r'"(\w+)"\s*:', text[i:])
            if m:
                keys.append(m.group(1))
                i += m.end() - 1
        i += 1
    return keys


def _ts_interface_fields(path: Path, name: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"export interface {name} \{{(.*?)\n\}}", text, re.S)
    if not m:
        raise AssertionError(f"前端未找到 interface {name}")
    fields = set(re.findall(r"^\s{2}(\w+)\??:", m.group(1), re.M))
    fields.discard("key")  # [key: string] index signature
    return fields


def test_create_game_contract_snapshot():
    """后端 create_game 返回字段 ⊆ 前端 GameMutationResponse 显式声明。"""
    backend_keys = _backend_return_top_keys(
        ROOT / "src" / "webui" / "services" / "games.py", "create_game"
    )
    frontend = _ts_interface_fields(
        ROOT / "frontend-v2" / "src" / "api" / "types.ts", "GameMutationResponse"
    )
    missing = [k for k in backend_keys if k not in frontend]
    assert not missing, (
        f"后端 create_game 返回了前端 GameMutationResponse 未声明的字段: {missing}\n"
        f"请在 frontend-v2/src/api/types.ts 补声明，否则前端会静默拿到 undefined。"
    )


def test_ts_interface_fields_extractor():
    """提取器自身冒烟：应抓到 GameMutationResponse 的已知字段。"""
    frontend = _ts_interface_fields(
        ROOT / "frontend-v2" / "src" / "api" / "types.ts", "GameMutationResponse"
    )
    for key in ("ok", "game_key", "world_name", "generated_password", "players"):
        assert key in frontend, f"前端 GameMutationResponse 应声明 {key}"
