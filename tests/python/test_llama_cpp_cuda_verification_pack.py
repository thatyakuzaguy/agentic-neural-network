from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    build_llama_cpp_cuda_verification_pack,
    write_llama_cpp_cuda_verification_pack_artifacts,
)


SCRIPT_ROOT = Path("D:/AgenticEngineeringNetwork/scripts/runtime")


def test_llama_cpp_cuda_verification_pack_scripts_are_read_only() -> None:
    pack = build_llama_cpp_cuda_verification_pack()

    assert pack["status"] == "PACK_READY_READ_ONLY"
    assert pack["no_model_load_by_default"] is True
    for script in pack["scripts"]:
        assert script["exists"] is True
        assert script["read_only"] is True
        assert script["blocked_tokens"] == []
        assert script["loads_models_by_default"] is False


def test_torch_and_llama_check_scripts_print_status() -> None:
    for script in ("check_torch_cuda.py", "check_llama_cpp_cuda.py"):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_ROOT / script)],
            cwd="D:/AgenticEngineeringNetwork",
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        assert payload["read_only"] is True
        assert payload["installs"] is False
        assert payload["downloads"] is False
        assert payload["model_load"] is False


def test_llama_cpp_cuda_verification_pack_artifacts(tmp_path: Path) -> None:
    artifacts = write_llama_cpp_cuda_verification_pack_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {
        "140_llama_cpp_cuda_verification_pack.json",
        "141_llama_cpp_cuda_verification_pack.md",
    }
    payload = json.loads((tmp_path / "140_llama_cpp_cuda_verification_pack.json").read_text(encoding="utf-8"))
    assert payload["version"] == "14.2"
