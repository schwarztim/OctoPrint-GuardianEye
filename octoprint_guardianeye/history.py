"""
Verdict History Storage for GuardianEye.

JSON-based storage in OctoPrint's plugin data folder:
  - verdict_history.json — rolling 500 entries
  - session_history.json — per-print summaries with print score
"""

import os
import json
import time
import uuid
import logging

_logger = logging.getLogger("octoprint.plugins.guardianeye.history")

_MAX_VERDICTS = 500


class VerdictHistory:
    """Stores individual AI vision verdicts."""

    def __init__(self, data_folder):
        self._path = os.path.join(data_folder, "verdict_history.json")
        self._entries = []
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path) as f:
                    self._entries = json.load(f)
        except Exception as e:
            _logger.warning("Could not load verdict history: %s", e)
            self._entries = []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w") as f:
                json.dump(self._entries[-_MAX_VERDICTS:], f, indent=1)
        except Exception as e:
            _logger.warning("Could not save verdict history: %s", e)

    def add(self, verdict_dict, cycle, layer, progress):
        entry = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": time.time(),
            "cycle": cycle,
            "layer": layer,
            "progress": progress,
            "failed": verdict_dict.get("failed", False),
            "reason": verdict_dict.get("reason", ""),
            "confidence": verdict_dict.get("confidence", 0.0),
            "provider": verdict_dict.get("provider", ""),
            "model": verdict_dict.get("model", ""),
            "latency_ms": verdict_dict.get("latency_ms", 0),
            "cost": verdict_dict.get("cost", 0.0),
            "false_positive": False,
            "snapshot": verdict_dict.get("snapshot", None),
        }
        self._entries.append(entry)
        if len(self._entries) > _MAX_VERDICTS:
            self._entries = self._entries[-_MAX_VERDICTS:]
        self._save()
        return entry

    def mark_false_positive(self, entry_id):
        for entry in self._entries:
            if entry.get("id") == entry_id:
                entry["false_positive"] = True
                self._save()
                return True
        return False

    def get_entries(self, limit=50):
        return list(reversed(self._entries[-limit:]))

    def clear(self):
        self._entries = []
        self._save()

    def get_statistics(self):
        total = len(self._entries)
        if total == 0:
            return {"total": 0, "ok": 0, "fail": 0, "false_positives": 0,
                    "fp_rate": 0.0, "avg_latency": 0, "total_cost": 0.0}

        ok = sum(1 for e in self._entries if not e.get("failed"))
        fail = sum(1 for e in self._entries if e.get("failed"))
        fp = sum(1 for e in self._entries if e.get("false_positive"))
        total_cost = sum(e.get("cost", 0.0) for e in self._entries)
        avg_latency = sum(e.get("latency_ms", 0) for e in self._entries) // total

        return {
            "total": total,
            "ok": ok,
            "fail": fail,
            "false_positives": fp,
            "fp_rate": round(fp / max(fail, 1) * 100, 1),
            "avg_latency": avg_latency,
            "total_cost": round(total_cost, 4),
        }


class SessionHistory:
    """Stores per-print session summaries."""

    def __init__(self, data_folder):
        self._path = os.path.join(data_folder, "session_history.json")
        self._sessions = []
        self._current = None
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path) as f:
                    self._sessions = json.load(f)
        except Exception as e:
            _logger.warning("Could not load session history: %s", e)
            self._sessions = []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w") as f:
                json.dump(self._sessions[-100:], f, indent=1)
        except Exception as e:
            _logger.warning("Could not save session history: %s", e)

    def start_session(self, filename=None):
        self._current = {
            "id": str(uuid.uuid4())[:8],
            "started": time.time(),
            "filename": filename,
            "cycles": 0,
            "ok_count": 0,
            "fail_count": 0,
            "max_consecutive_fails": 0,
            "emergency_stop": False,
            "total_cost": 0.0,
            "print_score": None,
        }

    def record_verdict(self, failed, cost=0.0):
        if self._current is None:
            return
        self._current["cycles"] += 1
        self._current["total_cost"] += cost
        if failed:
            self._current["fail_count"] += 1
        else:
            self._current["ok_count"] += 1

    def end_session(self, emergency_stop=False):
        if self._current is None:
            return None
        self._current["ended"] = time.time()
        self._current["emergency_stop"] = emergency_stop

        # Calculate print score (0-100)
        total = self._current["cycles"]
        if total > 0:
            ok_ratio = self._current["ok_count"] / total
            self._current["print_score"] = round(ok_ratio * 100, 1)

        self._sessions.append(self._current)
        self._save()
        result = self._current
        self._current = None
        return result

    def get_sessions(self, limit=20):
        return list(reversed(self._sessions[-limit:]))
