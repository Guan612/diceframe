"""Versioned adventure content packages.

Adventure packages are data. Ruleset runtimes remain the only mechanics
authority and may opt into one or more adventure graph formats.
"""

from .bundle import (
    ADVENTURE_GRAPH_FORMAT,
    AdventureBundleError,
    AdventureBundleLoader,
    LoadedAdventureBundle,
)
from .catalog import is_builtin_adventure_directory, sync_adventure_catalog

__all__ = [
    "ADVENTURE_GRAPH_FORMAT",
    "AdventureBundleError",
    "AdventureBundleLoader",
    "LoadedAdventureBundle",
    "is_builtin_adventure_directory",
    "sync_adventure_catalog",
]
