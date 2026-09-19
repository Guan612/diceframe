"""Content Module（模组）统一只读 facade（MOD-04，母方案 §50/§52/§108）。

普通用户的"模组 / 内容库（Compendium）"是产品层抽象；技术实现完全复用
既有 PluginHost 组件（PluginRuntime / ContributionRegistry /
PluginContentCatalog / AdventureSourceRegistry），**不新建数据库、不新建
lifecycle**。本模块只做三件事：

- ``list_modules``：已安装的 content-pack（含传统包与 adventure-module 模组）
  的模块卡片数据（母方案 §52：名称 / 版本 / 规则目标 / 冒险数 / 内容数 /
  状态 / 来源）；
- ``module_detail``：单个模组的概览 + 内容分组 + 冒险清单（§53 Tabs 的数据源）;
- ``module_content``：内容库只读详情（委托 ``PluginContentCatalog.get_content_resource``）。

边界：

- 只读：不安装、不启停、不改文件（生命周期在 LIFE 组，走既有 PluginHost API）。
- 不把插件类型混淆：provider / tool / bot-extension 等不进入模块库（§51）。
- 性能（母方案 §165）：列表只返回元数据计数，不读取全部 JSON body。
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from src.plugin_host.support import (
    content_delivery_mode,
    content_profile,
)
from src.webui.services.module_validation import (
    MODULE_PLUGIN_TYPE,
    ModulePackageValidation,
    parse_requires,
    validate_module_package,
)

_MODULE_CONTENT_KINDS = (
    "npc", "item", "spell", "class", "character_template", "world_template",
)


@dataclass(frozen=True)
class ModuleDependencies:
    """Explicit read-side dependencies for the module catalogue facade."""

    plugin_host: Any | None
    adventure_registry: Any | None
    ruleset_registry: Any | None = None
    list_instances: Callable[[], list[Any]] | None = None
    # FIX-01 §3.7：保护目标是"所有持久化存档"，不能只看内存 active GameInstance。
    # ``list_save_metadata`` 扫描存档目录，覆盖 paused / ended / 加载失败但元数据
    # 仍可读的对局；``refresh_adventure_sources`` 对应 §3.6——任何 destructive
    # module action 前先刷新来源注册表，不依赖"碰巧同步过"。
    list_save_metadata: Callable[[], list[dict[str, Any]]] | None = None
    refresh_adventure_sources: Callable[[], None] | None = None
    # 组合根声明的默认 runtime：模块声明了 ruleset_catalogs 但没写 requires 时，
    # 用它判断 catalog 契约归属（与 Adventure 绑定同一默认，不猜字段）。
    default_runtime_requirement: Callable[[], dict[str, Any]] | None = None


def _installed_content_packs(plugin_host: Any) -> list[Any]:
    runtimes = getattr(plugin_host, "plugins", {}) or {}
    return sorted(
        (
            runtime
            for runtime in runtimes.values()
            if str(runtime.manifest.get("plugin_type") or "") == "content-pack"
        ),
        key=lambda runtime: str(runtime.manifest.get("id") or ""),
    )


def _adventure_count(adventure_registry: Any, plugin_id: str) -> int:
    if adventure_registry is None:
        return 0
    source = adventure_registry.source_for("plugin", plugin_id)
    if source is None:
        return 0
    try:
        return len(source.loader.list(""))
    except Exception:  # noqa: BLE001 - 诊断列表绝不因单个坏包失败
        return 0


def _contribution_counts(contributions: Any, plugin_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in contributions.list():
        if item.plugin_id != plugin_id:
            continue
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return counts


def list_modules(deps: ModuleDependencies) -> dict[str, Any]:
    """模块库列表（母方案 §51：已安装；在线/本地导入由 marketplace 提供）。"""

    modules: list[dict[str, Any]] = []
    for runtime in _installed_content_packs(deps.plugin_host):
        plugin_id = str(runtime.manifest.get("id") or "")
        profile = content_profile(runtime.manifest)
        counts = _contribution_counts(deps.plugin_host.contributions, plugin_id)
        modules.append({
            "id": plugin_id,
            "name": str(runtime.manifest.get("name") or plugin_id),
            "version": str(runtime.manifest.get("version") or ""),
            "plugin_type": str(runtime.manifest.get("plugin_type") or ""),
            "content_profile": profile,
            "content_delivery_mode": content_delivery_mode(runtime.manifest),
            "is_module": profile == "adventure-module",
            "status": str(runtime.status or ""),
            "adventure_count": _adventure_count(deps.adventure_registry, plugin_id),
            "content_counts": counts,
        })
    return {"ok": True, "modules": modules}


def _refresh_adventure_sources(deps: ModuleDependencies) -> None:
    """Best-effort refresh of the plugin adventure-source registry (FIX-01 §3.6).

    读模型与 guard 都不能依赖"碰巧同步过 registry"（server restart / 刚启用 /
    刚安装都会让来源集合过期）。刷新失败不影响只读结果。
    """

    refresh = getattr(deps, "refresh_adventure_sources", None)
    if not callable(refresh):
        return
    try:
        refresh()
    except Exception:  # noqa: BLE001 - 刷新失败不拖垮只读目录
        pass


def module_detail(deps: ModuleDependencies, module_id: str) -> dict[str, Any]:
    """单个模组详情：概览 + 内容分组计数 + 冒险清单（只读）。"""

    runtime = getattr(deps.plugin_host, "plugins", {}).get(str(module_id or ""))
    if runtime is None or str(runtime.manifest.get("plugin_type") or "") != MODULE_PLUGIN_TYPE:
        return {"ok": False, "error_code": "MODULE_NOT_FOUND"}
    _refresh_adventure_sources(deps)
    plugin_id = str(runtime.manifest.get("id") or "")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in deps.plugin_host.contributions.list():
        if item.plugin_id != plugin_id:
            continue
        grouped.setdefault(item.kind, []).append({
            "key": item.key,
            "title": item.title,
            "description": item.description,
        })
    adventures: list[dict[str, Any]] = []
    source = (
        deps.adventure_registry.source_for("plugin", plugin_id)
        if deps.adventure_registry is not None
        else None
    )
    if source is not None:
        try:
            for bundle in source.loader.list(""):
                adventures.append({
                    "adventure_id": bundle.manifest.adventure_id,
                    "version": bundle.manifest.version,
                    "format": bundle.manifest.format,
                    "directory_id": bundle.root.name,
                })
        except Exception:  # noqa: BLE001 - 坏包不拖垮详情页
            adventures = []
    return {
        "ok": True,
        "module": {
            "id": plugin_id,
            "name": str(runtime.manifest.get("name") or plugin_id),
            "version": str(runtime.manifest.get("version") or ""),
            "content_profile": content_profile(runtime.manifest),
            "content_delivery_mode": content_delivery_mode(runtime.manifest),
            "status": str(runtime.status or ""),
            "content_counts": _contribution_counts(deps.plugin_host.contributions, plugin_id),
            "content": grouped,
            "adventures": adventures,
        },
    }


def module_adventures(deps: ModuleDependencies, module_id: str) -> dict[str, Any]:
    """Dedicated adventure-list read model for one module (API-02)."""

    detail = module_detail(deps, module_id)
    if not detail.get("ok"):
        return detail
    module = detail["module"]
    return {
        "ok": True,
        "module_id": module["id"],
        "adventures": module["adventures"],
    }


def module_content(
    deps: ModuleDependencies, module_id: str, kind: str, key: str, *, language: str = "",
) -> dict[str, Any]:
    """内容库只读详情；委托 PluginContentCatalog（不新建存储）。"""

    catalog = getattr(deps.plugin_host, "content", None)
    if catalog is None:
        return {"ok": False, "error_code": "CONTENT_UNAVAILABLE"}
    resource = catalog.get_content_resource(kind, key, plugin_id=str(module_id or ""), language=language)
    if resource is None:
        return {"ok": False, "error_code": "CONTENT_NOT_FOUND"}
    return {"ok": True, "content": resource}


# ---- LIFE-00：安装前兼容性预览（母方案 §33/§123）--------------------------
#
# FIX-01 §3.3：预览与安装共用同一套校验（src.webui.services.module_validation），
# 不再各自维护一份规则。这里只保留 facade 形状。


def preview_module_install(
    deps: ModuleDependencies,
    manifest: dict[str, Any],
    *,
    directory: Any | None = None,
    require_content_pack: bool = True,
) -> dict[str, Any]:
    """安装前兼容性预览：blockers（阻断）与 warnings（警告）分离（§57）。

    ``directory`` 给出已解压的包目录时同时做深度校验（Adventure 包真装载 /
    ruleset catalog 真装载）；模块安装面默认要求 content-pack。
    """

    validation = validate_module_package(
        manifest,
        deps=deps,
        directory=directory,
        require_content_pack=require_content_pack,
    )
    return validation.preview()


def validate_module_directory(
    deps: ModuleDependencies,
    directory: Any,
    manifest: dict[str, Any],
    *,
    require_content_pack: bool = True,
) -> ModulePackageValidation:
    """Validate one extracted package for the module install surface (raises)."""

    from src.webui.services.module_validation import validate_module_install

    return validate_module_install(
        directory,
        manifest,
        deps=deps,
        require_content_pack=require_content_pack,
    )


def module_compatibility(deps: ModuleDependencies, module_id: str) -> dict[str, Any]:
    """Preview the installed module's declared runtime compatibility."""

    runtime = getattr(deps.plugin_host, "plugins", {}).get(str(module_id or ""))
    if runtime is None or str(runtime.manifest.get("plugin_type") or "") != MODULE_PLUGIN_TYPE:
        return {"ok": False, "error_code": "MODULE_NOT_FOUND"}
    result = preview_module_install(deps, runtime.manifest)
    return {**result, "module_id": str(runtime.manifest.get("id") or "")}


