from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.db import get_connection

MODULE_NAME = "momentum_multi_asset"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _calc_return(series: pd.Series, lookback: int) -> float | None:
    if len(series) <= lookback:
        return None
    now = series.iloc[-1]
    then = series.iloc[-(lookback + 1)]
    if then is None or then == 0 or np.isnan(then):
        return None
    return float(now / then - 1)


def run_momentum_snapshot() -> dict:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT ticker, date, close FROM price_history ORDER BY ticker, date",
        conn,
    )

    if df.empty:
        conn.close()
        return {"status": "empty", "message": "No price history available.", "rows": 0}

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "ticker", "close"]).sort_values(["ticker", "date"])

    snapshot_rows = []

    for ticker, grp in df.groupby("ticker"):
        prices = grp["close"].astype(float).reset_index(drop=True)
        mom_3m = _calc_return(prices, 63)
        mom_6m = _calc_return(prices, 126)
        mom_12m = _calc_return(prices, 252)

        # 12-1M = return from t-252 to t-21
        mom_12_1m = None
        if len(prices) > 252 and len(prices) > 21:
            older = prices.iloc[-253]
            minus1 = prices.iloc[-22]
            if older and older != 0 and not np.isnan(older):
                mom_12_1m = float(minus1 / older - 1)

        values = [v for v in [mom_3m, mom_6m, mom_12m, mom_12_1m] if v is not None]
        rank_value = float(np.mean(values)) if values else None

        abs_mom_ok = bool(mom_12m is not None and mom_12m > 0)

        if not values:
            traffic = "YELLOW"
        elif abs_mom_ok and (rank_value or 0) > 0:
            traffic = "GREEN"
        elif not abs_mom_ok:
            traffic = "RED"
        else:
            traffic = "YELLOW"

        as_of_date = grp["date"].max().date().isoformat()

        snapshot_rows.append(
            {
                "run_at": _utc_now(),
                "module_name": MODULE_NAME,
                "as_of_date": as_of_date,
                "ticker": ticker,
                "mom_3m": mom_3m,
                "mom_6m": mom_6m,
                "mom_12m": mom_12m,
                "mom_12_1m": mom_12_1m,
                "rank_value": rank_value,
                "abs_mom_ok": 1 if abs_mom_ok else 0,
                "traffic_light": traffic,
            }
        )

    snap_df = pd.DataFrame(snapshot_rows)
    snap_df["rank_order"] = snap_df["rank_value"].rank(ascending=False, method="dense")

    cur = conn.cursor()
    for _, row in snap_df.iterrows():
        cur.execute(
            """
            INSERT INTO signal_snapshots(
                run_at, module_name, as_of_date, ticker,
                mom_3m, mom_6m, mom_12m, mom_12_1m,
                rank_value, abs_mom_ok, traffic_light, extra_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["run_at"],
                row["module_name"],
                row["as_of_date"],
                row["ticker"],
                row["mom_3m"],
                row["mom_6m"],
                row["mom_12m"],
                row["mom_12_1m"],
                row["rank_value"],
                int(row["abs_mom_ok"]),
                row["traffic_light"],
                "{}",
            ),
        )

    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "rows": int(len(snap_df)),
        "as_of": str(snap_df["as_of_date"].max()),
    }
