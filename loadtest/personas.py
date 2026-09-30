"""Four human-readable load personas, each exercising normal user behavior."""

from __future__ import annotations

import random
import string
import time
from datetime import UTC, datetime

from locust import FastHttpUser, between, task
from locust.contrib.fasthttp import FastHttpSession

from loadtest.common import (
    ABUSER_IP,
    PERSONA_WEIGHTS,
    THINK_TIME_SCALE,
    add_alias,
    add_pool,
    aliases,
    assert_redirect,
    choose_safe_url,
    expect,
    expiring_links,
    fake,
    fake_headers,
    live_links,
    parse_time,
    response_json,
    verify_created,
)


def wait(low: float, high: float):
    base = between(low, high)
    return lambda _user: base(None) * THINK_TIME_SCALE


class NoRedirectSession(FastHttpSession):
    """Honor allow_redirects=False against geventhttpclient's redirect property."""

    def request(self, method, url, *, allow_redirects=True, **kwargs):
        if allow_redirects:
            raise ValueError("Shortly load requests must never follow redirects")
        old_codes = self.client.redirect_response_codes
        self.client.redirect_response_codes = frozenset()
        try:
            return super().request(method, url, allow_redirects=False, **kwargs)
        finally:
            self.client.redirect_response_codes = old_codes


class ShortlyUser(FastHttpUser):
    abstract = True
    follow_redirects = False

    def on_start(self):
        # FastHttpSession currently toggles a misspelled attribute internally;
        # this adapter sets geventhttpclient's actual redirect-code setting.
        self.client = NoRedirectSession(
            base_url=self.host,
            request_event=self.environment.events.request,
            network_timeout=self.network_timeout,
            connection_timeout=self.connection_timeout,
            max_redirects=self.max_redirects,
            max_retries=self.max_retries,
            insecure=self.insecure,
            concurrency=self.concurrency,
            user=self,
            client_pool=self.client_pool,
            ssl_context_factory=self.ssl_context_factory,
            headers=self.default_headers,
            proxy_host=self.proxy_host,
            proxy_port=self.proxy_port,
        )
        self.fake_ip = fake.ipv4_public()
        self.user_agent = fake.user_agent()
        self.visits: dict[str, int] = {}
        self.last_clicks: dict[str, int] = {}
        self.last_shorten = 0.0

    def pace_shorten(self, minimum_interval: float = 6.0) -> None:
        """Keep legitimate per-user creates below the app's ten-per-minute limit."""
        if getattr(self, "is_abuser", False):
            return
        remaining = minimum_interval - (time.monotonic() - self.last_shorten)
        if remaining > 0:
            time.sleep(remaining)
        self.last_shorten = time.monotonic()

    def headers(self) -> dict[str, str]:
        return fake_headers(self)

    def visit(self, item: dict[str, str], name: str = "GET /{code} [known]") -> bool:
        with self.client.get(
            f"/{item['code']}",
            headers=self.headers(),
            name=name,
            catch_response=True,
            allow_redirects=False,
        ) as response:
            ok = expect(response, {302}, name)
            if ok:
                assert_redirect(response, item["url"])
                self.visits[item["code"]] = self.visits.get(item["code"], 0) + 1
            return ok

    def home(self) -> None:
        name = "GET / [home]"
        with self.client.get(
            "/", headers=self.headers(), name=name, catch_response=True, allow_redirects=False
        ) as response:
            expect(response, {200}, name)

    def recent(self) -> None:
        name = "GET /api/links/recent [poll]"
        with self.client.get(
            "/api/links/recent",
            headers=self.headers(),
            name=name,
            catch_response=True,
            allow_redirects=False,
        ) as response:
            expect(response, {200}, name)

    def create(
        self,
        url: str,
        alias: str | None = None,
        expiry: int | None = None,
        name: str = "POST /api/shorten [create]",
    ) -> dict:
        body = {"url": url}
        if alias:
            body["alias"] = alias
        if expiry is not None:
            body["expires_in_seconds"] = expiry
        self.pace_shorten()
        with self.client.post(
            "/api/shorten",
            json=body,
            headers=self.headers(),
            name=name,
            catch_response=True,
            allow_redirects=False,
        ) as response:
            if not expect(response, {201, 429}, name):
                return {}
            if response.status_code == 429:
                try:
                    delay = int(response.headers.get("Retry-After", "1"))
                except ValueError:
                    delay = 1
                time.sleep(min(max(delay, 1), 60))
                return {}
            data = verify_created(response, url, expiry is not None)
            if data.get("code"):
                item = {"code": data["code"], "url": url, "created_at": data["created_at"]}
                if expiry is not None:
                    item["expires_at"] = data.get("expires_at", "")
                    add_pool(expiring_links, item)
                else:
                    add_pool(live_links, item)
                if alias:
                    add_alias(alias)
                return item
            return {}

    def stats(self, item: dict[str, str]) -> None:
        code = item["code"]
        name = "GET /api/links/{code}/stats [own link]"
        for _ in range(2):
            with self.client.get(
                f"/api/links/{code}/stats",
                headers=self.headers(),
                name=name,
                catch_response=True,
                allow_redirects=False,
            ) as response:
                if not expect(response, {200}, name):
                    return
                data = response_json(response)
                clicks = data.get("clicks")
                required = self.visits.get(code, 0)
                previous = self.last_clicks.get(code, 0)
                if not isinstance(clicks, int) or clicks < required:
                    response.failure(f"stats clicks {clicks!r} below this user's {required} visits")
                if isinstance(clicks, int) and clicks < previous:
                    response.failure(f"stats clicks decreased from {previous} to {clicks}")
                if isinstance(clicks, int):
                    self.last_clicks[code] = clicks


