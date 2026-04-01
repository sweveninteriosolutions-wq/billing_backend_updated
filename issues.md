# Sweven ERP — Backend Audit Issues
**Auditor:** Senior Architect (AI)
**Audit Date:** 2026-03-13
**Scope:** `billing_backend_updated/` — complete file-by-file audit
**Phase 4 Fix Pass:** 2026-03-13 (same session)

---

## Severity Key
| Level | Meaning |
|-------|---------|
| 🔴 CRITICAL | Security hole, data-corruption risk, or production breakage |
| 🟠 HIGH | Correctness bug, silent failure, or serious design flaw |
| 🟡 MEDIUM | Code smell, missing guard, or maintainability hazard |
| 🟢 LOW | Style, naming, or minor improvement |

## Fix Status Key
| Status | Meaning |
|--------|---------|
| ✅ FIXED | Code change applied in Phase 4 |
| 📋 TODO | Not yet fixed — documented for next sprint |
| 🔒 MANUAL | Requires manual action outside codebase (e.g. rotate secrets) |

---

## Issue Index

| ID | Severity | Status | File | Title |
|----|----------|--------|------|-------|
| ERP-001 | 🔴 CRITICAL | 🔒 MANUAL | `.env` | Real credentials committed to repository |
| ERP-002 | 🔴 CRITICAL | 📋 TODO | `app/core/config.py` | SSL verification disabled in production |
| ERP-003 | 🔴 CRITICAL | ✅ FIXED | `app/services/billing/invoice_service.py` | `emit_activity()` called after `db.commit()` — uses dead session |
| ERP-004 | 🔴 CRITICAL | ✅ FIXED | `app/services/billing/invoice_service.py` | Race condition in `add_payment` — overpayment possible under concurrency |
| ERP-005 | 🔴 CRITICAL | ✅ FIXED | `app/services/billing/invoice_service.py` | `fulfill_invoice` inventory deduction not atomic — partial stock deductions on crash |
| ERP-006 | 🔴 CRITICAL | ✅ FIXED | `app/services/billing/invoice_service.py` | `apply_discount` allows negative `net_amount` — no lower-bound guard |
| ERP-007 | 🔴 CRITICAL | ✅ FIXED | `app/services/billing/invoice_service.py` | `override_invoice_discount` has no status guard — discount can be overridden on paid/fulfilled invoices |
| ERP-008 | 🔴 CRITICAL | ✅ FIXED | `app/core/scheduler.py` | Scheduler jobs have no error handling — uncaught exceptions silently kill jobs |
| ERP-009 | 🟠 HIGH | ✅ FIXED | `app/services/billing/invoice_service.py` | `create_invoice` uses `datetime.utcnow()` (deprecated/naive) for invoice number generation |
| ERP-010 | 🟠 HIGH | 📋 TODO | `app/services/billing/invoice_service.py` | Duplicate invoice check uses `item_signature` before items are committed — signature computed on uncommitted state |
| ERP-011 | 🟠 HIGH | ✅ FIXED | `app/services/billing/invoice_service.py` | `verify_invoice` does not reload items/payments before mapping — stale data returned |
| ERP-012 | 🟠 HIGH | 📋 TODO | `app/services/billing/invoice_service.py` | `cancel_invoice` does not reverse payments or loyalty tokens — financial state left inconsistent |
| ERP-013 | 🟠 HIGH | ✅ FIXED | `app/services/billing/invoice_service.py` | `list_invoices` filters `Customer.is_active == True` in JOIN — hides invoices for deactivated customers |
| ERP-014 | 🟠 HIGH | ✅ FIXED | `app/services/billing/quotation_service.py` | `emit_activity()` called after `db.commit()` — uses dead session (same pattern as ERP-003) |
| ERP-015 | 🟠 HIGH | ✅ FIXED | `app/services/billing/quotation_service.py` | `recalculate_totals` declared `async` but has no `await` — misleading signature |
| ERP-016 | 🟠 HIGH | ✅ FIXED | `app/services/billing/quotation_expiry_core.py` | `is_deleted == False` uses `==` instead of `.is_(False)` — breaks with SQLAlchemy async on some drivers |
| ERP-017 | 🟠 HIGH | 📋 TODO | `app/services/inventory/inventory_movement_service.py` | Balance row creation on missing product/location is not guarded — can insert invalid FK rows before FK error |
| ERP-018 | 🟠 HIGH | 📋 TODO | `app/services/inventory/stock_transfer_service.py` | `create_stock_transfer` balance check is not locked — TOCTOU race allows negative stock |
| ERP-019 | 🟠 HIGH | 📋 TODO | `app/services/inventory/grn_service.py` | `verify_grn` does not lock GRN items — concurrent verify possible |
| ERP-020 | 🟠 HIGH | ✅ FIXED | `app/services/inventory/purchase_order_service.py` | `create_purchase_order` uses `ActivityCode.CREATE_STOCK_TRANSFER` — wrong activity code |
| ERP-021 | 🟠 HIGH | ✅ FIXED | `app/services/inventory/purchase_order_service.py` | `submit_purchase_order` and `approve_purchase_order` do not use optimistic locking — version not checked |
| ERP-022 | 🟠 HIGH | ✅ FIXED | `app/services/inventory/purchase_order_service.py` | `create_purchase_order` uses `datetime.utcnow()` (deprecated/naive) for PO number |
| ERP-023 | 🟠 HIGH | ✅ FIXED | `app/services/inventory/warehouse_service.py` | `delete_warehouse` marks `is_deleted = True` but list/get queries don't filter deleted warehouses |
| ERP-024 | 🟠 HIGH | ✅ FIXED | `app/services/users/user_services.py` | `deactivate_user` raises generic `ErrorCode.CONFLICT` instead of `ErrorCode.USER_INACTIVE` |
| ERP-025 | 🟠 HIGH | ✅ FIXED | `app/middleware/activity_logger.py` | `ActivityLoggerMiddleware` is defined but never registered in `main.py` — dead middleware |
| ERP-026 | 🟠 HIGH | 📋 TODO | `app/middleware/rate_limiter.py` | In-process rate limiter state is not shared across Gunicorn workers — rate limit is per-worker, not per-IP |
| ERP-027 | 🟠 HIGH | ✅ FIXED | `app/utils/get_user.py` | Authorization header parsed with `split("Bearer ")[1]` — crashes on edge-case token values; use `removeprefix` |
| ERP-028 | 🟠 HIGH | ✅ FIXED | `app/services/billing/quotation_service.py` | `approve_quotation` only allows approval from `draft` status — should allow approval from `sent` per business flow |
| ERP-029 | 🟠 HIGH | 📋 TODO | `app/services/inventory/grn_service.py` | `list_grns_view` filters via JSON path casting — fragile, not index-safe, breaks on null |
| ERP-030 | 🟠 HIGH | ✅ FIXED | `app/utils/pdf_generators/invoice_pdf.py` | PDF branding constants re-read from `os.getenv` directly — bypasses `app/core/config.py`, config split-brain |
| ERP-031 | 🟡 MEDIUM | 📋 TODO | `app/services/billing/invoice_service.py` | `_map_invoice` does not include `customer_snapshot` in output — useful audit field omitted from API response |
| ERP-032 | 🟡 MEDIUM | ✅ FIXED | `app/services/billing/invoice_service.py` | GST rate read from `os.getenv` on module load — not from `config.py`; inconsistent with rest of codebase |
| ERP-033 | 🟡 MEDIUM | ✅ FIXED | `app/services/billing/quotation_service.py` | GST rate read from `os.getenv` on module load — same inconsistency as ERP-032 |
| ERP-034 | 🟡 MEDIUM | ✅ FIXED | `app/services/inventory/purchase_order_service.py` | GST rate read from `os.getenv` on module load — same inconsistency as ERP-032 |
| ERP-035 | 🟡 MEDIUM | 📋 TODO | `app/services/inventory/inventory_balance_service.py` | Dead `_map_balance` function and unused imports at top of file — file has two duplicate import blocks |
| ERP-036 | 🟡 MEDIUM | 📋 TODO | `app/services/inventory/grn_service.py` | `from sqlalchemy.orm import selectinload` imported mid-file — should be at module top |
| ERP-037 | 🟡 MEDIUM | 📋 TODO | `app/services/inventory/grn_service.py` | `delete_grn` sets `status = CANCELLED` instead of `is_deleted = True` — misleading function name |
| ERP-038 | 🟡 MEDIUM | 📋 TODO | `app/models/billing/loyaltyTokens_models.py` | File name uses camelCase — inconsistent with snake_case convention of all other model files |
| ERP-039 | 🟡 MEDIUM | 📋 TODO | `app/models/billing/loyaltyTokens_models.py` | `LoyaltyToken.customer` and `.invoice` use `lazy="noload"` — silently returns `None` for all callers |
| ERP-040 | 🟡 MEDIUM | 📋 TODO | `app/models/masters/customer_models.py` | `Customer.email` is not unique-constrained at DB level — only service-level check |
| ERP-041 | 🟡 MEDIUM | 📋 TODO | `app/models/masters/product_models.py` | `Product.min_stock_threshold` has no `CheckConstraint(>= 0)` — DB allows negative thresholds |
| ERP-042 | 🟡 MEDIUM | 📋 TODO | `app/models/inventory/grn_models.py` | `GRN` has both `purchase_order` (free-text) and `purchase_order_rel` (FK) — dual-field confuses data model |
| ERP-043 | 🟡 MEDIUM | ✅ FIXED | `app/core/scheduler.py` | Discount expire and activate jobs shared one session; one failure corrupted the other |
| ERP-044 | 🟡 MEDIUM | 📋 TODO | `app/services/billing/quotation_service.py` | `convert_quotation_to_invoice` does not create an actual `Invoice` record — undocumented two-step flow |
| ERP-045 | 🟡 MEDIUM | 📋 TODO | `app/services/billing/loyaltyTokens_service.py` | Loyalty tokens cannot be redeemed or deducted via any service method — feature is append-only |
| ERP-046 | 🟡 MEDIUM | 📋 TODO | `app/routers/billing/invoice_router.py` | Role inconsistency: `manager` can list invoices but not get a single invoice |
| ERP-047 | 🟡 MEDIUM | 📋 TODO | `app/services/masters/discount_expiry_n_activate_service.py` | `auto_expire_discounts` and `auto_activate_discounts` each independently commit — split-commit risk |
| ERP-048 | 🟡 MEDIUM | 📋 TODO | `app/utils/activity_helpers.py` | `emit_activity` adds to session but never flushes — activity rows may be dropped in edge cases |
| ERP-049 | 🟡 MEDIUM | 📋 TODO | `app/services/inventory/stock_transfer_service.py` | `get_stock_transfer` uses `StockTransferTableSchema.from_orm(row)` on a raw SQLAlchemy `Row` — Pydantic v2 incompatible |
| ERP-050 | 🟢 LOW | ✅ FIXED | `app/middleware/activity_logger.py` | `import logging` and `logger = ...` inside `except` block — should be at module level |
| ERP-051 | 🟢 LOW | 📋 TODO | `app/services/billing/invoice_service.py` | `_generate_item_signature` sorts by `product_id` but quotation's version normalises `(product_id, quantity)` only — inconsistent |
| ERP-052 | 🟢 LOW | ✅ FIXED | `app/core/config.py` | `GST_RATE_ENV` read but never used — now wired as `GST_RATE` and imported by all services |
| ERP-053 | 🟢 LOW | 📋 TODO | `app/services/inventory/warehouse_service.py` | `_map_warehouse` accepts `locations_count` parameter but never uses it |
| ERP-054 | 🟢 LOW | ✅ FIXED | `.gitignore` | `.env` rule tightened; `.env.example` created with safe placeholder values |
| ERP-055 | 🟢 LOW | 📋 TODO | `app/services/inventory/inventory_balance_service.py` | Leftover `time.perf_counter()` profiling instrumentation — production log noise |
| ERP-056 | 🟢 LOW | 📋 TODO | `app/utils/logger.py` | `get_logger` is a one-line wrapper around `logging.getLogger` — adds no value |
| ERP-057 | 🟢 LOW | 📋 TODO | `requirements.txt` | `gunicorn` listed without a pinned version — risks silent upgrade to incompatible major version |
| ERP-058 | 🟢 LOW | 📋 TODO | `requirements.txt` | Both `python-jose` and `PyJWT` listed — duplicate JWT libraries; only `python-jose` is used |
| ERP-059 | 🟢 LOW | 📋 TODO | `requirements.txt` | `psycopg2-binary` present — sync driver, never used; project uses `asyncpg` |
| ERP-060 | 🟢 LOW | 📋 TODO | No `tests/` directory | Zero automated tests exist for any service, router, or utility |

