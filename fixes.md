# Fixes Applied — May 2026

Nine bugs found by a parallel codebase audit (4 exploration agents) covering
all source modules.  Each fix is documented below with the **original code**,
**what was wrong**, and **what it was changed to**.

---

## Fix 1 — `scenario_builder.py:27` — `getattr()` on a `dict` always returns default

**File:** `scenario/hangzhou0b/scenario_builder.py`

### Original code

```python
mgmt_type = getattr(config.MANAGEMENT, "type", "static_order") if isinstance(config.MANAGEMENT, dict) else "static_order"
```

### What was wrong

`config.MANAGEMENT` is a `dict` (`{"type": "trace", "decision_interval": 10.0}`).
`getattr()` is a Python built-in that works on **objects** (looking up attributes
by name), **not** on dicts.  When called on a dict, Python raises
`AttributeError` and `getattr` returns the default `"static_order"` **every time**.

This means the management type was always detected as `"static_order"`, causing
the builder to pre-load all `PRODUCTION_JOBS` into production nodes (lines 28-32).
Then `create_management()` separately correctly read `"trace"` and
`TraceManagement` generated its **own** orders via pre-computation.  The result:
every noodle line received **two sets** of FG production orders — the static
pre-loads **plus** the trace-generated orders — congesting the queues.

### Intermediate (flawed) fix — applied first, then corrected

```python
mgmt_type = config.MANAGEMENT.get("type", "static_order") if isinstance(config.MANAGEMENT, dict) else "static_order"
```

This fixed the `getattr` → `KeyError` symptom but kept unnecessary defensive
code: an `isinstance` guard and a fallback default.  Both are noise because
`config.MANAGEMENT` is **always** a dict and **always** has a `"type"` key in
every scenario.  The proper fallback location is `builder.create_management()`
(line 126-128), not the scenario builder.

### Final (correct) fix

```python
mgmt_type = config.MANAGEMENT["type"]
```

### Why this is correct

- `config.MANAGEMENT` is always a `dict` — both `hangzhou0b` and `example`
  scenarios define it as `MANAGEMENT = {...}`.  The `isinstance` check is dead
  code.
- The dict always has a `"type"` key — both scenarios include it.  The
  fallback `"static_order"` is dead code that masks configuration errors.
- If someone accidentally omits `"type"`, a loud `KeyError` is **better** than
  silently defaulting to `"static_order"` — fail fast, fail obvious.
- The authoritative fallback lives in `builder.py:127`
  (`mgmt_cfg.get("type", "static_order")`), which is the single point of truth
  for default management type.  The scenario builder should not duplicate it.

---

## Fix 2 — `warehouse_node.py:134` — `available_pallets()` crashes on `None`

**File:** `src/infrastructure/warehouse_node.py`

### Original code

```python
def available_pallets(self) -> int | float:
    """Remaining pallet capacity (``inf`` for non-WAREHOUSE)."""
    if self.role != NodeRole.WAREHOUSE:
        return float("inf")
    return self.node_max_pallets - self.current_pallets()  # type: ignore[operator]
```

### What was wrong

`WarehouseNode.__init__` accepts `max_pallets: int | None = None`.  When a
WAREHOUSE node is constructed without specifying `max_pallets` (or when the
builder passes `cfg.get("max_pallets")` which returns `None`),
`self.node_max_pallets` is **`None`**.  The subtraction `None - int` raises
`TypeError: unsupported operand type(s) for -: 'NoneType' and 'int'` at
simulation runtime.

The `# type: ignore[operator]` suppressed the type checker but did nothing to
prevent the crash.

### Fixed code

```python
def available_pallets(self) -> int | float:
    """Remaining pallet capacity (``inf`` for non-WAREHOUSE)."""
    if self.role != NodeRole.WAREHOUSE:
        return float("inf")
    if self.node_max_pallets is None:
        return float("inf")
    return self.node_max_pallets - self.current_pallets()
```

### Why it works

When `max_pallets` is `None` (meaning unlimited / unconfigured), we return
`float("inf")` — the same sentinel used for SOURCE/SINK nodes.  This is
consistent with `check_capacity()` (line 138 in the original) which already
guards with `self.node_max_pallets is not None` before doing anything.

---

## Fix 3 — `trace_management.py` — missing `self.log` and silent order drops

**File:** `src/management/trace_management.py`

### 3a — Missing `self.log` attribute

#### Original code (lines 87-93)

