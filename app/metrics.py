from prometheus_client import Counter, Gauge

links_created = Counter("shortly_links_created_total", "Links created")
redirects = Counter("shortly_redirects_total", "Successful redirects")
rate_limited = Counter("shortly_rate_limited_total", "Rate limited requests")
blocked = Counter("shortly_blocked_total", "Blocked destination URLs")
redis_up = Gauge("shortly_redis_up", "Whether Redis is reachable")
build_info = Gauge("shortly_build_info", "Build version information", ["version"])
