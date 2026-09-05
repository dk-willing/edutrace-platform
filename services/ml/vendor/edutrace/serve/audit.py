"""Append-only audit log.

Every score, review, notification and safeguarding escalation is written here.
Three reasons this is not optional:

* **Legal.**  Act 843 gives data subjects access and correction rights; you
  cannot answer "what did the system say about my child, and who saw it" from
  application logs.
* **Model monitoring.**  Realised outcomes only become learnable if you kept
  what was predicted, when, and what was done about it.  Without the audit log
  there is no way to re-validate next year, which is the single most important
  maintenance task this system has.
* **Override auditing.**  The review gate is only meaningful if override
  accuracy can be examined by group, later.

What is deliberately **not** logged: narrative disclosures from a support
conversation, anything about abuse, self-harm, sexual activity, pregnancy or
health status.  Those are special personal data under Act 843 s.37, and the
safeguarding path records that an escalation happened, to whom, and when --
never what was said.  ``AuditLog.append`` rejects payloads carrying the
reserved keys, so the rule is enforced rather than documented.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

#: Keys that must never reach the audit log.
FORBIDDEN_KEYS = frozenset(
    {
        "disclosure",
        "disclosure_text",
        "narrative_disclosure",
        "safeguarding_detail",
        "health_detail",
        "abuse_detail",
        "student_name",
        "guardian_name",
        "guardian_msisdn",
        "free_text",
    }
)


class AuditViolation(RuntimeError):
    pass


class AuditLog:
    """JSONL append-only log with an fsync per record.

    JSONL because it is trivially greppable, streams, survives partial writes,
    and can be shipped to any warehouse.  Production should additionally write
    to append-only object storage with retention locks; a local file is
    tamper-evident at best.
    """

    def __init__(self, path: str | Path, fsync: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fsync = fsync

    def append(self, event: str, **payload: Any) -> dict[str, Any]:
        bad = FORBIDDEN_KEYS.intersection(payload)
        if bad:
            raise AuditViolation(
                f"refusing to write special-category or identifying fields to "
                f"the audit log: {sorted(bad)}. Safeguarding records store "
                f"metadata (that an escalation happened, to whom, when), never "
                f"content."
            )
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        line = json.dumps(record, default=str, separators=(",", ":"))
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                if self._fsync:
                    os.fsync(fh.fileno())
        return record

    def read(self, event: str | None = None) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if event is None or rec.get("event") == event:
                    yield rec

    def count(self, event: str | None = None) -> int:
        return sum(1 for _ in self.read(event))


__all__ = ["AuditLog", "AuditViolation", "FORBIDDEN_KEYS"]
