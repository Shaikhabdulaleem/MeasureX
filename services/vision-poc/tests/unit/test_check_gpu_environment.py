"""The GPU-readiness gate must never report READY with a missing requirement.

``scripts/check_gpu_environment.py`` is a standalone script (not part of the
package), so it is loaded by path."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_gpu_environment.py"
_spec = importlib.util.spec_from_file_location("check_gpu_environment", _SCRIPT)
assert _spec and _spec.loader
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)


_READY = {
    "torch_ok": True,
    "cuda_available": True,
    "missing": [],
    "sam2_ckpt_ok": True,
    "sam2_cfg_ok": True,
}


def test_ready_when_everything_present():
    assert chk._is_ready(**_READY) is True


def test_not_ready_missing_any_single_requirement():
    for drop in ("cuda_available", "sam2_ckpt_ok", "sam2_cfg_ok"):
        assert chk._is_ready(**{**_READY, drop: False}) is False
    assert chk._is_ready(**{**_READY, "torch_ok": False}) is False
    assert chk._is_ready(**{**_READY, "missing": ["sam2"]}) is False


def test_sam2_config_resolvable():
    assert chk._sam2_config_resolvable(None) is False
    assert chk._sam2_config_resolvable("") is False
    assert chk._sam2_config_resolvable(str(_SCRIPT)) is True  # an on-disk file resolves
    assert chk._sam2_config_resolvable("configs/sam2.1/nope.yaml") is False


def test_self_check_passes():
    assert chk.main(["--self-check"]) == 0
