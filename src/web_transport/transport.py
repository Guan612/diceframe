# -*- coding: utf-8 -*-
"""Web Server 的唯一 TLS 接入点。

web_server 只应看到 ServerTransport：scheme、tls_mode、ssl_context 与
endpoint。构建失败不抛异常——降级为 HTTP 并携带 degraded_error，由
"安全"页醒目展示，绝不静默也不锁死服务。
"""

from __future__ import annotations

import logging
import ssl
from dataclasses import dataclass, field
from pathlib import Path

from src.web_transport.certificates.base import CertificateError
from src.web_transport.certificates.self_signed import SelfSignedCertificateProvider
from src.web_transport.certificates.storage import CertificateStore
from src.web_transport.config import (
    TLS_MODE_OFF,
    TLS_MODE_SELF_SIGNED,
    WebTransportConfig,
    validate_activation,
)
from src.web_transport.endpoint import ServerEndpoint

logger = logging.getLogger("trpg.web_transport")


@dataclass
class ServerTransport:
    scheme: str
    tls_mode: str
    ssl_context: ssl.SSLContext | None
    endpoint: ServerEndpoint
    # 生效模式与期望模式不一致时的说明（降级不静默）。
    degraded_error: str = ""
    provider: object | None = None
    store: CertificateStore | None = None
    config: WebTransportConfig | None = None
    diagnostics: dict = field(default_factory=dict)


def _build_ssl_context(cert_path: Path, key_path: Path) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_path), str(key_path))
    return context


def build_server_transport(config: WebTransportConfig, data_dir: Path, port: int) -> ServerTransport:
    """根据配置构建 ServerTransport。off 模式 ssl_context=None。"""
    store = CertificateStore(data_dir)

    def http_transport(error: str = "") -> ServerTransport:
        return ServerTransport(
            scheme="http",
            tls_mode=TLS_MODE_OFF,
            ssl_context=None,
            endpoint=ServerEndpoint(scheme="http", port=port),
            degraded_error=error,
            provider=None,
            store=store,
            config=config,
        )

    if config.tls_mode == TLS_MODE_OFF:
        return http_transport()

    activation_error = validate_activation(config)
    if activation_error:
        # lets_encrypt / 自定义证书：schema 已解析但本版本不可启用。
        logger.error("Web Transport 模式 %s 不可用：%s", config.tls_mode, activation_error)
        return http_transport(activation_error)

    if config.tls_mode != TLS_MODE_SELF_SIGNED:
        return http_transport(f"不支持的连接模式：{config.tls_mode}")

    provider = SelfSignedCertificateProvider(store)
    try:
        prepared = provider.prepare()
        ssl_context = _build_ssl_context(prepared.cert_path, prepared.key_path)
    except (CertificateError, ssl.SSLError, OSError, ValueError) as exc:
        # 保留当前可用模式（HTTP），在"安全"页显式报错，不静默也不锁死。
        error = f"本地 HTTPS 启用失败，已暂时回退 HTTP：{exc}"
        logger.critical("%s", error, exc_info=True)
        return http_transport(error)

    return ServerTransport(
        scheme="https",
        tls_mode=TLS_MODE_SELF_SIGNED,
        ssl_context=ssl_context,
        endpoint=ServerEndpoint(scheme="https", port=port),
        provider=provider,
        store=store,
        config=config,
        diagnostics={"certificate": prepared.metadata.public_view()},
    )
