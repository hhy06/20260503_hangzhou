"""Shared SKU selection strategies for production planning."""

from bisect import bisect_left


def pick_sku(
    eligible: list[str],
    decision_mode: int,
    stock: dict,
    window_demand: dict,
    roll_demand: dict,
    produced_so_far: dict,
    cum_demand_series: dict,
    shipment_days: list[int],
) -> str | None:
    if decision_mode == 1:
        best_val = -float('inf')
        best_sku = None
        for sku in eligible:
            need = window_demand.get(sku, 0) - produced_so_far.get(sku, 0)
            if need > best_val:
                best_val = need
                best_sku = sku
        return best_sku

    if decision_mode == 2:
        best_score = (float('inf'), float('inf'))
        best_sku = None
        for sku in eligible:
            nd = roll_demand.get(sku, 0)
            bucket = 0 if stock.get(sku, 0) < nd else 1
            score = (bucket, -nd)
            if score < best_score:
                best_score = score
                best_sku = sku
        return best_sku

    if decision_mode == 3:
        best_score = (float('inf'), float('inf'))
        best_sku = None
        for sku in eligible:
            nd = roll_demand.get(sku, 0)
            bucket = 0 if stock.get(sku, 0) < nd else 1
            coverage = stock.get(sku, 0) / max(nd, 1)
            score = (bucket, coverage)
            if score < best_score:
                best_score = score
                best_sku = sku
        return best_sku

    if decision_mode == 4:
        best_day = float('inf')
        best_deficit = 0
        best_sku = None
        for sku in eligible:
            cum = cum_demand_series[sku]
            produced = produced_so_far.get(sku, 0)
            idx = bisect_left(cum, produced + 1)
            if idx < len(cum):
                fail_day = shipment_days[idx]
                deficit = cum[idx] - produced
                if (fail_day < best_day
                        or (fail_day == best_day and deficit > best_deficit)):
                    best_day = fail_day
                    best_deficit = deficit
                    best_sku = sku
        if best_sku is None:
            best_val = -float('inf')
            for sku in eligible:
                need = window_demand.get(sku, 0) - produced_so_far.get(sku, 0)
                if need > best_val:
                    best_val = need
                    best_sku = sku
        return best_sku

    return None