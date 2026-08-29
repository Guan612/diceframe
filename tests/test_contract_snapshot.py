"""前后端契约快照：后端关键端点返回的顶层字段必须被前端 types.ts 显式声明。

防止"后端加字段、前端漏改"导致的静默 undefined 漂移（types.ts 的 index
signature 会让 TS 永不报错，契约测试兜住）。

后端字段通过 AST 分析函数内所有 `return {...}` 字面量得到（函数重排、
拆分变量、增加早退分支都不影响结果）；前端字段来自 types.ts 这一公开
契约面本身。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _backend_return_top_keys(path: Path, func_name: str) -> list[str]:
    """提取函数内所有 return 字典字面量的顶层 key（合并）。"""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    target = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == func_name
        ),
        None,
    )
    assert target is not None, f"未找到后端函数 {func_name}"
    keys: set[str] = set()
    for node in ast.walk(target):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
    assert keys, f"{func_name} 未返回任何 dict 字面量"
    return sorted(keys)


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
