# Running the Test Suite

## Install test dependencies

```bash
cd billing_backend_updated
pip install pytest pytest-asyncio aiosqlite
# Or using requirements.txt (already includes pytest-asyncio==0.23.8):
pip install -r requirements.txt
```

## Run all tests

```bash
python -m pytest tests/ -v
```

## Run a specific module

```bash
python -m pytest tests/test_user_service.py -v
python -m pytest tests/test_quotation_service.py -v   # tests .returning() fix
python -m pytest tests/test_purchase_order_service.py -v  # tests BUG-3 fix
python -m pytest tests/test_grn_service.py -v         # tests BUG-4 fix
```

## Run with output on failure

```bash
python -m pytest tests/ -v --tb=short
```

## Environment

The test suite sets its own environment variables (APP_ENV=development, DB_TYPE=sqlite)
at the top of conftest.py — no .env file is needed to run tests.

All tests use an in-memory SQLite database. Each test is wrapped in a
SAVEPOINT that is rolled back after the test — no data persists between tests.

## Test coverage by module

| Module | Tests |
|--------|-------|
| user_services.py | 15 cases |
| customer_service.py | 11 cases |
| quotation_service.py | 18 cases (.returning() regression) |
| product_service.py | 14 cases |
| supplier_service.py | 13 cases |
| complaint_service.py | 15 cases |
| purchase_order_service.py | 14 cases (BUG-3 regression) |
| invoice_service.py | 19 cases |
| grn_service.py | 15 cases (BUG-4 regression) |
| **Total** | **134 cases** |

## What the mocks cover

`test_invoice_service.py::test_fulfill_invoice_success` and
`test_grn_service.py::test_verify_grn_success_mocked` both mock
`apply_inventory_movement` using `unittest.mock.AsyncMock`. This avoids
needing real InventoryBalance rows and lets the tests focus on the
invoice/GRN state machine logic.
