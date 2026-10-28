"""Mock pacing (BRIEF Section 13): each mock stage takes PETPOP_MOCK_SPEED x its real timeout, so the
Generating screen sees realistic timing; PETPOP_MOCK_SPEED=0 makes tests instant."""
import time

from backend.core.paths import mock_speed

TIMEOUTS = {"A": 10, "control": 10, "B": 60, "C": 90, "D": 150, "E": 90, "F": 120}


class Pace:
    def __init__(self, stage: str) -> None:
        self.stage = stage
        self.t0 = time.monotonic()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        if exc[0] is None:
            left = mock_speed() * TIMEOUTS[self.stage] - (time.monotonic() - self.t0)
            if left > 0:
                time.sleep(left)