```python
        # round-robin counters per SKU
        self._rr_counter: dict[str, int] = {}
        self._next_job_id: int = 1

        super().__init__(...)
```

#### What was wrong

`SafeStockManagement`, `StaticOrderManagement`, and every other management
subclass initialises `self.log = []` in their `__init__`.  `TraceManagement`
did not.  This meant:

- `_execute_decision` could not log dropped orders (would get `AttributeError`)
- Any code iterating `management.log` would silently miss trace management
  events
- Debugging supply chain issues was harder because trace decisions were
  invisible in the audit trail

#### Fixed code

```python
        self._rr_counter: dict[str, int] = {}
        self._next_job_id: int = 1
        self.log: list[dict] = []

        super().__init__(...)
```

---

### 3b — `_add_transport` silently skips missing edges

#### Original code (lines 121-123)

```python
        edge = self.find_edge(from_node, to_node)
        if edge is None:
            return
```

#### What was wrong

When a transport order targets a non-existent edge (e.g. due to a topology
mismatch or a routing bug), the order was silently dropped.  There was no log
entry to indicate the problem, making it look like the transport was simply
"not needed" when in reality it was being ordered into a void.

#### Fixed code

```python
        edge = self.find_edge(from_node, to_node)
        if edge is None:
            if hasattr(self, "log"):
                self.log.append({
                    "time": self.env.now(),
                    "type": "transport_order_dropped",
                    "sku": sku,
                    "quantity": quantity,
                    "from": from_node,
                    "to": to_node,
                    "reason": "no_edge",
                })
            return
```

---

### 3c — `_execute_decision` swallows missing edges and nodes

#### Original code (lines 404-413)

```python
    def _execute_decision(self, decision: Decision) -> None:
        for order in decision.transport_orders:
            edge = self.find_edge(order.from_node, order.to_node)
            if edge is not None:
                edge.add_transport_order(order)
        for order in decision.production_orders:
            node = self._production_nodes.get(order.node_name)
            if node is not None:
                node.add_production_order(order)
```

#### What was wrong

Between `make_decisions` (where the edge/node lookup happened) and
`_execute_decision` (where the order is registered), the simulation could
theoretically remove nodes or edges.  Even without that edge-case, if a
bug in `make_decisions` produced an order for an invalid endpoint, the order
was silently lost — no log, no warning, no trace.

#### Fixed code

```python
    def _execute_decision(self, decision: Decision) -> None:
        for order in decision.transport_orders:
            edge = self.find_edge(order.from_node, order.to_node)
            if edge is not None:
                edge.add_transport_order(order)
            else:
                self.log.append({
                    "time": self.env.now(),
                    "type": "transport_order_dropped",
                    "sku": order.sku,
                    "quantity": order.quantity,
                    "from": order.from_node,
                    "to": order.to_node,
                    "reason": "edge_removed_between_decision_and_execution",
                })
        for order in decision.production_orders:
            node = self._production_nodes.get(order.node_name)
            if node is not None:
                node.add_production_order(order)
            else:
                self.log.append({
                    "time": self.env.now(),
                    "type": "production_order_dropped",
                    "sku": order.sku,
                    "quantity": order.quantity,
                    "node": order.node_name,
                    "reason": "production_node_not_found",
                })
```

---

## Fix 4 + 5 — Bare key access on `conversion_factors` → `KeyError`

The same bug pattern existed in 3 files, 5 call sites total.

### What was wrong

Code accessed `conversion_factors` dict with square-bracket key lookup
(`dict[key]`) instead of `dict.get(key, default)`.  If a SKU was missing
from `PALLET_SIZE` (which any SKU not explicitly listed would be), the
simulation would crash with `KeyError` at execution time.

### 4a — `edge.py:150` — `_execute_order`

#### Original

```python
items_per_pallet = self.from_node.conversion_factors[sku]
```

#### Fixed

```python
items_per_pallet = self.from_node.conversion_factors.get(sku, 1)
```

---

### 4b — `edge.py:239` — `process()` candidate scan

#### Original

```python
items_per_pallet = self.from_node.conversion_factors[candidate.sku]
```

#### Fixed

```python
items_per_pallet = self.from_node.conversion_factors.get(candidate.sku, 1)
```

---

### 5a — `warehouse_node.py:106` — `items_per_pallet()`

#### Original

```python
def items_per_pallet(self, sku: str) -> int:
    return self.conversion_factors[sku]
```

#### Fixed

