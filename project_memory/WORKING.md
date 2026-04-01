# WORKING.md — Varasidhi Furnitures ERP
# Long-Term Reference Documentation

---

## 1. SYSTEM ARCHITECTURE OVERVIEW

### 1.1 High-Level Architecture

```
Internet
    |
[Vercel CDN] ——> [React Frontend (Vite + TS + Tailwind)]
    |
[HTTPS / CORS]
    |
[FastAPI Backend (Uvicorn + Gunicorn)]
    |
    |——> [PostgreSQL @ Supabase] (primary data store)
    |——> [Local File Storage] (GRN bills, invoice PDFs)
    |——> [APScheduler] (quotation expiry, discount activation)
```

### 1.2 Backend Layer Architecture

```
Request
  |
[FastAPI Router]            <- Route declaration, auth dependency injection
  |
[Service Layer]             <- Business logic, transactions, validation
  |
[SQLAlchemy Async ORM]      <- Query construction, relationship loading
  |
[PostgreSQL (asyncpg)]      <- Persistent storage
```

### 1.3 Frontend Layer Architecture

```
[React Component / Page]
  |
[React Query (useQuery / useMutation)]
  |
[API Mutation/Query file]           <- src/mutations/ or src/queries/
  |
[API function file]                 <- src/api/*.api.ts
  |
[client.ts]                         <- fetch wrapper with JWT, refresh queue, error handling
  |
[FastAPI Backend]
```

---

## 2. MODULE DESCRIPTIONS

### 2.1 Authentication (app/routers/auth/, app/services/auth/)

**Purpose:** Secure login, token issuance, token refresh, logout.

**Flow:**
1. POST /auth/login -> validates credentials, issues access_token + refresh_token
2. POST /auth/refresh -> validates refresh token, issues new access_token + rotated refresh_token
3. POST /auth/logout -> revokes refresh token in DB

**Key Files:**
- app/services/auth/auth_service.py - login, refresh, logout logic
- app/core/security.py - JWT creation, verification, bcrypt
- app/models/users/user_models.py - User, RefreshToken models

**Security Notes:**
- bcrypt for all passwords
- token_version on User model invalidates all sessions on password change
- Refresh tokens stored hashed in refresh_tokens table
- Access tokens expire in 15 minutes (configurable)
- Admin access tokens expire in 60 minutes (configurable)

---

### 2.2 Invoice System (app/routers/billing/invoice_router.py)

**Purpose:** Complete billing lifecycle from draft to fulfillment with GST.

**Lifecycle:**
```
draft -> [verify] -> verified -> [payment(s)] -> partially_paid / paid
paid -> [fulfill] -> fulfilled
draft/verified/partially_paid -> [cancel] -> cancelled
```

**Key Features:**
- GST calculation (CGST+SGST for intra-state, IGST for inter-state)
- Discount application (with admin override and reason)
- Multiple payment methods per invoice
- Automatic inventory deduction on fulfillment
- Loyalty token award on fulfillment (1 token per 1000 rupees)
- Customer snapshot preserved on invoice (immutable customer data at time of billing)
- Item signature hash for duplicate detection
- Optimistic locking via version field

**API Endpoints:**
```
POST   /invoices              - Create invoice (admin, cashier)
GET    /invoices              - List invoices with pagination (admin, cashier)
GET    /invoices/{id}         - Get single invoice (admin, cashier)
PATCH  /invoices/{id}         - Update draft invoice items (admin only)
POST   /invoices/{id}/verify  - Verify invoice (admin only)
POST   /invoices/{id}/discount         - Apply discount (admin only)
POST   /invoices/{id}/override-discount - Override discount with reason (admin only)
POST   /invoices/{id}/payments - Record payment (admin, cashier)
POST   /invoices/{id}/fulfill  - Fulfill invoice + deduct inventory (admin only)
POST   /invoices/{id}/cancel   - Cancel invoice (admin only)
```

---

### 2.3 Quotation System (app/routers/billing/quotation_router.py)

**Purpose:** Pre-invoice estimates sent to customers with validity period.

**Lifecycle:**
```
draft -> [send] -> sent -> [approve] -> approved -> [convert] -> invoiced
draft/sent/approved -> [cancel] -> cancelled
(APScheduler auto-expires quotations past valid_until date)
```

---

### 2.4 Inventory System

**Models:**
- InventoryLocation: Physical locations (warehouse, showroom, etc.)
- InventoryBalance: Current stock quantity per product per location
- InventoryMovement: Immutable ledger of all stock changes (STOCK_IN, STOCK_OUT, TRANSFER_IN, TRANSFER_OUT, ADJUSTMENT)
- StockTransfer: Movement request between two locations

