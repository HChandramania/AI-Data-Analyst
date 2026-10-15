"""Single-process bounded TTL cache of validated successful query tables only."""

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from threading import RLock
from time import monotonic

import sqlglot
from sqlglot import exp

POLICY_VERSION = "sql-v1-results-v1"


def reusable_sql(sql):
    tree = sqlglot.parse_one(sql, read="duckdb")
    if tree.find(exp.Limit):
        return False
    return bool(tree.args.get("order") or (tree.find(exp.AggFunc) and not tree.args.get("group")))


def cache_key(owner, datasets, sql, sources):
    paths = {name: Path(path) for name, path in sources}
    dependencies = sorted(
        (
            str(d.id),
            d.version,
            d.content_hash,
            paths[f"dataset_{d.id.hex}"].stat().st_size,
            paths[f"dataset_{d.id.hex}"].stat().st_mtime_ns,
        )
        for d in datasets
    )
    canonical = sqlglot.parse_one(sql, read="duckdb").sql(dialect="duckdb", normalize=True, comments=False)
    payload = [str(owner), dependencies, canonical, POLICY_VERSION, 500]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class ExecutionCache:
    def __init__(self, ttl=900, max_entries=128, max_bytes=64 * 1024 * 1024, clock=monotonic):
        self.ttl, self.max_entries, self.max_bytes, self.clock = ttl, max_entries, max_bytes, clock
        self.entries = OrderedDict()
        self.size = 0
        self.lock = RLock()

    def _remove(self, key):
        self.size -= len(self.entries.pop(key)[1])

    def get(self, key):
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return None, "not_found_or_changed"
            if entry[0] <= self.clock():
                self._remove(key)
                return None, "expired"
            self.entries.move_to_end(key)
            return json.loads(entry[1]), "hit"

    def put(self, key, table, owner, datasets):
        # A truncated result is not a complete reusable execution artifact.
        if table["truncated"]:
            return
        raw = json.dumps(table, allow_nan=False).encode()
        if len(raw) > min(self.max_bytes, 1024 * 1024):
            return
        with self.lock:
            for old, entry in list(self.entries.items()):
                if entry[0] <= self.clock() or old == key:
                    self._remove(old)
            while self.entries and (len(self.entries) >= self.max_entries or self.size + len(raw) > self.max_bytes):
                self._remove(next(iter(self.entries)))
            self.entries[key] = (self.clock() + self.ttl, raw, str(owner), {str(d.id) for d in datasets})
            self.size += len(raw)

    def invalidate(self, owner, dataset_id):
        with self.lock:
            for key, entry in list(self.entries.items()):
                if entry[2] == str(owner) and str(dataset_id) in entry[3]:
                    self._remove(key)