```python
def items_per_pallet(self, sku: str) -> int:
    return self.conversion_factors.get(sku, 1)
```

---

### 5b — `warehouse_node.py:111` — `pallets_for_quantity()`

#### Original

```python
return math.ceil(quantity / self.conversion_factors[sku])
```

#### Fixed

```python
return math.ceil(quantity / self.conversion_factors.get(sku, 1))
```

---

### 5c — `warehouse_node.py:114` — `quantity_for_pallets()`

#### Original

```python
return pallets * self.conversion_factors[sku]
```

#### Fixed

```python
return pallets * self.conversion_factors.get(sku, 1)
```

### Why `.get(sku, 1)` with default 1

`1` means "1 item per pallet" — effectively no pallet grouping.  This is the
safest fallback because:

- `math.ceil(quantity / 1) * 1 = quantity` — no distortion
- It matches the convention already used in `trace_management.py:_add_transport`
  (line 124 in the original) which used `.get(sku, 1)` since inception

---

## Fix 6 — `production_node.py:219` — infinite loop when `speed * dt < 1` and `speed = 0`

**File:** `src/infrastructure/production_node.py`

### Original code (lines 214-230)

```python
        # --- 4. batch loop ---
        speed: float = bom_entry["speed"]
        remaining: int = job.quantity

        while remaining > 0:
            batch_full = int(speed * self.global_time_step)

            if remaining > batch_full:
                batch = batch_full
                batch_duration = self.global_time_step
            else:
                batch = remaining
                batch_duration = remaining / speed

            yield self.hold(batch_duration)
            self._output_to_downstream(job.sku, batch)
            remaining -= batch
```

### What was wrong — two bugs

**Bug A — Zero batch size infinite loop:**
When `speed * global_time_step < 1.0` (e.g. `speed = 0.05`, `dt = 10` →
`0.5`), then `int(0.5) == 0`.  Now `batch_full = 0`, and since `remaining > 0`,
the code takes the `remaining > batch_full` branch, sets `batch = 0`, and
`remaining -= 0` never changes `remaining`.  The `while remaining > 0` loop
spins forever — the simulation hangs.

**Bug B — Division by zero when `speed = 0`:**
If `speed == 0`, the partial batch branch computes `batch_duration =
remaining / 0` → `ZeroDivisionError`.

### Fixed code

```python
        # --- 4. batch loop ---
        speed: float = bom_entry["speed"]
        remaining: int = job.quantity

        if speed <= 0:
            self.log.append({
                "time": self.env.now(),
                "type": "production_failed",
                "job_id": job.job_id,
                "sku": job.sku,
                "reason": "speed_zero",
            })
            return

        while remaining > 0:
            batch_full = max(1, int(speed * self.global_time_step))

            if remaining > batch_full:
                batch = batch_full
                batch_duration = self.global_time_step
            else:
                batch = remaining
                batch_duration = remaining / speed

            yield self.hold(batch_duration)
            self._output_to_downstream(job.sku, batch)
            remaining -= batch
```

### Why it works

- **Bug A fix:** `max(1, int(speed * dt))` ensures the minimum batch is 1 item,
  so `remaining -= 1` always makes progress.
- **Bug B fix:** Early `if speed <= 0: return` exits cleanly with a log entry
  instead of crashing.  `batch_duration = remaining / speed` is only reached
  when `speed > 0`.

---

## Fix 7 — `warehouse_node.py:141` — `print()` → structured logging

**File:** `src/infrastructure/warehouse_node.py`

### Original code

```python
    def check_capacity(self) -> None:
        """Print a warning if pallets exceed the soft cap."""
        if self.role == NodeRole.WAREHOUSE and self.node_max_pallets is not None:
            pal = self.current_pallets()
            if pal > self.node_max_pallets:
                print(
                    f"  [WARN] {self.display_name}: {pal} pallets"
                    f" > capacity {self.node_max_pallets}"
                )
```

### What was wrong

`print()` output goes to stdout and is **invisible** in programmatic log
consumption (`result.all_logs`).  Every other component logs to
`self.log.append(...)`, making this the only event type that couldn't be
inspected via the `SimulationResult` API.  It also broke the pattern for
automated analysis or report generation.

### Fixed code