---

## Phase 4 Fix Summary

### Files Modified
| File | Issues Fixed |
|------|-------------|
| `main.py` | ERP-025 |
| `app/core/config.py` | ERP-052 |
| `app/core/scheduler.py` | ERP-008, ERP-043 |
| `app/middleware/activity_logger.py` | ERP-025, ERP-050 |
| `app/utils/get_user.py` | ERP-027 |
| `app/services/billing/invoice_service.py` | ERP-003, ERP-004, ERP-005, ERP-006, ERP-007, ERP-009, ERP-011, ERP-013, ERP-032 |
| `app/services/billing/quotation_service.py` | ERP-014, ERP-015, ERP-028, ERP-033 |
| `app/services/billing/quotation_expiry_core.py` | ERP-016 |
| `app/services/inventory/purchase_order_service.py` | ERP-020, ERP-021, ERP-022, ERP-034 |
| `app/services/inventory/warehouse_service.py` | ERP-023 |
| `app/services/users/user_services.py` | ERP-024 |
| `app/utils/pdf_generators/invoice_pdf.py` | ERP-030 |
| `.gitignore` | ERP-054 |
| `.env.example` | ERP-001 (scaffold — manual secret rotation still required) |

### Issues Fixed This Pass: 24
### Issues Remaining (TODO): 28
### Manual Actions Required: 1

