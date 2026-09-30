"""Locust entry point for load against a host or the minikube Ingress."""

import csv
import os
from pathlib import Path

from locust import events

from loadtest.common import seed_links
from loadtest.personas import Abuser, CasualVisitor, Creator, PowerUser

__all__ = ["Abuser", "CasualVisitor", "Creator", "PowerUser"]

request_times: list[tuple[float, float, bool, str]] = []


@events.test_start.add_listener
def seed_shortly(environment, **_kwargs):
    if environment.runner and getattr(environment.runner, "worker_index", None) not in (None, 0):
        return
    seed_links()


@events.request.add_listener
def record_request(request_type, name, response_time, exception, start_time, **_kwargs):
    if os.getenv("LOCUST_TIMING_FILE"):
        request_times.append((start_time, response_time, exception is not None, name))


@events.test_stop.add_listener
def save_request_times(environment, **_kwargs):
    path = os.getenv("LOCUST_TIMING_FILE")
    if not path:
        return
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["timestamp", "response_time_ms", "failed", "name"])
        writer.writerows(request_times)