# ---- LIFE-01：绑定存档保护（母方案 §35/§36/§37/§124）------------------------

# 受保护操作 → 绑定存档存在时是否阻断。更新/禁用/卸载/覆盖安装一律默认 block；
# 母方案 §35：更新改变 bound adventure digest → BLOCK。
# FIX-01 §3.5：``overwrite``（本地覆盖安装 / 市场覆盖安装 / 后台自动更新）也是
# 改 package bytes 的破坏性操作，必须与 update 同等受保护。
PROTECTED_MODULE_ACTIONS = ("uninstall", "disable", "update", "overwrite", "stop")


def module_adventure_ids(deps: ModuleDependencies, module_id: str) -> set[str]:
    """The adventure ids a module package declares.

    FIX-01 §3.6：**不依赖"碰巧同步过 registry"**。来源优先级：

    1. runtime 自己声明的 declared-only 包目录（安装后即存在，server restart 后
       ``discover()`` 重建，且与 enabled/disabled 状态无关）；
    2. 退回到来源注册表（plugin 来源在禁用时会被同步移除，因此只作兜底）。
    """

    runtime = getattr(deps.plugin_host, "plugins", {}).get(str(module_id or ""))
    if runtime is None:
        return set()
    plugin_id = str(runtime.manifest.get("id") or "")
    root = getattr(runtime, "adventure_packages_root", None)
    directories = tuple(getattr(runtime, "adventure_package_directories", ()) or ())
    if root is not None and directories:
        from src.adventures import AdventureBundleLoader

        try:
            loader = AdventureBundleLoader(root, allowed_directory_ids=directories)
            return {
                bundle.manifest.adventure_id for bundle in loader.list("")
            }
        except Exception:  # noqa: BLE001 - 坏包不拖垮保护检查
            return set()
    registry = deps.adventure_registry
    if registry is None:
        return set()
    source = registry.source_for("plugin", plugin_id)
    if source is None:
        return set()
    try:
        return {bundle.manifest.adventure_id for bundle in source.loader.list("")}
    except Exception:  # noqa: BLE001 - 坏包不拖垮保护检查
        return set()