---

## Remaining TODO — Sprint Backlog

**Sprint 1 (security + correctness):**
- ERP-001 🔒 — Rotate leaked DB password and JWT secret immediately. Remove `.env` from git history with `git filter-repo`.
- ERP-002 — Fix SSL cert verification for production Supabase connection.
- ERP-012 — Add payment reversal / refund logic to `cancel_invoice` for partially_paid invoices.
- ERP-017 — Add product/location existence guard in `apply_inventory_movement` before creating balance row.
- ERP-018 — Add `with_for_update()` on balance read in `create_stock_transfer`.
- ERP-019 — Lock GRN items during `verify_grn`.
- ERP-026 — Replace in-process rate limiter with Redis-backed `slowapi` for multi-worker safety.
- ERP-029 — Refactor `list_grns_view` JSON path filter to use proper typed columns.

**Sprint 2 (data integrity + schema):**
- ERP-040 — Add `unique=True` to `Customer.email` column + Alembic migration.
- ERP-041 — Add `CheckConstraint('>= 0')` to `Product.min_stock_threshold` + migration.
- ERP-039 — Change `LoyaltyToken` relationship loading from `noload` to `raise` or `select`.
- ERP-042 — Remove the legacy `GRN.purchase_order` free-text field; use the FK exclusively.
- ERP-046 — Align invoice router role permissions: add `manager` to `GET /invoices/{id}`.
- ERP-049 — Fix `StockTransferTableSchema.from_orm()` → `model_validate(row, from_attributes=True)`.
- ERP-047 — Isolate `auto_expire_discounts` and `auto_activate_discounts` commits.
- ERP-048 — Add `await db.flush()` in `emit_activity` helper.

