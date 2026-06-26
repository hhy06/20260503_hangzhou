import time
from datetime import datetime

import salabim as sim


class DayProgressMonitor(sim.Component):
    def __init__(
        self,
        day_in_minutes: float = 1440.0,
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self._day_in_minutes = day_in_minutes
        self._wall_start = time.time()
        super().__init__(name="DayProgressMonitor", env=env, **kwargs)

    def process(self):
        day = 0
        while True:
            yield self.hold(self._day_in_minutes)
            day += 1
            sim_t = self.env.now()
            wall_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elapsed = time.time() - self._wall_start
            print(
                f"[DAY {day:>4}] sim_time={sim_t:>10.0f}  wall={wall_now}  elapsed={elapsed:.1f}s",
                flush=True,
            )
