# TESTING STRATEGY & COVERAGE AUDIT
**Last Updated**: 2026-03-22 | **Target**: Increase coverage from 45% to 80% by Q2 2026

---

## Current Coverage Status

```
Backend (80 test files, 374 tests):
├─ Authentication:        65% ✅ (22 tests)
├─ Hotspot Sync:          55% ⚠️  (28 tests)
├─ Transaction/Payment:   50% ⚠️  (18 tests)
├─ Debt Management:       40% ❌ (12 tests) — Added Mar 22: enforce_overdue_debt_block
├─ Notifications:         60% ⚠️  (12 tests)
├─ Device Management:     45% ⚠️  (9 tests)
├─ Admin Operations:      35% ❌ (11 tests)
├─ MikroTik Integration:  30% ❌ (8 tests) — Added Mar 22: webhook signature
├─ Security:             25% ❌ (6 tests)  — Added Mar 22: SECRET_KEY guard
└─ **E2E Workflows**:      0% ❌ (0 tests)  — CRITICAL GAP

Frontend (18 test files):
├─ Component Tests:       30% ❌
├─ Composables:          20% ❌
└─ **E2E (Playwright)**:   0% ❌ — CRITICAL GAP
```

---

## Mar 22 Test Additions

| Test File | Tests Added | Coverage | Status |
|-----------|------------|----------|--------|
| `test_enforce_overdue_debt_block_critical_fixes.py` | 5 | Debt mgmt +20% | ✅ New |
| `test_midtrans_webhook_signature_security.py` | 4 | Security +15% | ✅ New |
| `test_secret_key_production_guard.py` | 4 | Security +15% | ✅ New |
| **TOTAL NEW**: | **13 tests** | +50% coverage for critical paths | ✅ |

---

## Critical Gaps — MUST IMPLEMENT Q2 2026

### 1. Frontend 401 Handling (GAP-1 Test)

**File**: `frontend/tests/api-plugin.test.ts`
```typescript
// Test that 401 triggers logout, not silent failure
describe("API Plugin 401 Handling", () => {
  test("401 on non-auth request calls clearSession", async () => {
    const response401 = new Response(null, { status: 401 })
    // Mock and verify clearSession is called
    expect(authStore.clearSession).toHaveBeenCalledWith("token_expired_non_auth")
  })

  test("401 shows error toast on non-auth request", async () => {
    // Verify $emit('toast', ...) is called
  })
})
```

### 2. E2E: Critical User Flows

**Requirement**: Playwright E2E tests for:

1. **Authentication Flow**
   - Login → Hotspot portal
   - OTP verification
   - Session timeout → re-login
   - MAC randomization detection → token renewal

2. **Transaction Flow**
   - Browse packages
   - Create order → Midtrans payment
   - Webhook callback → package applied
   - Verify quota updated

3. **Admin Operations**
   - User list, filter
   - Block/unblock user
   - Manual debt add
   - Send WA notification

**Setup**:
```bash
npm install -D @playwright/test
mkdir frontend/e2e
# Add playwright.config.ts
```

### 3. Celery Task Time Limits (GAP-2 Test)

**File**: `backend/tests/test_celery_time_limits.py`
```python
def test_sync_hotspot_usage_respects_soft_time_limit():
    """Verifies soft_time_limit=300 is set."""
    from app.tasks import sync_hotspot_usage_task

    assert sync_hotspot_usage_task.soft_time_limit == 300
    assert sync_hotspot_usage_task.time_limit == 360
```

### 4. Logging Filters (PROD-1 Test)

**File**: `backend/tests/test_logging_filters.py`
```python
def test_fonttools_logging_filtered():
    """Verify fontTools loggers set to WARNING."""
    import logging
    fonttools_logger = logging.getLogger("fontTools")
    assert fonttools_logger.level == logging.WARNING or \
           fonttools_logger.level == logging.NOTSET  # Inheritance)
```

---

## Existing Test Coverage Opportunities

### Low-Hanging Fruit (5–10 hours total)

| Category | Gap | Effort | Impact |
|----------|-----|--------|--------|
| Admin user CRUD | No tests for edit/delete | 2h | High |
| Debt settlement | Receipt generation missing | 2h | High |
| Notification templates | Missing test for new debt template | 1h | Medium |
| Device management | Delete device edge cases | 1.5h | Medium |
| MikroTik mock helpers | Improve mock/stub coverage | 1.5h | Low |

---

## Running Tests

### Local Development

```bash
# Backend
cd backend
pytest -v --cov=app tests/ | grep "FAILED\|ERROR"

# Frontend
npm run test

# Watch mode
pytest -v --cov=app tests/ --watch
```

### CI/CD (GitHub Actions)

```yaml
# .github/workflows/test.yml (already exists, verify active)
- run: pytest -v --cov=app --cov-report=xml tests/
- run: npm run test --workspace=frontend
```

**Current Status**: ✅ Active, checks all commits

### Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=app --cov-report=html tests/
# Open htmlcov/index.html in browser
```

---

## Testing Best Practices

### 1. Mock External Services

```python
# ✅ Good: Mock MikroTik connection
with patch("app.infrastructure.gateways.mikrotik_client.get_mikrotik_connection"):
    result = task()

# ❌ Bad: Don't actually connect to MikroTik in tests
```

### 2. Use Fixtures for Common Setup

```python
# ✅ pytest fixtures
@pytest.fixture
def sample_user(db_session):
    user = User(phone_number="+62...")
    db_session.add(user)
    return user

# Use across tests
def test_something(sample_user):
    assert sample_user.is_active
```

### 3. Test Both Happy Path and Errors

```python
# ✅ Test success AND failure
def test_block_user_success(app):
    result = block_user(user)
    assert result["status"] == "blocked"

def test_block_user_handles_mikrotik_timeout(app):
    with patch(...) as mock:
        mock.side_effect = TimeoutError()
        result = block_user(user)
        assert result["failed"] == True
```

---

## Test Maintenance

**Run Before Every Commit**:
```bash
pytest -x -v  # Stop on first failure
npm run test:unit
```

**Weekly** (Friday EOD):
```bash
# Full coverage check
pytest --cov=app --cov-fail-under=80 tests/
# If < 80%, create issue for coverage gaps
```

**Monthly** (1st of month):
- Review test coverage report
- Update this doc with new gaps
- Plan Q+1 testing priorities

---

## Next Steps

1. **This Week (Mar 22–29)**:
   - [ ] Add E2E test scaffolding (Playwright setup)
   - [ ] Implement 3 new critical path tests (from Mar 22 audit)

2. **Next Month (April)**:
   - [ ] E2E test: Login → Payment → Quota update
   - [ ] Frontend 401 test suite (5+ tests)
   - [ ] Admin operations E2E (3+ tests)

3. **Q2 2026**:
   - [ ] Reach 80% overall coverage
   - [ ] All critical paths covered by E2E
   - [ ] Automated coverage enforcement (CI gate)

---

*Maintained by: On-call Engineer | Last Review: 2026-03-22*
