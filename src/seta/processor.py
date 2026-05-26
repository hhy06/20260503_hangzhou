"""SET4 — Simulation Event Trace Analyzer data processor.

Reads simulation output from a ``run_*/`` directory containing ``meta.json``
and ``sim.jsonl``, then transforms raw events into merged summaries and
job cards conforming to the SET4 data contract.

Usage::

    from seta.processor import process_run

    result = process_run("path/to/run_20250401_120000")
    # result is a JSON-serialisable dict
"""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
from typing import Any


__all__ = ["process_run"]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EDGE_PATTERN = re.compile(r"^E\(\s*(.+?)\s*->\s*(.+?)\s*\)$")
"""Regex to parse an edge name like ``E(source -> target)``."""

MERGEABLE_TYPES = frozenset({"production_output", "received", "debited"})
"""Event subtypes that can be merged when contiguous and group-key-identical."""

_FAILURE_TOLERANCE = 0.001
"""Absolute tolerance for uniform-interval detection."""


# ---------------------------------------------------------------------------
# Low-level I/O helpers
# ---------------------------------------------------------------------------


def _load_json(path: str) -> Any:
    """Load a JSON file and return the parsed object."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_jsonl(path: str) -> list[dict]:
    """Load a JSON-lines file, returning a list of parsed dicts."""
    records: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Edge-name helpers
# ---------------------------------------------------------------------------


def _parse_edge_name(name: str) -> tuple[str, str] | None:
    """If *name* looks like ``E(a -> b)`` return ``(a, b)``, else ``None``."""
    m = _EDGE_PATTERN.match(name)
    if m:
        return m.group(1), m.group(2)
    return None


def _is_edge(name: str) -> bool:
    """Return ``True`` if *name* is an edge identifier (``E(...)``)."""
    return name.startswith("E(") and name.endswith(")")


# ---------------------------------------------------------------------------
# Scenario-module resolution
# ---------------------------------------------------------------------------


def _ensure_workspace_on_path() -> None:
    """Ensure the current working directory is on ``sys.path``."""
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)


def _resolve_scenario_module(
    meta: dict,
    scenario_module: Any = None,
) -> Any:
    """Return a module that exports ``NODES``.

    If *scenario_module* is given it is returned directly.
    Otherwise the module is auto-imported from ``meta["scenario"]``
    (e.g. ``"scenario.t_hangzhou1"`` → ``scenario.t_hangzhou1.plant_topology``).
    Returns ``None`` when neither source is available.
    """
    if scenario_module is not None:
        return scenario_module

    scenario_name: str = meta.get("scenario", "")
    if not scenario_name:
        return None

    _ensure_workspace_on_path()

    candidates = [
        f"{scenario_name}.plant_topology",
        scenario_name,
    ]
    for candidate in candidates:
        try:
            mod = importlib.import_module(candidate)
            if hasattr(mod, "NODES"):
                return mod
        except (ImportError, ModuleNotFoundError):
            continue

    return None


# ---------------------------------------------------------------------------
# Display-name / node-type resolution
# ---------------------------------------------------------------------------


def _get_display_name(node_id: str, scenario_mod: Any) -> str:
    """Resolve the display name for *node_id* via the scenario ``NODES`` dict."""
    if scenario_mod is not None and hasattr(scenario_mod, "NODES"):
        cfg = scenario_mod.NODES.get(node_id)
        if cfg and "display_name" in cfg:
            return cfg["display_name"]
    return node_id


def _get_node_type(node_id: str, scenario_mod: Any) -> str:
    """Resolve the type string for *node_id*."""
    if _is_edge(node_id):
        return "edge"
    if scenario_mod is not None and hasattr(scenario_mod, "NODES"):
        cfg = scenario_mod.NODES.get(node_id)
        if cfg and "type" in cfg:
            return cfg["type"]
    return "warehouse"


# ---------------------------------------------------------------------------
# Merge algorithm — group key
# ---------------------------------------------------------------------------


def _get_merge_group_key(event: dict, etype: str) -> tuple | None:
    """Compute the merge-group key for a mergeable *event*.

    Returns ``None`` for non-mergeable types (caller should have checked).
    """
    node = event.get("node", "")
    if etype == "production_output":
        return (node, event.get("order_id"), event.get("sku"), event.get("destination"))
    if etype == "received":
        return (node, event.get("sku"), event.get("source"))
    if etype == "debited":
        return (node, event.get("sku"))
    return None


# ---------------------------------------------------------------------------
# Display-string builders
# ---------------------------------------------------------------------------


def _event_display(
    etype: str,
    first: dict,
    count: int,
    t0: float,
    tn: float,
    interval: float | None,
    qty: int,
    total: int,
) -> str:
    """Build the human-readable ``display`` string for an event or merged group."""
    sku = first.get("sku", "")

    # -- Merged multi-event display (mergeable types only, count > 1) ----------
    if etype in MERGEABLE_TYPES and count > 1:
        range_str = f"t={t0}→{int(tn)}" if tn == int(tn) else f"t={t0}→{tn}"
        interval_str = ""
        if interval is not None:
            iv = int(interval) if interval == int(interval) else interval
            interval_str = f", every {iv}t"

        if etype == "production_output":
            dest = first.get("destination", "")
            return (
                f"production_output: {count} steps × {qty} units = {total} total, "
                f"{range_str}{interval_str} → {dest}"
            )
        if etype == "received":
            source = first.get("source", "")
            return (
                f"received: {count} arrivals × {qty} units = {total} total, "
                f"{range_str}{interval_str} from {source}"
            )
        if etype == "debited":
            return (
                f"debited: {count} departures × {qty} units = {total} total, "
                f"{range_str}{interval_str}"
            )

    # -- Single-event display --------------------------------------------------
    t = first.get("time", 0.0)

    if etype == "production_output":
        dest = first.get("destination", "")
        return f"production_output: {sku} × {qty} → {dest}"

    if etype == "received":
        source = first.get("source", "")
        return f"received: {qty} units of {sku} at t={t} from {source}"

    if etype == "debited":
        return f"debited: {qty} units of {sku} at t={t}"

    if etype == "production_started":
        return f"production_started: {sku} × {qty}"

    if etype == "production_completed":
        return f"production_completed: {sku} × {qty}"

    if etype == "materials_consumed":
        inputs = first.get("inputs", {})
        items = ", ".join(f"{k}: {v}" for k, v in inputs.items())
        return f"materials_consumed: {sku} × {qty} | inputs: {{{items}}}"

    if etype == "production_failed":
        reason = first.get("reason", "")
        req = first.get("required", {})
        ava = first.get("available", {})
        req_s = ", ".join(f"{k}: {v}" for k, v in req.items())
        ava_s = ", ".join(f"{k}: {v}" for k, v in ava.items())
        return (
            f"production_failed: {sku} — {reason} "
            f"(required: {{{req_s}}}, available: {{{ava_s}}})"
        )

    if etype == "transport_order_added":
        oid = first.get("order_id", "")
        from_n = first.get("from", "")
        to_n = first.get("to", "")
        return f"transport_order_added: #{oid} {sku} × {qty} from {from_n} → {to_n}"

    if etype == "transport_started":
        oid = first.get("order_id", "")
        from_n = first.get("from", "")
        to_n = first.get("to", "")
        pallets = first.get("pallets", 0)
        return (
            f"transport_started: #{oid} {sku} × {qty} from {from_n} → {to_n} "
            f"({pallets} pallets)"
        )

    if etype == "transport_completed":
        oid = first.get("order_id", "")
        from_n = first.get("from", "")
        to_n = first.get("to", "")
        return f"transport_completed: #{oid} {sku} × {qty} from {from_n} → {to_n}"

    if etype == "capacity_warning":
        pallets = first.get("pallets", 0)
        max_p = first.get("max_pallets", 0)
        return f"capacity_warning: {pallets} pallets (max {max_p})"

    # Fallback for any unforeseen type
    return f"{etype}: {sku} × {qty} at t={t}"


# ---------------------------------------------------------------------------
# Merged-event construction
# ---------------------------------------------------------------------------


def _build_merged_event_dict(etype: str, group: list[dict]) -> dict:
    """Turn a group of identical mergeable events into a single merged dict.

    Works for groups of size 1 as well.
    """
    count = len(group)
    first = group[0]
    last = group[-1]
    t0 = first.get("time", 0.0)
    tn = last.get("time", 0.0)
    qty = first.get("quantity", 0)
    total = qty * count

    # -- Interval detection ----------------------------------------------------
    interval: float | None = None
    if count > 1:
        raw_interval = (tn - t0) / (count - 1)
        rounded = round(raw_interval, 6)
        expected_total = rounded * (count - 1)
        if abs(expected_total - (tn - t0)) <= _FAILURE_TOLERANCE:
            interval = raw_interval  # uniform spacing

    duration = tn - t0 if count > 1 else None
    display = _event_display(etype, first, count, t0, tn, interval, qty, total)

    # -- Type-specific fields --------------------------------------------------
    sku = first.get("sku")
    order_id = first.get("order_id")

    dest = first.get("destination") if etype == "production_output" else None
    source = first.get("source") if etype == "received" else None
    inputs = first.get("inputs") if etype == "materials_consumed" else None
    reason = first.get("reason") if etype == "production_failed" else None
    required = first.get("required") if etype == "production_failed" else None
    available = first.get("available") if etype == "production_failed" else None
    pallets = first.get("pallets") if etype == "capacity_warning" else None
    max_pallets = first.get("max_pallets") if etype == "capacity_warning" else None

    from_node: str | None = None
    to_node: str | None = None
    pallets_count: int | None = None
    if etype in ("transport_order_added", "transport_started", "transport_completed"):
        from_node = first.get("from")
        to_node = first.get("to")
    if etype == "transport_started":
        pallets_count = first.get("pallets")

    return {
        "type": etype,
        "time": t0,
        "end_time": tn if count > 1 else None,
        "count": count,
        "quantity": qty,
        "total": total,
        "interval": interval,
        "duration": duration,
        "display": display,
        "sku": sku,
        "order_id": order_id,
        "destination": dest,
        "source": source,
        "inputs": inputs,
        "reason": reason,
        "required": required,
        "available": available,
        "pallets": pallets,
        "max_pallets": max_pallets,
        "from_node": from_node,
        "to_node": to_node,
        "pallets_count": pallets_count,
        "raw": first,
    }


def _build_single_event_dict(event: dict) -> dict:
    """Wrap a non-mergeable event in the standard merged-event shape (count=1)."""
    etype = event.get("type", "unknown")
    t = event.get("time", 0.0)
    qty = event.get("quantity", 0)
    sku = event.get("sku", "")
    display = _event_display(etype, event, 1, t, t, None, qty, qty)

    order_id = event.get("order_id")
    dest = event.get("destination") if etype == "production_output" else None
    source = event.get("source") if etype == "received" else None
    inputs = event.get("inputs") if etype == "materials_consumed" else None
    reason = event.get("reason") if etype == "production_failed" else None
    required = event.get("required") if etype == "production_failed" else None
    available = event.get("available") if etype == "production_failed" else None
    pallets = event.get("pallets") if etype == "capacity_warning" else None
    max_pallets = event.get("max_pallets") if etype == "capacity_warning" else None

    from_node: str | None = None
    to_node: str | None = None
    pallets_count: int | None = None
    if etype in ("transport_order_added", "transport_started", "transport_completed"):
        from_node = event.get("from")
        to_node = event.get("to")
    if etype == "transport_started":
        pallets_count = event.get("pallets")

    return {
        "type": etype,
        "time": t,
        "end_time": None,
        "count": 1,
        "quantity": qty,
        "total": qty,
        "interval": None,
        "duration": None,
        "display": display,
        "sku": sku,
        "order_id": order_id,
        "destination": dest,
        "source": source,
        "inputs": inputs,
        "reason": reason,
        "required": required,
        "available": available,
        "pallets": pallets,
        "max_pallets": max_pallets,
        "from_node": from_node,
        "to_node": to_node,
        "pallets_count": pallets_count,
        "raw": event,
    }


def _merge_node_events(events: list[dict]) -> list[dict]:
    """Merge contiguous mergeable events for a single node's event list.

    *events* must already be sorted by time.
    """
    if not events:
        return []

    result: list[dict] = []
    i = 0
    n = len(events)

    while i < n:
        ev = events[i]
        etype: str = ev.get("type", "")

        if etype in MERGEABLE_TYPES:
            # Start / extend a merge group
            group_key = _get_merge_group_key(ev, etype)
            group: list[dict] = [ev]
            j = i + 1
            while j < n:
                nxt = events[j]
                nxt_type = nxt.get("type", "")
                if nxt_type != etype:
                    break
                nxt_key = _get_merge_group_key(nxt, nxt_type)
                if nxt_key != group_key:
                    break
                group.append(nxt)
                j += 1

            result.append(_build_merged_event_dict(etype, group))
            i = j
        else:
            # Non-mergeable → single event dict
            result.append(_build_single_event_dict(ev))
            i += 1

    return result


# ---------------------------------------------------------------------------
# Job-card builders
# ---------------------------------------------------------------------------


def _build_display_summary(card: dict) -> str:
    """One-line human-readable summary for an order card."""
    oid = card["order_id"]
    sku = card["sku"]
    qty = card["quantity"]
    status = card["status"]

    start = card.get("actual_start")
    end = card.get("actual_end")
    dur = card.get("duration")

    if start is not None and end is not None:
        s = int(start) if start == int(start) else start
        e = int(end) if end == int(end) else end
        d = int(dur) if (dur is not None and dur == int(dur)) else dur
        time_str = f"t={s}→{e} ({d}t)"
    elif start is not None:
        s = int(start) if start == int(start) else start
        time_str = f"t={s}→?"
    else:
        time_str = "t=?"

    if card["order_type"] == "production":
        node = card.get("node_name") or "?"
        return f"#{oid} | {sku} × {qty} | {node} | {time_str} | {status}"

    # transport
    from_n = card.get("from_node") or "?"
    to_n = card.get("to_node") or "?"
    return f"#{oid} | {sku} × {qty} | {from_n} → {to_n} | {time_str} | {status}"


def _build_job_cards(
    event_records: list[dict],
    order_records: list[dict],
    merged_by_node: dict[str, list[dict]],
) -> dict[int, dict]:
    """Build order/job-card dicts from ``order_issued`` records and events.

    Parameters
    ----------
    event_records : list[dict]
        Raw ``event``-type records (with ``_type="event"``).
    order_records : list[dict]
        Raw ``order_issued`` records.
    merged_by_node : dict[str, list[dict]]
        Merged events keyed by node/edge name.

    Returns
    -------
    dict[int, dict]
        Order cards keyed by ``order_id``.
    """
    # Index raw events by order_id
    raw_by_oid: dict[int, list[dict]] = {}
    for ev in event_records:
        oid = ev.get("order_id")
        if oid is not None:
            raw_by_oid.setdefault(oid, []).append(ev)

    # Index merged events by order_id (across all nodes)
    merged_by_oid: dict[int, list[dict]] = {}
    for m_events in merged_by_node.values():
        for me in m_events:
            oid = me.get("order_id")
            if oid is not None:
                merged_by_oid.setdefault(oid, []).append(me)

    orders: dict[int, dict] = {}

    for rec in order_records:
        oid: int = rec.get("order_id", 0)
        otype: str = rec.get("order_type", "production")
        sku: str = rec.get("sku", "")
        qty: int = rec.get("quantity", 0)

        raw_evs = raw_by_oid.get(oid, [])
        merged_evs = merged_by_oid.get(oid, [])

        # ---- Compute actual_start / actual_end / status -------------------
        actual_start: float | None = None
        actual_end: float | None = None

        if otype == "production":
            for ev in raw_evs:
                et = ev.get("type")
                if et == "production_started":
                    t = ev.get("time", 0.0)
                    if actual_start is None or t < actual_start:
                        actual_start = t
                elif et in ("production_completed", "production_failed"):
                    t = ev.get("time", 0.0)
                    if actual_end is None or t > actual_end:
                        actual_end = t

            has_completed = any(
                e.get("type") == "production_completed" for e in raw_evs
            )
            has_failed = any(
                e.get("type") == "production_failed" for e in raw_evs
            )
            status = (
                "completed"
                if has_completed
                else ("failed" if has_failed else "in_progress")
            )

            card: dict = {
                "order_id": oid,
                "order_type": otype,
                "sku": sku,
                "quantity": qty,
                "node_name": rec.get("node_name"),
                "activate_time": rec.get("activate_time"),
                "expect_time": rec.get("expect_time"),
                "from_node": None,
                "to_node": None,
                "start_time": None,
            }

        else:  # transport
            for ev in raw_evs:
                et = ev.get("type")
                if et == "transport_started":
                    t = ev.get("time", 0.0)
                    if actual_start is None or t < actual_start:
                        actual_start = t
                elif et == "transport_completed":
                    t = ev.get("time", 0.0)
                    if actual_end is None or t > actual_end:
                        actual_end = t

            has_completed = any(
                e.get("type") == "transport_completed" for e in raw_evs
            )
            status = "completed" if has_completed else "in_progress"

            card = {
                "order_id": oid,
                "order_type": otype,
                "sku": sku,
                "quantity": qty,
                "node_name": None,
                "activate_time": None,
                "expect_time": rec.get("expect_time"),
                "from_node": rec.get("from_node"),
                "to_node": rec.get("to_node"),
                "start_time": rec.get("start_time"),
            }

        duration = (
            (actual_end - actual_start)
            if (actual_start is not None and actual_end is not None)
            else None
        )

        card["actual_start"] = actual_start
        card["actual_end"] = actual_end
        card["duration"] = duration
        card["status"] = status

        # ---- Nodes involved (unique, in order of first appearance) --------
        nodes_involved: list[str] = []
        for ev in raw_evs:
            n = ev.get("node", "")
            if n and n not in nodes_involved:
                nodes_involved.append(n)

        card["events"] = merged_evs
        card["nodes_involved"] = nodes_involved
        card["display_summary"] = _build_display_summary(card)
        orders[oid] = card

    return orders


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def process_run(
    run_dir: str,
    scenario_module: Any = None,
) -> dict:
    """Process a simulation run directory and return the full data dict.

    Parameters
    ----------
    run_dir : str
        Path to the ``run_*`` directory containing ``meta.json`` and
        ``sim.jsonl``.
    scenario_module : module, optional
        A Python module that exports ``NODES`` (plant topology).  If
        ``None``, the module is auto-imported from ``meta.json``'s
        ``scenario`` field (e.g. ``"scenario.t_hangzhou1"`` →
        ``scenario.t_hangzhou1.plant_topology``).

    Returns
    -------
    dict
        JSON-serialisable structure conforming to the SET4 data contract:
        ``{"meta", "nodes", "edges", "orders", "node_list", "edge_list"}``.

    Raises
    ------
    FileNotFoundError
        If ``meta.json`` or ``sim.jsonl`` is missing.
    json.JSONDecodeError
        If either file is malformed.
    """
    # ==================================================================
    # 1.  Load raw data
    # ==================================================================
    meta = _load_json(os.path.join(run_dir, "meta.json"))
    raw_records = _load_jsonl(os.path.join(run_dir, "sim.jsonl"))

    init_state_records: list[dict] = []
    order_records: list[dict] = []
    event_records: list[dict] = []

    for rec in raw_records:
        rec_type = rec.get("_type", "")
        if rec_type == "init_state":
            init_state_records.append(rec)
        elif rec_type == "order_issued":
            order_records.append(rec)
        elif rec_type == "event":
            event_records.append(rec)

    # ==================================================================
    # 2.  Resolve scenario module (for display names)
    # ==================================================================
    scenario_mod = _resolve_scenario_module(meta, scenario_module)

    # Build reverse map: display_name -> node_id
    _display_to_id: dict[str, str] = {}
    if scenario_mod is not None and hasattr(scenario_mod, "NODES"):
        for nid, cfg in scenario_mod.NODES.items():
            dn = cfg.get("display_name", "")
            if dn:
                _display_to_id[dn] = nid

    def _norm(name: str) -> str:
        """Map a Chinese display name back to its English node ID."""
        if _is_edge(name):
            return name
        return _display_to_id.get(name, name)

    # 3.  Normalise node names & group events by node
    for rec in init_state_records:
        rec["node"] = _norm(rec.get("node", ""))
    for rec in event_records:
        rec["node"] = _norm(rec.get("node", ""))
    for rec in order_records:
        if "node_name" in rec:
            rec["node_name"] = _norm(rec.get("node_name", ""))
        if "from_node" in rec:
            rec["from_node"] = _norm(rec.get("from_node", ""))
        if "to_node" in rec:
            rec["to_node"] = _norm(rec.get("to_node", ""))
    node_events: dict[str, list[dict]] = {}
    for ev in event_records:
        node_events.setdefault(ev.get("node", ""), []).append(ev)

    for node in node_events:
        node_events[node].sort(key=lambda e: e.get("time", 0.0))

    merged_by_node: dict[str, list[dict]] = {
        node: _merge_node_events(evs) for node, evs in node_events.items()
    }

    # ==================================================================
    # 4.  Build nodes / edges dicts
    # ==================================================================
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    # Discover all node names from events and init_state
    all_node_names: set[str] = set(node_events.keys())
    for rec in init_state_records:
        all_node_names.add(rec.get("node", ""))
    # Also include topology nodes that may have no events (e.g. source)
    if scenario_mod is not None and hasattr(scenario_mod, "NODES"):
        all_node_names.update(scenario_mod.NODES.keys())

    for name in sorted(all_node_names):
        if not name:
            continue
        edge_parts = _parse_edge_name(name)
        if edge_parts:
            src, dst = edge_parts
            src_disp = _get_display_name(src, scenario_mod)
            dst_disp = _get_display_name(dst, scenario_mod)
            edges[name] = {
                "id": name,
                "display_name": f"E({src_disp} → {dst_disp})",
                "from": src,
                "to": dst,
                "from_display": src_disp,
                "to_display": dst_disp,
                "events": merged_by_node.get(name, []),
                "jobs": [],
            }
        else:
            nodes[name] = {
                "id": name,
                "display_name": _get_display_name(name, scenario_mod),
                "type": _get_node_type(name, scenario_mod),
                "init_inventory": {},
                "events": merged_by_node.get(name, []),
                "jobs": [],
            }

    # Populate initial inventories
    for rec in init_state_records:
        n = rec.get("node", "")
        if n in nodes:
            nodes[n]["init_inventory"][rec.get("sku", "")] = rec.get("quantity", 0)

    # Populate job references (order IDs) on nodes / edges
    for ev in event_records:
        n = ev.get("node", "")
        oid = ev.get("order_id")
        if oid is None:
            continue
        target = nodes.get(n) or edges.get(n)
        if target is not None and oid not in target["jobs"]:
            target["jobs"].append(oid)

    # ==================================================================
    # 5.  Build order / job cards
    # ==================================================================
    orders = _build_job_cards(event_records, order_records, merged_by_node)

    # ==================================================================
    # 6.  Build node_list / edge_list
    # ==================================================================
    node_list = sorted(
        [
            {"id": n["id"], "display_name": n["display_name"], "type": n["type"]}
            for n in nodes.values()
        ],
        key=lambda x: x["id"],
    )
    edge_list = sorted(
        [
            {
                "id": e["id"],
                "display_name": e["display_name"],
                "from": e["from"],
                "to": e["to"],
            }
            for e in edges.values()
        ],
        key=lambda x: x["id"],
    )

    # ==================================================================
    # 7.  Assemble result
    # ==================================================================
    return {
        "meta": {
            "scenario": meta.get("scenario", ""),
            "sim_duration": meta.get("sim_duration", 0.0),
            "management_type": meta.get("management_type", ""),
            "decision_interval": meta.get("decision_interval", 0.0),
            "num_nodes": meta.get("num_nodes", len(nodes)),
            "num_edges": meta.get("num_edges", len(edges)),
            "event_count": meta.get("event_count", len(event_records)),
            "order_count": meta.get("order_count", len(order_records)),
        },
        "nodes": nodes,
        "edges": edges,
        "orders": orders,
        "node_list": node_list,
        "edge_list": edge_list,
    }
