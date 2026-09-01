from pathlib import Path

import asyncio
import logging
import os
import sys

from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent))
from src.runtime_env import load_project_env
from src.runtime_asyncio import install_runtime_exception_handler
from src.runtime_logging import RETENTION_DAYS, configure_runtime_logging

load_project_env(Path(__file__).resolve().with_name(".env"))

from src.common_factory import TRPGSubsystems, create_trpg_subsystems
from src.adventures import sync_adventure_catalog
from src.migrations.config import (
    DEFAULT_NARRATIVE_MAX_TOKENS,
    migrate_generation_defaults as _migrate_generation_defaults,
)
from src.ai_providers import (
    resolve_provider,
)
from src.network_proxy import effective_proxy_url, is_supported_proxy_url, mask_proxy_url
from src.template_catalog import sync_template_catalog
from src.tts import SpeechService
from src.asr import AsrService
from src.imagegen import ImageGenerationService
from src.webui.api import WebAPI
from src.webui.cors import parse_cors_origins
from src.webui.config_update import (
    API_RUNTIME_CONFIG_KEYS,
    MODEL_RUNTIME_CONFIG_KEYS,
    bot_plugin_changes,
    clean_text_value,
    connection_test_timeout,
    normalize_api_format,
    prepare_config_update,
    provider_runtime_changed,
)
from src.webui.composition import (
    RuntimeComposition,
    RuntimeFactories,
    RuntimePaths as CompositionPaths,
)
from src.webui.application import ApplicationDependencies, create_app
from src.webui.runtime_config import (
    ConfigStore,
    RuntimePaths,
)
from src.webui.host_credentials import HostCredentials
from src.webui.bootstrap import (
    BootstrapDependencies,
    BootstrapPaths,
    WebUIBootstrap,
)
from src.webui.access_control import WebAccessControl
from src.webui.routes._common import _get_api, _require_confirmed_request

logger = logging.getLogger("trpg")
logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")


ROOT = Path(__file__).parent
RUNTIME_PATHS = RuntimePaths.from_root(ROOT, os.environ)
CONFIG_STORE = ConfigStore(RUNTIME_PATHS, os.environ, logger=logger)
DATA_DIR = RUNTIME_PATHS.data_dir
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = RUNTIME_PATHS.config_file
SECRETS_FILE = RUNTIME_PATHS.secrets_file
ACCESS_TOKEN_FILE = RUNTIME_PATHS.access_token_file


def _quarantine_invalid_json(path: Path) -> Path | None:
    return CONFIG_STORE.quarantine_invalid_json(path)


def _load_json_object(path: Path, label: str) -> dict:
    return CONFIG_STORE.load_json_object(path, label)


RUNTIME_CONFIG = CONFIG_STORE.load()
STATE = RUNTIME_CONFIG.state
HOST = RUNTIME_CONFIG.host
PORT = RUNTIME_CONFIG.port
TRANSPORT = RUNTIME_CONFIG.transport
WEB_CORS_ENV_VALUE = RUNTIME_CONFIG.cors_env_value
WEB_CORS_CONFIG_VALUE = RUNTIME_CONFIG.cors_config_value
WEB_CORS_ORIGINS = RUNTIME_CONFIG.cors_origins
API_KEY = str(STATE.get("api_key", ""))
_migrated = RUNTIME_CONFIG.generation_defaults_migrated

PROMPTS_DIR = RUNTIME_PATHS.prompts_dir
BUILTIN_RULES_DIR = RUNTIME_PATHS.builtin_rules_dir
BUILTIN_WORLDS_DIR = RUNTIME_PATHS.builtin_worlds_dir
BUILTIN_ADVENTURES_DIR = RUNTIME_PATHS.builtin_adventures_dir
RULES_DIR = RUNTIME_PATHS.rules_dir
WORLDS_DIR = RUNTIME_PATHS.worlds_dir
ADVENTURES_DIR = RUNTIME_PATHS.adventures_dir
STATIC_V2_DIR = RUNTIME_PATHS.static_v2_dir

