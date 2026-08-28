"""内置 QQ / NapCat 插件与权威独立仓库的流程一致性测试。

独立 `qq-napcat` 仓库已使用“行动收齐后系统自动判定并掷骰”，内置副本
`trpg/plugins/qq-napcat` 必须保持同一流程，不得退回“玩家手动发送 @我 掷骰
确认”的旧行为。本测试通过检查内置插件源码与 README 文案来捕获漂移；
不依赖工作区里的兄弟 `qq-napcat` 目录，可在任意 checkout 单独运行。
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "qq-napcat"
ADAPTER = PLUGIN_ROOT / "src" / "bots" / "qq" / "adapter.py"
README_CN = PLUGIN_ROOT / "README_CN.md"
README_EN = PLUGIN_ROOT / "README_EN.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_builtin_qq_adapter_uses_automatic_adjudication() -> None:
    """内置 adapter.py 必须采用自动判定，不保留手动掷骰确认流程。"""
    source = _read(ADAPTER)

    # 新流程：新检定结果展示与“系统自动判断并掷骰”帮助文案。
    for marker in (
        "format_check_result",
        "检定由系统自动判断并掷骰",
        "checks are adjudicated and rolled automatically",
        "Checks are adjudicated and rolled automatically after everyone acts",
        "不需要手动确认掷骰",
    ):
        assert marker in source, f"内置 adapter.py 缺少新流程标记: {marker!r}"

    # 旧流程：手动确认掷骰相关的状态与提示必须移除。
    for marker in (
        "pending_dice",
        "回复 @我 掷骰",
        "roll — confirm a pending check",
        "3. 需要检定时：@我 掷骰",
        "There is no roll waiting for confirmation",
    ):
        assert marker not in source, f"内置 adapter.py 仍残留旧流程标记: {marker!r}"


def test_builtin_qq_plugin_readme_cn_has_no_manual_roll() -> None:
    """内置插件中文 README 不得再让玩家手动确认掷骰。"""
    text = _read(README_CN)
    for marker in ("@Bot 掷骰", "@bot 掷骰", "确认需要骰子的行动"):
        assert marker not in text, f"内置 README_CN 仍残留手动掷骰说明: {marker!r}"
    assert "不需要玩家确认掷骰" in text


def test_builtin_qq_plugin_readme_en_has_no_manual_roll() -> None:
    """内置插件英文 README 不得再让玩家手动确认掷骰。"""
    text = _read(README_EN)
    for marker in ("@Bot roll", "confirm an action that is waiting for dice"):
        assert marker not in text, f"内置 README_EN 仍残留手动掷骰说明: {marker!r}"
    assert "without player confirmation" in text


def test_builtin_qq_adapter_supports_read_only_kp_questions() -> None:
    source = _read(ADAPTER)
    readme_cn = _read(README_CN)
    readme_en = _read(README_EN)

    for marker in (
        "_kp_question",
        "self.api.ask_kp",
        "桌外问 KP（不耗行动）",
        "_ask_kp_group",
    ):
        assert marker in source or marker in readme_cn, f"缺少 KP 答疑标记: {marker!r}"
    assert "@Bot 询问 <问题>" in readme_cn
    assert "@Bot ask <question>" in readme_en
