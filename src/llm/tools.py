"""LLM 工具协议定义。

工具 schema 只描述模型可以提出的意图；玩家身份、属性、目标值和骰制仍由
命令层校验，模型不能直接生成骰值或写入游戏状态。
"""

from __future__ import annotations

from typing import Any


DICE_CHECKS_TOOL_NAME = "dice_checks"

DICE_CHECKS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": DICE_CHECKS_TOOL_NAME,
        "description": (
            "Inspect the complete batch of player actions and request only checks that are "
            "meaningful, uncertain, and consequential. Return an empty checks array when no roll is needed."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "checks": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "player": {
                                "type": "string",
                                "description": "Exact player id or character name from the supplied roster.",
                            },
                            "attribute": {
                                "type": "string",
                                "description": (
                                    "Exact canonical attribute key from the supplied ruleset. Required for d20; "
                                    "optional for a d100 skill check. Never put a skill name here."
                                ),
                            },
                            "skill": {
                                "type": "string",
                                "description": "Optional exact skill name from the supplied character sheet.",
                            },
                            "target": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "description": (
                                    "Situational DC for d20. Omit for d100: the server derives the percentile "
                                    "threshold from the selected character attribute or skill."
                                ),
                            },
                            "modifier": {
                                "type": "integer",
                                "minimum": -20,
                                "maximum": 20,
                                "description": "Optional situational modifier; do not include sheet bonuses here.",
                            },
                            "advantage": {
                                "type": "string",
                                "enum": ["normal", "advantage", "disadvantage"],
                            },
                            "kind": {
                                "type": "string",
                                "enum": ["check", "save", "attack"],
                            },
                            "opponent": {
                                "type": "string",
                                "description": "Optional player/NPC opponent reference for a contested check.",
                            },
                            "assist": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 5,
                            },
                            "reason": {
                                "type": "string",
                                "maxLength": 160,
                                "description": "Short private reason for why a check is warranted.",
                            },
                        },
                        "required": ["player"],
                    },
                },
            },
            "required": ["checks"],
        },
    },
}