_rule_sync = sync_template_catalog(BUILTIN_RULES_DIR, RULES_DIR, "rules")
_world_sync = sync_template_catalog(BUILTIN_WORLDS_DIR, WORLDS_DIR, "worlds")
_adventure_sync = sync_adventure_catalog(BUILTIN_ADVENTURES_DIR, ADVENTURES_DIR)
if any(_rule_sync.values()) or any(_world_sync.values()) or any(_adventure_sync.values()):
    logger.info(
        "模板目录已同步到 data: rules=%s worlds=%s adventures=%s",
        _rule_sync, _world_sync, _adventure_sync,
    )


def _atomic_write_json(path: Path, data: dict) -> None:
    CONFIG_STORE.atomic_write_json(path, data)


def _mask_secret(value: str) -> dict:
    return CONFIG_STORE.mask_secret(value)


def _public_config() -> dict:
    return CONFIG_STORE.public_view(RUNTIME_CONFIG)


def save_config():
    CONFIG_STORE.save(STATE)


def _legacy_plugin_bot_token() -> str:
    return _host_credentials().legacy_plugin_bot_token()


def _ensure_bot_token() -> str:
    return _host_credentials().ensure_bot_token()


def _write_access_token_file(password: str) -> None:
    _host_credentials().write_access_token_file(password)


def _delete_access_token_file() -> None:
    _host_credentials().delete_access_token_file()


def _read_access_token_file() -> str:
    return _host_credentials().read_access_token_file()


def _generate_initial_access_password() -> None:
    _host_credentials().generate_initial_access_password()


def _host_credentials() -> HostCredentials:
    return HostCredentials(
        state=STATE,
        data_dir=DATA_DIR,
        access_token_file=ACCESS_TOKEN_FILE,
        environ=os.environ,
        save_config=save_config,
        logger=logger,
    )


if _migrated:
    save_config()
    logger.warning("已迁移 generation 默认值到新版本配置")


def _build_subsystems(
    reuse: TRPGSubsystems | None = None,
    config: dict | None = None,
) -> TRPGSubsystems:
    return _runtime_composition().build_subsystems(reuse=reuse, config=config)


def _config_with_resolved_api_refs(config: dict) -> dict:
    return RuntimeComposition.config_with_resolved_api_refs(config)


def _make_api(subsystems: TRPGSubsystems, plugin_host=None, config: dict | None = None, hub_client=None) -> WebAPI:
    return _runtime_composition().make_api(
        subsystems,
        plugin_host=plugin_host,
        config=config,
        hub_client=hub_client,
    )


def _activate_api_runtime(subsystems: TRPGSubsystems, api: WebAPI) -> None:
    RuntimeComposition.activate_api_runtime(subsystems, api)


def _runtime_composition() -> RuntimeComposition:
    """Build the composition boundary from current compatibility globals."""
    return RuntimeComposition(
        paths=CompositionPaths(
            data_dir=DATA_DIR,
            prompts_dir=PROMPTS_DIR,
            rules_dir=RULES_DIR,
            worlds_dir=WORLDS_DIR,
            adventures_dir=ADVENTURES_DIR,
        ),
        state=STATE,
        save_config=save_config,
        factories=RuntimeFactories(
            create_subsystems=create_trpg_subsystems,
            create_web_api=WebAPI,
            create_speech=SpeechService,
            create_asr=AsrService,
            create_imagegen=ImageGenerationService,
        ),
    )


BOOTSTRAP = WebUIBootstrap(
    BootstrapDependencies(
        paths=BootstrapPaths(root=ROOT, data_dir=DATA_DIR),
        state=STATE,
        environ=os.environ,
        transport=TRANSPORT,
        credentials=_host_credentials,
        save_config=save_config,
        build_subsystems=_build_subsystems,
        make_api=_make_api,
        activate_api_runtime=_activate_api_runtime,
    ),
    logger=logger,
)

ACCESS_CONTROL = WebAccessControl(STATE)
auth_middleware = ACCESS_CONTROL.middleware


async def api_config_get(request: web.Request) -> web.Response:
    return web.json_response(_public_config())


async def api_config_post(request: web.Request) -> web.Response:
    denied = _require_confirmed_request(request)
    if denied is not None:
        return denied
    body = await request.json()
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "配置请求必须是 JSON 对象"}, status=400)
    reload_lock = request.app.get("_config_reload_lock")
    if reload_lock is None:
        reload_lock = asyncio.Lock()
        request.app["_config_reload_lock"] = reload_lock
    async with reload_lock:
        return await _apply_config_update(request, body)


async def _apply_config_update(request: web.Request, body: dict) -> web.Response:
    if "web_cors_origins" in body and WEB_CORS_ENV_VALUE:
        return web.json_response(
            {"ok": False, "error": "TRPG_WEB_CORS_ORIGINS 已由环境变量接管，请修改 .env 后重启后端"},
            status=409,
        )
    prepared = prepare_config_update(STATE, body)
    if prepared.error:
        return web.json_response({"ok": False, "error": prepared.error}, status=400)
    access_password_changed = prepared.access_password_changed
    changed_keys = prepared.changed_keys
    model_runtime_changed = bool(changed_keys & MODEL_RUNTIME_CONFIG_KEYS) or provider_runtime_changed(changed_keys)
    api_runtime_changed = bool(changed_keys & API_RUNTIME_CONFIG_KEYS) or provider_runtime_changed(changed_keys)
    old_subs = request.app.get("subsystems")
    plugin_host = request.app.get("plugin_host")
    old_embedding = (
        old_subs.memory_store.embedding_client
        if old_subs is not None and old_subs.memory_store is not None
        else None
    )
    subsystems = old_subs
    new_api = request.app.get("api")
    try:
        # 先用候选配置完整构建，成功后才提交 STATE 和磁盘配置。
        if model_runtime_changed:
            subsystems = _build_subsystems(reuse=old_subs, config=prepared.state)
            new_api = _make_api(subsystems, plugin_host, config=prepared.state)
        elif api_runtime_changed and old_subs is not None:
            new_api = _make_api(old_subs, plugin_host, config=prepared.state)
    except Exception as exc:
        if old_subs is not None and old_subs.memory_store is not None:
            old_subs.memory_store.embedding_client = old_embedding
        if subsystems is not None and subsystems is not old_subs:
            if subsystems.llm_client:
                await subsystems.llm_client.close()
            new_embedding = getattr(subsystems.memory_store, "embedding_client", None)
            if new_embedding is not None and new_embedding is not old_embedding:
                await new_embedding.close()
        logger.exception("配置更新后的运行时重建失败")
        return web.json_response(
            {"ok": False, "error": f"运行时重载失败，配置未保存：{exc}"},
            status=500,
        )

    previous_state = dict(STATE)
    STATE.clear()
    STATE.update(prepared.state)
    try:
        # save_config 保留既有无参约定；同步写盘失败时立即恢复内存状态。
        save_config()
    except Exception as exc:
        STATE.clear()
        STATE.update(previous_state)
        if old_subs is not None and old_subs.memory_store is not None:
            old_subs.memory_store.embedding_client = old_embedding
        if subsystems is not None and subsystems is not old_subs:
            if subsystems.llm_client:
                await subsystems.llm_client.close()
            candidate_embedding = getattr(subsystems.memory_store, "embedding_client", None)
            if candidate_embedding is not None and candidate_embedding is not old_embedding:
                await candidate_embedding.close()
        logger.exception("保存候选配置失败")
        return web.json_response({"ok": False, "error": f"配置保存失败：{exc}"}, status=500)

    if "web_cors_origins" in changed_keys:
        request.app["cors_origins"] = parse_cors_origins(STATE.get("web_cors_origins", ""))

    if access_password_changed:
        _delete_access_token_file()

    plugin_warning = ""
    plugin_changes = bot_plugin_changes(body, STATE)
    if plugin_changes and plugin_host and "qq-napcat" in plugin_host.plugins:
        try:
            await plugin_host.update_config("qq-napcat", plugin_changes)
        except Exception as exc:
            plugin_warning = f"NapCat 插件配置同步失败：{exc}"
            logger.exception("NapCat 插件配置同步失败")

    if plugin_host and ("ai_providers" in changed_keys or provider_runtime_changed(changed_keys)):
        try:
            await plugin_host.restart_ai_provider_consumers()
        except Exception as exc:
            provider_warning = f"AI 服务商插件重启失败：{exc}"
            plugin_warning = f"{plugin_warning}；{provider_warning}" if plugin_warning else provider_warning
            logger.exception("AI 服务商插件重启失败")

    if model_runtime_changed and subsystems is not None:
        _activate_api_runtime(subsystems, new_api)
        request.app["subsystems"] = subsystems
        request.app["api"] = new_api
    elif api_runtime_changed and new_api is not None:
        _activate_api_runtime(old_subs, new_api)
        request.app["api"] = new_api

    if model_runtime_changed and old_subs is not None and subsystems is not None:
        if old_subs.llm_client and old_subs.llm_client is not subsystems.llm_client:
            try:
                await old_subs.llm_client.close()
            except Exception:
                logger.warning("关闭旧模型客户端失败", exc_info=True)
        new_embedding = getattr(subsystems.memory_store, "embedding_client", None)
        if old_embedding is not None and old_embedding is not new_embedding:
            try:
                await old_embedding.close()
            except Exception:
                logger.warning("关闭旧 Embedding 客户端失败", exc_info=True)
    # 配置更新后，如果 embedding 已启用，立即补齐存量记忆的向量
    emb_now = STATE.get("embedding_enabled", False) and bool(
        STATE.get("embedding_base_url", "") or resolve_provider(STATE, STATE.get("embedding_provider_ref", "")))
    if model_runtime_changed and emb_now and subsystems is not None:
        try:
            count = await subsystems.memory_store.embed_all_pending()
            if count:
                logger.info("[Embedding] 配置更新后补齐 %d 条向量记忆", count)
        except Exception:
            logger.warning("配置更新后 embedding 补齐失败", exc_info=True)
    payload = {"ok": True, "access_password_changed": access_password_changed}
    if prepared.warnings:
        payload["warnings"] = list(prepared.warnings)
    if plugin_warning:
        payload["warning"] = plugin_warning
    return web.json_response(payload)