```python
    def check_capacity(self) -> None:
        """Log a warning if pallets exceed the soft cap."""
        if self.role == NodeRole.WAREHOUSE and self.node_max_pallets is not None:
            pal = self.current_pallets()
            if pal > self.node_max_pallets:
                self.log.append({
                    "time": self.env.now(),
                    "type": "capacity_warning",
                    "node": self.display_name,
                    "pallets": pal,
                    "max_pallets": self.node_max_pallets,
                })
```

### Why it works

Now `capacity_warning` entries appear in `SimulationResult.all_logs` alongside
all other events, sortable by time, filterable by type, and inspectable by
automated analysis.

---

## Fix 8 — `warehouse_node.py:158-174` — `debit_whole()` never logs success

**File:** `src/infrastructure/warehouse_node.py`

### Original code

```python
    def debit_whole(self, sku: str, quantity: int) -> bool:
        if self.role == NodeRole.SOURCE:
            return True
        if self.role != NodeRole.WAREHOUSE:
            return False
        current = self.inventory.get(sku, 0)
        if current < quantity:
            return False
        self.inventory[sku] = current - quantity
        if self.inventory[sku] <= 0:
            del self.inventory[sku]
        return True
```

### What was wrong

`receive()` (the inbound counterpart) logs every successful receipt with
timestamp, SKU, quantity, and source.  `debit_whole()` logged **nothing** on
success.  This asymmetry made it impossible to trace where inventory went
after arriving at a warehouse — it just "disappeared" from the log perspective.
Diagnosing vanishing inventory required manual debugging.

### Fixed code

```python
    def debit_whole(self, sku: str, quantity: int) -> bool:
        if self.role == NodeRole.SOURCE:
            return True
        if self.role != NodeRole.WAREHOUSE:
            return False
        current = self.inventory.get(sku, 0)
        if current < quantity:
            return False
        self.inventory[sku] = current - quantity
        if self.inventory[sku] <= 0:
            del self.inventory[sku]
        self.log.append({
            "time": self.env.now(),
            "type": "debited",
            "sku": sku,
            "quantity": quantity,
        })
        return True
```

### Why it works

Every outbound movement now leaves a `"debited"` log entry.  The audit trail is
symmetric: `receive()` logs arrivals, `debit_whole()` logs departures.

---

## Fix 9 — `trace_management.py:103-107` — `_pick_producer` `ZeroDivisionError`

**File:** `src/management/trace_management.py`

### Original code

```python
    def _pick_producer(self, sku: str, candidates: list[str]) -> str:
        """Round-robin selection across candidate production nodes."""
        idx = self._rr_counter.get(sku, 0) % len(candidates)
        self._rr_counter[sku] = idx + 1
        return candidates[idx]
```

### What was wrong

If `candidates` is an empty list (no production node produces this SKU),
`len(candidates)` is `0` and `x % 0` raises `ZeroDivisionError`.  The original
call sites in `_accum_fg_tree` and `_accum_wip_tree` had no guard for this —
they checked `if not producers: return` but the `producers` variable came from
`.get(sku, [])`, which could return `[]`.  The caller would then pass `[]`
to `_pick_producer`, crashing the simulation.

### Fixed code

```python
    def _pick_producer(self, sku: str, candidates: list[str]) -> str | None:
        """Round-robin selection across candidate production nodes."""
        if not candidates:
            return None
        idx = self._rr_counter.get(sku, 0) % len(candidates)
        self._rr_counter[sku] = idx + 1
        return candidates[idx]
```

**Callers also updated:**

```python
        # In _accum_fg_tree:
        noodle = self._pick_producer(fg_sku, producers)
        if noodle is None:
            return

        # In _accum_wip_tree:
        producer = self._pick_producer(wip_sku, producers)
        if producer is None:
            return
```

### Why it works

Return type changed from `str` to `str | None`.  Both callers check for `None`
and return early, preventing downstream crashes from trying to index
`self._production_nodes[None]`.

---

## Verification

All fixes applied and simulation re-run with `python main.py scenario.hangzhou0b`:

```
  发货 final received: {
    '成品SKU1': 1000, '成品SKU2': 1000, '成品SKU3': 1000,
    '成品SKU4': 1000, '成品SKU5': 1000, '成品SKU6': 1000,
    '成品SKU7': 1000, '成品SKU8': 1000, '成品SKU9': 1000,
    '成品SKU10': 1000
  }
```

**Total FG delivered: 10,000 units** (1,000 per SKU × 10 SKUs) ✅

LSP diagnostics on all modified files: **0 new errors** (3 pre-existing
`Environment | None` type mismatches in sim.Component base class are unchanged).