class CasualVisitor(ShortlyUser):
    abstract = False
    weight = PERSONA_WEIGHTS["visitor"]
    wait_time = wait(1, 4)

    @task(70)
    def follow_live_link(self):
        if live_links:
            self.visit(random.choice(live_links))
        else:
            self.home()

    @task(15)
    def browse_home(self):
        self.home()

    @task(10)
    def poll_recent_links(self):
        self.recent()

    @task(5)
    def revisit_expiring_link(self):
        if not expiring_links:
            self.home()
            return
        item = random.choice(expiring_links)
        expiry = parse_time(item["expires_at"])
        remaining = (expiry - datetime.now(UTC)).total_seconds()
        allowed = {302} if remaining > 2 else {410} if remaining < -2 else {302, 410}
        name = "GET /{code} [expiring]"
        with self.client.get(
            f"/{item['code']}",
            headers=self.headers(),
            name=name,
            catch_response=True,
            allow_redirects=False,
        ) as response:
            if response.status_code not in allowed:
                response.failure(
                    f"{name}: expected {sorted(allowed)}, got {response.status_code}; "
                    f"code={item['code']}, expires_at={item['expires_at']}, "
                    f"remaining={remaining:.3f}s"
                )
                return
            if expect(response, allowed, name) and response.status_code == 302:
                assert_redirect(response, item["url"])


class Creator(ShortlyUser):
    abstract = False
    weight = PERSONA_WEIGHTS["creator"]
    wait_time = wait(3, 8)

    @task
    def create_visit_and_check(self):
        expiry = random.choice([None, None, None, 60, 3600])
        item = self.create(choose_safe_url(), expiry=expiry)
        if not item:
            return
        for _ in range(random.randint(1, 4)):
            self.visit(item)
        self.stats(item)


