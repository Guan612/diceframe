# -*- coding: utf-8 -*-
"""连接安全（Web Transport）服务：状态查询、切换事务与自签证书管理。

修改、签发与重新生成操作都走这里，保证：
- prepare 只验证 / 生成候选，不切换当前服务；
- activate 只接受一次性 preparation token，避免刷新或重试重复执行；
- 失败保留当前可用模式，不写入不可启动的配置。
"""

from __future__ import annotations

import os
import secrets as secrets_module
import ssl
import time
from pathlib import Path
from typing import Any, Callable

from src.web_transport import (
    TLS_MODE_LETS_ENCRYPT,
    TLS_MODE_OFF,
    TLS_MODE_SELF_SIGNED,
    CertificateError,
    CertificateStore,
    SelfSignedCertificateProvider,
    ServerTransport,
    WebTransportConfig,
    parse_web_transport,
    validate_activation,
)

_PREPARATION_TTL_SECONDS = 600


class SecurityTransportService:
    def __init__(
        self,
        state: dict[str, Any],
        save_config: Callable[[], None],
        data_dir: Path,
        transport: ServerTransport,
    ) -> None:
        self._state = state
        self._save_config = save_config
        self._transport = transport
        self._store = CertificateStore(data_dir)
        self._provider = SelfSignedCertificateProvider(self._store)
        self._preparations: dict[str, dict[str, Any]] = {}

    # ---- 状态 ----

    def current_config(self) -> WebTransportConfig:
        return parse_web_transport(self._state.get("web_transport") or {})

    def get_status(self) -> dict[str, Any]:
        config = self.current_config()
        status: dict[str, Any] = {
            "ok": True,
            "tls_mode": self._transport.tls_mode,
            "scheme": self._transport.scheme,
            "tls_mode_source": config.tls_mode_source,
            "restart_required": False,
        }
        if self._transport.degraded_error:
            status["degraded_error"] = self._transport.degraded_error
        metadata = self._provider.metadata()
        if metadata is not None:
            status["certificate"] = metadata.public_view()
        return status

    # ---- 切换事务 ----

    def prepare(self, mode: str) -> dict[str, Any]:
        mode = str(mode or "").strip().lower()
        if mode == TLS_MODE_LETS_ENCRYPT:
            return {"ok": False, "error": "Let's Encrypt 证书尚未开放（技术验证中），请先使用本地 HTTPS"}
        if mode not in (TLS_MODE_OFF, TLS_MODE_SELF_SIGNED):
            return {"ok": False, "error": f"不支持的连接模式：{mode or '(空)'}"}
        if mode == TLS_MODE_OFF:
            # 关闭不生成候选证书，直接走 disable 事务。
            return {"ok": False, "error": "关闭连接安全请使用 disable 操作"}
        env_mode = str(os.environ.get("TRPG_TLS_MODE") or "").strip().lower()
        if env_mode and env_mode != mode:
            return {"ok": False, "error": "TRPG_TLS_MODE 已由环境变量接管，请修改 .env 后重启后端"}

        try:
            prepared = self._provider.prepare()
            # 候选必须真的能建出 SSLContext，才允许进入 activate。
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(str(prepared.cert_path), str(prepared.key_path))
        except (CertificateError, ssl.SSLError, OSError, ValueError) as exc:
            return {"ok": False, "error": f"本地证书验证失败：{exc}"}

        token = secrets_module.token_urlsafe(24)
        self._preparations[token] = {
            "mode": TLS_MODE_SELF_SIGNED,
            "fingerprint": prepared.metadata.fingerprint_sha256,
            "expires_at": time.time() + _PREPARATION_TTL_SECONDS,
        }
        self._expire_preparations()
        return {
            "ok": True,
            "mode": TLS_MODE_SELF_SIGNED,
            "token": token,
            "certificate": prepared.metadata.public_view(),
        }

    def activate(self, token: str) -> dict[str, Any]:
        token = str(token or "").strip()
        preparation = self._preparations.get(token)
        if not preparation:
            return {"ok": False, "error": "准备令牌无效或已使用，请重新执行检查"}
        if time.time() > preparation["expires_at"]:
            self._preparations.pop(token, None)
            return {"ok": False, "error": "准备令牌已过期，请重新执行检查"}

        mode = preparation["mode"]
        candidate = WebTransportConfig(tls_mode=mode)
        error = validate_activation(candidate)
        if error:
            return {"ok": False, "error": error}
        # 候选证书在 prepare 与 activate 之间可能被 regenerate 替换；
        # 再次验证指纹，不一致则要求重新 prepare。
        try:
            prepared = self._provider.prepare()
        except CertificateError as exc:
            return {"ok": False, "error": f"本地证书验证失败：{exc}"}
        if prepared.metadata.fingerprint_sha256 != preparation["fingerprint"]:
            return {"ok": False, "error": "证书在检查后发生了变化，请重新执行检查"}

        # 一次性令牌：无论后续成败都销毁，防止重试重复执行。
        self._preparations.pop(token, None)
        self._state["web_transport"] = {"tls_mode": mode}
        self._save_config()
        return {
            "ok": True,
            "tls_mode": mode,
            "target_scheme": "https" if mode != TLS_MODE_OFF else "http",
            "restart_required": True,
        }

    def disable(self) -> dict[str, Any]:
        # 关闭 HTTPS 不删除证书文件与后续阶段保留的账户数据。
        self._state["web_transport"] = {"tls_mode": TLS_MODE_OFF}
        self._save_config()
        return {"ok": True, "tls_mode": TLS_MODE_OFF, "target_scheme": "http", "restart_required": True}

    # ---- 自签证书管理 ----

    def regenerate_self_signed(self) -> dict[str, Any]:
        old = self._provider.metadata()
        try:
            prepared = self._provider.regenerate()
        except (CertificateError, OSError, ValueError) as exc:
            return {"ok": False, "error": f"重新生成本地证书失败：{exc}"}
        current_mode = self.current_config().tls_mode
        return {
            "ok": True,
            "restart_required": current_mode == TLS_MODE_SELF_SIGNED,
            "certificate": prepared.metadata.public_view(),
            "previous_fingerprint": old.fingerprint_sha256 if old else "",
        }

    # ---- 内部 ----

    def _expire_preparations(self) -> None:
        now = time.time()
        for token in [t for t, item in self._preparations.items() if item["expires_at"] < now]:
            self._preparations.pop(token, None)
