from app.constants.activity_codes import ActivityCode


ACTIVITY_TEMPLATES = {
    # ---------------- AUTH ----------------
    ActivityCode.LOGIN:
        "{actor_role} ({actor_email}) logged in",

    ActivityCode.LOGOUT:
        "{actor_role} ({actor_email}) logged out",

    # ---------------- USERS ----------------
    ActivityCode.CREATE_USER:
        "{actor_role} ({actor_email}) created user {target_email} with role {target_role}",

    ActivityCode.UPDATE_USER_ROLE:
        "{actor_role} ({actor_email}) changed role of {target_email} to {target_role}",

    ActivityCode.UPDATE_USER_EMAIL:
        "{actor_role} ({actor_email}) changed email of user to {target_email}",

    ActivityCode.UPDATE_USER_PASSWORD:
        "{actor_role} ({actor_email}) reset password for user {target_email}",

    ActivityCode.DEACTIVATE_USER:
        "{actor_role} ({actor_email}) deactivated user {target_email}",

    ActivityCode.REACTIVATE_USER:
        "{actor_role} ({actor_email}) reactivated user {target_email}",

    # ---------------- CUSTOMERS ----------------
    ActivityCode.CREATE_CUSTOMER:
        "{actor_role} ({actor_email}) created customer {target_name}",

    ActivityCode.UPDATE_CUSTOMER:
        "{actor_role} ({actor_email}) updated customer {target_name}: {changes}",

    ActivityCode.DEACTIVATE_CUSTOMER:
        "{actor_role} ({actor_email}) deactivated customer {target_name}",

    ActivityCode.REACTIVATE_CUSTOMER:
        "{actor_role} ({actor_email}) reactivated customer {target_name}",

    # ---------------- SUPPLIERS ----------------
    ActivityCode.CREATE_SUPPLIER:
        "{actor_role} ({actor_email}) created supplier {target_name}",

    ActivityCode.UPDATE_SUPPLIER:
        "{actor_role} ({actor_email}) updated supplier {target_name}: {changes}",

    ActivityCode.DEACTIVATE_SUPPLIER:
        "{actor_role} ({actor_email}) deactivated supplier {target_name}",

    ActivityCode.REACTIVATE_SUPPLIER:
        "{actor_role} ({actor_email}) reactivated supplier {target_name}",
    
    # ---------------- PRODUCTS ----------------
    ActivityCode.CREATE_PRODUCT:
    "{actor_role} ({actor_email}) created product {target_name} ({sku})",

    ActivityCode.UPDATE_PRODUCT:
    "{actor_role} ({actor_email}) updated product {target_name}: {changes}",

    ActivityCode.DEACTIVATE_PRODUCT:
    "{actor_role} ({actor_email}) deactivated product {target_name}",

    ActivityCode.REACTIVATE_PRODUCT:
    "{actor_role} ({actor_email}) reactivated product {target_name}",

    # ---------------- INVENTORY ----------------
    ActivityCode.CREATE_LOCATION:
        "{actor_role} ({actor_email}) created inventory location {target_name}",

    ActivityCode.UPDATE_LOCATION:
        "{actor_role} ({actor_email}) updated inventory location {target_name}: {changes}",

    ActivityCode.DEACTIVATE_LOCATION:
        "{actor_role} ({actor_email}) deactivated inventory location {target_name}",

    ActivityCode.REACTIVATE_LOCATION:
        "{actor_role} ({actor_email}) reactivated inventory location {target_name}",
    ActivityCode.INVENTORY_MOVEMENT:
    "{actor_role} ({actor_email}) performed inventory movement "
    "{movement_type} of {quantity_change} units "
    "for product {product_id} at location {location_id} "
    "(ref: {reference_type}:{reference_id})",

    # ---------------- GRN ----------------
    ActivityCode.CREATE_GRN:
    "{actor_role} ({actor_email}) created GRN {target_name}",
    ActivityCode.UPDATE_GRN:
    "{actor_role} ({actor_email}) updated GRN {target_name}: {changes}",
    ActivityCode.VERIFY_GRN:
    "{actor_role} ({actor_email}) verified GRN {target_name}",
    ActivityCode.DELETE_GRN:
    "{actor_role} ({actor_email}) deleted GRN {target_name}",

    # ---------------- QUOTATIONS ----------------
    ActivityCode.CREATE_QUOTATION:
    "{actor_role} ({actor_email}) created quotation {target_name}",

    ActivityCode.UPDATE_QUOTATION:
    "{actor_role} ({actor_email}) updated quotation {target_name}: {changes}",

    ActivityCode.APPROVE_QUOTATION:
    "{actor_role} ({actor_email}) approved quotation {target_name}",

    ActivityCode.CONVERT_QUOTATION_TO_INVOICE:
    "{actor_role} ({actor_email}) converted quotation {target_name} to invoice",

    ActivityCode.DELETE_QUOTATION:
    "{actor_role} ({actor_email}) deleted quotation {target_name}",

    ActivityCode.CANCEL_QUOTATION:
    "{actor_role} ({actor_email}) cancelled quotation {target_name}",

    ActivityCode.EXPIRE_QUOTATION:
    "{actor_role} ({actor_email}) expired quotation {target_name}: {changes}",

    # ---------------- INVOICES ----------------
    ActivityCode.CREATE_INVOICE:
        "{actor_role} ({actor_email}) created invoice {target_name}",

    ActivityCode.UPDATE_INVOICE:
        "{actor_role} ({actor_email}) updated invoice {target_name}",

    ActivityCode.APPLY_DISCOUNT:
        "{actor_role} ({actor_email}) applied discount ₹{new_value} on invoice {target_name}",

    ActivityCode.OVERRIDE_DISCOUNT:
        "{actor_role} ({actor_email}) overrode discount on invoice {target_name} "
        "(old ₹{old_value}, new ₹{new_value})",

    ActivityCode.VERIFY_INVOICE:
        "{actor_role} ({actor_email}) verified invoice {target_name}",

    ActivityCode.ADD_PAYMENT:
        "Invoice {target_name} received payment of ₹{amount}",

    ActivityCode.MARK_PAID:
        "Invoice {target_name} marked as fully paid",

    ActivityCode.FULFILL_INVOICE:
        "Invoice {target_name} fulfilled; inventory deducted and loyalty awarded",

    ActivityCode.CANCEL_INVOICE:
        "{actor_role} ({actor_email}) cancelled invoice {target_name}",
    
    # ---------------- DISCOUNTS ----------------
    ActivityCode.CREATE_DISCOUNT:
        "{actor_role} ({actor_email}) created discount {target_name} ({target_code})",
    ActivityCode.UPDATE_DISCOUNT:
        "{actor_role} ({actor_email}) updated discount {target_name} ({target_code}): {changes}",
    ActivityCode.DEACTIVATE_DISCOUNT:
        "{actor_role} ({actor_email}) deactivated discount {target_name} ({target_code})",
    ActivityCode.REACTIVATE_DISCOUNT:
        "{actor_role} ({actor_email}) reactivated discount {target_name} ({target_code})",
    ActivityCode.EXPIRE_DISCOUNT:
        "{actor_role} ({actor_email}) expired discount {target_name} ({target_code})",
    ActivityCode.ACTIVATE_DISCOUNT:
        "{actor_role} ({actor_email}) activated discount {target_name} ({target_code})",
    
    # ---------------- STOCK TRANSFERS ----------------
    ActivityCode.CREATE_STOCK_TRANSFER:
        "{actor_role} ({actor_email}) created stock transfer {target_name}",
    ActivityCode.UPDATE_STOCK_TRANSFER:
        "{actor_role} ({actor_email}) updated stock transfer {target_name}: {changes}",
    ActivityCode.COMPLETE_STOCK_TRANSFER:
        "{actor_role} ({actor_email}) completed stock transfer {target_name}",
    ActivityCode.CANCEL_STOCK_TRANSFER:
        "{actor_role} ({actor_email}) cancelled stock transfer {target_name}",
    
    # ---------------- COMPLAINTS ----------------
    ActivityCode.CREATE_COMPLAINT:
        "{actor_role} ({actor_email}) created complaint #{target_id} for customer {customer_id}",

    ActivityCode.UPDATE_COMPLAINT:
        "{actor_role} ({actor_email}) updated complaint #{target_id}: {changes}",

    ActivityCode.UPDATE_COMPLAINT_STATUS:
        "{actor_role} ({actor_email}) changed complaint #{target_id} status "
        "from {old_status} → {new_status}",

    ActivityCode.DELETE_COMPLAINT:
        "{actor_role} ({actor_email}) deleted complaint #{target_id}",
    
}

