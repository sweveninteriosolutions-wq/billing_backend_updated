# 1. Architecture Overview
**Project:** Varasidhi Furnitures — ERP Billing & Inventory System  
**Audit Date:** 2026  
**Auditor:** Senior Architect / Security / Performance Review  

---

## 1. Current State

### System Overview
A two-tier web application:

- **Backend:** Python 3.11 + FastAPI (async) + SQLAlchemy 2.0 (async) + PostgreSQL (Supabase hosted)
- **Frontend:** React 18 + TypeScript + Vite + TanStack Query v5 + Tailwind/shadcn
- **Deployment Target:** Backend → Render/Railway (Docker container), Frontend → Vercel
- **Database:** Supabase PostgreSQL (asyncpg direct connection, no ORM cache)
- **Auth:** JWT HS256 + refresh token rotation (DB-stored refresh tokens)
- **Scheduler:** APScheduler (in-process, async) for quotation expiry + discount lifecycle
- **PDF Gen:** ReportLab (server-side, synchronous blocking)

### Structural Layout

```
billing_backend_updated/
  main.py                    — App factory, middleware registration, router mounting
  app/
    core/        — config, db engine, security, error handlers, logging, scheduler
    models/      — SQLAlchemy ORM models (billing, inventory, masters, users, support)
    routers/     — FastAPI routers grouped by domain
    services/    — Business logic layer (separate from routers)
    schemas/     — Pydantic v2 request/response schemas
    middleware/  — Rate limiter, activity logger, request logger
    utils/       — Auth guards, PDF generators, response helpers, activity helpers
    constants/   — Error codes, activity codes, movement types
    scripts/     — (utility scripts, not examined)

billing_frontend_updated/
  src/
    api/         — Typed fetch wrappers per domain (client.ts + domain.api.ts)
    providers/   — AuthProvider (session management), ThemeProvider
    queries/     — React Query read hooks (per domain)
    mutations/   — React Query write hooks (per domain)
    modules/     — Page components grouped by domain
    components/  — Shared UI components (layout, dialogs, tables)
    hooks/       — useConfirm, usePagination, useDebounce
    routes/      — RequireAuth guard
    types/       — TypeScript types per domain
    errors/      — ErrorBoundary, AppError, useGlobalError
```

### Domain Modules

| Domain | Backend Routes | Frontend Pages |
|---|---|---|
| Auth | /auth/login, /refresh, /logout | Login page |
| Users | /users | UsersPage |
| Customers | /customers | CustomersPage |
| Products | /products | ProductsPage |
| Suppliers | /suppliers | SuppliersPage |
| Quotations | /quotations | QuotationsPage |
| Invoices | /invoices + /pdf | InvoicesPage |
| Payments | /payments | PaymentsPage |
| Discounts | /discounts | DiscountsPage |
| Inventory Balances | /inventory-balances | InventoryBalancesPage |
| Inventory Locations | /inventory-locations | (settings) |
| Inventory Movements | /inventory-movements | InventoryMovementsPage |
| GRN | /grn | GRNPage |
| Stock Transfer | /stock-transfers | StockTransfersPage |
| Purchase Orders | /purchase-orders | PurchaseOrdersPage |
| Warehouses | /warehouses | WarehousesPage |
| Loyalty Tokens | /loyalty-tokens | LoyaltyTokensPage |
| Complaints | /complaints | ComplaintsPage |
| File Uploads | /files | (embedded in GRN dialog) |
| Reports | /reports/* | SalesReportPage |
| Activity Log | /activity | UserActivityPage |

---

## 2. Critical Issues

### ARCH-001 — No API Versioning
All routes are mounted at root (e.g., `/invoices`, `/auth/login`). There is no `/v1/` prefix. Any breaking API change will break all clients simultaneously with no migration window.

### ARCH-002 — Monolith Without Clear Boundaries
The application is a single FastAPI monolith. Domains (billing, inventory, masters) share the same DB session, same process, same scheduler. This is fine at this scale but the domain boundaries are logical only — no hard enforcement. Service files can import across domains freely (invoice_service imports inventory_movement_service).

### ARCH-003 — Scheduler Is In-Process, Single Instance Only
APScheduler runs inside the FastAPI process. When gunicorn starts multiple workers, each worker starts its own scheduler instance — quotation expiry and discount jobs will fire multiple times simultaneously. This can produce duplicate DB writes or race conditions.

### ARCH-004 — No Message Queue / Async Task Infrastructure
Long-running operations (PDF generation, inventory fulfillment loops) are executed synchronously in the request-response cycle. ReportLab PDF generation is entirely synchronous (blocking the event loop). There is no Celery, RQ, or async task queue.

### ARCH-005 — No Caching Layer
Zero caching (no Redis, no in-memory cache). Every request hits Supabase directly, including repeated lookups of static data (products, customers, warehouses). No cache-aside pattern, no response caching.

### ARCH-006 — Uploads Stored on Local Container Filesystem
Files (GRN attachments, generated PDFs) are written to `uploads/` inside the container (`/app/uploads/invoices`). On Render/Railway, containers are ephemeral — filesystem is wiped on every deploy or restart. All generated PDFs and uploaded files will be lost.

### ARCH-007 — No Environment Separation Beyond APP_ENV Flag
There is no staging environment configuration. The only separation is a single `APP_ENV` string. No separate staging DB, no staging secrets, no staging CORS.

---

## 3. Production Gaps

- No API versioning — breaking changes will have no migration path
- No background task queue — PDF generation blocks the event loop
- No persistent file storage — uploads lost on container restart
- No Redis — rate limiter is per-process only; scheduler fires per-worker
- No CDN — all static assets served from Vercel edge but API responses are uncached

---

## 4. Impact

- Container restart on Render = all PDFs and GRN attachments lost permanently
- Scaling to 2+ workers = scheduler runs duplicate jobs, rate limiter ineffective
- A bug in invoice endpoint takes down the entire ERP (single process)
- Any API change without versioning breaks the live frontend immediately

---

## 5. Recommended Fixes

1. **Add `/api/v1/` prefix** to all routers immediately. Update frontend client.ts BASE_URL.
2. **Move scheduler to a dedicated worker** (separate Render worker service with `--workers 1` and `ENABLE_SCHEDULER=true`). Disable scheduler in web workers.
3. **Move file storage to S3/Supabase Storage** — replace local `uploads/` writes with cloud object storage. Use pre-signed URLs for download.
4. **Wrap ReportLab PDF generation in `asyncio.run_in_executor`** to avoid blocking the async event loop.
5. **Add Redis** — use for rate limiter (slowapi) and optionally for caching hot read paths (product list, customer lookup).
