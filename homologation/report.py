"""Homologation result collection and reporting."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ScenarioStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class ScenarioResult:
    case_id: str
    name: str
    status: ScenarioStatus
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HomologationReport:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    results: list[ScenarioResult] = field(default_factory=list)

    def add(
        self,
        case_id: str,
        name: str,
        status: ScenarioStatus,
        detail: str = "",
        **metadata: Any,
    ) -> None:
        self.results.append(
            ScenarioResult(
                case_id=case_id,
                name=name,
                status=status,
                detail=detail,
                metadata=metadata,
            )
        )

    @property
    def all_passed(self) -> bool:
        return all(r.status in (ScenarioStatus.PASS, ScenarioStatus.SKIP) for r in self.results)

    @property
    def has_failures(self) -> bool:
        return any(r.status == ScenarioStatus.FAIL for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "summary": {
                "total": len(self.results),
                "passed": sum(1 for r in self.results if r.status == ScenarioStatus.PASS),
                "failed": sum(1 for r in self.results if r.status == ScenarioStatus.FAIL),
                "skipped": sum(1 for r in self.results if r.status == ScenarioStatus.SKIP),
                "ok": self.all_passed,
            },
            "results": [
                {
                    "case_id": r.case_id,
                    "name": r.name,
                    "status": r.status.value,
                    "detail": r.detail,
                    "metadata": r.metadata,
                }
                for r in self.results
            ],
        }

    def print_summary(self) -> None:
        sep = "=" * 64
        print(f"\n{sep}")
        print("  MT5 ADAPTER — HOMOLOGATION REPORT")
        print(sep)
        for r in self.results:
            mark = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[r.status.value]
            line = f"  {mark} {r.case_id}: {r.name}"
            if r.detail:
                line += f" — {r.detail}"
            print(line)
        print(sep)
        counts = self.to_dict()["summary"]
        print(
            f"  Total: {counts['total']}  "
            f"Passed: {counts['passed']}  "
            f"Failed: {counts['failed']}  "
            f"Skipped: {counts['skipped']}"
        )
        print(f"  Overall: {'PASS' if self.all_passed else 'FAIL'}")
        print(sep)

    def write_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)
