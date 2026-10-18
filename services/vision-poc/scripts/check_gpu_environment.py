"""Runtime sanity check for the MeasureX vision GPU environment.

Reports what a real (non-mocked) run needs: Python/torch/CUDA, the GPU and its
VRAM, host RAM, whether the required packages import, and whether the model
weights the real stack uses are present or will auto-download.

    python scripts/check_gpu_environment.py
    python scripts/check_gpu_environment.py --self-check   # offline asserts, no GPU

Nothing here imports the measurex_vision package or loads a model — it is safe to
run before `pip install -e` finishes. Exit code is 0 when the real stack can run
(torch + CUDA + required packages import, and the SAM 2 checkpoint + config are in
place — SAM 2 has no auto-download), 1 otherwise.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import sys

# Packages the real GDINO -> SAM 2 -> Depth Anything V2 stack needs to import.
REQUIRED = ("numpy", "torch", "transformers", "PIL", "cv2", "timm", "sam2")
OPTIONAL = ("depth_pro",)  # research-only; not needed for the normal GPU test


def _importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _fmt_bytes(n: float) -> str:
    return f"{n / 1024 ** 3:.1f} GB"


def _available_ram_bytes() -> int | None:
    """Host RAM, best-effort and dependency-free (Linux is the GPU target)."""
    try:  # Linux (Lightning AI, Kaggle)
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    try:  # POSIX fallback
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, AttributeError, OSError):
        return None


def report() -> int:
    print("== MeasureX vision GPU environment ==")
    print(f"Python        : {platform.python_version()} ({sys.executable})")

    torch_ok = _importable("torch")
    cuda_available = False
    if torch_ok:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        print(f"torch         : {torch.__version__}")
        print(f"CUDA (torch)  : {torch.version.cuda or 'n/a'}")
        print(f"CUDA available: {cuda_available}")
        if cuda_available:
            props = torch.cuda.get_device_properties(0)
            print(f"GPU           : {props.name}")
            print(f"GPU VRAM      : {_fmt_bytes(props.total_memory)}")
        else:
            print("GPU           : none visible to torch")
    else:
        print("torch         : NOT INSTALLED")

    ram = _available_ram_bytes()
    print(f"Host RAM      : {_fmt_bytes(ram) if ram else 'unknown'}")

    print("Packages:")
    missing = [p for p in REQUIRED if not _importable(p)]
    for pkg in REQUIRED:
        print(f"  {'OK ' if pkg not in missing else 'MISSING'} {pkg}")
    for pkg in OPTIONAL:
        print(f"  {'OK ' if _importable(pkg) else '-- '} {pkg} (optional, research-only)")

    print("Model weights:")
    sam2_ckpt = os.environ.get("MEASUREX_SAM2_CHECKPOINT")
    sam2_cfg = os.environ.get("MEASUREX_SAM2_CONFIG")
    sam2_ckpt_ok = bool(sam2_ckpt) and os.path.exists(sam2_ckpt)
    sam2_cfg_ok = _sam2_config_resolvable(sam2_cfg)
    print(f"  SAM 2 checkpoint   : {_weight_status(sam2_ckpt, 'set MEASUREX_SAM2_CHECKPOINT')}")
    print(f"  SAM 2 config       : {_sam2_config_status(sam2_cfg, sam2_cfg_ok)}")
    print("  Grounding DINO     : auto-downloads from Hugging Face on first run")
    print("  Depth Anything V2  : auto-downloads from Hugging Face on first run")
    depth_pro = os.environ.get("MEASUREX_DEPTH_CHECKPOINT") or os.path.join(
        os.environ.get("MEASUREX_VISION_WEIGHTS_DIR", "./weights"), "depth_pro.pt"
    )
    print(f"  Depth Pro (opt.)   : {_weight_status(depth_pro, 'optional, research only')}")

    ready = _is_ready(
        torch_ok=torch_ok, cuda_available=cuda_available, missing=missing,
        sam2_ckpt_ok=sam2_ckpt_ok, sam2_cfg_ok=sam2_cfg_ok,
    )
    print()
    print(
        "READY: real stack can run."
        if ready
        else "NOT READY: see MISSING / CUDA / SAM 2 checkpoint/config above."
    )
    return 0 if ready else 1


def _is_ready(*, torch_ok: bool, cuda_available: bool, missing: list[str],
              sam2_ckpt_ok: bool, sam2_cfg_ok: bool) -> bool:
    """The real production stack can run only with CUDA, every required package,
    and the SAM 2 checkpoint + config in place (SAM 2 has no auto-download)."""
    return torch_ok and cuda_available and not missing and sam2_ckpt_ok and sam2_cfg_ok


def _sam2_config_resolvable(cfg: str | None) -> bool:
    """SAM 2 config is resolvable when set and either a real file on disk or
    shipped inside the installed ``sam2`` package (``build_sam2`` resolves it
    from there via Hydra, e.g. ``configs/sam2.1/sam2.1_hiera_s.yaml``)."""
    if not cfg:
        return False
    if os.path.exists(cfg):
        return True
    try:
        import sam2  # only reached when a config is set (CI never sets one)
    except ImportError:
        return False
    return os.path.exists(os.path.join(os.path.dirname(sam2.__file__), cfg))


def _sam2_config_status(cfg: str | None, resolvable: bool) -> str:
    if not cfg:
        return "not configured (set MEASUREX_SAM2_CONFIG)"
    if resolvable:
        suffix = "" if os.path.exists(cfg) else " (resolved from sam2 package)"
        return f"present: {cfg}{suffix}"
    return f"NOT RESOLVABLE: {cfg}"


def _weight_status(path: str | None, hint: str) -> str:
    if not path:
        return f"not configured ({hint})"
    return f"present: {path}" if os.path.exists(path) else f"MISSING: {path}"


def _self_check() -> int:
    """Offline asserts for the pure helpers (no GPU, no heavy deps)."""
    assert _fmt_bytes(16 * 1024 ** 3) == "16.0 GB"
    assert _importable("os") and not _importable("definitely_not_a_module_xyz")
    assert _weight_status(None, "hint").startswith("not configured")
    assert _weight_status(__file__, "hint").startswith("present")
    assert _weight_status(__file__ + ".nope", "hint").startswith("MISSING")

    # SAM 2 config resolution: an on-disk file resolves; an unset/absent one does not.
    assert _sam2_config_resolvable(__file__) is True
    assert _sam2_config_resolvable(None) is False
    assert _sam2_config_resolvable("configs/does_not_exist.yaml") is False

    # READY gate: everything present passes; dropping any single requirement fails.
    ready_kwargs = {
        "torch_ok": True, "cuda_available": True, "missing": [],
        "sam2_ckpt_ok": True, "sam2_cfg_ok": True,
    }
    assert _is_ready(**ready_kwargs) is True
    assert _is_ready(**{**ready_kwargs, "cuda_available": False}) is False
    assert _is_ready(**{**ready_kwargs, "missing": ["sam2"]}) is False
    assert _is_ready(**{**ready_kwargs, "sam2_ckpt_ok": False}) is False
    assert _is_ready(**{**ready_kwargs, "sam2_cfg_ok": False}) is False
    print("self-check OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help="run offline asserts and exit")
    args = parser.parse_args(argv)
    return _self_check() if args.self_check else report()


if __name__ == "__main__":
    raise SystemExit(main())
