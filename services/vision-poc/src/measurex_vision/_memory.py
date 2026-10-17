"""Release GPU/CPU memory held by a just-used model (low-memory pipeline mode)."""

from __future__ import annotations

import gc


def free_torch_memory() -> None:
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
