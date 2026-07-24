# JWT Secret Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject JWT secrets shorter than 32 UTF-8 bytes at configuration load time and eliminate PyJWT insecure-key warnings from the test suite.

**Architecture:** Keep the policy at the `Settings` boundary so every application entry point receives validated configuration. Tests explicitly provide a safe JWT secret so results do not depend on the developer's local `.env`.

**Tech Stack:** Python 3.12, pydantic-settings, Pydantic field validators, pytest, PyJWT

## Global Constraints

- Measure the secret using `len(value.encode("utf-8"))`, not Python character count.
- Reject values shorter than 32 bytes with `JWT_SECRET must be at least 32 bytes`.
- Do not include the secret value in validation errors or logs.
- Do not change JWT claims, signing algorithm, expiry durations, or cookies.
- Do not modify the developer's untracked `.env`.

---

### Task 1: Enforce the JWT secret boundary

**Files:**
- Modify: `tests/test_config.py`
- Modify: `app/config.py`

**Interfaces:**
- Consumes: Pydantic's `field_validator`.
- Produces: `Settings.jwt_secret`, guaranteed to contain at least 32 UTF-8 bytes.

- [ ] **Step 1: Write failing boundary tests**

Add constants and tests to `tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError

SAFE_JWT_SECRET = "test-jwt-secret-that-is-32-bytes!"


def test_jwt_secret_rejects_fewer_than_32_bytes(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", "x" * 31)

    with pytest.raises(ValidationError, match="JWT_SECRET must be at least 32 bytes"):
        config_module.Settings(_env_file=None)


def test_jwt_secret_accepts_exactly_32_bytes(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    assert config_module.Settings(_env_file=None).jwt_secret == "x" * 32


def test_jwt_secret_measures_utf8_bytes(monkeypatch):
    secret = "가" * 11
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", secret)

    assert config_module.Settings(_env_file=None).jwt_secret == secret
```

Replace every existing `"test-secret"` value and assertion in this file with
`SAFE_JWT_SECRET`.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
uv run pytest tests/test_config.py -q
```

Expected: the 31-byte rejection test fails because no `ValidationError` is raised.

- [ ] **Step 3: Implement the minimal validator**

Update `app/config.py`:

```python
from pydantic import field_validator


class Settings(BaseSettings):
    # existing settings remain unchanged

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_at_least_32_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        return value
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```powershell
uv run pytest tests/test_config.py -q
```

Expected: all configuration tests pass with no JWT key-length warning.

- [ ] **Step 5: Commit the validated boundary**

```powershell
git add app/config.py tests/test_config.py
git commit -m "fix: JWT 비밀키 최소 길이 강제"
```

### Task 2: Isolate tests and update example configuration

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_sql_logging.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `Settings` validation introduced in Task 1.
- Produces: a test environment and example configuration that always satisfy the 32-byte policy.

- [ ] **Step 1: Write a failing test-environment assertion**

Add to `tests/test_config.py`:

```python
def test_cached_test_settings_use_safe_jwt_secret():
    assert len(config_module.get_settings().jwt_secret.encode("utf-8")) >= 32
```

- [ ] **Step 2: Run the assertion and verify RED**

Run:

```powershell
uv run pytest tests/test_config.py::test_cached_test_settings_use_safe_jwt_secret -q
```

Expected: configuration loading fails when the current local `.env` contains a
secret shorter than 32 bytes.

- [ ] **Step 3: Make the test environment explicit**

Before importing application modules in `tests/conftest.py`, add:

```python
os.environ["JWT_SECRET"] = "test-jwt-secret-that-is-32-bytes!"
```

In `tests/test_sql_logging.py`, replace the direct `jwt_secret="x"` argument with:

```python
jwt_secret="test-jwt-secret-that-is-32-bytes!"
```

In `.env.example`, replace the secret line with:

```dotenv
JWT_SECRET=replace-with-at-least-32-random-bytes
```

- [ ] **Step 4: Run configuration and security tests**

Run:

```powershell
uv run pytest tests/test_config.py tests/test_security.py tests/test_sql_logging.py -q
```

Expected: all selected tests pass and the warnings summary contains no
`InsecureKeyLengthWarning`.

- [ ] **Step 5: Commit test and example configuration**

```powershell
git add tests/conftest.py tests/test_config.py tests/test_sql_logging.py .env.example
git commit -m "test: 안전한 JWT 비밀키로 테스트 격리"
```

### Task 3: Full regression verification

**Files:**
- Verify only; no planned source changes.

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: evidence that backend behavior and frontend checks remain healthy.

- [ ] **Step 1: Run the full backend test suite**

Run:

```powershell
uv run pytest -q
```

Expected: 340 tests pass, two external stock smoke tests may remain skipped, and
there are zero `InsecureKeyLengthWarning` entries.

- [ ] **Step 2: Run frontend lint**

Run:

```powershell
npm.cmd run lint
```

Expected: exit code 0. The pre-existing `react(only-export-components)` warning
in `web/src/lib/auth.tsx` may remain because it is outside this task.

- [ ] **Step 3: Run frontend build**

Run:

```powershell
npm.cmd run build
```

Expected: TypeScript and Vite build finish with exit code 0.

- [ ] **Step 4: Inspect the final diff**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; the user's pre-existing
`web/src/components/table/seqColumn.ts` modification remains untouched.
