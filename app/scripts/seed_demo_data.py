"""
app/scripts/seed_demo_data.py
═══════════════════════════════════════════════════════════════════════════════
Varasidhi Furnitures — ERP Demo Data Seeder
Business scenario: furniture manufacturer/retailer in Bengaluru, Karnataka.
Covers full ERP flow: Supplier → PO → GRN → Inventory → Quotation → Invoice
                      → Payment → Fulfillment → Loyalty Tokens

Usage:
    python -m app.scripts.seed_demo_data

HARD RULES RESPECTED:
  ✔ Admin user NOT created (existing admin required)seed_demo_data
  ✔ All FK constraints honoured
  ✔ All CHECK constraints satisfied (GST breakup, payment consistency, etc.)
  ✔ flush() after each dependency group; single commit at end
  ✔ item_signature computed using same algorithm as service layer
  ✔ Inventory balances reflect final state (post GRN + transfers + fulfillment)
═══════════════════════════════════════════════════════════════════════════════
"""

import asyncio
import hashlib
import json
import logging
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.constants.grn import GRNStatus
from app.models.billing.invoice_models import Invoice, InvoiceItem
from app.models.billing.loyalty_token_models import LoyaltyToken
from app.models.billing.payment_models import Payment
from app.models.billing.quotation_models import Quotation, QuotationItem
from app.models.enums.complaint_status import ComplaintStatus, ComplaintPriority
from app.models.enums.invoice_status import InvoiceStatus
from app.models.enums.quotation_status import QuotationStatus
from app.models.enums.stock_transfer_status import TransferStatus
from app.models.inventory.grn_models import GRN, GRNItem
from app.models.inventory.inventory_balance_models import InventoryBalance
from app.models.inventory.inventory_location_models import InventoryLocation
from app.models.inventory.inventory_movement_models import InventoryMovement
from app.models.inventory.purchase_order_models import PurchaseOrder, PurchaseOrderItem
from app.models.inventory.stock_transfer_models import StockTransfer
from app.models.inventory.warehouse_models import Warehouse
from app.models.masters.customer_models import Customer
from app.models.masters.discount_models import Discount
from app.models.masters.product_models import Product
from app.models.masters.supplier_models import Supplier
from app.models.support.activity_models import UserActivity
from app.models.support.complaint_models import Complaint
from app.models.support.file_upload_models import FileUpload
from app.models.users.user_models import User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed_demo")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
GST_RATE   = Decimal("0.18")
CGST_RATE  = Decimal("0.09")   # half of 18 %
SGST_RATE  = Decimal("0.09")
Q2 = Decimal("0.01")           # quantize target


# ─────────────────────────────────────────────────────────────────────────────
# SIGNATURE HELPERS  (mirrors service-layer logic exactly)
# ─────────────────────────────────────────────────────────────────────────────

