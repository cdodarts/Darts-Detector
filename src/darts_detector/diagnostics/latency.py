# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.diagnostics.latency — per-stage latency timer and JSONL logger.

@internal

Records per-stage elapsed times to a JSONL log file and emits warnings when a
stage exceeds its budget. Stage budgets come from docs/LATENCY_BUDGET.md.
(capture: 100 ms at 30 FPS default per D-019; was 50 ms at 60 FPS)

  - WARNING logged if elapsed > 1.5x budget  (D-009, LATENCY_BUDGET.md)
  - ERROR   logged if elapsed > 2.0x budget  (treated as regression)

The log file is append-only JSONL. Each line is a JSON object:
  {"ts": <ISO-8601>, "stage": "<name>", "elapsed_ms": <float>, "over_budget": <bool>}
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default stage budgets from docs/LATENCY_BUDGET.md (Pi 5 4GB target, ms)
DEFAULT_STAGE_BUDGETS: dict[str, float] = {
    "capture": 100.0,
    "motion": 200.0,
    "diff": 60.0,
    "candidate": 80.0,
    "fusion": 30.0,
    "score": 5.0,
    "emit": 10.0,
}


class LatencyLogger:
    """
    Append-only per-stage latency recorder.

    Args:
        log_path: Path to the JSONL log file. Created on first write.
        stage_budgets: Override the default stage budgets (ms). Keys are stage names.
    """

    def __init__(
        self,
        log_path: Path,
        stage_budgets: Optional[dict[str, float]] = None,
    ) -> None:
        self._log_path = log_path
        self._budgets: dict[str, float] = {
            **DEFAULT_STAGE_BUDGETS,
            **(stage_budgets or {}),
        }
        # Ensure parent directory exists.
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, stage: str, elapsed_ms: float) -> None:
        """
        Record a stage timing and append it to the log file.

        Also emits a warning or error if the elapsed time exceeds budget thresholds.
        """
        self._warn_if_over_budget(stage, elapsed_ms)
        over_budget = self._is_over_budget(stage, elapsed_ms)
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "stage": stage,
            "elapsed_ms": round(elapsed_ms, 3),
            "over_budget": over_budget,
        }
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _warn_if_over_budget(self, stage: str, elapsed_ms: float) -> None:
        budget = self._budgets.get(stage)
        if budget is None:
            return
        ratio = elapsed_ms / budget
        if ratio >= 2.0:
            logger.error(
                "LATENCY REGRESSION: stage '%s' took %.1f ms (budget %.1f ms, %.0f%%). "
                "Exceeds 200%% — treat as merge-blocking regression.",
                stage,
                elapsed_ms,
                budget,
                ratio * 100,
            )
        elif ratio >= 1.5:
            logger.warning(
                "Latency warning: stage '%s' took %.1f ms (budget %.1f ms, %.0f%%).",
                stage,
                elapsed_ms,
                budget,
                ratio * 100,
            )

    def _is_over_budget(self, stage: str, elapsed_ms: float) -> bool:
        budget = self._budgets.get(stage)
        if budget is None:
            return False
        return elapsed_ms > budget


class StageTimer:
    """
    Context-manager helper for timing a single pipeline stage.

    Usage::

        with StageTimer("capture", latency_logger) as t:
            frame = camera.read()
        # t.elapsed_ms is available after the block

    """

    def __init__(self, stage: str, latency_logger: LatencyLogger) -> None:
        self._stage = stage
        self._logger = latency_logger
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "StageTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000.0
        self._logger.record(self._stage, self.elapsed_ms)
