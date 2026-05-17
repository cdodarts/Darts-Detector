# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.config.camera_config — Pydantic v2 models for cameras.yaml.

@internal

Loads and validates the camera configuration file. All fields map 1:1 to
the cameras.yaml schema. Validation is strict: invalid config fails closed
with a clear error message rather than silently falling back to defaults.

See docs/CONFIGURATION.md for the full schema specification.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class CameraResolution(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ExposureConfig(BaseModel):
    mode: Literal["manual", "auto"] = "manual"
    value: Optional[int] = None


class WhiteBalanceConfig(BaseModel):
    mode: Literal["manual", "auto"] = "manual"
    value: Optional[int] = None


class CropRect(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


CameraRole = Literal["cam_1", "cam_2", "cam_3"]


class CameraEntry(BaseModel):
    cameraId: str
    name: str
    friendlyName: str = "Autodarts DIY Cam"
    # devicePath is the USB device instance path on Windows (e.g. USB\VID_0C45&PID_6366\...).
    # Leave empty until the user runs list_devices and identifies each physical port.
    devicePath: str = ""
    role: CameraRole
    resolution: CameraResolution = CameraResolution(width=1280, height=720)
    fps: int = Field(default=30, gt=0)  # D-019: default 30 FPS; was 60
    exposure: ExposureConfig = ExposureConfig(mode="manual", value=100)
    gain: int = 0
    brightness: int = 0
    contrast: int = 0
    whiteBalance: WhiteBalanceConfig = WhiteBalanceConfig(mode="manual", value=4500)
    rotation: int = Field(default=0, ge=0, lt=360)
    crop: Optional[CropRect] = None
    enabled: bool = True
    # TODO-gamma: Add in Phase 1.5 — maps to cv2.CAP_PROP_GAMMA. Part of tuning fingerprint (D-020).
    # TODO-saturation: Add in Phase 1.5 — maps to cv2.CAP_PROP_SATURATION. Part of tuning fingerprint.
    # TODO-sharpness: Add in Phase 1.5 — maps to cv2.CAP_PROP_SHARPNESS. Part of tuning fingerprint.
    # TODO-backlight: Add in Phase 1.5 — backlightCompensation bool, maps to cv2.CAP_PROP_BACKLIGHT. Part of tuning fingerprint.

    @field_validator("cameraId")
    @classmethod
    def camera_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("cameraId must not be empty")
        return v


class CamerasConfig(BaseModel):
    version: int = Field(default=1, ge=1)
    cameras: list[CameraEntry]

    @field_validator("cameras")
    @classmethod
    def validate_cameras(cls, cameras: list[CameraEntry]) -> list[CameraEntry]:
        ids = [c.cameraId for c in cameras]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate cameraId values found in cameras.yaml")
        roles = [c.role for c in cameras if c.enabled]
        if len(roles) != len(set(roles)):
            raise ValueError("Duplicate role values found among enabled cameras")
        return cameras

    def enabled_cameras(self) -> list[CameraEntry]:
        """Return only the enabled cameras, ordered by role."""
        role_order: dict[CameraRole, int] = {
            "cam_1": 0,
            "cam_2": 1,
            "cam_3": 2,
        }
        return sorted(
            [c for c in self.cameras if c.enabled],
            key=lambda c: role_order.get(c.role, 99),
        )

    def camera_by_role(self, role: CameraRole) -> Optional[CameraEntry]:
        """Return the first enabled camera with the given role, or None."""
        for cam in self.cameras:
            if cam.role == role and cam.enabled:
                return cam
        return None


def load_cameras_config(path: Path) -> CamerasConfig:
    """
    Load and validate cameras.yaml from the given path.

    Raises FileNotFoundError if the file does not exist.
    Raises ValueError (via Pydantic ValidationError) if the config is invalid.
    Fails closed — never returns a partially-valid config.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"cameras.yaml not found at {path}. "
            "Run 'uv run python -m darts_detector.capture.list_devices' to identify "
            "your cameras, then edit config/cameras.yaml."
        )
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raise ValueError(f"cameras.yaml at {path} is empty or blank.")
    return CamerasConfig.model_validate(raw)
