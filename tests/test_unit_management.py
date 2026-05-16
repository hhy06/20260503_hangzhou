"""Unit tests for JobManager (now a sim.Component agent)."""

import pytest
import salabim as sim
from src.management import Job, JobManager, DECISION_INTERVAL
from src.warehouse_node import OutboundOrder, WarehouseNode, NodeRole


# ---------------------------------------------------------------------------
# Job sorting (pure dataclass — no SALABIM dependency)
# ---------------------------------------------------------------------------

class TestJobSorting:
    """JobManager sorts jobs by time on construction."""

    def test_jobs_sorted_on_init(self):
        jobs = [
            Job(time=10.0, from_node="A", to_node="B", orders=[]),
            Job(time=0.0, from_node="A", to_node="B", orders=[]),
            Job(time=5.0, from_node="A", to_node="B", orders=[]),
        ]
        sim.yieldless(False)
        env = sim.Environment(trace=False)
        mgr = JobManager(jobs, {}, env)
        assert mgr.jobs[0].time == 0.0
        assert mgr.jobs[1].time == 5.0
        assert mgr.jobs[2].time == 10.0


# ---------------------------------------------------------------------------
# Job issuance timing (via sim.Component process loop)
# ---------------------------------------------------------------------------

class TestJobIssuance:
    """JobManager's process() loop issues jobs at the right times.

    The component wakes every *DECISION_INTERVAL* (10) minutes.  These tests
    advance simulation time and inspect the component's event log.
    """

    @pytest.fixture
    def env(self):
        sim.yieldless(False)
        return sim.Environment(trace=False)

    @pytest.fixture
    def source(self, env):
        return WarehouseNode(
            name="Source",
            role=NodeRole.SOURCE,
            conversion_factors={"SKU_X": 10},
            env=env,
        )

    @pytest.fixture
    def sink(self, env):
        return WarehouseNode(
            name="Sink",
            role=NodeRole.SINK,
            conversion_factors={"SKU_X": 10},
            env=env,
        )

    # ------------------------------------------------------------------
    # Core timing
    # ------------------------------------------------------------------

    def test_no_jobs_before_scheduled_time(self, env, source, sink):
        """Jobs scheduled in the future should not be issued at first wake."""
        jobs = [
            Job(time=10.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=50, priority=1)]),
        ]
        nodes = {"Source": source, "Sink": sink}
        mgr = JobManager(jobs, nodes, env)

        # Advance part-way — the 10-minute job should NOT have fired
        env.run(DECISION_INTERVAL - 1)
        assert len(mgr.log) == 0

        # Advance past the job time — now it should fire
        env.run(10.0)
        assert len(mgr.log) == 1
        assert mgr.log[0]["time"] == 10.0

    def test_jobs_fire_at_scheduled_time(self, env, source, sink):
        """Jobs should be issued when their scheduled time is reached."""
        jobs = [
            Job(time=10.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=50, priority=1)]),
        ]
        nodes = {"Source": source, "Sink": sink}
        mgr = JobManager(jobs, nodes, env)

        env.run(10.0)
        assert len(mgr.log) == 1
        ev = mgr.log[0]
        assert ev["time"] == 10.0
        assert ev["from"] == "Source"
        assert ev["to"] == "Sink"
        assert ev["orders"] == [("SKU_X", 50, 1)]

    def test_multiple_jobs_same_time(self, env, source, sink):
        """Multiple jobs at the same time should all be issued together."""
        jobs = [
            Job(time=0.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=30, priority=1)]),
            Job(time=0.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_Y", quantity=20, priority=2)]),
        ]
        nodes = {"Source": source, "Sink": sink}
        mgr = JobManager(jobs, nodes, env)

        env.run(0.1)
        assert len(mgr.log) == 2

    def test_jobs_issuance_idempotent(self, env, source, sink):
        """Jobs should only be issued once."""
        jobs = [
            Job(time=0.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=50, priority=1)]),
        ]
        nodes = {"Source": source, "Sink": sink}
        mgr = JobManager(jobs, nodes, env)

        env.run(0.1)
        assert len(mgr.log) == 1

        # Second run to same time — no new events
        env.run(0.1)
        assert len(mgr.log) == 1

    def test_jobs_fire_in_time_order(self, env, source, sink):
        """Jobs issued at different times should fire as time advances."""
        jobs = [
            Job(time=10.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=50, priority=1)]),
            Job(time=20.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=30, priority=1)]),
        ]
        nodes = {"Source": source, "Sink": sink}
        mgr = JobManager(jobs, nodes, env)

        env.run(10.0)
        assert len(mgr.log) == 1

        env.run(20.0)
        assert len(mgr.log) == 2

    # ------------------------------------------------------------------
    # Decision interval
    # ------------------------------------------------------------------

    def test_wake_cycle_respects_interval(self, env, source, sink):
        """The component should wake every DECISION_INTERVAL, not every step."""
        jobs = [
            Job(time=5.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=50, priority=1)]),
        ]
        nodes = {"Source": source, "Sink": sink}
        mgr = JobManager(jobs, nodes, env)

        # Advance past the job time in small steps — job should still only
        # be issued once (when the component wakes).
        for t in range(1, 15):
            env.run(float(t))
        assert len(mgr.log) == 1

    def test_initial_wake_at_time_zero(self, env, source, sink):
        """Jobs scheduled at t=0 should be issued on the first wake."""
        jobs = [
            Job(time=0.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=50, priority=1)]),
        ]
        nodes = {"Source": source, "Sink": sink}
        mgr = JobManager(jobs, nodes, env)

        env.run(0.1)  # any positive time triggers the first wake
        assert len(mgr.log) == 1
        assert mgr.log[0]["time"] == 0.0