**Key Rule:** Every stock change must be recorded as an InventoryMovement. Direct balance updates without a movement entry are not allowed.

**Low Stock Detection:** Products with InventoryBalance.quantity < Product.min_stock_threshold are "low stock".

---

### 2.5 GRN System (Goods Receipt Note)

**Purpose:** Record goods received from suppliers, update inventory.

**Lifecycle:** draft -> verified -> (inventory updated) / cancelled

**File Attachments:** GRN supports a bill_file field. File uploads are stored in uploads/grn/ directory with metadata in file_uploads table.

---

### 2.6 Supplier Management

**Fields:** supplier_code, name, contact_person, phone, email, address, gstin
**Relationships:** Suppliers link to Products (default supplier) and GRNs (goods receipts)

---

### 2.7 Purchase Order System (NEW - Added in this upgrade)

**Purpose:** Formal order to supplier before goods are received.

**Lifecycle:**
```
draft -> [submit] -> pending_approval -> [approve] -> approved -> [receive via GRN] -> partially_received / received
draft/pending_approval/approved -> [cancel] -> cancelled
```

**Models:** PurchaseOrder, PurchaseOrderItem

**Key Fields:**
- supplier_id: Which supplier
- expected_delivery_date: When goods are expected
- approved_by_id: User who approved the PO
- grn_id: Linked GRN when goods arrive

---

### 2.8 Warehouse System (NEW - Added in this upgrade)

**Purpose:** Formal warehouse entities that InventoryLocations belong to.

**Model: Warehouse**
- id, code, name, address, city, state, pincode, gstin
- location_type: WAREHOUSE / SHOWROOM / TRANSIT
- is_active

**Relationship:** InventoryLocation now has warehouse_id FK pointing to Warehouse.

**Default Warehouse:** "Main Warehouse" (code: MAIN-WH) is seeded as default.

---

### 2.9 File Upload System (NEW - Added in this upgrade)

**Purpose:** Track all uploaded files with metadata.

**Storage Structure:**
```
uploads/
  grn/          <- GRN bill images
  supplier/     <- Supplier invoice images
  invoices/     <- Generated invoice PDFs
```

**Model: FileUpload**
- entity_type: GRN / SUPPLIER_INVOICE / INVOICE_PDF
- entity_id: FK to the related record
- original_filename
- storage_path: Path on disk
- mime_type
- file_size_bytes

**Upload Endpoint:** POST /uploads/{entity_type}/{entity_id}
**Supported formats:** jpg, jpeg, png, pdf
**Max size:** 10MB

---

### 2.10 Discount Management

**Purpose:** Time-bound discounts automatically activated and expired by scheduler.

**Types:** percentage or flat amount
**Scheduler:** Runs every minute in development, configurable in production.

---

### 2.11 Loyalty Token System

**Purpose:** Reward customers for purchases. 1 token awarded per 1000 rupees of invoice value at fulfillment.

---

### 2.12 Activity Log (Audit Trail)

**Model:** UserActivity
**Design:** Immutable, append-only. Records are NEVER updated or deleted.
**Captures:** user_id, username_snapshot, message, created_at

Used to track all significant business events: invoice creation, payment, fulfillment, GRN verification, stock transfers, etc.

---

## 3. DATABASE RELATIONSHIPS

```
User
  |-> RefreshToken (1:N)
  |-> created records via AuditMixin (polymorphic)

Customer
  |-> Quotation (1:N)
  |-> Invoice (1:N)
  |-> LoyaltyToken (1:N)
  |-> Complaint (1:N)

Invoice
  |-> InvoiceItem (1:N, cascade delete)
  |-> Payment (1:N, cascade delete)
  |-> LoyaltyToken (1:N)
  |-> Quotation (N:1, optional)

Quotation
  |-> QuotationItem (1:N, cascade delete)
  |-> Invoice (1:N, optional)

Supplier
  |-> Product (1:N, default supplier)
  |-> GRN (1:N)
  |-> PurchaseOrder (1:N)  [NEW]

Product
  |-> InventoryBalance (1:N, per location)
  |-> InventoryMovement (1:N)
  |-> InvoiceItem (1:N)
  |-> QuotationItem (1:N)
  |-> GRNItem (1:N)
  |-> PurchaseOrderItem (1:N)  [NEW]

Warehouse  [NEW]
  |-> InventoryLocation (1:N)

InventoryLocation
  |-> InventoryBalance (1:N)
  |-> InventoryMovement (1:N)
  |-> GRN (1:N)
  |-> Warehouse (N:1)  [NEW]

GRN
  |-> GRNItem (1:N, cascade delete)
  |-> Supplier (N:1)
  |-> InventoryLocation (N:1)
  |-> PurchaseOrder (N:1, optional)  [NEW]
  |-> FileUpload (1:N)  [NEW]

PurchaseOrder  [NEW]
  |-> PurchaseOrderItem (1:N, cascade delete)
  |-> Supplier (N:1)
  |-> GRN (1:N, optional)

StockTransfer
  |-> Product (N:1)
  |-> InventoryLocation from (N:1)
  |-> InventoryLocation to (N:1)

FileUpload  [NEW]
  |-> Polymorphic: GRN / Supplier / Invoice
```

