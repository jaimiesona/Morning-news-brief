"""Remember what previous briefs contained, so today's is actually new.

Ranking rewards corroboration, and a big story keeps accumulating coverage for
days — so without a memory the same subject wins every morning under a slightly
different headline. This keeps a small record of what has already been sent and
filters those stories out.

The record is a plain JSON file. On GitHub Actions the workflow commits it back to
the repository, since a runner's disk is wiped after every run.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Set

from .config import config
from .deduplication import tokenise
from .models import Cluster

log = logging.getLogger(__name__)


def _similarity(a: Set[str], b: Set[str]) -> float:
    """Overlap normalised by the smaller set, so a terse headline still matches
    a wordier one about the same event."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


class History:
    def __init__(self, path: str = None):
        self.path = path or config.history_path
        self.entries: List[dict] = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            self.entries = data.get("stories", [])
        except (json.JSONDecodeError, OSError) as exc:
            # A corrupt history must never stop the brief; start over instead.
            log.warning("Could not read history (%s) — starting a fresh one", exc)
            self.entries = []
        self._prune()

    def _prune(self) -> None:
        cutoff = (date.today() - timedelta(days=config.history_days)).isoformat()
        self.entries = [e for e in self.entries if e.get("date", "") >= cutoff]

    def seen(self, cluster: Cluster) -> bool:
        tokens = tokenise(cluster.lead.title)
        if len(tokens) < 3:
            return False
        for entry in self.entries:
            if _similarity(tokens, set(entry.get("tokens", []))) >= config.history_threshold:
                return True
        return False

    def record(self, clusters: List[Cluster]) -> None:
        today = date.today().isoformat()
        for cluster in clusters:
            tokens = sorted(tokenise(cluster.lead.title))
            if len(tokens) < 3:
                continue
            self.entries.append({
                "date": today,
                "title": cluster.lead.title[:150],
                "tokens": tokens,
            })

    def save(self) -> None:
        self._prune()
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {"updated": datetime.now().isoformat(timespec="seconds"),
                   "stories": self.entries}
        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=1, ensure_ascii=False)
            log.info("History now holds %d stories from the last %d days",
                     len(self.entries), config.history_days)
        except OSError as exc:
            log.warning("Could not save history (%s) — tomorrow may repeat today", exc)

    def filter_new(self, clusters: List[Cluster]) -> List[Cluster]:
        if not config.suppress_seen:
            return clusters
        fresh = [c for c in clusters if not self.seen(c)]
        dropped = len(clusters) - len(fresh)
        if dropped:
            log.info("Dropped %d stories already covered in a recent brief", dropped)
        return fresh
