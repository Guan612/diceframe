"""World-level GM narrative style: normalization and prompt rendering.

gm_style 只调整叙事口吻，不得改变 canonical identity 或 mechanics。
旧世界缺字段时 normalize 为全缺省、render 为空串，行为与未引入前一致。
所有读取边界必须经过 normalize_gm_style，禁止散落 .get 默认值。
"""

from __future__ import annotations

from typing import Any

from src.engine.language import localized_text

VERBOSITY_LEVELS = ("brief", "normal", "detailed")
MAX_TONE_CHARS = 120
MAX_CUSTOM_INSTRUCTIONS = 2000


def normalize_gm_style(raw: Any) -> dict[str, str]:
    """宽容读取边界：类型/取值非法时回退缺省，不抛异常。"""
    if not isinstance(raw, dict):
        return {"tone": "", "verbosity": "normal", "custom_instructions": ""}
    tone = str(raw.get("tone") or "").strip()[:MAX_TONE_CHARS]
    verbosity = str(raw.get("verbosity") or "").strip().casefold()
    if verbosity not in VERBOSITY_LEVELS:
        verbosity = "normal"
    custom = str(raw.get("custom_instructions") or "").strip()[:MAX_CUSTOM_INSTRUCTIONS]
    return {"tone": tone, "verbosity": verbosity, "custom_instructions": custom}


def render_gm_style_section(world_data: dict[str, Any] | None, language: str) -> str:
    """把 gm_style 渲染为 GM prompt 的叙事风格小节；全缺省时返回空串。"""
    style = normalize_gm_style((world_data or {}).get("gm_style"))
    if not style["tone"] and style["verbosity"] == "normal" and not style["custom_instructions"]:
        return ""
    lines = [
        localized_text(language, {
            "en": "## GM Narration Style",
            "zh-CN": "## GM 叙事风格",
            "ja": "## GM ナラティブスタイル",
        }),
        localized_text(language, {
            "en": "The following only adjusts narration style and must never override the rules and mechanics adjudication above.",
            "zh-CN": "以下仅调整叙事风格，不得覆盖上文规则与机制判定。",
            "ja": "以下はナラティブスタイルのみを調整し、上記のルールと機制判定を上書きしてはならない。",
        }),
    ]
    if style["tone"]:
        lines.append(localized_text(language, {
            "en": f"Narration tone: {style['tone']}",
            "zh-CN": f"叙事口吻：{style['tone']}",
            "ja": f"ナラティブのトーン：{style['tone']}",
        }))
    if style["verbosity"] == "brief":
        lines.append(localized_text(language, {
            "en": "Keep narration concise; only describe key actions and turning points.",
            "zh-CN": "叙述从简，只写关键行动与转折。",
            "ja": "叙述は簡潔に。重要な行動と転換点のみを書く。",
        }))
    elif style["verbosity"] == "detailed":
        lines.append(localized_text(language, {
            "en": "Narration may be detailed, including environment, emotion, and sensory description.",
            "zh-CN": "叙述可以详尽，包含环境、情绪与感官描写。",
            "ja": "叙述は詳細にしてよい。環境・感情・感覚描写を含めてよい。",
        }))
    if style["custom_instructions"]:
        lines.append("")
        lines.append(style["custom_instructions"])
    return "\n".join(lines)
