from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_engineering_network.orchestration.application.risk_register import default_risk_register
from agentic_engineering_network.shared.config import Settings


class EvidenceStore:
    def __init__(self, settings: Settings) -> None:
        self.root = settings.run_state_path.parent
        self.root.mkdir(parents=True, exist_ok=True)

    def read_business_context(self) -> dict[str, object]:
        return self._read_json("business-context.json", {})

    def write_business_context(self, payload: dict[str, object]) -> dict[str, object]:
        self._write_json("business-context.json", payload)
        return payload

    def read_human_gate_decisions(self) -> list[dict[str, object]]:
        payload = self._read_json("human-gates.json", [])
        return payload if isinstance(payload, list) else []

    def append_human_gate_decision(self, decision: dict[str, object]) -> list[dict[str, object]]:
        decisions = self.read_human_gate_decisions()
        decisions = [item for item in decisions if item.get("gate_id") != decision.get("gate_id")]
        decisions.append(decision)
        self._write_json("human-gates.json", decisions)
        return decisions

    def read_risks(self) -> list[dict[str, object]]:
        payload = self._read_json("risk-register.json", [])
        if isinstance(payload, list) and payload:
            return payload
        risks = default_risk_register()
        self._write_json("risk-register.json", risks)
        return risks

    def write_risks(self, risks: list[dict[str, object]]) -> list[dict[str, object]]:
        self._write_json("risk-register.json", risks)
        return risks

    def _path(self, name: str) -> Path:
        return self.root / name

    def _read_json(self, name: str, default: Any) -> Any:
        path = self._path(name)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    def _write_json(self, name: str, payload: Any) -> None:
        self._path(name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
