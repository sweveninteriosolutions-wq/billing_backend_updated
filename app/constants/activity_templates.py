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


}

