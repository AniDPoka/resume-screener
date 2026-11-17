"""The audit file: a record of every step and every score in a run, saved as JSON.

One file per run, in audit_logs/, named by the time the run started. It is saved again after
every step, so even a run that stops halfway leaves a full record of what happened up to then.
The AI key is never written here: only the settings passed in are recorded.
"""

import json
from datetime import datetime
from pathlib import Path


class Audit:
    def __init__(self, settings, folder="audit_logs"):
        """settings: what this run used (model, temperature, thresholds...). Never include the key."""
        started = datetime.now()
        self.path = Path(folder) / f"run_{started:%Y-%m-%d_%H-%M-%S}.json"
        number = 2
        while self.path.exists():  # two runs in the same second get separate files
            self.path = Path(folder) / f"run_{started:%Y-%m-%d_%H-%M-%S}_{number}.json"
            number += 1
        self.record = {"run_started": started.isoformat(timespec="seconds"), "settings": settings, "steps": []}

    def log(self, step, **details):
        """Adds one step (e.g. "score", "consistency_check") with its details, then saves."""
        entry = {"time": datetime.now().isoformat(timespec="seconds"), "step": step, **details}
        self.record["steps"].append(entry)
        self.save()
        return entry

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.record, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.path