---

## 4. BACKEND API STRUCTURE

### 4.1 Router Groups

```
/auth/*          - Login, refresh, logout
/users/*         - User CRUD (admin only)
/activity/*      - Activity log (admin only)
/customers/*     - Customer CRUD
/suppliers/*     - Supplier CRUD
/products/*      - Product CRUD
/discounts/*     - Discount management
/inventory/balances/*     - Stock balance per location
/inventory/locations/*    - Location management
/inventory/movements/*    - Movement ledger (read-only)
/inventory/low-stock      - Products below threshold [NEW]
/grns/*          - GRN management
/stock-transfers/*        - Transfer management
/quotations/*    - Quotation lifecycle
/invoices/*      - Invoice lifecycle
/payments/*      - Payment management
/loyalty-tokens/*         - Token management
/complaints/*    - Complaint management
/purchase-orders/*        - PO management [NEW]
/warehouses/*    - Warehouse management [NEW]
/uploads/*       - File upload [NEW]
/reports/*       - Sales and inventory reports [NEW]
```

### 4.2 Standard Response Format

All endpoints return:
```json
{
  "success": true,
  "message": "...",
  "data": { ... }
}
```

Errors return:
```json
{
  "success": false,
  "message": "Human-readable message",
  "error_code": "MACHINE_READABLE_CODE",
  "details": null
}
```

### 4.3 Pagination Pattern

List endpoints accept: page (default 1), page_size (default 20, max 100)

Response includes: total, items[]

---

## 5. FRONTEND FOLDER STRUCTURE

```
src/
  api/                   <- API function files (one per backend module)
  components/
    layout/              <- MainLayout, Navbar, Sidebar
    navigation/          <- Breadcrumbs
    ui/                  <- shadcn/ui components
  errors/                <- Error boundary, error types, error mapper
  hooks/                 <- Custom React hooks
  lib/                   <- Utility functions, API base
  modules/
    admin/               <- Users, Activity Log, Discounts
    billing/             <- Customers, Quotations, Invoices, Payments
    dashboard/           <- Role-based dashboards
    inventory/           <- Products, Suppliers, GRN, Stock Transfer, Locations
    reports/             <- Sales reports, inventory reports
  mutations/             <- React Query mutation hooks (one per module)
  providers/             <- Auth, Query, Theme, Toast providers
  queries/               <- React Query query hooks (one per module)
  routes/                <- Route guards (RequireAuth)
  types/                 <- TypeScript interfaces matching backend schemas
  utils/                 <- formatDate, formatMoney, buildQueryParams
```

---

## 6. DEPLOYMENT ARCHITECTURE

### 6.1 Current

```
Frontend: Vercel (auto-deploy from git)
Backend:  Not deployed (needs deployment host)
Database: Supabase PostgreSQL (managed)
```

### 6.2 Recommended Production Setup

```
Frontend:  Vercel (current, keep)
Backend:   Railway / Render / DigitalOcean App Platform
           Docker container: uvicorn + gunicorn
Database:  Supabase PostgreSQL (current, keep)
Files:     Local disk (container) or upgrade to S3/Supabase Storage
```

### 6.3 Environment Variables Required

```
APP_ENV                          = production
APP_VERSION                      = 1.x.x
DATABASE_URL                     = postgresql+asyncpg://...
DB_TYPE                          = postgres
JWT_ACCESS_SECRET_KEY            = [RANDOM 256-bit secret - NOT the Supabase anon key]
ACCESS_TOKEN_EXPIRE_MINUTES      = 15
ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS        = 7
CORS_ORIGINS                     = https://your-frontend.vercel.app
ENABLE_SCHEDULER                 = true
UPLOAD_DIR                       = /app/uploads
GST_RATE                         = 0.18
```

### 6.4 Docker Setup

Dockerfile is located at: billing_backend_updated/Dockerfile

