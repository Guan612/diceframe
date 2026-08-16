"""Audit rule templates for fields whose absence silently degrades gameplay.

Checks every bundled/plugin rule file (after resolving ``extends`` inheritance):

- Hard errors (exit 1): invalid JSON, missing ``rule_id``, malformed
  ``special_stats`` entries. These make a rule unusable or ambiguous.
- Warnings (exit 0 unless ``--strict``): ``special_stats`` entries without an
  explicit ``initial`` (the engine initializes them to max -- fine for
  resource pools, catastrophic for progress bars like KPI), and d20 rules
  with a skill budget whose effective skill bonus is always zero (skill
  values then have no mechanical effect).

Warnings are advisory: pure-narrative design is a legitimate choice; the goal
is to make the consequence visible, not to forbid it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rules.rule_system import RuleSystem  # noqa: E402

SCAN_GLOBS = [
    ROOT / "templates" / "rules" / "*.json",
    ROOT / "plugins" / "*" / "content" / "rules" / "*.json",
    ROOT / "data" / "plugin-packages" / "*" / "content" / "rules" / "*.json",
]

# Engine gives these keys dedicated initialization (CoC SAN/Luck).
_ENGINE_INITIALIZED_KEYS = {"sanity", "luck"}


def iter_rule_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in SCAN_GLOBS:
        files.update(p for p in Path(ROOT).glob(str(pattern.relative_to(ROOT))) if p.is_file())
    return sorted(files)


def audit_file(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    rel = path.relative_to(ROOT)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{rel}: JSON 无效: {exc}"], []

    if raw.get("abstract"):
        return [], []
    if not str(raw.get("rule_id") or "").strip():
        return [f"{rel}: 缺少 rule_id"], []

    for stat in raw.get("special_stats") or []:
        if not isinstance(stat, dict) or not str(stat.get("key") or "").strip():
            errors.append(f"{rel}: special_stats 存在缺 key 的条目")
            continue
        if "initial" not in stat and stat.get("key") not in _ENGINE_INITIALIZED_KEYS:
            warnings.append(
                f"{rel}: 特殊属性 '{stat.get('key')}' 未写 initial，引擎将默认初始化为满值 "
                f"({stat.get('key')}={stat.get('max', 99)})；进度条型属性请显式写 initial"
            )

    # 技能加值检查只对 d20 规则有意义：d100 技能值本身就是成功率，none 无检定。
    if str(raw.get("dice_system") or "").lower() != "d20":
        return errors, warnings
    try:
        rule = RuleSystem.load(path)
    except Exception as exc:  # 继承断裂/公式坏等，交给加载报错
        errors.append(f"{rel}: 规则加载失败: {exc}")
        return errors, warnings

    has_skill_budget = (
        bool(raw.get("skills"))
        or bool(rule.template.get("skill_pools"))
        or rule.skill_point_total > 0
        or rule.max_skill_value > 0
    )
    if (
        has_skill_budget
        and rule.skill_mode != "proficiency"
        and rule.skill_bonus(80) == 0
    ):
        warnings.append(
            f"{rel}: 定义了技能但有效技能加值恒为 0（技能值不影响检定）。"
            f"如需技能生效请配置 skill_value_to_bonus（参考 base_d20: 20->+1, 40->+2, 60->+3, 80->+4），"
            f"纯叙事设计可忽略"
        )
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="警告也视为失败（用于内容包源头仓库的自检）")
    args = parser.parse_args()

    files = iter_rule_files()
    if not files:
        print("未发现规则文件，无内容可审计", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for path in files:
        errors, warnings = audit_file(path)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    for line in all_warnings:
        print(f"[warn] {line}")
    for line in all_errors:
        print(f"[error] {line}", file=sys.stderr)
    print(f"规则审计完成: {len(files)} 个文件, {len(all_warnings)} 个警告, {len(all_errors)} 个错误")
    if all_errors:
        return 1
    if args.strict and all_warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
