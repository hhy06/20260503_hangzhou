"""Generate demand.xlsx for scenario srw_hangzhou1.

Sources (from outside the repo):
    ~/transf/temp/masterkong_large_康师傅/key_sku_share_2025H2.csv
        -> 260 SKUs with 2025H2 production share (%)
    ~/transf/temp/masterkong_large_康师傅/daily_forecast_2026_2027.csv
        -> Daily total demand in CS across 2026-01-01 .. 2027-12-31

Rules:
    * Shares are renormalized to sum to 100% across the 260 SKUs.
    * Per-SKU daily quantity = daily_total_CS * (sku_share / 100), floor to int.
    * CS values are passed through as simulation units (no case-to-unit conversion).
    * Every SKU x every day row is emitted (including quantity=0 days).
    * time origin: t=0 corresponds to 2026-01-01 00:00 (start of day 0).
      Each demand row's start_time = day_index_minutes + SHIFT_OFFSET_MIN,
      where the shift offset represents an intra-day dispatch moment (e.g.
      480 min = 08:00).
    * Rows are sorted by start_time then by SKU id (strict non-decreasing
      start_time, as required by the demand loader).

Output:
    demand.xlsx, sheet=DEMAND, columns:
        sku | quantity | from_node | to_node | start_time
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SRC_DIR = Path.home() / "transf" / "temp" / "masterkong_large_康师傅"
SHARE_CSV = SRC_DIR / "key_sku_share_2025H2.csv"
FORECAST_CSV = SRC_DIR / "daily_forecast_2026_2027.csv"

OUT_PATH = Path(__file__).resolve().parents[0] / "demand.xlsx"

FROM_NODE = "fg_storage"
TO_NODE = "sink"

# Intra-day dispatch time (minutes after midnight). 480 = 08:00.
SHIFT_OFFSET_MIN = 480

# First day of simulation (t=0). Shares apply to every day in the forecast range.
T0 = pd.Timestamp("2026-01-01")


def load_sku_shares(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns={
        "物料": "sku",
        "product_name": "name",
        "占比%": "share_pct",
        "2025H2产量": "production",
    })
    df = df[["sku", "name", "share_pct", "production"]].copy()
    df["share_pct"] = pd.to_numeric(df["share_pct"], errors="coerce")
    df = df.dropna(subset=["share_pct"])
    total = df["share_pct"].sum()
    if total <= 0:
        raise ValueError(f"Sum of share_pct is non-positive: {total}")
    df["share_norm"] = df["share_pct"] / total  # sums to 1.0
    df = df.sort_values("sku").reset_index(drop=True)
    print(f"[SHARE] {len(df)} SKUs, raw sum={total:.4f}%, normalized sum={df['share_norm'].sum():.6f}")
    return df


def load_daily_forecast(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, thousands=",")
    df = df.rename(columns={
        "日期": "date",
        "当日分配(CS)": "daily_cs",
        "是否假日/周日": "note",
    })
    df["date"] = pd.to_datetime(df["date"])
    df["daily_cs"] = pd.to_numeric(df["daily_cs"], errors="coerce").fillna(0).astype("int64")
    df = df.sort_values("date").reset_index(drop=True)
    # Compute integer day offset from T0 (minutes), plus intra-day shift
    df["day_offset"] = (df["date"] - T0).dt.days.astype("int64")
    df["start_time"] = df["day_offset"] * 1440 + SHIFT_OFFSET_MIN
    print(f"[FORECAST] {len(df)} days: {df['date'].min().date()} -> {df['date'].max().date()}, "
          f"total CS = {df['daily_cs'].sum():,}, non-zero days = {(df['daily_cs'] > 0).sum()}")
    return df


def build_demand(shares: pd.DataFrame, forecast: pd.DataFrame) -> pd.DataFrame:
    sku_ids = shares["sku"].values
    shares_norm = shares["share_norm"].values.astype("float64")

    dates = forecast["date"].values
    start_times = forecast["start_time"].values.astype("int64")
    daily_cs = forecast["daily_cs"].values.astype("int64")

    # quantities[day_idx, sku_idx] = floor(daily_cs * share_norm)
    qty = np.floor(daily_cs[:, None] * shares_norm[None, :]).astype("int64")

    # Distribute the per-day remainder (daily_cs - row_sum) across the top-N SKUs
    # so that total emitted quantity equals the exact daily forecast total.
    daily_emitted = qty.sum(axis=1)
    remainder = daily_cs - daily_emitted  # shape (n_days,)
    top_idx = np.argsort(-shares_norm)  # SKUs ranked by share descending
    for d in range(qty.shape[0]):
        r = int(remainder[d])
        if r <= 0:
            continue
        for k in range(r):
            qty[d, top_idx[k]] += 1

    n_days, n_sku = qty.shape
    out = pd.DataFrame({
        "sku": np.tile(sku_ids, n_days),
        "quantity": qty.ravel(order="C"),  # day-major
        "from_node": FROM_NODE,
        "to_node": TO_NODE,
        "start_time": np.repeat(start_times, n_sku),
    })
    # Sort strictly by (start_time, sku) -> start_time is non-decreasing
    out = out.sort_values(["start_time", "sku"], kind="stable").reset_index(drop=True)
    return out


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Generate demand.xlsx")
    parser.add_argument("--days", type=int, default=30,
                       help="Generate only first N days (0 = all days)")
    parser.add_argument("--start-date", type=str, default="",
                       help="Skip days before this date (YYYY-MM-DD)")
    args = parser.parse_args()
    
    shares = load_sku_shares(SHARE_CSV)
    forecast = load_daily_forecast(FORECAST_CSV)
    
    if args.start_date:
        from_date = pd.Timestamp(args.start_date)
        forecast = forecast[forecast["date"] >= from_date].reset_index(drop=True)
        print(f"[FILTER] Skipping days before {args.start_date}")
    
    if args.days > 0:
        forecast = forecast.head(args.days).copy()
        print(f"[FILTER] Using first {args.days} days only")
    
    demand = build_demand(shares, forecast)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        demand.to_excel(writer, sheet_name="DEMAND", index=False)

    total_qty = int(demand["quantity"].sum())
    n_days = int(demand["start_time"].nunique())
    n_skus = int(demand["sku"].nunique())
    last_t = int(demand["start_time"].max())
    print(f"[DEMAND] wrote {OUT_PATH}")
    print(f"[DEMAND]   rows           = {len(demand):,}  ({n_skus} SKUs x {n_days} days)")
    print(f"[DEMAND]   total quantity = {total_qty:,} CS (simulation units)")
    print(f"[DEMAND]   start_time max = {last_t:,} min  ({last_t/1440:.1f} days)")


if __name__ == "__main__":
    main()
