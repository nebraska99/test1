import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DB_PATH


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS import_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            rows_total INTEGER DEFAULT 0,
            rows_valid INTEGER DEFAULT 0,
            rows_inserted INTEGER DEFAULT 0,
            rows_updated INTEGER DEFAULT 0,
            warnings_json TEXT DEFAULT '[]',
            errors_json TEXT DEFAULT '[]',
            notes TEXT DEFAULT '',
            FOREIGN KEY (upload_id) REFERENCES raw_uploads(id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL NOT NULL,
            volume REAL,
            source_upload_id INTEGER,
            ingested_at TEXT NOT NULL,
            UNIQUE(ticker, date),
            FOREIGN KEY (source_upload_id) REFERENCES raw_uploads(id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS signal_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT NOT NULL,
            module_name TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            mom_3m REAL,
            mom_6m REAL,
            mom_12m REAL,
            mom_12_1m REAL,
            rank_value REAL,
            abs_mom_ok INTEGER NOT NULL,
            traffic_light TEXT NOT NULL,
            extra_json TEXT DEFAULT '{}'
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS module_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_name TEXT NOT NULL UNIQUE,
            config_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio_satellites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'inactive',
            notes TEXT DEFAULT '',
            metrics_json TEXT DEFAULT '{}',
            last_updated TEXT NOT NULL
        );
        """
    )

    conn.commit()
    conn.close()


def seed_defaults() -> None:
    conn = get_connection()
    cur = conn.cursor()

    modules = {
        "momentum_multi_asset": {"enabled": True, "min_history_rows": 260},
        "regime_detector": {"enabled": False},
        "dual_momentum_classica": {"enabled": False},
        "beverage_basket": {"enabled": False},
        "tech_league": {"enabled": False},
        "random_asset_league": {"enabled": False},
        "portfolio_satellite_monitor": {"enabled": False},
        "kpo_standard": {"enabled": False},
        "art_of_execution_simple": {"enabled": False},
    }

    now = utc_now_iso()
    for module_name, cfg in modules.items():
        cur.execute(
            """
            INSERT INTO module_configs(module_name, config_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(module_name) DO NOTHING;
            """,
            (module_name, json.dumps(cfg), now),
        )

    satellites = ["Alluvial satellite", "Navarro satellite"]
    for satellite_name in satellites:
        cur.execute(
            """
            INSERT INTO portfolio_satellites(name, status, notes, metrics_json, last_updated)
            VALUES(?, 'placeholder', 'Placeholder for V1', '{}', ?)
            ON CONFLICT(name) DO NOTHING;
            """,
            (satellite_name, now),
        )

    conn.commit()
    conn.close()


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    conn = get_connection()
    row = conn.execute(query, params).fetchone()
    conn.close()
    return row


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows
