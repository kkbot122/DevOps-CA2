"""Scale from idle to the target surge, hold, then ramp down."""

from __future__ import annotations

import os

from locust import LoadTestShape


class SurgeShape(LoadTestShape):
    ramp_up = 60
    hold = max(1, int(os.getenv("SURGE_HOLD", "180")))
    ramp_down = 30
    target = max(10, int(os.getenv("SURGE_USERS", "200")))

    def tick(self):
        elapsed = self.get_run_time()
        if elapsed < self.ramp_up:
            users = round(self.target * elapsed / self.ramp_up)
        elif elapsed < self.ramp_up + self.hold:
            users = self.target
        elif elapsed < self.ramp_up + self.hold + self.ramp_down:
            remaining = 1 - (elapsed - self.ramp_up - self.hold) / self.ramp_down
            users = round(10 + (self.target - 10) * remaining)
        else:
            return None
        return max(1, users), max(1, min(users, int(os.getenv("SPAWN", "10"))))
