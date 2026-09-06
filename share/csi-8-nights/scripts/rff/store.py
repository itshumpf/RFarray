#!/usr/bin/env python3
"""SQLite backend: history of [source, CFO, SFO, timestamp, RSSI].

One row per accepted window observation. Source models (centroids) are
persisted as JSON blobs so a restart resumes with everything it has ever
learned. Default database lives at data/rff.db.
"""
import json
import os
import sqlite3

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "..", "data", "rff.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id         INTEGER PRIMARY KEY,
    mac        TEXT UNIQUE NOT NULL,
    name       TEXT,
    first_seen REAL,
    last_seen  REAL
);
CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY,
    source_id   INTEGER NOT NULL REFERENCES sources(id),
    node        TEXT,
    ts_pc       REAL,               -- unix seconds
    ts_esp_us   INTEGER,            -- node-local wifi clock
    rssi        REAL,
    cfo_hz      REAL,               -- raw residual CFO
    sfo_slope   REAL,               -- raw phase slope, rad/subcarrier
    cfo_ref_hz  REAL,               -- reference-corrected (NULL if no ref)
    sfo_ref     REAL,
    n_frames    INTEGER,
    quality     REAL,
    d2_self     REAL,               -- Mahalanobis² vs own centroid
    verdict     TEXT
);
CREATE INDEX IF NOT EXISTS idx_obs_source_ts
    ON observations (source_id, ts_pc);
CREATE TABLE IF NOT EXISTS models (
    source_id  INTEGER PRIMARY KEY REFERENCES sources(id),
    json       TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path=DEFAULT_DB):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        # one Store per thread, or guard externally; check_same_thread stays on
        self.db = sqlite3.connect(path)
        self.db.executescript(_SCHEMA)
        self._source_ids = {}          # mac -> id cache

    def source_id(self, mac, name=None, now=None):
        mac = mac.lower()
        if mac in self._source_ids:
            if now is not None:
                self.db.execute("UPDATE sources SET last_seen=? WHERE id=?",
                                (now, self._source_ids[mac]))
            return self._source_ids[mac]
        row = self.db.execute("SELECT id FROM sources WHERE mac=?",
                              (mac,)).fetchone()
        if row:
            sid = row[0]
        else:
            cur = self.db.execute(
                "INSERT INTO sources (mac, name, first_seen, last_seen) "
                "VALUES (?,?,?,?)", (mac, name, now, now))
            sid = cur.lastrowid
        self._source_ids[mac] = sid
        return sid

    def add_observation(self, source_id, node, ts_pc, obs,
                        d2_self=None, verdict=None):
        self.db.execute(
            "INSERT INTO observations (source_id, node, ts_pc, ts_esp_us, "
            "rssi, cfo_hz, sfo_slope, cfo_ref_hz, sfo_ref, n_frames, "
            "quality, d2_self, verdict) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (source_id, node, ts_pc, obs.get("ts_us"), obs.get("rssi"),
             obs.get("cfo"), obs.get("sfo"), obs.get("cfo_ref"),
             obs.get("sfo_ref"), obs.get("n_frames"), obs.get("quality"),
             d2_self, verdict))

    def save_model(self, source_id, model):
        self.db.execute(
            "INSERT INTO models (source_id, json) VALUES (?,?) "
            "ON CONFLICT(source_id) DO UPDATE SET json=excluded.json",
            (source_id, json.dumps(model.to_dict())))

    def load_models(self):
        from .discriminator import SourceModel
        out = {}
        for sid, blob in self.db.execute("SELECT source_id, json FROM models"):
            out[sid] = SourceModel.from_dict(json.loads(blob))
        return out

    def commit(self):
        self.db.commit()

    def close(self):
        self.db.commit()
        self.db.close()
