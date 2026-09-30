# Baseline rate-limit realism check

Command used:

```sh
kubectl -n urlshortener logs -l app.kubernetes.io/component=api --since-time=2026-09-30T18:54:21Z --tail=-1 --prefix --max-log-requests 10
```

Distinct client_ip values: **62**

IP addresses with 429 responses: **198.51.100.250**

The scenario asserts that more than ten source IPs reach the app and that the only rate-limited source is the shared Abuser address `198.51.100.250`.