async def api_bot_token_post(request: web.Request) -> web.Response:
    denied = _require_confirmed_request(request)
    if denied is not None:
        return denied
    body = await request.json()
    action = str(body.get("action") or "reveal").strip().lower()
    if action not in {"reveal", "regenerate"}:
        return web.json_response({"ok": False, "error": "不支持的 Bot Token 操作"}, status=400)

    regenerated = action == "regenerate"
    if regenerated:
        if os.getenv("TRPG_BOT_TOKEN"):
            return web.json_response({
                "ok": False,
                "error": "Bot API Token 由环境变量 TRPG_BOT_TOKEN 管理，请修改环境变量后重启",
            }, status=409)
        import secrets as _secrets
        token = _secrets.token_urlsafe(32)
        STATE["bot_token"] = token
        save_config()
    else:
        token = _ensure_bot_token()

    return web.json_response({
        "ok": True,
        "token": token,
        "masked": _mask_secret(token)["masked"],
        "regenerated": regenerated,
    })


def _is_safe_external_url(url: str) -> bool:
    """防 SSRF：要求 http(s)，禁云元数据/私网/回环；保留 127.0.0.1 与 localhost 供本地 ollama。"""
    if not url or not url.startswith(("http://", "https://")):
        return False
    from urllib.parse import urlparse
    import ipaddress
    host = (urlparse(url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_unspecified or ip.is_reserved:
        return False
    return True


async def api_test_connection(request: web.Request) -> web.Response:
    body = await request.json()
    # provider_id 指定服务商时，凭据默认取自服务商库（明文 key 只存在于服务端）；
    # body 里的显式明文输入仍然优先，供未保存前直接测试。
    provider = resolve_provider(STATE, str(body.get("provider_id") or ""))
    if provider:
        base_url = clean_text_value(body.get("base_url")) or provider["base_url"]
        api_key = clean_text_value(body.get("api_key")) or provider["api_key"]
        api_format = normalize_api_format(body.get("api_format") or provider["api_format"])
    else:
        base_url = clean_text_value(body.get("base_url")) or STATE.get("base_url", "")
        api_key = clean_text_value(body.get("api_key")) or STATE.get("api_key", "")
        api_format = normalize_api_format(body.get("api_format") or STATE.get("api_format"))
    if not _is_safe_external_url(base_url):
        return web.json_response({"ok": False, "error": "base_url 非法或不允许"}, status=400)
    proxy_url = _proxy_from_test_body(body)
    if proxy_url and not is_supported_proxy_url(proxy_url):
        return web.json_response({"ok": False, "error": "代理地址仅支持 http:// 或 https://"}, status=400)
    result = await _get_api(request).test_connection(
        base_url=base_url,
        api_key=api_key,
        model=clean_text_value(body.get("model")) or STATE.get("model", ""),
        proxy_url=proxy_url,
        api_format=api_format,
    )
    return web.json_response(result)


async def api_config_provider_models_post(request: web.Request) -> web.Response:
    body = await request.json()
    provider = resolve_provider(STATE, str(body.get("provider_id") or ""))
    if provider:
        base_url = clean_text_value(body.get("base_url")) or provider["base_url"]
        api_key = clean_text_value(body.get("api_key")) or provider["api_key"]
        api_format = normalize_api_format(body.get("api_format") or provider["api_format"])
    else:
        base_url = clean_text_value(body.get("base_url"))
        api_key = clean_text_value(body.get("api_key"))
        api_format = normalize_api_format(body.get("api_format"))
    if not _is_safe_external_url(base_url):
        return web.json_response({"ok": False, "error": "base_url 非法或不允许", "models": []}, status=400)
    proxy_url = _proxy_from_test_body(body)
    if proxy_url and not is_supported_proxy_url(proxy_url):
        return web.json_response({"ok": False, "error": "代理地址仅支持 http:// 或 https://", "models": []}, status=400)
    result = await _get_api(request).list_models(
        base_url=base_url,
        api_key=api_key,
        proxy_url=proxy_url,
        api_format=api_format,
    )
    return web.json_response(result)


def _proxy_from_test_body(body: dict) -> str:
    if "proxy_enabled" not in body and "proxy_url" not in body:
        return effective_proxy_url(bool(STATE.get("proxy_enabled")), STATE.get("proxy_url", ""))
    enabled = bool(body.get("proxy_enabled"))
    proxy_url = str(body.get("proxy_url") or "").strip()
    if not proxy_url:
        proxy_url = STATE.get("proxy_url", "")
    return effective_proxy_url(enabled, proxy_url)


async def api_test_embedding(request: web.Request) -> web.Response:
    body = await request.json()
    provider = resolve_provider(STATE, str(body.get("provider_id") or ""))
    if provider:
        base_url = clean_text_value(body.get("base_url")) or provider["base_url"]
        api_key = clean_text_value(body.get("api_key")) or provider["api_key"]
    else:
        base_url = clean_text_value(body.get("base_url"))
        api_key = clean_text_value(body.get("api_key")) or STATE.get("embedding_api_key") or STATE.get("api_key", "")
    model = clean_text_value(body.get("model")) or "nomic-embed-text"
    if not _is_safe_external_url(base_url):
        return web.json_response({"ok": False, "error": "Base URL 非法或不允许"})
    from src.memory.embedding import EmbeddingClient
    import time
    proxy_url = _proxy_from_test_body(body)
    if proxy_url and not is_supported_proxy_url(proxy_url):
        return web.json_response({"ok": False, "error": "代理地址仅支持 http:// 或 https://"}, status=400)
    client = EmbeddingClient(
        base_url, api_key, model,
        proxy_url=proxy_url,
        timeout_seconds=connection_test_timeout(STATE),
    )
    start = time.time()
    try:
        emb = await client.embed("测试")
        elapsed = round(time.time() - start, 2)
        if emb and len(emb) > 0:
            return web.json_response({"ok": True, "dimension": len(emb), "elapsed": elapsed})
        return web.json_response({"ok": False, "error": "Embedding API 返回异常", "elapsed": elapsed})
    finally:
        await client.close()


async def api_test_proxy(request: web.Request) -> web.Response:
    body = await request.json()
    enabled = bool(body.get("proxy_enabled", STATE.get("proxy_enabled", False)))
    proxy_url = str(body.get("proxy_url", STATE.get("proxy_url", "")) or "").strip()
    proxy = effective_proxy_url(enabled, proxy_url)
    if enabled and not proxy:
        return web.json_response({"ok": False, "error": "已启用代理，但代理地址为空"}, status=400)
    if proxy and not is_supported_proxy_url(proxy):
        return web.json_response({"ok": False, "error": "代理地址仅支持 http:// 或 https://"}, status=400)
    url = str(STATE.get("base_url") or "").strip().rstrip("/")
    if not _is_safe_external_url(url):
        return web.json_response({"ok": False, "error": "请先配置有效的模型服务地址"}, status=400)
    import aiohttp
    import time
    start = time.time()
    try:
        timeout = aiohttp.ClientTimeout(total=connection_test_timeout(STATE))
        async with aiohttp.ClientSession() as session:
            request_kwargs = {"proxy": proxy} if proxy else {}
            async with session.get(url, timeout=timeout, **request_kwargs) as resp:
                text = await resp.text()
                elapsed = round(time.time() - start, 2)
                # 401/403/404 也说明网络链路已连通；这里只测试连接，不校验 API Key。
                if resp.status < 500:
                    return web.json_response({
                        "ok": True,
                        "status": resp.status,
                        "elapsed": elapsed,
                        "proxy": mask_proxy_url(proxy),
                    })
                return web.json_response({
                    "ok": False,
                    "error": f"HTTP {resp.status}: {text[:160]}",
                    "elapsed": elapsed,
                    "proxy": mask_proxy_url(proxy),
                })
    except Exception as exc:
        logger.exception("test-connection 异常")
        return web.json_response({
            "ok": False,
            "error": "连接异常，请查看服务器日志",
            "elapsed": round(time.time() - start, 2),
            "proxy": mask_proxy_url(proxy),
        })


def _application_dependencies() -> ApplicationDependencies:
    return ApplicationDependencies(
        data_dir=DATA_DIR,
        static_v2_dir=STATIC_V2_DIR,
        cors_origins=WEB_CORS_ORIGINS,
        transport=TRANSPORT,
        config_state=STATE,
        save_config=save_config,
        on_startup=BOOTSTRAP.on_startup,
        on_cleanup=BOOTSTRAP.on_cleanup,
        auth_middleware=auth_middleware,
        config_get=api_config_get,
        config_post=api_config_post,
        bot_token_post=api_bot_token_post,
        provider_models_post=api_config_provider_models_post,
        test_connection=api_test_connection,
        test_embedding=api_test_embedding,
        test_proxy=api_test_proxy,
    )


app = create_app(_application_dependencies())

if __name__ == "__main__":
    runtime_log_path = configure_runtime_logging(DATA_DIR)
    logger.info("运行日志写入 %s（保留 %s 天）", runtime_log_path, RETENTION_DAYS)
    if TRANSPORT.degraded_error:
        logger.critical("%s", TRANSPORT.degraded_error)
    print(f"DiceFrame WebUI: {TRANSPORT.endpoint.url('127.0.0.1')}  (host={HOST})")
    if not API_KEY:
        print("请在 WebUI 设置页填写 API Key")
    runtime_loop = asyncio.new_event_loop()
    install_runtime_exception_handler(runtime_loop)
    web.run_app(
        app,
        host=HOST,
        port=PORT,
        ssl_context=TRANSPORT.ssl_context,
        loop=runtime_loop,
    )
    if app["runtime_control"]["restart_requested"]:
        logger.info("DiceFrame 清理完成，正在重新启动")
        os.execv(sys.executable, [sys.executable, *sys.argv])
