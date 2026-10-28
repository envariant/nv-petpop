"""Mock pacing (BRIEF Section 13): on profiles with `pacing_reference_s` (the mock profile) each mock stage
takes PETPOP_MOCK_SPEED x its reference seconds, so the Generating screen sees realistic timing.
PETPOP_MOCK_SPEED=0 makes tests instant; real profiles never pace."""
import time

from backend.core.genai import Profile
from backend.core.paths import mock_speed


class Pace:
    def __init__(self, stage: str) -> None:
        self.stage = stage
        self.t0 = time.monotonic()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        ref = Profile().get("pacing_reference_s") or {}
        if exc[0] is None and self.stage in ref:
            left = mock_speed() * float(ref[self.stage]) - (time.monotonic() - self.t0)
            if left > 0:
                time.sleep(left)
