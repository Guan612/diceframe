"""Web Transport 配置解析、兼容与脱敏契约。"""

from __future__ import annotations

from src.web_transport.config import (
    TLS_MODE_LETS_ENCRYPT,
    TLS_MODE_OFF,
    TLS_MODE_SELF_SIGNED,
    parse_web_transport,
    validate_activation,
)


def test_missing_field_defaults_to_off():
    config = parse_web_transport({})
    assert config.tls_mode == TLS_MODE_OFF
    assert config.scheme == "http"
    assert config.tls_mode_source == "default"


def test_none_saved_config_is_off():
    config = parse_web_transport(None, {})
    assert config.tls_mode == TLS_MODE_OFF


def test_all_public_modes_parse():
    assert parse_web_transport({"tls_mode": "off"}).tls_mode == "off"
    assert parse_web_transport({"tls_mode": "self_signed"}).tls_mode == "self_signed"
    assert parse_web_transport({"tls_mode": "lets_encrypt"}).tls_mode == "lets_encrypt"
    assert parse_web_transport({"tls_mode": "SELF_SIGNED"}).scheme == "https"


def test_invalid_mode_falls_back_to_off():
    config = parse_web_transport({"tls_mode": "turbo_tls"})
    assert config.tls_mode == TLS_MODE_OFF
    # lets_encrypt 之外的无效值同样不可激活。
    assert validate_activation(config) is None or "不支持" in validate_activation(config)


def test_env_overrides_saved_config():
    config = parse_web_transport(
        {"tls_mode": "off"},
        {"TRPG_TLS_MODE": "self_signed"},
    )
    assert config.tls_mode == TLS_MODE_SELF_SIGNED
    assert config.tls_mode_source == "env"


def test_invalid_env_mode_is_ignored():
    config = parse_web_transport(
        {"tls_mode": "self_signed"},
        {"TRPG_TLS_MODE": "not-a-mode"},
    )
    assert config.tls_mode == TLS_MODE_SELF_SIGNED
    assert config.tls_mode_source == "config"


def test_unknown_fields_are_ignored_for_rollback_safety():
    config = parse_web_transport(
        {"tls_mode": "off", "future_option": {"nested": True}, "tls_strangeness": 1},
        {},
    )
    assert config.tls_mode == TLS_MODE_OFF


def test_reserved_fields_are_reported_not_silently_applied():
    config = parse_web_transport(
        {"tls_mode": "off", "cert_file": "C:/some.pem", "key_file": "C:/some.key"},
        {},
    )
    assert config.cert_file and config.key_file
    assert "web_transport.cert_file" in config.reserved_rejects
    error = validate_activation(config)
    assert error and "暂不支持" in error


def test_acme_reserved_block_is_reported():
    config = parse_web_transport(
        {"tls_mode": "off", "acme": {"identifier_type": "dns", "identifier": "example.com"}},
        {},
    )
    assert "web_transport.acme" in config.reserved_rejects


def test_lets_encrypt_activation_is_rejected_in_phase_a():
    error = validate_activation(parse_web_transport({"tls_mode": "lets_encrypt"}))
    assert error and "尚未开放" in error


def test_redacted_view_contains_no_key_material():
    config = parse_web_transport(
        {"tls_mode": "self_signed", "cert_file": "C:/secret.pem", "key_file": "C:/secret.key"},
        {},
    )
    view = config.redacted_view()
    text = repr(view)
    assert "secret" not in text
    assert "cert_file" not in text
    assert "key_file" not in text
    assert view["tls_mode"] == "self_signed"
    assert view["scheme"] == "https"
    assert view["lets_encrypt_available"] is False
