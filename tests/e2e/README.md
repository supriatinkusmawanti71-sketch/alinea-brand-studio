# E2E Smoke Tests

These tests verify a locally running Docker Compose stack. They are skipped by
default so normal unit-test and CI runs do not require Docker services.

Run manually:

```sh
./scripts/run-e2e.sh
```

To keep the stack running after the test:

```sh
KEEP_STACK=1 ./scripts/run-e2e.sh
```

Current scope:

- Docker Compose long-running services are running and healthy.
- Gateway health endpoint responds.
- Web health endpoint responds.
- API readiness and docs endpoints respond.
- MinIO live health endpoint responds.

After M0 is merged, add the real business flow here.
