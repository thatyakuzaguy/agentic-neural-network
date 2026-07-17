"""Read-only ANN runtime/backend guard check.

This script imports ANN diagnostics and prints launch guard state. It does not
execute terminal operations, install dependencies, or load models.
"""

from __future__ import annotations

import json

from agentic_network.runtime_engine.local_model_activation import (
    LOCAL_TEST_TOKEN,
    build_real_inference_launch_guard,
    diagnose_cuda_environment,
    diagnose_llama_cpp_real_status,
)


def main() -> None:
    cuda = diagnose_cuda_environment()
    llama = diagnose_llama_cpp_real_status()
    guard = build_real_inference_launch_guard(confirm=True, approval_token=LOCAL_TEST_TOKEN, experimental=True)
    print(
        json.dumps(
            {
                "script": "check_ann_runtime_backend",
                "read_only": True,
                "installs": False,
                "downloads": False,
                "model_load": False,
                "cuda_status": cuda["status"],
                "llama_cpp_status": llama["status"],
                "launch_guard_status": guard["status"],
                "launch_guard_failed_checks": [check["name"] for check in guard["failed_checks"]],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
