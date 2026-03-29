import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import pandas as pd

from app.config import RAW_UPLOADS_DIR
from app.db import get_connection


@dataclass
class ImportResult:
    filename: str
    upload_id: int | None = None
    rows_total: int = 0
    rows_valid: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "ok"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_ticker(value: str) -> str:
    value = (value or "").strip().upper()
    if ":" in value:
        value = value.split(":", 1)[1]
    value = re.sub(r"[^A-Z0-9._\-]", "", value)
    return value


def _detect_delimiter(sample_text: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        if sample_text.count(";") > sample_text.count(","):
            return ";"
        return ","


def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = {c: c.strip().lower().replace(" ", "_") for c in df.columns}
    df = df.rename(columns=normalized)

    aliases = {
        "time": "date",
        "timestamp": "date",
        "datetime": "date",
        "symbol": "ticker",
        "ticker_symbol": "ticker",
        "last": "close",
        "vol": "volume",
    }
    for src, dst in aliases.items():
        if src in df.columns and dst not in df.columns:
            df = df.rename(columns={src: dst})
    return df


def _store_raw_file(filename: str, content: bytes) -> tuple[Path, str]:
    file_hash = hashlib.sha256(content).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_name = f"{stamp}_{uuid4().hex[:8]}_{filename}"
    path = RAW_UPLOADS_DIR / out_name
    path.write_bytes(content)
    return path, file_hash


def _load_dataframe(file_like: BinaryIO, filename: str) -> tuple[pd.DataFrame, bytes]:
    content = file_like.read()
    sample = content[:8192].decode("utf-8", errors="ignore")
    delimiter = _detect_delimiter(sample)

    try:
        df = pd.read_csv(
            pd.io.common.BytesIO(content),
            sep=delimiter,
            engine="python",
            encoding="utf-8-sig",
            on_bad_lines="skip",
        )
    except UnicodeDecodeError:
        df = pd.read_csv(
            pd.io.common.BytesIO(content),
            sep=delimiter,
            engine="python",
            encoding="latin1",
            on_bad_lines="skip",
        )

    if df.empty:
        raise ValueError(f"CSV vuoto o non leggibile: {filename}")

    return df, content


def _normalize_dataframe(df: pd.DataFrame, fallback_ticker: str | None) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    df = _standardize_columns(df)

    required_any = {"date", "close"}
    missing = [c for c in required_any if c not in df.columns]
    if missing:
        raise ValueError(f"Colonne obbligatorie mancanti: {', '.join(missing)}")

    if "ticker" not in df.columns:
        if fallback_ticker:
            df["ticker"] = fallback_ticker
            warnings.append(f"Ticker assente nel CSV: uso ticker da filename '{fallback_ticker}'.")
        else:
            raise ValueError("Colonna ticker/symbol mancante e impossibile inferire da filename.")

    df["ticker"] = df["ticker"].astype(str).map(_safe_ticker)
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(" ", "", regex=False)
                )
                # remove thousands separators only when clearly used as grouping
                df[col] = df[col].str.replace(r"(?<=\d)[.,](?=\d{3}\b)", "", regex=True)
                # convert decimal comma to decimal dot
                df[col] = df[col].str.replace(",", ".", regex=False)
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = pd.NA

    before = len(df)
    df = df.dropna(subset=["ticker", "date", "close"])  # remove invalid rows
    removed = before - len(df)
    if removed > 0:
        warnings.append(f"Rimosse {removed} righe invalide (date/close/ticker mancanti).")

    invalid_prices = (df["close"] <= 0).sum()
    if invalid_prices > 0:
        warnings.append(f"Trovate {invalid_prices} righe con close <= 0 (possibili anomalie).")

    df["date"] = df["date"].dt.date.astype(str)
    df = df.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")

    # Gap warnings (very simple heuristic)
    for ticker, grp in df.groupby("ticker"):
        dates = pd.to_datetime(grp["date"], utc=True).sort_values()
        if len(dates) > 1:
            max_gap = dates.diff().dt.days.fillna(0).max()
            if max_gap > 10:
                warnings.append(f"Gap temporale ampio rilevato per {ticker}: {int(max_gap)} giorni.")

    return df, warnings


def import_tradingview_csv(file_like: BinaryIO, filename: str) -> ImportResult:
    started_at = _utc_now()
    conn = get_connection()
    cur = conn.cursor()

    result = ImportResult(filename=filename)

    log_id = None
    try:
        df_raw, raw_bytes = _load_dataframe(file_like, filename)
        raw_path, file_hash = _store_raw_file(filename, raw_bytes)

        cur.execute(
            """
            INSERT INTO raw_uploads(filename, stored_path, file_hash, size_bytes, uploaded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (filename, str(raw_path), file_hash, len(raw_bytes), started_at),
        )
        upload_id = cur.lastrowid
        result.upload_id = upload_id

        cur.execute(
            """
            INSERT INTO import_logs(upload_id, started_at, status)
            VALUES (?, ?, 'processing')
            """,
            (upload_id, started_at),
        )
        log_id = cur.lastrowid

        fallback_ticker = _safe_ticker(Path(filename).stem)
        df_clean, warnings = _normalize_dataframe(df_raw, fallback_ticker=fallback_ticker)
        result.rows_total = len(df_raw)
        result.rows_valid = len(df_clean)
        result.warnings.extend(warnings)

        inserted = 0
        updated = 0
        now = _utc_now()

        for _, row in df_clean.iterrows():
            existing = cur.execute(
                "SELECT id FROM price_history WHERE ticker = ? AND date = ?",
                (row["ticker"], row["date"]),
            ).fetchone()

            if existing:
                updated += 1
                cur.execute(
                    """
                    UPDATE price_history
                    SET open = ?, high = ?, low = ?, close = ?, volume = ?, source_upload_id = ?, ingested_at = ?
                    WHERE ticker = ? AND date = ?
                    """,
                    (
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                        upload_id,
                        now,
                        row["ticker"],
                        row["date"],
                    ),
                )
            else:
                inserted += 1
                cur.execute(
                    """
                    INSERT INTO price_history(
                        ticker, date, open, high, low, close, volume, source_upload_id, ingested_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["ticker"],
                        row["date"],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                        upload_id,
                        now,
                    ),
                )

        result.rows_inserted = inserted
        result.rows_updated = updated
        if result.errors:
            result.status = "error"
        elif result.warnings:
            result.status = "warning"
        else:
            result.status = "ok"

    except Exception as exc:  # robust import error handling
        result.status = "error"
        result.errors.append(str(exc))

    finished_at = _utc_now()

    if log_id:
        cur.execute(
            """
            UPDATE import_logs
            SET finished_at = ?, status = ?, rows_total = ?, rows_valid = ?, rows_inserted = ?, rows_updated = ?,
                warnings_json = ?, errors_json = ?, notes = ?
            WHERE id = ?
            """,
            (
                finished_at,
                result.status,
                result.rows_total,
                result.rows_valid,
                result.rows_inserted,
                result.rows_updated,
                json.dumps(result.warnings, ensure_ascii=False),
                json.dumps(result.errors, ensure_ascii=False),
                "Import TradingView CSV",
                log_id,
            ),
        )

    conn.commit()
    conn.close()
    return result
