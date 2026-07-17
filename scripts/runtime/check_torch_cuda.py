"""Read-only Torch/CUDA runtime check for ANN.

This script does not install packages, download files, compile code, or load
models. It only imports torch if present and prints JSON status.
"""

from __future__ import annotations

import json


def main() -> None:
    payload = {
        "script": "check_torch_cuda",
        "read_only": True,
        "installs": False,
        "downloads": False,
        "model_load": False,
    }
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        devices = []
        if cuda_available:
            for index in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(index)
                devices.append(
                    {
                        "index": index,
                        "name": torch.cuda.get_device_name(index),
                        "total_vram_mb": round(int(props.total_memory) / (1024 * 1024), 2),
                    }
                )
        payload.update(
            {
                "status": "cuda_available" if cuda_available else "cuda_unavailable",
                "torch_importable": True,
                "torch_version": getattr(torch, "__version__", "unknown"),
                "torch_cuda_version": str(getattr(torch.version, "cuda", None)),
                "cuda_available": cuda_available,
                "device_count": len(devices),
                "devices": devices,
            }
        )
    except Exception as exc:  # pragma: no cover - depends on optional runtime.
        payload.update(
            {
                "status": "torch_unavailable",
                "torch_importable": False,
                "error": f"{type(exc).__name__}:{exc}",
            }
        )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