def _active_bindings(deps: ModuleDependencies) -> list[dict[str, Any]]:
    """Bindings from in-memory instances (active / paused / ended)."""

    rows: list[dict[str, Any]] = []
    for instance in (deps.list_instances or (lambda: []))():
        binding = getattr(instance, "adventure_binding", {}) or {}
        rows.append({
            "game_key": "|".join(str(part) for part in instance.game_key),
            "adventure_id": str(binding.get("adventure_id") or ""),
            "run_id": str(instance.run_id or ""),
            "content_digest": str(binding.get("content_digest") or ""),
            "state": str(getattr(getattr(instance, "state", ""), "value", "") or ""),
            "metadata_readable": True,
        })
    return rows


def _persisted_bindings(deps: ModuleDependencies) -> list[dict[str, Any]]:
    """Bindings from persisted saves (FIX-01 §3.7).

    扫描存档目录而不是内存 registry，因此重启后、ENDED 对局、以及加载/恢复失败
    但元数据仍可读的存档同样受保护。
    """

    scanner = getattr(deps, "list_save_metadata", None)
    if not callable(scanner):
        return []
    rows: list[dict[str, Any]] = []
    try:
        entries = scanner() or []
    except Exception:  # noqa: BLE001 - 扫描失败不拖垮只读目录
        return []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rows.append({
            "game_key": str(entry.get("game_key") or ""),
            "adventure_id": str(entry.get("adventure_id") or ""),
            "run_id": str(entry.get("run_id") or ""),
            "content_digest": str(entry.get("content_digest") or ""),
            "state": str(entry.get("state") or ""),
            "metadata_readable": bool(entry.get("metadata_readable", False)),
        })
    return rows


