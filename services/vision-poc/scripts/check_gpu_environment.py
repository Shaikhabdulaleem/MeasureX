"""Runtime sanity check for the MeasureX vision GPU environment.

Reports what a real (non-mocked) run needs: Python/torch/CUDA, the GPU and its
VRAM, host RAM, whether the required packages import, and whether the model
weights the real stack uses are present or will auto-download.

    python scripts/check_gpu_environment.py
    python scripts/check_gpu_environment.py --self-check   # offline asserts, no GPU

Nothing here imports the measurex_vision package or loads a model — it is safe to
run before `pip install -e` finishes. Exit code is 0 when the real stack can run
(torch + CUDA + required packages import), 1 otherwise.
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
    print(f"  SAM 2 checkpoint   : {_weight_status(sam2_ckpt, 'set MEASUREX_SAM2_CHECKPOINT')}")
    print(f"  SAM 2 config       : {_weight_status(os.environ.get('MEASUREX_SAM2_CONFIG'), 'set MEASUREX_SAM2_CONFIG')}")
    print("  Grounding DINO     : auto-downloads from Hugging Face on first run")
    print("  Depth Anything V2  : auto-downloads from Hugging Face on first run")
    depth_pro = os.environ.get("MEASUREX_DEPTH_CHECKPOINT") or os.path.join(
        os.environ.get("MEASUREX_VISION_WEIGHTS_DIR", "./weights"), "depth_pro.pt"
    )
    print(f"  Depth Pro (opt.)   : {_weight_status(depth_pro, 'optional, research only')}")

    ready = torch_ok and cuda_available and not missing
    print()
    print("READY: real stack can run." if ready else "NOT READY: see MISSING / CUDA above.")
    return 0 if ready else 1


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
    print("self-check OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help="run offline asserts and exit")
    args = parser.parse_args(argv)
    return _self_check() if args.self_check else report()


if __name__ == "__main__":
    raise SystemExit(main())
