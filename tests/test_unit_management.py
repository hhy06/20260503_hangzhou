"""Unit tests for JobManager."""

import pytest
import salabim as sim
from src.management import Job, JobManager
from src.warehouse_node import OutboundOrder, WarehouseNode, NodeRole


# ---------------------------------------------------------------------------
# Job sorting
# ---------------------------------------------------------------------------

class TestJobSorting:
    """JobManager sorts jobs by time on construction."""

    def test_jobs_sorted_on_init(self):
        jobs = [
            Job(time=10.0, from_node="A", to_node="B", orders=[]),
            Job(time=0.0, from_node="A", to_node="B", orders=[]),
            Job(time=5.0, from_node="A", to_node="B", orders=[]),
        ]
        env = sim.Environment(trace=False)
        mgr = JobManager(jobs, env)
        assert mgr.jobs[0].time == 0.0
        assert mgr.jobs[1].time == 5.0
        assert mgr.jobs[2].time == 10.0


# ---------------------------------------------------------------------------
# Job issuance timing
# ---------------------------------------------------------------------------

class TestJobIssuance:
    """JobManager.issue_pending_jobs() fires jobs at the right times.

    These are lightweight integration checks with real (but static) nodes.
    """

    @pytest.fixture
    def env(self):
        return sim.Environment(trace=False)

    @pytest.fixture
    def source(self, env):
        return WarehouseNode(
            name="Source",
            role=NodeRole.SOURCE,
            conversion_factors={"SKU_X": 10},
            env=env,
        )

    def test_no_jobs_before_time(self, env, source):
        jobs = [
            Job(time=10.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=50, priority=1)]),
        ]
        nodes = {"Source": source}
        mgr = JobManager(jobs, env)

        # At t=0, no jobs should fire
        events = mgr.issue_pending_jobs(nodes)
        assert len(events) == 0

    def test_jobs_fire_at_scheduled_time(self, env, source):
        jobs = [
            Job(time=10.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=50, priority=1)]),
        ]
        nodes = {"Source": source}
        mgr = JobManager(jobs, env)

        # Advance to t=10
        env.run(10.0)
        events = mgr.issue_pending_jobs(nodes)
        assert len(events) == 1
        assert events[0]["time"] == 10.0
        assert events[0]["from"] == "Source"
        assert events[0]["to"] == "Sink"
        assert events[0]["orders"] == [("SKU_X", 50, 1)]

    def test_multiple_jobs_same_time(self, env, source):
        jobs = [
            Job(time=5.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=30, priority=1)]),
            Job(time=5.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_Y", quantity=20, priority=2)]),
        ]
        nodes = {"Source": source}
        mgr = JobManager(jobs, env)

        env.run(5.0)
        events = mgr.issue_pending_jobs(nodes)
        assert len(events) == 2

    def test_jobs_issuance_idempotent(self, env, source):
        """Calling issue_pending_jobs twice at the same time should only fire once."""
        jobs = [
            Job(time=5.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=50, priority=1)]),
        ]
        nodes = {"Source": source}
        mgr = JobManager(jobs, env)

        env.run(5.0)
        events1 = mgr.issue_pending_jobs(nodes)
        assert len(events1) == 1

        events2 = mgr.issue_pending_jobs(nodes)
        assert len(events2) == 0  # already issued

    def test_jobs_fire_in_time_order(self, env, source):
        """Jobs issued at different times should fire as time advances."""
        jobs = [
            Job(time=10.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=50, priority=1)]),
            Job(time=20.0, from_node="Source", to_node="Sink",
                orders=[OutboundOrder(sku="SKU_X", quantity=30, priority=1)]),
        ]
        nodes = {"Source": source}
        mgr = JobManager(jobs, env)

        env.run(10.0)
        e1 = mgr.issue_pending_jobs(nodes)
        assert len(e1) == 1

        env.run(20.0)
        e2 = mgr.issue_pending_jobs(nodes)
        assert len(e2) == 1