def module_bound_rows(
    deps: ModuleDependencies,
    module_id: str,
) -> list[dict[str, Any]]:
    """Every save (memory + persisted) bound to one module, deduped by game key."""

    adventure_ids = module_adventure_ids(deps, module_id)
    if not adventure_ids:
        return []
    merged: dict[str, dict[str, Any]] = {}
    for row in (*_active_bindings(deps), *_persisted_bindings(deps)):
        if row["adventure_id"] not in adventure_ids:
            continue
        key = row["game_key"]
        current = merged.get(key)
        # 内存实例更权威（有 state / 最新 run_id）；缺失时用存档元数据补齐。
        if current is None or not current.get("state"):
            merged[key] = {**current, **row} if current else row
    return sorted(merged.values(), key=lambda item: item["game_key"])


def module_bound_games(
    deps: ModuleDependencies,
    module_id: str,
) -> list[dict[str, Any]]:
    """List the games bound to one module's adventures（§35 UI 数据源）。"""

    return [
        {
            "game_key": row["game_key"],
            "adventure_id": row["adventure_id"],
            "run_id": row["run_id"],
        }
        for row in module_bound_rows(deps, module_id)
    ]


def assert_module_action_allowed(deps: ModuleDependencies, module_id: str, action: str) -> None:
    """Guard for uninstall/disable/update/overwrite/stop（母方案 §124：默认 block）。

    绑定存档存在时抛 :class:`ModuleInUse`；调用方（插件生命周期 API / 插件宿主）
    把它转成结构化错误，UI 展示"哪些存档正在使用"。

    FIX-01 §3.6：guard 前先刷新 module/adventure 来源注册表，避免
    "server restart → registry 为空 → destructive action fail-open"。
    """

    if action not in PROTECTED_MODULE_ACTIONS:
        return
    refresh = getattr(deps, "refresh_adventure_sources", None)
    if callable(refresh):
        try:
            refresh()
        except Exception:  # noqa: BLE001 - 刷新失败不得让 guard 变成 fail-open
            pass
    bound = module_bound_games(deps, module_id)
    if bound:
        raise ModuleInUse(module_id, action, bound)


class ModuleInUse(ValueError):
    """The module is bound by games; the protected action must not proceed."""

    def __init__(self, module_id: str, action: str, games: list[dict[str, Any]]) -> None:
        self.module_id = str(module_id)
        self.action = str(action)
        self.games = list(games)
        super().__init__(
            f"module {self.module_id!r} is used by {len(self.games)} game(s); "
            f"{self.action} blocked"
        )




# ---- LIFE-02：Module Usage Index（母方案 §125/§169）-------------------------


def module_usages(deps: ModuleDependencies, module_id: str) -> dict[str, Any]:
    """模块使用索引：哪个模块 / 哪个冒险被哪些存档绑定（只读聚合）。

    FIX-01 §3.7：与 bound-save guard 同源——内存实例 + 持久化存档元数据。
    """

    runtime = getattr(deps.plugin_host, "plugins", {}).get(str(module_id or ""))
    if runtime is None:
        return {"ok": False, "error_code": "MODULE_NOT_FOUND"}
    plugin_id = str(runtime.manifest.get("id") or "")
    adventure_ids = module_adventure_ids(deps, module_id)
    by_adventure: dict[str, list[dict[str, Any]]] = {
        adventure_id: [] for adventure_id in sorted(adventure_ids)
    }
    for row in module_bound_rows(deps, module_id):
        adventure_id = row["adventure_id"]
        if adventure_id in by_adventure:
            by_adventure[adventure_id].append({
                "game_key": row["game_key"],
                "run_id": row["run_id"],
                "content_digest": row["content_digest"],
                "state": row["state"],
                "metadata_readable": row["metadata_readable"],
            })
    usages = [
        {"adventure_id": adventure_id, "games": games}
        for adventure_id, games in by_adventure.items()
    ]
    total = sum(len(item["games"]) for item in usages)
    return {"ok": True, "module_id": plugin_id, "usages": usages, "total_games": total}


__all__ = [
    "ModuleDependencies",
    "ModuleInUse",
    "PROTECTED_MODULE_ACTIONS",
    "assert_module_action_allowed",
    "list_modules",
    "module_adventures",
    "module_adventure_ids",
    "module_bound_games",
    "module_bound_rows",
    "module_content",
    "module_compatibility",
    "module_detail",
    "module_usages",
    "parse_requires",
    "preview_module_install",
    "validate_module_directory",
]
