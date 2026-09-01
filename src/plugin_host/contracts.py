"""Typed application contracts for the plugin host boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, NotRequired, TypedDict

from src.plugin_sdk.contracts import (
    BridgeExtensionDescriptor,
    ProviderCapabilityDescriptor,
    ToolDescriptor,
)


class PluginManifest(TypedDict, total=False):
    schema_version: int
    id: str
    name: str
    version: str
    description: str
    plugin_type: str
    entrypoint: list[str]
    min_app_version: str
    permissions: list[str]
    capabilities: list[str]
    contributes: dict[str, object]
    content_schema_version: int
    locale_schema_version: int
    default_locale: str
    config_schema: str
    tool_ui: str
    docs: str


class PluginTypeDescriptor(TypedDict):
    level: str
    summary: str
    process_mode: str
    inferred_permissions: list[str]
    required_permission: str | None
    contributes: Mapping[str, str] | None
    filterable: bool
    filter_order: int
    cleanup: NotRequired[list[str]]


class PluginSupportView(TypedDict):
    level: str
    summary: str


class PluginTypeListView(TypedDict):
    id: str
    level: str
    filterable: bool
    filter_order: int


class PluginContributionView(TypedDict):
    plugin_id: str
    plugin_name: str
    plugin_type: str
    kind: str
    key: str
    path: str
    title: str
    description: str


class PluginPublicDetail(TypedDict, total=False):
    id: str
    name: object
    version: object
    description: object
    plugin_type: str
    support: PluginSupportView
    has_entrypoint: bool
    enabled: bool
    running: bool
    status: str
    error: str
    schema: dict[str, Any]
    config: dict[str, Any]
    capabilities: object
    permissions: list[str]
    permission_details: list[dict[str, str]]
    min_app_version: str
    needs_core_update: bool
    tool_ui: str
    tools: list[ToolDescriptor]
    bridge_extensions: list[BridgeExtensionDescriptor]
    contributions: list[PluginContributionView]
    docs: object


PluginStoppedCallback = Callable[[str], Awaitable[None]]
AIProviderResolver = Callable[[str], object]
