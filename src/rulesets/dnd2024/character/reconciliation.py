"""Re-derive D&D 2024 canonical mechanics from live character state.

Authority runs one way only::

    character_sheet.equipment      <- 当前实际穿戴（live authority）
    character_sheet.inventory      <- 当前持有但未穿戴
    ruleset_character.equipment.item_refs
                                   <- 上面两者的 Ruleset Projection，不是第三份事实

``equipment.item_grants`` stays what it always was: character creation
provenance.  It records what a class/background package once handed out and is
never rewritten here, so selling or dropping starter gear can not be undone by
a later projection.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .derivation import derive_armor_class
from .primitives import ref_id as _ref_id

logger = logging.getLogger("trpg")

_MAX_OPERATION_LOG = 32

# 参与 canonical 装备投影的物品类型。其余（消耗品、工具包、箭矢…）留在 live
# inventory，不进入规则投影。
_PROJECTED_ITEM_TYPES = frozenset({"weapon", "armor", "shield", "focus"})

# Ruleset item type -> generic equipment slot.
#
# The generic layer owns the slot vocabulary but cannot know what a ruleset item
# is: with no item definition to consult it drops every non-weapon into "body",
# so putting on a shield or a holy symbol would evict the armor.  Mapping the
# ruleset's own item types onto generic slots keeps that knowledge where it
# belongs -- the specific layer depends on the generic vocabulary, never the
# other way round.  Armor deliberately keeps the historical "body" slot so
# existing saves need no migration.
_GENERIC_SLOTS = {
    "weapon": "main_hand",
    "armor": "body",
    "shield": "off_hand",
    "focus": "accessory",
}


def _normalized(text: Any) -> str:
    return str(text or "").strip().casefold()


def build_item_identity_index(bundles: Iterable[Any]) -> dict[str, str]:
    """Map every display name the ruleset ships, in every locale, to an item id.

    Locale never participates in rule authority: 锁子甲 / Chain Mail both have
    to land on ``item:chain_mail``.  The index is built from the bundle's own
    localized item definitions, so it stays correct when content is translated
    or renamed -- unlike a hand-maintained table of strings.
    """

    index: dict[str, str] = {}
    for bundle in bundles:
        for item in bundle.list("item"):
            item_id = str(item.get("id") or "")
            if not item_id:
                continue
            index.setdefault(_normalized(item_id), item_id)
            name = _normalized(item.get("name"))
            if name:
                index.setdefault(name, item_id)
    return index


def _compat_alias_index(known_ids: frozenset[str]) -> dict[str, str]:
    """Legacy display-name aliases, kept strictly as an old-save compat path.

    These cover locales the bundle does not ship content for (ja) and older
    hand-written names.  Only aliases that resolve to an item the ruleset
    actually defines are accepted, so the table can never invent mechanics.
    """

    from src.engine.constants import ITEM_KEY_ALIASES

    return {
        _normalized(alias): item_key
        for alias, item_key in ITEM_KEY_ALIASES.items()
        if item_key in known_ids
    }


class Dnd2024CharacterStateReconciler:
    """Project live equipment onto canonical D&D 2024 mechanics.

    Idempotent by construction: it compares the freshly derived projection with
    what the character already carries and writes nothing -- no canonical
    change, no revision bump, no operation log entry -- when they agree.
    """

    def __init__(self, bundle: Any, *, locale_bundles: Sequence[Any] = ()) -> None:
        self.bundle = bundle
        self._names = build_item_identity_index(locale_bundles or (bundle,))
        self._known_ids = frozenset(
            str(item.get("id") or "") for item in bundle.list("item")
        )
        self._aliases = _compat_alias_index(self._known_ids)

    # ------------------------------------------------------------------
    # canonical identity resolution
    # ------------------------------------------------------------------

    def _resolve_item_id(self, row: Mapping[str, Any]) -> str:
        """Resolve one live equipment row to a canonical item id.

        Priority is fixed by contract: an explicit ``item_ref`` wins, then the
        generic layer's ``item_key``, and only then -- as an old-save compat
        path -- the display name.  A localized name is never allowed to be the
        lasting identity; see :meth:`reconcile`, which writes the resolved
        ``item_ref`` back onto the row so the name is not consulted again.
        """

        raw_ref = str(row.get("item_ref") or "")
        if raw_ref:
            item_id = _ref_id(raw_ref, "item")
            if item_id in self._known_ids:
                return item_id

        item_key = str(row.get("item_key") or "")
        if item_key and item_key in self._known_ids:
            return item_key

        name = _normalized(row.get("name"))
        if not name:
            return ""
        return self._names.get(name) or self._aliases.get(name, "")

    def _project_equipped_refs(
        self, equipment: Sequence[Any], warnings: list[str],
    ) -> list[str]:
        """Return the canonical refs for what is currently worn."""

        refs: list[str] = []
        for row in equipment:
            if not isinstance(row, dict):
                continue
            item_id = self._resolve_item_id(row)
            if not item_id:
                # §64：解析不出规则身份时只记录警告并忽略其专业规则效果，
                # 绝不猜一个最像的物品，更不能因此删除玩家的装备。
                warnings.append(f"unresolved live equipment: {row.get('name')!r}")
                continue
            item = self.bundle.get("item", item_id) or {}
            if item.get("item_type") in _PROJECTED_ITEM_TYPES:
                refs.append(f"item:{item_id}")
        return list(dict.fromkeys(refs))

    def _annotate_live_rows(self, rows: Iterable[Any]) -> None:
        """Write canonical identity and placement onto live rows in place.

        Purchased or looted rows arrive carrying only a display name, so the
        generic layer has nothing to place them by.  Filling in ``item_ref``,
        ``type`` and ``slot`` here means a later equip lands in the right slot
        without the generic layer ever learning a D&D rule, and the localized
        name is never consulted again for this row.  Existing values are left
        alone: this annotates, it never overrides.
        """

        for row in rows:
            if not isinstance(row, dict):
                continue
            item_id = self._resolve_item_id(row)
            if not item_id:
                continue
            item = self.bundle.get("item", item_id) or {}
            item_type = str(item.get("item_type") or "")
            if not row.get("item_ref"):
                row["item_ref"] = f"item:{item_id}"
            if not row.get("item_key"):
                row["item_key"] = item_id
            if item_type and not row.get("type"):
                row["type"] = item_type
            slot = _GENERIC_SLOTS.get(item_type, "")
            if slot and not str(row.get("slot") or ""):
                row["slot"] = slot

    # ------------------------------------------------------------------
    # reconciliation
    # ------------------------------------------------------------------

    def reconcile(
        self, sheet: dict[str, Any], changed_domains: frozenset[str] = frozenset(),
    ) -> dict[str, Any] | None:
        """Re-derive the projection from ``sheet``; return a summary or ``None``.

        ``None`` means the projection was already current and the sheet was not
        touched.  ``changed_domains`` is only a hint about which live facts
        moved; the authoritative values are re-read from the sheet here.
        """

        canonical = sheet.get("ruleset_character")
        if not isinstance(canonical, dict):
            return None
        equipment = sheet.get("equipment")
        if not isinstance(equipment, list):
            equipment = []

        inventory = sheet.get("inventory")
        if not isinstance(inventory, list):
            inventory = []

        warnings: list[str] = []
        # §42：解析成功就把 canonical identity 补齐到 live metadata。背包行也要
        # 标注，否则刚买来的盾牌在装备时仍然没有槽位信息可用。
        self._annotate_live_rows(equipment)
        self._annotate_live_rows(inventory)
        item_refs = self._project_equipped_refs(equipment, warnings)

        abilities = canonical.get("abilities")
        if not isinstance(abilities, dict) or "dex" not in abilities:
            warnings.append("canonical abilities are unavailable; armor class not re-derived")
            return None
        armor_class = derive_armor_class(abilities, item_refs, self.bundle, warnings=warnings)

        canonical_equipment = canonical.setdefault("equipment", {})
        derived = canonical.setdefault("derived", {})
        previous_refs = list(canonical_equipment.get("item_refs") or [])
        previous_ac = derived.get("armor_class")
        mirror_ac = sheet.get("armor_class")

        for warning in warnings:
            logger.warning("D&D2024 装备投影告警: %s", warning)

        if (
            previous_refs == item_refs
            and previous_ac == armor_class
            and mirror_ac == armor_class
        ):
            return None

        canonical_equipment["item_refs"] = item_refs
        derived["armor_class"] = armor_class
        # §28：legacy / public mirror 必须与 canonical 一致，因为 Combat、UI、
        # LLM view 可能读不同层；但计算 authority 仍然只有上面那一处。
        sheet["armor_class"] = armor_class

        sources = canonical.get("sources")
        if isinstance(sources, dict) and isinstance(sources.get("content_entities"), list):
            sources["content_entities"] = list(dict.fromkeys(
                [*sources["content_entities"], *item_refs],
            ))

        revision = int(sheet.get("ruleset_revision", 0) or 0) + 1
        sheet["ruleset_revision"] = revision
        raw_log = sheet.get("ruleset_operation_log")
        operation_log = list(raw_log) if isinstance(raw_log, list) else []
        operation_log.append({
            "kind": "character_reconcile",
            "domains": sorted(changed_domains),
            "revision": revision,
        })
        sheet["ruleset_operation_log"] = operation_log[-_MAX_OPERATION_LOG:]

        return {
            "item_refs": item_refs,
            "armor_class": armor_class,
            "revision": revision,
            "warnings": warnings,
        }
