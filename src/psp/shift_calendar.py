"""Generate shift timeline for the planning horizon."""

from src.psp.types import Shift


SHIFT_DURATION = 690
DAY_START = 480  # 08:00
NIGHT_START = 1200  # 20:00


def build_shifts(num_days: int) -> list[Shift]:
    shifts: list[Shift] = []
    for d in range(num_days):
        base = d * 1440
        shifts.append(Shift(
            index=len(shifts),
            day=d + 1,
            type="day",
            start_time=base + DAY_START,
            end_time=base + DAY_START + SHIFT_DURATION,
        ))
        shifts.append(Shift(
            index=len(shifts),
            day=d + 1,
            type="night",
            start_time=base + NIGHT_START,
            end_time=base + NIGHT_START + SHIFT_DURATION,
        ))
    return shifts
