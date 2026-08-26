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

__all__ = [
    "ADVENTURE_GRAPH_FORMAT",
    "AdventureBundleError",
    "AdventureBundleLoader",
    "LoadedAdventureBundle",
]
