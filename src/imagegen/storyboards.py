"""Shared multi-scene storyboard normalization and image composition."""

from __future__ import annotations

import io
import json
import re
from typing import Any

from PIL import Image, ImageDraw


MAX_STORYBOARD_PANELS = 6

# Character cards are user-authored public data, so keep the image prompt
# projection deliberately small and only select fields that can describe a
# visible person.  In particular, this helper never receives a game log.
_APPEARANCE_KEYS = (
    "appearance", "physical_description", "visual_description", "appearance_description",
    "looks", "外貌", "外貌特征", "外观", "人物外貌",
)
_VISUAL_MARKERS = re.compile(
    r"(?:外貌|外观|外形|头发|发色|眼睛|瞳|身高|体型|肤色|脸|面容|穿着|服装|衣着|裙|斗篷|铠|甲|盔|眼镜|义体|"
    r"appearance|look(?:s)?|hair|eyes?|height|build|skin|face|wear(?:s|ing)?|clothing|outfit|glasses|prosthetic)",
    re.IGNORECASE,
)
_EQUIPMENT_MARKERS = re.compile(r"(?:衣|裙|袍|斗篷|铠|甲|盔|帽|眼镜|服|coat|cloak|armor|armour|dress|uniform|hat|helmet|glasses)", re.IGNORECASE)


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _participants(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.replace("，", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    return list(dict.fromkeys(_text(item, 80) for item in values if _text(item, 80)))[:8]


def _first_text(mapping: Any, keys: tuple[str, ...], limit: int) -> str:
    if not isinstance(mapping, dict):
        return ""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return _text(value, limit)
    return ""


def _background_visual_excerpt(value: Any, limit: int = 360) -> str:
    """Extract only visually descriptive lines from a legacy freeform bio."""
    if not isinstance(value, str):
        return ""
    lines = [" ".join(line.split()) for line in value.splitlines() if line.strip()]
    selected: list[str] = []
    for line in lines:
        if _VISUAL_MARKERS.search(line):
            selected.append(line)
        if len(selected) >= 3:
            break
    return _text("；".join(selected), limit)


def _equipment_visual_excerpt(value: Any, limit: int = 240) -> str:
    if not isinstance(value, list):
        return ""
    names: list[str] = []
    for item in value:
        if isinstance(item, str):
            name = _text(item, 100)
        elif isinstance(item, dict):
            name = _text(item.get("name"), 100)
            slot = _text(item.get("slot"), 40)
            if name and not (_EQUIPMENT_MARKERS.search(name) or slot in {"armor", "body", "accessory"}):
                continue
        else:
            continue
        if name and name not in names:
            names.append(name)
        if len(names) >= 5:
            break
    return _text("、".join(names), limit)


def _public_character_summary(uid: str, player: Any) -> str:
    if not isinstance(player, dict):
        return ""
    sheet = player.get("character_sheet")
    if not isinstance(sheet, dict):
        sheet = player
    nested = sheet.get("ruleset_character")
    nested = nested if isinstance(nested, dict) else {}
    profile = nested.get("profile")
    profile = profile if isinstance(profile, dict) else sheet.get("profile")
    profile = profile if isinstance(profile, dict) else {}
    name = _text(player.get("character_name") or sheet.get("character_name") or uid, 100)
    traits: list[str] = []
    race = _text(sheet.get("race"), 60)
    role = _text(sheet.get("class"), 80)
    if race:
        traits.append(f"race/species: {race}")
    if role:
        traits.append(f"role: {role}")
    appearance = _first_text(profile, _APPEARANCE_KEYS, 520)
    if not appearance:
        appearance = _first_text(nested, _APPEARANCE_KEYS, 520)
    if not appearance:
        appearance = _first_text(sheet, _APPEARANCE_KEYS, 520)
    if not appearance:
        appearance = _background_visual_excerpt(sheet.get("background"), 360)
    if not appearance:
        appearance = _background_visual_excerpt(nested.get("background"), 360)
    equipment = _equipment_visual_excerpt(sheet.get("equipment"))
    details: list[str] = []
    if appearance:
        details.append(f"appearance: {appearance}")
    if equipment:
        details.append(f"visual equipment: {equipment}")
    if not details and not traits:
        return name
    return f"{name} ({'; '.join(traits + details)})"


def public_character_appearances(players: Any) -> dict[str, str]:
    """Return bounded, public appearance summaries keyed by stable player ID."""
    if not isinstance(players, dict):
        return {}
    result: dict[str, str] = {}
    for uid, player in list(players.items())[:16]:
        key = _text(uid, 80)
        summary = _public_character_summary(key, player)
        if key and summary:
            result[key] = summary[:900]
    return result


def normalize_scene_panels(raw: Any, *, max_panels: int = MAX_STORYBOARD_PANELS) -> tuple[list[dict[str, Any]], int]:
    """Normalize untrusted panel data and return ``(panels, compressed_count)``."""

    if not isinstance(raw, (list, tuple)):
        return [], 0
    panels: list[dict[str, Any]] = []
    by_location: dict[str, dict[str, Any]] = {}
    overflow = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        participants = _participants(item.get("participants", item.get("players")))
        location = _text(item.get("location"), 160)
        description = _text(item.get("description", item.get("prompt")), 700)
        if not location and not description:
            continue
        location = location or "当前场景"
        description = description or location
        location_key = re.sub(r"[\s，,。.!！?？:：;；、]+", "", location).casefold()
        existing = by_location.get(location_key)
        if existing is not None:
            existing["participants"] = list(dict.fromkeys(
                [*existing["participants"], *participants]
            ))[:8]
            if description not in existing["description"]:
                existing["description"] = _text(
                    f"{existing['description']}；{description}", 700,
                )
            continue
        if len(panels) >= max(1, int(max_panels)):
            overflow += 1
            continue
        panel = {
            "participants": participants,
            "location": location,
            "description": description,
        }
        panels.append(panel)
        by_location[location_key] = panel
    return panels, overflow


def _fallback_scene_panel(
    *, narration: str, actions: Any, current_scene: str, players: Any,
    global_prompt: str,
) -> list[dict[str, Any]]:
    participant_ids: list[str] = []
    if isinstance(actions, (list, tuple)):
        participant_ids.extend(
            _text(action.get("user_id"), 80)
            for action in actions
            if isinstance(action, dict) and _text(action.get("user_id"), 80)
        )
    if not participant_ids and isinstance(players, dict):
        participant_ids.extend(_text(uid, 80) for uid in players if _text(uid, 80))
    location = _text(current_scene, 160) or "当前场景"
    description = _text(narration, 700) or _text(global_prompt, 700) or location
    return [{
        "participants": list(dict.fromkeys(participant_ids))[:8],
        "location": location,
        "description": description,
    }]


def _json_object(text: Any) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        value = json.loads(raw[start:end + 1])
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _evidence_text(value: Any) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]+", "", str(value or "").casefold())


async def infer_scene_panels(
    llm_client: Any,
    *,
    narration: str,
    actions: Any,
    current_scene: str,
    players: Any,
    global_prompt: str = "",
    declared_panels: Any = None,
) -> tuple[list[dict[str, Any]], int]:
    """Infer public simultaneous locations, falling back conservatively to one shot."""

    declared, declared_compressed = normalize_scene_panels(declared_panels)
    if declared:
        return declared, declared_compressed

    fallback = _fallback_scene_panel(
        narration=narration,
        actions=actions,
        current_scene=current_scene,
        players=players,
        global_prompt=global_prompt,
    )
    if llm_client is None or not hasattr(llm_client, "call"):
        return fallback, 0

    public_players: list[dict[str, str]] = []
    if isinstance(players, dict):
        for uid, player in list(players.items())[:16]:
            uid_text = _text(uid, 80)
            if not uid_text:
                continue
            name = ""
            if isinstance(player, dict):
                name = _text(player.get("character_name"), 100)
            public_players.append({"id": uid_text, "name": name or uid_text})
    if len(public_players) < 2:
        return fallback, 0
    public_actions: list[dict[str, str]] = []
    if isinstance(actions, (list, tuple)):
        for action in actions[:16]:
            if not isinstance(action, dict):
                continue
            text = _text(action.get("text"), 500)
            if text:
                public_actions.append({
                    "player_id": _text(action.get("user_id"), 80),
                    "action": text,
                })

    payload = {
        "current_scene": _text(current_scene, 160),
        "players": public_players,
        "public_actions": public_actions,
        "public_gm_narration": _text(narration, 1600),
        "gm_visual_draft": _text(global_prompt, 1800),
    }
    system_prompt = (
        "You analyze public tabletop RPG narration for scene illustration. "
        "Return only one JSON object with a panels array. Use 2-6 panels only when the text "
        "clearly places player characters in different locations at the same time. Do not split "
        "sequential beats, camera angles, or different actions in one location. If locations are "
        "uncertain, return exactly one panel. Merge characters at the same location. Preserve the "
        "story order. Each panel must contain participants (exact player IDs from the input), "
        "location, and a concise public visual description. Never infer secrets or private content. "
        "Maximum six panels. Also return compressed_count for distinct locations omitted beyond six."
    )
    try:
        response = await llm_client.call(
            system_prompt,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            temperature=0.1,
            max_tokens=900,
            json_mode=True,
        )
        parsed = _json_object(getattr(response, "content", ""))
        inferred, removed = normalize_scene_panels(parsed.get("panels"))
    except Exception:
        return fallback, 0
    if not inferred:
        return fallback, 0

    allowed_ids = {item["id"] for item in public_players}
    name_to_id = {item["name"].casefold(): item["id"] for item in public_players}
    for panel in inferred:
        resolved: list[str] = []
        for participant in panel["participants"]:
            uid = participant if participant in allowed_ids else name_to_id.get(participant.casefold(), "")
            if uid and uid not in resolved:
                resolved.append(uid)
        panel["participants"] = resolved

    # One panel remains one uninterrupted image even when the model improves
    # the location or participant metadata.
    if len(inferred) == 1:
        if not inferred[0]["participants"]:
            inferred[0]["participants"] = fallback[0]["participants"]
        return inferred, 0
    evidence_parts = [str(narration or ""), str(global_prompt or "")]
    if isinstance(actions, (list, tuple)):
        evidence_parts.extend(
            str(action.get("text") or "")
            for action in actions
            if isinstance(action, dict)
        )
    public_evidence = _evidence_text(" ".join(evidence_parts))
    # Multi-panel output needs textual evidence for every claimed location.
    # This rejects a model-created comic split when the public story only
    # describes one place.
    if any(
        not (location_key := _evidence_text(panel["location"]))
        or location_key not in public_evidence
        for panel in inferred
    ):
        return fallback, 0
    try:
        reported_compressed = max(0, int(parsed.get("compressed_count") or 0))
    except (TypeError, ValueError):
        reported_compressed = 0
    return inferred, reported_compressed + removed


def storyboard_layout(panel_count: int) -> str:
    return {
        1: "single", 2: "two-panel", 3: "three-panel", 4: "four-panel",
        5: "five-panel", 6: "six-panel",
    }.get(max(1, min(MAX_STORYBOARD_PANELS, int(panel_count or 1))), "single")


def storyboard_metadata(panels: Any, compressed_count: int = 0) -> dict[str, Any]:
    normalized, removed = normalize_scene_panels(panels)
    return {
        "layout": storyboard_layout(len(normalized)),
        "panels": normalized,
        "compressed_count": max(0, int(compressed_count or 0)) + removed,
    }


def build_storyboard_prompt(
    panels: Any,
    *,
    global_prompt: str = "",
    character_appearances: Any = None,
) -> tuple[str, dict[str, Any]]:
    """Build a provider-neutral prompt and metadata for one shared image."""

    metadata = storyboard_metadata(panels)
    normalized = metadata["panels"]
    if not normalized:
        return _text(global_prompt, 8000), metadata
    if len(normalized) == 1:
        lines = [
            "Create one continuous wide tabletop RPG scene illustration in a single frame.",
            "This is one location and one uninterrupted camera view. Do not create panels, "
            "comic grids, collages, split screens, gutters, borders, or multiple separate images.",
        ]
    else:
        lines = [
            "Create one shared tabletop RPG storyboard image with exactly "
            f"{len(normalized)} distinct panels, in the listed order.",
        ]
    included_appearance_uids: set[str] = set()
    for index, panel in enumerate(normalized, 1):
        people = ", ".join(panel["participants"]) or "the shared party"
        label = "Scene" if len(normalized) == 1 else f"Panel {index}"
        lines.append(
            f"{label}: location {panel['location']}; subjects {people}; "
            f"visual description {panel['description']}."
        )
        if isinstance(character_appearances, dict):
            selected = panel["participants"]
            candidates = (
                [
                    (uid, character_appearances[uid])
                    for uid in selected
                    if uid in character_appearances and uid not in included_appearance_uids
                ]
                if selected else [
                    (uid, value)
                    for uid, value in character_appearances.items()
                    if uid not in included_appearance_uids
                ]
            )
            summaries = []
            for uid, value in candidates:
                summary = _text(value, 900)
                if summary:
                    summaries.append(summary)
                    included_appearance_uids.add(uid)
            if summaries:
                lines.append(
                    label + " public character appearance references: "
                    + " | ".join(summaries[:8]) + ". Keep these identities and clothing consistent."
                )
    if global_prompt.strip():
        lines.append(f"Overall context and style: {_text(global_prompt, 1800)}")
    if len(normalized) == 1:
        lines.append(
            "Use a natural horizontal scene composition with restrained colors and a readable environment. "
            "No text, names, labels, watermark, speech bubbles, UI, or internal divider lines."
        )
    else:
        lines.append(
            "Use a clean comic storyboard composition with clear dark gutters between panels. "
            "Keep each panel visually separate, restrained colors, readable environment, "
            "no text, names, labels, watermark, speech bubbles, or UI."
        )
    return "\n".join(lines)[:8000], metadata


def draw_storyboard_dividers(image: Image.Image, panel_count: int) -> Image.Image:
    """Draw deterministic gutters after generation so panel boundaries are guaranteed."""

    count = max(1, min(MAX_STORYBOARD_PANELS, int(panel_count or 1)))
    if count <= 1:
        return image
    result = image.convert("RGB")
    draw = ImageDraw.Draw(result)
    width, height = result.size
    line_width = max(4, min(width, height) // 180)
    # Keep gutters legible on both dark and bright generated scenes without
    # hard-coding a color that disappears into the artwork.
    luminance = sum(result.resize((1, 1)).getpixel((0, 0))) / 3
    color = (238, 240, 244) if luminance < 110 else (28, 31, 35)
    if count == 2:
        x = width // 2
        draw.rectangle((x - line_width // 2, 0, x + line_width // 2, height), fill=color)
    elif count == 3:
        x = (width * 2) // 3
        y = height // 2
        draw.rectangle((x - line_width // 2, 0, x + line_width // 2, height), fill=color)
        draw.rectangle((x, y - line_width // 2, width, y + line_width // 2), fill=color)
    elif count == 4:
        x = width // 2
        y = height // 2
        draw.rectangle((x - line_width // 2, 0, x + line_width // 2, height), fill=color)
        draw.rectangle((0, y - line_width // 2, width, y + line_width // 2), fill=color)
    elif count == 5:
        y = height * 3 // 5
        for x in (width // 3, width * 2 // 3):
            draw.rectangle((x - line_width // 2, 0, x + line_width // 2, y), fill=color)
        draw.rectangle((0, y - line_width // 2, width, y + line_width // 2), fill=color)
        draw.rectangle((width // 2 - line_width // 2, y, width // 2 + line_width // 2, height), fill=color)
    else:
        for x in (width // 3, width * 2 // 3):
            draw.rectangle((x - line_width // 2, 0, x + line_width // 2, height), fill=color)
        y = height // 2
        draw.rectangle((0, y - line_width // 2, width, y + line_width // 2), fill=color)
    return result


def overlay_storyboard_dividers(raw: bytes, panel_count: int) -> bytes:
    """Overlay gutters on provider bytes while preserving a normal PNG payload."""

    if panel_count <= 1:
        return raw
    with Image.open(io.BytesIO(raw)) as source:
        image = draw_storyboard_dividers(source, panel_count)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