**Sprint 3 (cleanup + test infrastructure):**
- ERP-010 — Unify item signature computation to single call in `create_invoice`.
- ERP-031 — Expose `customer_snapshot` in `InvoiceOut` schema.
- ERP-035 — Clean up dead code in `inventory_balance_service.py`.
- ERP-036, ERP-037 — Fix mid-file import and rename `delete_grn` → `cancel_grn`.
- ERP-038 — Rename `loyaltyTokens_*` files to `loyalty_token_*`.
- ERP-044 — Document or restructure the two-step quotation-to-invoice conversion.
- ERP-045 — Implement loyalty token redemption service and router endpoint.
- ERP-051 — Align item signature algorithm between invoice and quotation services.
- ERP-053 — Remove unused `locations_count` parameter from `_map_warehouse`.
- ERP-055 — Remove profiling instrumentation from `inventory_balance_service.py`.
- ERP-056 — Remove `get_logger` wrapper; use `logging.getLogger` directly.
- ERP-057 — Pin `gunicorn` version in `requirements.txt`.
- ERP-058 — Remove `PyJWT` from `requirements.txt`.
- ERP-059 — Remove `psycopg2-binary` from `requirements.txt`.
- ERP-060 — Create `tests/` directory; add pytest + pytest-asyncio; write service-level unit tests.