class PowerUser(ShortlyUser):
    abstract = False
    weight = PERSONA_WEIGHTS["power"]
    wait_time = wait(2, 6)

    def pace_shorten(self, minimum_interval: float = 10.0) -> None:
        super().pace_shorten(minimum_interval)

    def on_start(self):
        super().on_start()
        if aliases:
            self.conflict(random.choice(tuple(aliases)), "duplicate alias")

    def alias(self) -> str:
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        return f"{fake.word()}-{suffix}"[:32]

    def conflict(self, alias: str, label: str) -> None:
        name = f"POST /api/shorten [{label}]"
        self.pace_shorten()
        with self.client.post(
            "/api/shorten",
            json={"url": choose_safe_url(), "alias": alias},
            headers=self.headers(),
            name=name,
            catch_response=True,
            allow_redirects=False,
        ) as response:
            expect(response, {409, 429}, name)

    @task
    def create_alias_and_expiring_link(self):
        if aliases and random.random() < 0.5:
            self.conflict(random.choice(tuple(aliases)), "duplicate alias")
        if random.random() < 0.1:
            reserved = random.choice(["api", "admin", "metrics"])
            name = "POST /api/shorten [reserved alias]"
            self.pace_shorten()
            with self.client.post(
                "/api/shorten",
                json={"url": choose_safe_url(), "alias": reserved},
                headers=self.headers(),
                name=name,
                catch_response=True,
                allow_redirects=False,
            ) as response:
                expect(response, {409, 429}, name)

        alias = self.alias()
        item = self.create(choose_safe_url(), alias=alias, expiry=random.choice([60, 3600]))
        if item:
            for _ in range(random.randint(1, 3)):
                self.visit(item, "GET /{code} [custom alias]")
            self.stats(item)

        seconds = random.randint(5, 10)
        ephemeral = self.create(
            choose_safe_url(), expiry=seconds, name="POST /api/shorten [ephemeral]"
        )
        if ephemeral:
            time.sleep(seconds + 2.1)
            name = "GET /{code} [expired]"
            with self.client.get(
                f"/{ephemeral['code']}",
                headers=self.headers(),
                name=name,
                catch_response=True,
                allow_redirects=False,
            ) as response:
                expect(response, {410}, name)


class Abuser(ShortlyUser):
    abstract = False
    weight = PERSONA_WEIGHTS["abuser"]
    wait_time = wait(0.5, 3)

    def on_start(self):
        super().on_start()
        self.fake_ip = ABUSER_IP
        self.is_abuser = True
        # Exercise validation and blocking before the shared IP exhausts its quota.
        self.invalid_url()
        self.blocked_domain()
        self.shorten_burst()

    @task(3)
    def invalid_url(self):
        bad = random.choice(
            [
                "ftp://example.com/x",
                "https:///no-host",
                "",
                "https://" + "a" * 2100,
                "https://example.com/white space",
            ]
        )
        name = "Abuser POST /api/shorten [invalid URL]"
        with self.client.post(
            "/api/shorten",
            json={"url": bad},
            headers=self.headers(),
            name=name,
            catch_response=True,
            allow_redirects=False,
        ) as response:
            expect(response, {422, 429}, name)

    @task(2)
    def blocked_domain(self):
        target = random.choice(["https://evil.example/blocked", "https://sub.malware.test/blocked"])
        name = "Abuser POST /api/shorten [blocked domain]"
        with self.client.post(
            "/api/shorten",
            json={"url": target},
            headers=self.headers(),
            name=name,
            catch_response=True,
            allow_redirects=False,
        ) as response:
            expect(response, {403, 429}, name)

    @task(2)
    def unknown_link(self):
        name = "Abuser GET /{code} [unknown]"
        code = "missing-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        with self.client.get(
            f"/{code}",
            headers=self.headers(),
            name=name,
            catch_response=True,
            allow_redirects=False,
        ) as response:
            expect(response, {404}, name)

    @task(2)
    def scan_paths(self):
        path = random.choice(["/.env", "/wp-login.php", "/admin", "/api/links/zzzzzz/stats"])
        name = "Abuser GET /{path} [path scan]"
        with self.client.get(
            path, headers=self.headers(), name=name, catch_response=True, allow_redirects=False
        ) as response:
            expect(response, {404, 401}, name)

    @task(1)
    def wrong_admin_token(self):
        name = "Abuser GET /admin/chaos [unauthorized]"
        with self.client.get(
            "/admin/chaos",
            headers={**self.headers(), "X-Admin-Token": "wrong-token"},
            name=name,
            catch_response=True,
            allow_redirects=False,
        ) as response:
            expect(response, {401}, name)

    @task(1)
    def shorten_burst(self):
        for _ in range(15):
            name = "Abuser POST /api/shorten [burst]"
            with self.client.post(
                "/api/shorten",
                json={"url": choose_safe_url()},
                headers=self.headers(),
                name=name,
                catch_response=True,
                allow_redirects=False,
            ) as response:
                expect(response, {201, 422, 429}, name)
