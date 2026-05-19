"""Base Management component — abstract periodic decision-maker.

A :class:`Management` subclasses implement a periodic decision loop:
``process()`` calls :meth:`make_decision` every ``decision_interval``
time units.
"""

from typing import Any
import salabim as sim


class Management(sim.Component):
    """Base class for management decision-makers in the simulation.

    Subclasses must implement :meth:`make_decision`.

    Parameters
    ----------
    decision_interval : float
        Minutes between ``make_decision()`` calls (default 10.0).
    name : str, optional
        SALABIM component name.
    env : sim.Environment | None
    """

    def __init__(
        self,
        decision_interval: float = 10.0,
        name: str = "Management",
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self.decision_interval = decision_interval
        super().__init__(name=name, env=env, **kwargs)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def find_edge(self, from_node_name: str, to_node_name: str) -> Any | None:
        """Locate the first edge whose endpoints match the given names.

        Subclasses may override with a faster lookup (e.g. a dict).
        """
        # Provided here as a convenience; subclasses with access to
        # the edge list can implement this themselves.
        raise NotImplementedError(
            f"{type(self).__name__} must implement find_edge()"
        )

    # ------------------------------------------------------------------
    # decision logic (must be overridden)
    # ------------------------------------------------------------------

    def make_decision(self) -> None:
        """Called every ``decision_interval`` time units."""
        raise NotImplementedError(
            f"{type(self).__name__} must implement make_decision()"
        )

    # ------------------------------------------------------------------
    # SALABIM process
    # ------------------------------------------------------------------

    def process(self):
        """SALABIM coroutine: call ``make_decision()`` periodically."""
        while True:
            self.make_decision()
            yield self.hold(self.decision_interval)