Build:  docker build -t varasidhi-erp-backend .
Run:    docker run -p 8000:8000 --env-file .env varasidhi-erp-backend

---

## 7. MAINTENANCE GUIDELINES

### 7.1 Database Migrations

- All schema changes must be done via Alembic migrations
- NEVER drop columns or tables in production
- Always add columns with nullable=True or a default value
- Migration files live in: alembic/versions/
- Generate: alembic revision --autogenerate -m "description"
- Apply: alembic upgrade head
- Rollback: alembic downgrade -1

### 7.2 Adding a New Module

1. Create model in app/models/{domain}/{name}_models.py
2. Import model in app/models/__init__.py
3. Create schema in app/schemas/{domain}/{name}_schemas.py
4. Create service in app/services/{domain}/{name}_service.py
5. Create router in app/routers/{domain}/{name}_router.py
6. Register router in app/routers/__init__.py
7. Include router in main.py
8. Create Alembic migration if schema changed
9. Add API function in frontend src/api/{name}.api.ts
10. Add query/mutation hooks in src/queries/ and src/mutations/
11. Add TypeScript types in src/types/{name}.ts
12. Create page component in src/modules/{domain}/pages/
13. Add route in src/App.tsx

### 7.3 Adding New User Roles

Roles are enforced via require_role() in routers.
Current roles: admin, cashier, manager, inventory

To add a role:
1. Update require_role calls in relevant routers
2. Update frontend role checks in RequireAuth.tsx
3. Update sidebar visibility in Sidebar.tsx

### 7.4 Scheduler Jobs

Located in: app/services/{domain}/*_service.py and app/core/scheduler.py

Current jobs:
- Quotation expiry check (every hour)
- Discount activation check (every minute)
- Discount expiry check (every minute)

Adding a new scheduled job:
1. Create core function in app/services/{domain}/{name}_core.py
2. Register job in app/core/scheduler.py

---

## 8. FUTURE SCALABILITY STRATEGY

### 8.1 Short-Term (Next 3 months)

- Add Alembic migrations for all pending schema changes
- Deploy backend to Railway or Render
- Move file uploads to Supabase Storage (S3-compatible)
- Add Redis for frequently-read product catalog caching
- Add /api/v1/ versioning prefix

### 8.2 Medium-Term (3-12 months)

- Add Celery + Redis for background jobs (replace APScheduler)
- Add email notifications (invoice sent, low stock alert)
- Add barcode/QR scanning for product lookup on billing page
- Add customer portal (read-only invoice/payment history)
- Add multi-branch support (multiple showrooms)

### 8.3 Long-Term (12+ months)

- Add accounting module (ledger, P&L, balance sheet)
- Add HR module (staff, attendance, payroll)
- Add CRM module (lead tracking, follow-ups)
- Add mobile app (React Native with same API)
- Add data warehouse for analytics (separate read replica)

---

## 9. KNOWN ISSUES AND WORKAROUNDS

### Issue 1: fulfill_invoice hardcodes location_id=1 — ✅ FIXED
File: app/services/billing/invoice_service.py
Fix Applied: Now reads `DEFAULT_WAREHOUSE_LOCATION_ID` from config.py → .env
Set `DEFAULT_WAREHOUSE_LOCATION_ID=1` in .env (or the correct location ID for your main warehouse)

### Issue 2: Customer.invoices and Customer.quotations use selectin loading
File: app/models/masters/customer_models.py
Impact: Loading any customer record loads ALL their invoices and quotations
Workaround: Avoid fetching customers in loops
Fix: Change to lazy="dynamic" or remove relationship, use explicit queries

### Issue 3: invoice_pdf.py is broken — ✅ FIXED
File: app/utils/pdf_generators/invoice_pdf.py
Fix Applied: Complete rewrite with correct model imports, correct field names, branded GST template.

### Issue 4: JWT_ACCESS_SECRET_KEY is Supabase anon key — ⚠️ NOT YET FIXED
Impact: Tokens could theoretically be forged if attacker knows the key
Fix: Generate a proper random secret: python -c "import secrets; print(secrets.token_hex(32))"
     Update .env immediately — DO THIS BEFORE PRODUCTION USE

### Issue 5: New routes added to frontend App.tsx — ✅ FIXED
All 5 previously unrouted pages (Payments, Complaints, Reports, Warehouses) are now fully routed.

### Issue 6: Warehouse management had no router/service — ✅ FIXED
Full Warehouse CRUD implemented: model was ready, service + router + frontend page added.

### Issue 7: AdminDashboard used hardcoded mock data — ✅ FIXED
All dashboard metrics now come from live API endpoints.
