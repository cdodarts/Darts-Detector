# SPDX-License-Identifier: GPL-3.0-or-later
"""
Pytest root conftest — registers shared CLI options for all tests.

pytest only collects ``pytest_addoption`` hooks from conftest.py files (not
from individual test modules), so option registration lives here.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--cameras",
        type=int,
        default=3,
        help="Number of cameras to test (1, 2, or 3). Default: 3.",
    )
    parser.addoption(
        "--duration",
        type=float,
        default=30.0,
        help="Capture duration in seconds. Default: 30.",
    )
    parser.addoption(
        "--config",
        type=str,
        default="config/cameras.yaml",
        help="Path to cameras.yaml. Default: config/cameras.yaml.",
    )
