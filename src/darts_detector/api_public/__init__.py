# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.api_public — public stable API surface.

@public-stable

This package is intentionally sparse until Phase 8 (WebSocket dart event output).
The sanctioned plugin interface before Phase 8 is the WebSocket event stream.

Adding symbols here requires a documented use case and an RFC for non-trivial additions.
Internal modules must NOT import from this package — the dependency flows outward only.

See docs/PLUGIN_ARCHITECTURE.md and DECISIONS.md D-013.
"""
