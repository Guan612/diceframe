"""Adventure catalogue and server-owned compatibility resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.adventures import AdventureBundleError, LoadedAdventureBundle

if TYPE_CHECKING:
    from src.webui.api import WebAPI


def _runtime_for_rule(api: "WebAPI", rule_id: str, language: str) -> Any | None:
    rule = api._load_rule_by_id(str(rule_id or "").strip(), language)
    if rule is None:
        return None
    try:
        return api._ruleset_registry.resolve(rule.template)
    except (AttributeError, TypeError, ValueError):
        return None


def _compatibility(
    bundle: LoadedAdventureBundle, runtime: Any | None, world_id: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    manifest = bundle.manifest
    if runtime is None:
        reasons.append("ruleset_runtime_unavailable")
    else:
        formats = set(getattr(runtime.capabilities, "adventure_formats", ()) or ())
        if manifest.format not in formats:
            reasons.append("adventure_format_unsupported")
        if runtime.runtime_id != manifest.required_runtime_id:
            reasons.append("runtime_id_mismatch")
        if runtime.runtime_version < manifest.required_runtime_version:
            reasons.append("runtime_version_too_old")
    if (
        manifest.world_policy == "fixed"
        and str(world_id or "") != manifest.recommended_world_id
    ):
        reasons.append("world_mismatch")
    return ("compatible" if not reasons else "incompatible", reasons)


def list_adventures(
    api: "WebAPI", rule_id: str = "", world_id: str = "", language: str = "",
) -> dict[str, Any]:
    runtime = _runtime_for_rule(api, rule_id, language)
    try:
        bundles = api._adventure_loader.list(language)
    except AdventureBundleError as exc:
        return {"ok": False, "error_code": "ADVENTURE_CATALOG_INVALID", "error": str(exc)}
    items: list[dict[str, Any]] = []
    for bundle in bundles:
        status, reasons = _compatibility(bundle, runtime, world_id)
        adventure = bundle.adventure
        items.append({
            "adventure_id": bundle.manifest.adventure_id,
            "version": bundle.manifest.version,
            "format": bundle.manifest.format,
            "world_policy": bundle.manifest.world_policy,
            "recommended_world_id": bundle.manifest.recommended_world_id,
            "required_runtime": {
                "id": bundle.manifest.required_runtime_id,
                "minimum_version": bundle.manifest.required_runtime_version,
            },
            "name": str(adventure.get("tutorial", {}).get("name") or adventure.get("name") or adventure["id"]),
            "summary": str(adventure.get("tutorial", {}).get("summary") or adventure.get("summary") or ""),
            "estimated_minutes": int(adventure.get("estimated_minutes", 0) or 0),
            "compatibility": status,
            "incompatibility_reasons": reasons,
        })
    return {"ok": True, "adventures": items}


def resolve_binding(
    api: "WebAPI", adventure_id: str, rule_id: str, world_id: str, language: str,
) -> dict[str, Any]:
    wanted = str(adventure_id or "").strip()
    if not wanted:
        return {}
    runtime = _runtime_for_rule(api, rule_id, language)
    try:
        bundle = api._adventure_loader.resolve(wanted, language)
    except AdventureBundleError as exc:
        raise ValueError(str(exc)) from exc
    status, reasons = _compatibility(bundle, runtime, world_id)
    if status != "compatible":
        raise ValueError(f"adventure package is incompatible: {', '.join(reasons)}")
    return bundle.binding(world_id)