def _grn_sig(items: list[dict]) -> str:
    """Mirrors grn_service.generate_grn_item_signature()"""
    normalized = sorted(
        [
            {
                "product_id": i["product_id"],
                "quantity": int(i["quantity"]),
                "unit_cost": str(Decimal(str(i["unit_cost"])).quantize(Q2)),
            }
            for i in items
        ],
        key=lambda x: x["product_id"],
    )
    payload = json.dumps(normalized, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _quotation_sig(items: list[tuple]) -> str:
    """Mirrors quotation_service.generate_item_signature().
    items: list of (product_id, quantity)
    """
    normalized = sorted(f"{pid}:{qty}" for pid, qty in items)
    return hashlib.sha256("|".join(normalized).encode()).hexdigest()


def _invoice_sig(items: list[dict]) -> str:
    """Mirrors invoice_service._generate_item_signature().
    items: list of {'product_id': int, 'quantity': int, 'unit_price': Decimal}
    """
    sorted_items = sorted(items, key=lambda x: x["product_id"])
    raw = "|".join(
        f"{i['product_id']}:{i['quantity']}:{i['unit_price']}" for i in sorted_items
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _transfer_sig(product_id: int, quantity: int,
                  from_location_id: int, to_location_id: int) -> str:
    """Mirrors stock_transfer_service.generate_transfer_signature()"""
    payload = json.dumps(
        {
            "from": from_location_id,
            "product_id": product_id,
            "quantity": int(quantity),
            "to": to_location_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# GST CALCULATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _intra_gst(gross: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Intra-state: CGST + SGST each 9%, no IGST.
    Returns (cgst, sgst, igst, tax_total).
    Satisfies CHECK: (cgst_amount + sgst_amount + igst_amount) = tax_amount
    AND: is_inter_state = FALSE AND igst_amount = 0
    """
    cgst = (gross * CGST_RATE).quantize(Q2, rounding=ROUND_HALF_UP)
    sgst = (gross * SGST_RATE).quantize(Q2, rounding=ROUND_HALF_UP)
    igst = Decimal("0.00")
    tax  = cgst + sgst + igst
    return cgst, sgst, igst, tax


def _inter_gst(gross: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Inter-state: IGST 18%, no CGST/SGST.
    Returns (cgst, sgst, igst, tax_total).
    Satisfies CHECK: is_inter_state = TRUE AND igst_amount > 0
    AND cgst_amount = 0 AND sgst_amount = 0
    """
    cgst = Decimal("0.00")
    sgst = Decimal("0.00")
    igst = (gross * GST_RATE).quantize(Q2, rounding=ROUND_HALF_UP)
    tax  = igst
    return cgst, sgst, igst, tax


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

async def seed_demo_data() -> None:
    async with AsyncSessionLocal() as db:
        await _seed(db)


async def _seed(db: AsyncSession) -> None:  # noqa: C901 (complexity OK for seeder)
    log.info("═" * 66)
    log.info("  Varasidhi Furnitures — ERP Demo Data Seeder")
    log.info("═" * 66)

    # ─────────────────────────────────────────────────────────────────────
    # STEP 0 — FIND EXISTING ADMIN USER  (DO NOT CREATE)
    # ─────────────────────────────────────────────────────────────────────
    result = await db.execute(
        select(User)
        .where(User.role == "admin", User.is_active.is_(True))
        .order_by(User.id)
        .limit(1)
    )
    admin = result.scalar_one_or_none()
    if not admin:
        log.error("No active admin user found. Run create_admin.py first and retry.")
        sys.exit(1)
    A = admin.id          # admin_id shorthand
    log.info(f"✔  Admin user : {admin.username!r} (id={A})")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 1 — WAREHOUSES
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [1] Warehouses …")
    wh_main = Warehouse(
        code="WH-MAIN", name="Main Warehouse – Peenya",
        address="No. 45, Industrial Layout, Peenya",
        city="Bengaluru", state="Karnataka", pincode="560058",
        gstin="29VARAF0001A1Z5", phone="+91 80 2345 6789",
        location_type="WAREHOUSE", is_active=True, version=1,
        created_by_id=A,
    )
    wh_show = Warehouse(
        code="WH-SHOW", name="MG Road Showroom",
        address="No. 12, Brigade Road, MG Road",
        city="Bengaluru", state="Karnataka", pincode="560001",
        gstin="29VARAF0001A1Z5", phone="+91 80 4112 3456",
        location_type="SHOWROOM", is_active=True, version=1,
        created_by_id=A,
    )
    db.add_all([wh_main, wh_show])
    await db.flush()
    log.info(f"     ✔ wh_main={wh_main.id}  wh_show={wh_show.id}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 2 — INVENTORY LOCATIONS
    # NOTE: DEFAULT_WAREHOUSE_LOCATION_ID=1 (env). After seeding, update
    #       .env to match the actual ID of MAIN-GODOWN if it differs from 1.
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [2] Inventory Locations …")
    loc_godown = InventoryLocation(
        code="MAIN-GODOWN", name="Main Godown",
        is_active=True, version=1, warehouse_id=wh_main.id,
        created_by_id=A,
    )
    loc_showroom = InventoryLocation(
        code="SHOWROOM", name="Showroom Floor",
        is_active=True, version=1, warehouse_id=wh_show.id,
        created_by_id=A,
    )
    db.add_all([loc_godown, loc_showroom])
    await db.flush()
    L1 = loc_godown.id    # Primary / Godown location
    L2 = loc_showroom.id  # Showroom location
    log.info(f"     ✔ godown={L1}  showroom={L2}")
    if L1 != 1:
        log.warning(
            f"     ⚠ MAIN-GODOWN id={L1}. "
            f"Set DEFAULT_WAREHOUSE_LOCATION_ID={L1} in .env for fulfill_invoice to work."
        )

    # ─────────────────────────────────────────────────────────────────────
    # STEP 3 — SUPPLIERS
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [3] Suppliers …")
    _sup_rows = [
        dict(supplier_code="SUP-001", name="Karnataka Wood Works",
             contact_person="Ravi Kumar",    phone="+91 80 2345 1001",
             email="sales@karnatakawoodworks.com",
             address="Shivajinagar Industrial Area, Bengaluru, KA 560001",
             gstin="29KARWD0001B1Z9"),
        dict(supplier_code="SUP-002", name="Chennai Fabric & Foam House",
             contact_person="Venkat Swamy",  phone="+91 44 4567 8901",
             email="orders@chennaifabric.com",
             address="T. Nagar, Chennai, Tamil Nadu 600017",
             gstin="33CHFAB0002C1Z1"),
        dict(supplier_code="SUP-003", name="Mumbai Metal & Hardware Co.",
             contact_person="Nitin Shah",    phone="+91 22 6789 0123",
             email="supply@mumbaimetals.com",
             address="Kurla West, Mumbai, Maharashtra 400070",
             gstin="27MMBMT0003D1Z3"),
        dict(supplier_code="SUP-004", name="Hyderabad Glass & Mirror",
             contact_person="Salman Qureshi", phone="+91 40 2234 5678",
             email="info@hydglass.com",
             address="Secunderabad, Hyderabad, Telangana 500003",
             gstin="36HYDGM0004E1Z5"),
    ]
    sup_objs: list[Supplier] = []
    for d in _sup_rows:
        s = Supplier(**d, version=1, created_by_id=A)
        db.add(s)
        sup_objs.append(s)
    await db.flush()
    S1, S2, S3, S4 = [s.id for s in sup_objs]
    log.info(f"     ✔ S1={S1} S2={S2} S3={S3} S4={S4}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 4 — PRODUCTS  (15 furniture SKUs)
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [4] Products …")
    # (sku, hsn_code, name, category, price, supplier_id, description, min_threshold)
    _prod_rows = [
        ("SKU-001", 9403, "Teak King Bed Frame",          "Bedroom",  Decimal("25000"), S1,
         "Solid teak king-size bed frame with storage headboard", 2),
        ("SKU-002", 9403, "Teak Queen Bed Frame",         "Bedroom",  Decimal("18000"), S1,
         "Solid teak queen-size bed frame", 3),
        ("SKU-003", 9403, "Bedside Table – Teak",         "Bedroom",  Decimal("3500"),  S1,
         "Two-drawer bedside table, teak finish", 5),
        ("SKU-004", 9403, "Wardrobe 3-Door Sliding",      "Bedroom",  Decimal("22000"), S1,
         "3-door sliding wardrobe with centre mirror panel", 2),
        ("SKU-005", 9401, "L-Shape Sofa 5-Seater",        "Living",   Decimal("35000"), S2,
         "Premium velvet-fabric L-shape sofa with chaise", 2),
        ("SKU-006", 9403, "Walnut Coffee Table",          "Living",   Decimal("8500"),  S3,
         "Solid walnut top coffee table with hairpin steel legs", 3),
        ("SKU-007", 9403, "Engineered Wood TV Unit 180cm","Living",   Decimal("12000"), S3,
         "180 cm TV unit with push-open drawers and shelf", 3),
        ("SKU-008", 9403, "Solid Wood Bookshelf 5-Shelf", "Study",    Decimal("6500"),  S1,
         "5-shelf solid sheesham bookshelf, open design", 3),
        ("SKU-009", 9403, "6-Seater Dining Table",        "Dining",   Decimal("28000"), S1,
         "6-seater sheesham solid-wood dining table", 2),
        ("SKU-010", 9401, "Dining Chair Set of 6",        "Dining",   Decimal("15000"), S2,
         "Cushioned fabric dining chairs – set of 6", 2),
        ("SKU-011", 9403, "Executive Office Desk",        "Office",   Decimal("18500"), S1,
         "L-shaped executive desk with pedestal drawers", 2),
        ("SKU-012", 9401, "Ergonomic Office Chair",       "Office",   Decimal("8000"),  S2,
         "High-back ergonomic mesh chair with lumbar support", 5),
        ("SKU-013", 9403, "4-Drawer Filing Cabinet",      "Office",   Decimal("9500"),  S3,
         "Steel 4-drawer vertical filing cabinet, black", 3),
        ("SKU-014", 7009, "Full-Length Dressing Mirror",  "Bedroom",  Decimal("4500"),  S4,
         "Free-standing full-length mirror, antique gold frame", 5),
        ("SKU-015", 9403, "Oval Glass-Top Center Table",  "Living",   Decimal("11000"), S3,
         "Oval tempered-glass top center table with chrome legs", 3),
    ]
    prod_objs: list[Product] = []
    for sku, hsn, name, cat, price, sup_id, desc, thresh in _prod_rows:
        p = Product(
            sku=sku, hsn_code=hsn, name=name, category=cat, price=price,
            supplier_id=sup_id, description=desc,
            min_stock_threshold=thresh, version=1,
            created_by_id=A,
        )
        db.add(p)
        prod_objs.append(p)
    await db.flush()
    # P[1] .. P[15]  map to product IDs
    P: dict[int, int] = {i + 1: prod_objs[i].id for i in range(15)}
    log.info(f"     ✔ Products: {list(P.values())}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 5 — PURCHASE ORDERS
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [5] Purchase Orders …")

    # (product_idx, qty_ordered, unit_cost)
    _po1_items = [
        (1,  5,  Decimal("20000")),
        (2,  8,  Decimal("14000")),
        (3,  15, Decimal("2800")),
        (4,  6,  Decimal("17500")),
        (8,  10, Decimal("5200")),
        (9,  4,  Decimal("22000")),
        (11, 6,  Decimal("15000")),
    ]
    _po2_items = [
        (5,  10, Decimal("28000")),
        (10, 8,  Decimal("12000")),
        (12, 15, Decimal("6500")),
    ]
    _po3_items = [
        (6,  12, Decimal("6800")),
        (7,  10, Decimal("9500")),
        (13, 8,  Decimal("7500")),
        (15, 7,  Decimal("8800")),
    ]
    _po4_items = [
        (14, 20, Decimal("3600")),
    ]

    def _po_totals(items):
        gross = sum(qty * cost for _, qty, cost in items)
        tax   = (gross * GST_RATE).quantize(Q2, rounding=ROUND_HALF_UP)
        net   = gross + tax
        return gross, tax, net

    def _make_po(num, sup_id, items, status, version, exp_date, notes):
        g, t, n = _po_totals(items)
        return PurchaseOrder(
            po_number=num, supplier_id=sup_id, location_id=L1,
            status=status, expected_date=exp_date, notes=notes,
            gross_amount=g, tax_amount=t, net_amount=n,
            version=version, approved_by_id=A,
            created_by_id=A, updated_by_id=A,
        )

    po1 = _make_po("PO-2024-001", S1, _po1_items, "approved",  3, date(2024, 2, 10),
                   "Bedroom & study collection — Q1 restock")
    po2 = _make_po("PO-2024-002", S2, _po2_items, "fulfilled", 4, date(2024, 2, 15),
                   "Sofas and chairs — full batch")
    po3 = _make_po("PO-2024-003", S3, _po3_items, "fulfilled", 4, date(2024, 2, 20),
                   "Living/dining tables and filing cabinets")
    po4 = _make_po("PO-2024-004", S4, _po4_items, "fulfilled", 4, date(2024, 2, 25),
                   "Full-length mirror range")
    db.add_all([po1, po2, po3, po4])
    await db.flush()

    # PO items
    for po_obj, raw_items in [(po1, _po1_items), (po2, _po2_items),
                               (po3, _po3_items), (po4, _po4_items)]:
        for pidx, qty, cost in raw_items:
            db.add(PurchaseOrderItem(
                po_id=po_obj.id, product_id=P[pidx],
                quantity_ordered=qty, quantity_received=qty,   # fully received
                unit_cost=cost, line_total=(qty * cost),
            ))
    await db.flush()
    log.info(f"     ✔ PO ids: {po1.id}, {po2.id}, {po3.id}, {po4.id}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 6 — GRNs  (status = VERIFIED — inventory already consumed)
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [6] GRNs (VERIFIED) …")

    def _grn_items_dicts(raw_items):
        return [{"product_id": P[pidx], "quantity": qty, "unit_cost": cost}
                for pidx, qty, cost in raw_items]

    g1_items = _grn_items_dicts(_po1_items)
    g2_items = _grn_items_dicts(_po2_items)
    g3_items = _grn_items_dicts(_po3_items)
    g4_items = _grn_items_dicts(_po4_items)

    grn1 = GRN(
        supplier_id=S1, location_id=L1, purchase_order_id=po1.id,
        purchase_order="PO-2024-001",
        bill_number="BILL-KWW-0124", notes="Bedroom collection – fully received",
        status=GRNStatus.VERIFIED, version=2,
        item_signature=_grn_sig(g1_items),
        created_by_id=A, updated_by_id=A,
    )
    grn2 = GRN(
        supplier_id=S2, location_id=L1, purchase_order_id=po2.id,
        purchase_order="PO-2024-002",
        bill_number="BILL-CFF-0124", notes="Sofas and chairs – fully received",
        status=GRNStatus.VERIFIED, version=2,
        item_signature=_grn_sig(g2_items),
        created_by_id=A, updated_by_id=A,
    )
    grn3 = GRN(
        supplier_id=S3, location_id=L1, purchase_order_id=po3.id,
        purchase_order="PO-2024-003",
        bill_number="BILL-MMH-0124", notes="Tables and filing cabinets",
        status=GRNStatus.VERIFIED, version=2,
        item_signature=_grn_sig(g3_items),
        created_by_id=A, updated_by_id=A,
    )
    grn4 = GRN(
        supplier_id=S4, location_id=L1, purchase_order_id=po4.id,
        purchase_order="PO-2024-004",
        bill_number="BILL-HGM-0124", notes="Mirror range received",
        status=GRNStatus.VERIFIED, version=2,
        item_signature=_grn_sig(g4_items),
        created_by_id=A, updated_by_id=A,
    )
    db.add_all([grn1, grn2, grn3, grn4])
    await db.flush()

    for grn_obj, items_list in [
        (grn1, g1_items), (grn2, g2_items),
        (grn3, g3_items), (grn4, g4_items),
    ]:
        for itm in items_list:
            db.add(GRNItem(
                grn_id=grn_obj.id, product_id=itm["product_id"],
                quantity=itm["quantity"], unit_cost=itm["unit_cost"],
            ))
    await db.flush()
    log.info(f"     ✔ GRN ids: {grn1.id}, {grn2.id}, {grn3.id}, {grn4.id}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 7 — CUSTOMERS  (10 customers, mix of B2C and B2B)
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [7] Customers …")
    _cust_rows = [
        ("CUST-001", "Rajesh Kumar",           "rajesh.kumar@gmail.com",
         "+91 98765 43210", {"line1": "12, Sadashivanagar", "city": "Bengaluru",
                              "state": "Karnataka", "pincode": "560080"}, None),
        ("CUST-002", "Priya Sharma",            "priya.sharma@gmail.com",
         "+91 99876 54321", {"line1": "34, Koramangala 5th Block", "city": "Bengaluru",
                              "state": "Karnataka", "pincode": "560095"}, None),
        ("CUST-003", "Arjun Enterprises",       "purchase@arjunenterprises.com",
         "+91 80 4567 8901", {"line1": "88, Industrial Estate, Peenya", "city": "Bengaluru",
                               "state": "Karnataka", "pincode": "560058"}, "29ARJNE0003F1Z2"),
        ("CUST-004", "Meena Reddy",             "meena.reddy@yahoo.com",
         "+91 94400 12345", {"line1": "7-1-397, Ameerpet", "city": "Hyderabad",
                              "state": "Telangana", "pincode": "500016"}, None),
        ("CUST-005", "Tech Solutions Pvt Ltd",  "admin@techsolutions.in",
         "+91 80 3456 7890", {"line1": "45, Whitefield Road, ITPL", "city": "Bengaluru",
                               "state": "Karnataka", "pincode": "560066"}, "29TKSOL0005G1Z0"),
        ("CUST-006", "Suresh Patel",            "suresh.patel@hotmail.com",
         "+91 97890 67890", {"line1": "23, JP Nagar 6th Phase", "city": "Bengaluru",
                              "state": "Karnataka", "pincode": "560078"}, None),
        ("CUST-007", "Lakshmi Interiors",       "billing@lakshmiinteriors.com",
         "+91 80 2890 5678", {"line1": "101, Commercial Street", "city": "Bengaluru",
                               "state": "Karnataka", "pincode": "560001"}, "29LKINT0007H1Z8"),
        ("CUST-008", "Deepak Mehta",            "deepak.mehta@rediffmail.com",
         "+91 96300 23456", {"line1": "56, Malleswaram 15th Cross", "city": "Bengaluru",
                              "state": "Karnataka", "pincode": "560055"}, None),
        ("CUST-009", "Green Homes Pvt Ltd",     "purchase@greenhomes.co.in",
         "+91 80 5678 9012", {"line1": "200, Bannerghatta Road", "city": "Bengaluru",
                               "state": "Karnataka", "pincode": "560076"}, "29GRHNM0009I1Z6"),
        ("CUST-010", "Venkat & Sons",           "venkat.sons@gmail.com",
         "+91 98456 78901", {"line1": "67, Chamrajpet Main Road", "city": "Bengaluru",
                              "state": "Karnataka", "pincode": "560018"}, None),
    ]
    cust_objs: list[Customer] = []
    for code, name, email, phone, addr, gstin in _cust_rows:
        c = Customer(
            customer_code=code, name=name, email=email, phone=phone,
            address=addr, gstin=gstin, is_active=True,
            version=1, created_by_id=A,
        )
        db.add(c)
        cust_objs.append(c)
    await db.flush()
    C: dict[int, int] = {i + 1: cust_objs[i].id for i in range(10)}
    log.info(f"     ✔ Customers: {list(C.values())}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 8 — DISCOUNTS
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [8] Discounts …")
    disc_objs = [
        Discount(name="Summer Sale 2024", code="SUMMER24",
                 discount_type="percentage", discount_value=Decimal("10.00"),
                 is_active=True, start_date=date(2024, 4, 1), end_date=date(2024, 6, 30),
                 usage_limit=100, used_count=23, note="10 % off all furniture",
                 created_by_id=A),
        Discount(name="Flat 2000 Off", code="FLAT2000",
                 discount_type="flat", discount_value=Decimal("2000.00"),
                 is_active=True, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
                 usage_limit=50, used_count=12, note="₹2,000 off on orders above ₹20,000",
                 created_by_id=A),
        Discount(name="New Year Special", code="NEWYEAR24",
                 discount_type="flat", discount_value=Decimal("5000.00"),
                 is_active=False, start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
                 usage_limit=20, used_count=20, note="Expired new-year promotion",
                 created_by_id=A),
        Discount(name="Bulk B2B Discount", code="BULK15",
                 discount_type="percentage", discount_value=Decimal("15.00"),
                 is_active=True, start_date=date(2024, 3, 1), end_date=date(2024, 12, 31),
                 usage_limit=None, used_count=5, note="15 % for bulk B2B orders",
                 created_by_id=A),
    ]
    db.add_all(disc_objs)
    await db.flush()
    log.info(f"     ✔ Discounts: {[d.id for d in disc_objs]}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 9 — QUOTATIONS  (8 quotations, various statuses)
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [9] Quotations …")

    def _make_quotation(qnum, cid, raw_items, status, is_inter, version,
                        valid_until, description, notes):
        """raw_items: list of (product_idx, qty, unit_price)"""
        subtotal = sum(qty * price for _, qty, price in raw_items)
        cgst, sgst, igst, tax = (
            _inter_gst(subtotal) if is_inter else _intra_gst(subtotal)
        )
        total  = subtotal + tax
        sig    = _quotation_sig([(P[pidx], qty) for pidx, qty, _ in raw_items])
        return Quotation(
            quotation_number=qnum, customer_id=cid,
            status=status, is_inter_state=is_inter,
            subtotal_amount=subtotal, tax_amount=tax, total_amount=total,
            cgst_rate=(Decimal("9.00")  if not is_inter else Decimal("0.00")),
            sgst_rate=(Decimal("9.00")  if not is_inter else Decimal("0.00")),
            igst_rate=(Decimal("18.00") if is_inter     else Decimal("0.00")),
            cgst_amount=cgst, sgst_amount=sgst, igst_amount=igst,
            valid_until=valid_until, version=version,
            description=description, notes=notes,
            item_signature=sig,
            created_by_id=A, updated_by_id=A,
        )

    # (qnum, cid, raw_items, status, is_inter, version, valid_until, description, notes)
    _quot_specs = [
        ("QT-2024-001", C[1],
         [(1, 1, Decimal("25000")), (3, 2, Decimal("3500"))],
         QuotationStatus.approved, False, 3, date(2024, 12, 31),
         "King bed + 2 bedside tables", "Approved by customer via phone call"),

        ("QT-2024-002", C[2],
         [(5, 1, Decimal("35000")), (6, 1, Decimal("8500"))],
         QuotationStatus.converted_to_invoice, False, 4, date(2024, 12, 31),
         "L-shape sofa + walnut coffee table", "Converted to invoice INV-2024-002"),

        ("QT-2024-003", C[3],
         [(2, 2, Decimal("18000")), (4, 1, Decimal("22000")), (3, 4, Decimal("3500"))],
         QuotationStatus.sent, False, 2, date(2024, 12, 31),
         "2x Queen beds + wardrobe + 4 bedside tables", "Awaiting customer sign-off"),

        ("QT-2024-004", C[5],
         [(11, 3, Decimal("18500")), (12, 5, Decimal("8000"))],
         QuotationStatus.draft, False, 1, date(2024, 12, 31),
         "Office furniture bulk order – 3 desks + 5 chairs", None),

        ("QT-2024-005", C[6],
         [(9, 1, Decimal("28000")), (10, 1, Decimal("15000"))],
         QuotationStatus.expired, False, 2, date(2024, 1, 31),
         "6-seater dining set combo", "Expired — customer became unresponsive"),

        ("QT-2024-006", C[7],
         [(7, 2, Decimal("12000")), (8, 3, Decimal("6500"))],
         QuotationStatus.approved, False, 3, date(2024, 12, 31),
         "TV units and bookshelves for showroom fit-out", None),

        ("QT-2024-007", C[4],
         [(14, 3, Decimal("4500"))],
         QuotationStatus.sent, True, 2, date(2024, 12, 31),
         "Full-length mirrors – inter-state to Hyderabad", "Awaiting purchase order"),

        ("QT-2024-008", C[8],
         [(15, 2, Decimal("11000"))],
         QuotationStatus.cancelled, False, 2, date(2024, 12, 31),
         "Oval center tables", "Cancelled — customer sourced locally"),
    ]

    quot_objs: list[tuple[Quotation, list]] = []
    for args in _quot_specs:
        qnum, cid, raw_items, *rest = args
        q = _make_quotation(qnum, cid, raw_items, *rest)
        db.add(q)
        quot_objs.append((q, raw_items))
    await db.flush()

    for q_obj, raw_items in quot_objs:
        for pidx, qty, unit_price in raw_items:
            prod = prod_objs[pidx - 1]
            db.add(QuotationItem(
                quotation_id=q_obj.id, product_id=P[pidx],
                product_name=prod.name,
                hsn_code=prod.hsn_code,           # NOT NULL
                quantity=qty, unit_price=unit_price,
                line_total=(qty * unit_price),
                created_by_id=A,
            ))
    await db.flush()
    log.info(f"     ✔ Quotations: {[q.id for q, _ in quot_objs]}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 10 — INVOICES  (8 invoices spanning all statuses)
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [10] Invoices …")

    def _make_invoice(inv_num, cid, q_id, raw_items, is_inter, status,
                      discount_amount, total_paid, version, cust_obj):
        """raw_items: list of (product_idx, qty, unit_price)"""
        gross = sum(qty * price for _, qty, price in raw_items)
        cgst, sgst, igst, tax = (
            _inter_gst(gross) if is_inter else _intra_gst(gross)
        )
        # net = gross + tax − discount
        # CHECK: total_paid + balance_due = net_amount
        net         = gross + tax - discount_amount
        balance_due = net - total_paid

        snapshot = {
            "id":    cust_obj.id,
            "name":  cust_obj.name,
            "email": cust_obj.email,
            "phone": cust_obj.phone,
        }
        sig_items = [
            {"product_id": P[pidx], "quantity": qty, "unit_price": str(unit_price)}
            for pidx, qty, unit_price in raw_items
        ]
        return Invoice(
            invoice_number=inv_num,
            customer_id=cid, quotation_id=q_id,
            status=status, is_inter_state=is_inter,
            gross_amount=gross, tax_amount=tax,
            discount_amount=discount_amount,
            net_amount=net,
            total_paid=total_paid,
            balance_due=balance_due,
            cgst_rate=(Decimal("9.00")  if not is_inter else Decimal("0.00")),
            sgst_rate=(Decimal("9.00")  if not is_inter else Decimal("0.00")),
            igst_rate=(Decimal("18.00") if is_inter     else Decimal("0.00")),
            cgst_amount=cgst, sgst_amount=sgst, igst_amount=igst,
            customer_snapshot=snapshot,
            item_signature=_invoice_sig(sig_items),
            version=version,
            created_by_id=A, updated_by_id=A,
        )

    # Reference quotation objects (already flushed, have IDs)
    q1, q2, q6, q7 = (
        quot_objs[0][0], quot_objs[1][0],
        quot_objs[5][0], quot_objs[6][0],
    )

    # (inv_num, cid, q_id, raw_items, is_inter, status, discount, total_paid, version)
    _inv_specs = [
        # INV-001: FULFILLED — Rajesh Kumar, king bed + 2 bedside tables
        ("INV-2024-001", C[1], q1.id,
         [(1, 1, Decimal("25000")), (3, 2, Decimal("3500"))],
         False, InvoiceStatus.fulfilled,
         Decimal("0.00"),      Decimal("37760.00"),  2),

        # INV-002: PAID — Priya Sharma, sofa + coffee table
        ("INV-2024-002", C[2], q2.id,
         [(5, 1, Decimal("35000")), (6, 1, Decimal("8500"))],
         False, InvoiceStatus.paid,
         Decimal("0.00"),      Decimal("51330.00"),  2),

        # INV-003: VERIFIED — Arjun Enterprises, 2 queen beds + wardrobe
        ("INV-2024-003", C[3], None,
         [(2, 2, Decimal("18000")), (4, 1, Decimal("22000"))],
         False, InvoiceStatus.verified,
         Decimal("0.00"),      Decimal("0.00"),      2),

        # INV-004: PARTIALLY_PAID — Tech Solutions, desks + chairs
        ("INV-2024-004", C[5], None,
         [(11, 2, Decimal("18500")), (12, 3, Decimal("8000"))],
         False, InvoiceStatus.partially_paid,
         Decimal("0.00"),      Decimal("30000.00"),  2),

        # INV-005: FULFILLED — Suresh Patel, dining table + chairs
        ("INV-2024-005", C[6], None,
         [(9, 1, Decimal("28000")), (10, 1, Decimal("15000"))],
         False, InvoiceStatus.fulfilled,
         Decimal("0.00"),      Decimal("50740.00"),  2),

        # INV-006: PARTIALLY_PAID — Lakshmi Interiors, TV unit + bookshelves
        #   FLAT2000 discount applied → net = 29500 − 2000 = 27500
        ("INV-2024-006", C[7], q6.id,
         [(7, 1, Decimal("12000")), (8, 2, Decimal("6500"))],
         False, InvoiceStatus.partially_paid,
         Decimal("2000.00"),   Decimal("15000.00"),  3),

        # INV-007: DRAFT — Meena Reddy (inter-state), mirrors
        ("INV-2024-007", C[4], q7.id,
         [(14, 2, Decimal("4500"))],
         True, InvoiceStatus.draft,
         Decimal("0.00"),      Decimal("0.00"),      1),

        # INV-008: VERIFIED — Deepak Mehta, center table + bookshelf
        ("INV-2024-008", C[8], None,
         [(15, 1, Decimal("11000")), (8, 1, Decimal("6500"))],
         False, InvoiceStatus.verified,
         Decimal("0.00"),      Decimal("0.00"),      2),
    ]

    inv_objs: list[tuple[Invoice, list]] = []
    for inv_num, cid, q_id, raw_items, is_inter, status, disc, paid, version in _inv_specs:
        # Locate the Customer object for snapshot
        cust_idx = list(C.values()).index(cid)
        cust_obj = cust_objs[cust_idx]
        inv = _make_invoice(inv_num, cid, q_id, raw_items, is_inter,
                            status, disc, paid, version, cust_obj)
        db.add(inv)
        inv_objs.append((inv, raw_items))
    await db.flush()

    for inv_obj, raw_items in inv_objs:
        for pidx, qty, unit_price in raw_items:
            db.add(InvoiceItem(
                invoice_id=inv_obj.id, product_id=P[pidx],
                quantity=qty, unit_price=unit_price,
                line_total=(qty * unit_price),
                created_by_id=A, updated_by_id=A,
            ))
    await db.flush()

    # Short-hand references
    inv1, inv2, inv3, inv4, inv5, inv6, inv7, inv8 = [o for o, _ in inv_objs]
    log.info(f"     ✔ Invoices: {[inv_obj.id for inv_obj, _ in inv_objs]}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 11 — PAYMENTS
    # Amounts must keep  total_paid + balance_due = net_amount (already set)
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [11] Payments …")
    pay_objs = [
        Payment(invoice_id=inv1.id, amount=Decimal("37760.00"),
                payment_method="cash",          created_by_id=A),
        Payment(invoice_id=inv2.id, amount=Decimal("51330.00"),
                payment_method="bank_transfer", created_by_id=A),
        Payment(invoice_id=inv4.id, amount=Decimal("30000.00"),
                payment_method="bank_transfer", created_by_id=A),
        Payment(invoice_id=inv5.id, amount=Decimal("25000.00"),
                payment_method="cash",          created_by_id=A),
        Payment(invoice_id=inv5.id, amount=Decimal("25740.00"),
                payment_method="upi",           created_by_id=A),
        Payment(invoice_id=inv6.id, amount=Decimal("15000.00"),
                payment_method="cheque",        created_by_id=A),
    ]
    db.add_all(pay_objs)
    await db.flush()
    log.info(f"     ✔ Payments: {[p.id for p in pay_objs]}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 12 — LOYALTY TOKENS
    # Earned on fulfill_invoice: tokens = int(net_amount // 1000)
    #   INV-001: net=37760  → 37 tokens
    #   INV-005: net=50740  → 50 tokens
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [12] Loyalty Tokens …")
    lt_objs = [
        LoyaltyToken(customer_id=C[1], invoice_id=inv1.id, tokens=37, created_by_id=A),
        LoyaltyToken(customer_id=C[6], invoice_id=inv5.id, tokens=50, created_by_id=A),
    ]
    db.add_all(lt_objs)
    await db.flush()
    log.info(f"     ✔ Loyalty Tokens: {[lt.id for lt in lt_objs]}  (37 + 50 = 87 tokens)")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 13 — STOCK TRANSFERS  (3 completed, 1 pending)
    # completed: p5(3), p6(4), p12(5) from L1→L2
    # pending  : p14(6) from L1→L2
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [13] Stock Transfers …")
    _st_specs = [
        (P[5],  3, L1, L2, TransferStatus.completed, A, A),
        (P[6],  4, L1, L2, TransferStatus.completed, A, A),
        (P[12], 5, L1, L2, TransferStatus.completed, A, A),
        (P[14], 6, L1, L2, TransferStatus.pending,   A, None),
    ]
    st_objs: list[StockTransfer] = []
    for pid, qty, from_l, to_l, status, by_id, comp_by in _st_specs:
        st = StockTransfer(
            product_id=pid, quantity=qty,
            from_location_id=from_l, to_location_id=to_l,
            status=status, transferred_by_id=by_id,
            completed_by_id=comp_by,
            item_signature=_transfer_sig(pid, qty, from_l, to_l),
            created_by_id=A, updated_by_id=A,
        )
        db.add(st)
        st_objs.append(st)
    await db.flush()
    log.info(f"     ✔ Transfers: {[st.id for st in st_objs]}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 14 — INVENTORY MOVEMENTS  (full ledger log)
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [14] Inventory Movements …")
    movements: list[InventoryMovement] = []

    # ── GRN STOCK_IN events (positive qty_change) ─────────────────────
    for grn_obj, items_list in [
        (grn1, g1_items), (grn2, g2_items),
        (grn3, g3_items), (grn4, g4_items),
    ]:
        for itm in items_list:
            movements.append(InventoryMovement(
                product_id=itm["product_id"], location_id=L1,
                quantity_change=itm["quantity"],   # positive → STOCK_IN
                reference_type="GRN", reference_id=grn_obj.id,
                created_by_id=A,
            ))

    # ── TRANSFER_OUT / TRANSFER_IN for completed transfers ──────────────
    completed_transfers = [
        (st_objs[0], P[5],  3),
        (st_objs[1], P[6],  4),
        (st_objs[2], P[12], 5),
    ]
    for st_obj, pid, qty in completed_transfers:
        movements.append(InventoryMovement(
            product_id=pid, location_id=L1,
            quantity_change=-qty,              # TRANSFER_OUT from godown
            reference_type="TRANSFER", reference_id=st_obj.id,
            created_by_id=A,
        ))
        movements.append(InventoryMovement(
            product_id=pid, location_id=L2,
            quantity_change=qty,               # TRANSFER_IN to showroom
            reference_type="TRANSFER", reference_id=st_obj.id,
            created_by_id=A,
        ))

    # ── STOCK_OUT for fulfilled invoices (negative qty_change) ──────────
    inv1_raw = [(1, 1, Decimal("25000")), (3, 2, Decimal("3500"))]
    inv5_raw = [(9, 1, Decimal("28000")), (10, 1, Decimal("15000"))]

    for pidx, qty, _ in inv1_raw:
        movements.append(InventoryMovement(
            product_id=P[pidx], location_id=L1,
            quantity_change=-qty,              # STOCK_OUT
            reference_type="INVOICE", reference_id=inv1.id,
            created_by_id=A,
        ))
    for pidx, qty, _ in inv5_raw:
        movements.append(InventoryMovement(
            product_id=P[pidx], location_id=L1,
            quantity_change=-qty,              # STOCK_OUT
            reference_type="INVOICE", reference_id=inv5.id,
            created_by_id=A,
        ))

    db.add_all(movements)
    await db.flush()
    log.info(f"     ✔ Movements: {len(movements)} records")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 15 — INVENTORY BALANCES  (pre-computed final state)
    #
    # Start: all zeros
    # After GRN1 (loc1): p1=5, p2=8, p3=15, p4=6, p8=10, p9=4,  p11=6
    # After GRN2 (loc1): p5=10, p10=8, p12=15
    # After GRN3 (loc1): p6=12, p7=10, p13=8,  p15=7
    # After GRN4 (loc1): p14=20
    # After transfers (completed):
    #   loc1: p5 10→7, p6 12→8, p12 15→10
    #   loc2: p5=3, p6=4, p12=5
    # After fulfilled invoices (loc1):
    #   inv1: p1 5→4, p3 15→13
    #   inv5: p9 4→3,  p10 8→7
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [15] Inventory Balances …")
    _l1_bal = {
        P[1]:  4,
        P[2]:  8,
        P[3]:  13,
        P[4]:  6,
        P[5]:  7,
        P[6]:  8,
        P[7]:  10,
        P[8]:  10,
        P[9]:  3,
        P[10]: 7,
        P[11]: 6,
        P[12]: 10,
        P[13]: 8,
        P[14]: 20,
        P[15]: 7,
    }
    _l2_bal = {
        P[5]:  3,
        P[6]:  4,
        P[12]: 5,
    }
    for pid, qty in _l1_bal.items():
        db.add(InventoryBalance(
            product_id=pid, location_id=L1, quantity=qty,
            created_by_id=A, updated_by_id=A,
        ))
    for pid, qty in _l2_bal.items():
        db.add(InventoryBalance(
            product_id=pid, location_id=L2, quantity=qty,
            created_by_id=A, updated_by_id=A,
        ))
    await db.flush()
    log.info(f"     ✔ Balances: {len(_l1_bal)} at godown, {len(_l2_bal)} at showroom")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 16 — COMPLAINTS  (5 records)
    # Unique index is partial (PostgreSQL): unique on
    #   (customer_id, invoice_id, product_id) WHERE is_deleted = FALSE
    # Each combination below is unique.
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [16] Complaints …")
    comp_objs = [
        Complaint(
            customer_id=C[1], invoice_id=inv1.id, product_id=P[1],
            title="King Bed Frame – Minor scratch on headboard",
            description=(
                "Customer noticed a small scratch on the headboard when "
                "unpacking. Requesting replacement of the headboard panel."
            ),
            status=ComplaintStatus.RESOLVED, priority=ComplaintPriority.LOW,
            verified_by_id=A, created_by_id=A,
        ),
        Complaint(
            customer_id=C[5], invoice_id=inv4.id, product_id=P[11],
            title="Executive Desk – Drawer mechanism stiff",
            description=(
                "One of the three drawers is extremely stiff to open. "
                "Appears to be a manufacturing defect in the slide mechanism."
            ),
            status=ComplaintStatus.IN_PROGRESS, priority=ComplaintPriority.HIGH,
            verified_by_id=A, created_by_id=A,
        ),
        Complaint(
            customer_id=C[6], invoice_id=inv5.id, product_id=P[9],
            title="Dining Table – Uneven legs causing wobble",
            description=(
                "Table wobbles significantly. One leg appears shorter. "
                "Customer requests technician visit."
            ),
            status=ComplaintStatus.OPEN, priority=ComplaintPriority.MEDIUM,
            verified_by_id=None, created_by_id=A,
        ),
        Complaint(
            customer_id=C[2], invoice_id=inv2.id, product_id=P[5],
            title="Sofa – Fabric colour mismatch from catalogue",
            description=(
                "Delivered fabric colour lighter than catalogue sample. "
                "Customer accepted after explanation of lighting differences."
            ),
            status=ComplaintStatus.CLOSED, priority=ComplaintPriority.LOW,
            verified_by_id=A, created_by_id=A,
        ),
        Complaint(
            customer_id=C[7], invoice_id=inv6.id, product_id=None,
            title="Delivery – Delayed by 5 working days",
            description=(
                "Delivery promised within 7 days but arrived on day 12. "
                "Customer requesting compensation or future discount."
            ),
            status=ComplaintStatus.OPEN, priority=ComplaintPriority.MEDIUM,
            verified_by_id=None, created_by_id=A,
        ),
    ]
    db.add_all(comp_objs)
    await db.flush()
    log.info(f"     ✔ Complaints: {[c.id for c in comp_objs]}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 17 — FILE UPLOADS  (mock metadata records)
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [17] File Uploads …")
    fu_objs = [
        FileUpload(entity_type="grn", entity_id=grn1.id,
                   original_filename="BILL-KWW-0124.pdf",
                   storage_path=f"uploads/grn/{grn1.id}/BILL-KWW-0124.pdf",
                   mime_type="application/pdf", file_size_bytes=204800,
                   created_by_id=A),
        FileUpload(entity_type="grn", entity_id=grn2.id,
                   original_filename="BILL-CFF-0124.pdf",
                   storage_path=f"uploads/grn/{grn2.id}/BILL-CFF-0124.pdf",
                   mime_type="application/pdf", file_size_bytes=184320,
                   created_by_id=A),
        FileUpload(entity_type="grn", entity_id=grn3.id,
                   original_filename="BILL-MMH-0124.pdf",
                   storage_path=f"uploads/grn/{grn3.id}/BILL-MMH-0124.pdf",
                   mime_type="application/pdf", file_size_bytes=172032,
                   created_by_id=A),
        FileUpload(entity_type="grn", entity_id=grn4.id,
                   original_filename="BILL-HGM-0124.pdf",
                   storage_path=f"uploads/grn/{grn4.id}/BILL-HGM-0124.pdf",
                   mime_type="application/pdf", file_size_bytes=98304,
                   created_by_id=A),
        FileUpload(entity_type="invoice", entity_id=inv1.id,
                   original_filename=f"{inv1.invoice_number}.pdf",
                   storage_path=f"uploads/invoices/{inv1.id}/{inv1.invoice_number}.pdf",
                   mime_type="application/pdf", file_size_bytes=153600,
                   created_by_id=A),
        FileUpload(entity_type="invoice", entity_id=inv2.id,
                   original_filename=f"{inv2.invoice_number}.pdf",
                   storage_path=f"uploads/invoices/{inv2.id}/{inv2.invoice_number}.pdf",
                   mime_type="application/pdf", file_size_bytes=158720,
                   created_by_id=A),
        FileUpload(entity_type="supplier_bill", entity_id=S1,
                   original_filename="Karnataka_Wood_Works_Invoice_Jan2024.pdf",
                   storage_path=f"uploads/suppliers/{S1}/KWW_Invoice_Jan2024.pdf",
                   mime_type="application/pdf", file_size_bytes=317440,
                   created_by_id=A),
    ]
    db.add_all(fu_objs)
    await db.flush()
    log.info(f"     ✔ File Uploads: {len(fu_objs)}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 18 — USER ACTIVITY  (15 audit log entries)
    # ─────────────────────────────────────────────────────────────────────
    log.info("── [18] User Activity …")
    ua_objs = [
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message="Supplier created: Karnataka Wood Works (SUP-001)"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"Bulk product creation: 15 furniture SKUs loaded"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"Purchase Order PO-2024-001 raised with Karnataka Wood Works"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"Purchase Order PO-2024-002 raised with Chennai Fabric & Foam House"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"GRN {grn1.id} (BILL-KWW-0124) verified — 7 product lines stocked at godown"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"GRN {grn2.id} (BILL-CFF-0124) verified — 3 product lines stocked"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"GRN {grn3.id} (BILL-MMH-0124) verified — 4 product lines stocked"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"GRN {grn4.id} (BILL-HGM-0124) verified — mirrors stocked"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"Stock transfer ST-{st_objs[0].id}: 3x L-Shape Sofa godown→showroom [COMPLETED]"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"Invoice {inv1.invoice_number} created for Rajesh Kumar — ₹37,760"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"Invoice {inv1.invoice_number} verified"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"Payment ₹37,760 received for {inv1.invoice_number} [cash] — invoice PAID"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"Invoice {inv1.invoice_number} fulfilled — inventory deducted, 37 loyalty tokens issued to Rajesh Kumar"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"Invoice {inv5.invoice_number} fulfilled — 50 loyalty tokens issued to Suresh Patel"),
        UserActivity(user_id=A, username_snapshot=admin.username,
                     message=f"Demo seed completed: {len(prod_objs)} products | 10 customers | 8 invoices | 4 GRNs"),
    ]
    db.add_all(ua_objs)
    await db.flush()
    log.info(f"     ✔ User Activity: {len(ua_objs)} records")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 19 — SINGLE FINAL COMMIT
    # ─────────────────────────────────────────────────────────────────────
    log.info("── Committing …")
    await db.commit()

    # ─────────────────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────────────────
    log.info("═" * 66)
    log.info("  ✅  SEED COMPLETE")
    log.info("═" * 66)
    log.info("")
    log.info("  TABLE SUMMARY")
    log.info("  ─────────────────────────────────────────────────────")
    log.info(f"  warehouses          : 2")
    log.info(f"  inventory_locations : 2  (godown id={L1}, showroom id={L2})")
    log.info(f"  suppliers           : 4")
    log.info(f"  products            : 15  (Bedroom / Living / Dining / Office / Study)")
    log.info(f"  purchase_orders     : 4   (1 approved, 3 fulfilled)")
    log.info(f"  purchase_order_items: {sum(len(i) for i in [_po1_items,_po2_items,_po3_items,_po4_items])}")
    log.info(f"  grns                : 4   (all VERIFIED)")
    log.info(f"  grn_items           : {sum(len(i) for i in [g1_items,g2_items,g3_items,g4_items])}")
    log.info(f"  customers           : 10  (8 intra-state KA + 1 inter-state TS + 1 KA B2B)")
    log.info(f"  discounts           : 4")
    log.info(f"  quotations          : 8   (draft/sent/approved/converted/expired/cancelled)")
    log.info(f"  invoices            : 8   (draft/verified/partial/paid/fulfilled)")
    log.info(f"  payments            : 6   (cash/bank_transfer/upi/cheque)")
    log.info(f"  loyalty_tokens      : 2   (87 tokens total)")
    log.info(f"  stock_transfers     : 4   (3 completed, 1 pending)")
    log.info(f"  inventory_movements : {len(movements)}")
    log.info(f"  inventory_balances  : {len(_l1_bal) + len(_l2_bal)}")
    log.info(f"  complaints          : 5")
    log.info(f"  file_uploads        : {len(fu_objs)}")
    log.info(f"  user_activity       : {len(ua_objs)}")
    log.info("  ─────────────────────────────────────────────────────")
    if L1 != 1:
        log.warning(f"  ⚠ Set DEFAULT_WAREHOUSE_LOCATION_ID={L1} in .env")
    log.info("")
    log.info("  INVOICE STATUS BREAKDOWN")
    log.info("  ─────────────────────────────────────────────────────")
    log.info(f"  INV-2024-001  Rajesh Kumar       FULFILLED  ₹37,760")
    log.info(f"  INV-2024-002  Priya Sharma        PAID       ₹51,330")
    log.info(f"  INV-2024-003  Arjun Enterprises   VERIFIED   ₹68,440")
    log.info(f"  INV-2024-004  Tech Solutions       PARTIAL    ₹71,980  (paid ₹30,000)")
    log.info(f"  INV-2024-005  Suresh Patel         FULFILLED  ₹50,740")
    log.info(f"  INV-2024-006  Lakshmi Interiors    PARTIAL    ₹27,500  (paid ₹15,000, disc ₹2,000)")
    log.info(f"  INV-2024-007  Meena Reddy          DRAFT      ₹10,620  (inter-state IGST)")
    log.info(f"  INV-2024-008  Deepak Mehta         VERIFIED   ₹20,650")
    log.info("═" * 66)


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
