# -*- coding: utf-8 -*-
"""Web Transport 配置解析。

HTTP / HTTPS 只是不同的 Web Transport 配置，不属于业务层概念。
本模块负责 schema、旧配置默认值、环境变量覆盖和脱敏序列化，
不得被游戏、规则、AI 等业务模块引用。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Mapping

logger = logging.getLogger("trpg.web_transport")

# 公开支持的 TLS 模式。lets_encrypt 在本版本仅完成 schema 解析，
# 签发能力（阶段 C）落地前 UI 与 API 都必须显式标注"暂未开放"。
TLS_MODE_OFF = "off"
TLS_MODE_SELF_SIGNED = "self_signed"
TLS_MODE_LETS_ENCRYPT = "lets_encrypt"
PUBLIC_TLS_MODES = (TLS_MODE_OFF, TLS_MODE_SELF_SIGNED, TLS_MODE_LETS_ENCRYPT)

# 当前版本实际可启用的模式。
AVAILABLE_TLS_MODES = (TLS_MODE_OFF, TLS_MODE_SELF_SIGNED)

_ENV_TLS_MODE = "TRPG_TLS_MODE"
_ENV_CERT_FILE = "TRPG_TLS_CERT_FILE"
_ENV_KEY_FILE = "TRPG_TLS_KEY_FILE"


@dataclass
class WebTransportConfig:
    """解析后的 Web Transport 配置。

    只保存 canonical 值；未知子字段在解析时被丢弃，旧版本回滚不会因
    陌生字段崩溃，新版本也不会把展示用文本误存为 identity。
    """

    tls_mode: str = TLS_MODE_OFF
    # 配置来源，用于 UI 说明当前模式来自环境变量还是用户设置。
    tls_mode_source: str = "default"
    # 预留字段：外部证书（阶段 D）与 ACME（阶段 C）。本版本解析后
    # 若出现非空值，会在校验时报告"暂不支持"，绝不静默忽略。
    cert_file: str = ""
    key_file: str = ""
    reserved_rejects: list[str] = field(default_factory=list)

    @property
    def scheme(self) -> str:
        return "https" if self.tls_mode != TLS_MODE_OFF else "http"

    def redacted_view(self) -> dict[str, Any]:
        """对外（API / 日志）使用的脱敏视图，不含任何密钥材料或路径内容。"""
        return {
            "tls_mode": self.tls_mode,
            "scheme": self.scheme,
            "tls_mode_source": self.tls_mode_source,
            "lets_encrypt_available": False,
        }


def _clean_mode(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def parse_web_transport(saved: Mapping[str, Any] | None, env: Mapping[str, str] | None = None) -> WebTransportConfig:
    """从保存的配置与环境变量解析 Web Transport 配置。

    环境变量优先级高于保存的配置（与现有 env > saved config 约定一致）。
    无效 tls_mode 不抛异常：记录 warning 并按 off 处理，保证旧配置或
    手工编辑后的 config.json 仍能启动（回滚安全）。
    """
    saved = saved if isinstance(saved, Mapping) else {}
    env = env if env is not None else os.environ

    config = WebTransportConfig()

    config_mode = _clean_mode(saved.get("tls_mode"))
    if config_mode in PUBLIC_TLS_MODES:
        config.tls_mode = config_mode
        config.tls_mode_source = "config"
    elif config_mode:
        logger.warning("web_transport.tls_mode=%r 不是有效值，已按 HTTP 处理", config_mode)

    env_mode = _clean_mode(env.get(_ENV_TLS_MODE))
    if env_mode:
        if env_mode in PUBLIC_TLS_MODES:
            config.tls_mode = env_mode
            config.tls_mode_source = "env"
        else:
            logger.warning("%s=%r 不是有效值，已忽略", _ENV_TLS_MODE, env_mode)

    # 阶段 D 预留：外部证书文件。出现即显式拒绝，避免用户误以为已生效。
    for name, attr in ((_ENV_CERT_FILE, "cert_file"), (_ENV_KEY_FILE, "key_file")):
        env_value = str(env.get(name) or "").strip()
        saved_value = str(saved.get(attr) or "").strip()
        value = env_value or saved_value
        if value:
            setattr(config, attr, value)
            config.reserved_rejects.append(name if env_value else f"web_transport.{attr}")

    # 阶段 C 预留：ACME 字段只做存在性检查，不做模糊猜测式解析。
    if isinstance(saved.get("acme"), Mapping) and saved.get("acme"):
        config.reserved_rejects.append("web_transport.acme")

    return config


def validate_activation(config: WebTransportConfig) -> str | None:
    """返回阻止启用该配置的中文错误；None 表示可以启用。"""
    # 阶段 D 预留：外部证书文件。出现即显式拒绝，避免用户误以为已生效。
    if config.cert_file or config.key_file:
        return "自定义证书文件尚未开放（暂不支持 TRPG_TLS_CERT_FILE / TRPG_TLS_KEY_FILE）"
    if config.tls_mode in AVAILABLE_TLS_MODES:
        return None
    if config.tls_mode == TLS_MODE_LETS_ENCRYPT:
        return "Let's Encrypt 证书尚未开放（技术验证中），请先使用本地 HTTPS 或 HTTP"
    return f"不支持的连接模式：{config.tls_mode or '(空)'}"


def web_transport_config_from_state(state: Mapping[str, Any], env: Mapping[str, str] | None = None) -> WebTransportConfig:
    """从 web_server STATE 中的 web_transport 字段重建配置（用于运行期切换）。"""
    return parse_web_transport(state.get("web_transport") or {}, env)
