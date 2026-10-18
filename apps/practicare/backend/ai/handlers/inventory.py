"""
PractiCare AI Inventory Domain Handlers
Handles supply level monitoring, threshold alerts, out-of-stock and expiry tracking, and (for Owner/Manager)
inventory creation, updates, stock adjustments and the review-and-confirm import workflow.
Enforces strict tenant scoping. Validation, status, expiry, item resolution and duplicate rules come from
inventory_service so the AI and REST paths behave identically; role checks happen in the Tool Gateway and again here.
"""

from typing import Dict, Any, List, Tuple
from datetime import date
from sqlalchemy.orm import Session

import models
import inventory_service
from ai.context import SecurityContext
from ai.helpers import parse_bool_arg
from ai.policy import can_user_manage_inventory


def _require_manage(context: SecurityContext) -> None:
    if not can_user_manage_inventory(context.user_role):
        raise PermissionError("Only Owner and Manager can create, update, adjust or import inventory.")


def _resolve(db: Session, context: SecurityContext, args: Dict[str, Any]) -> models.InventoryItem:
    """Exactly one tenant item from item_id or item_query (name). Never creates an item."""
    return inventory_service.resolve_inventory_item(db, context.tenant_id, args.get("item_id"), args.get("item_query"))


def _validate_room(db: Session, context: SecurityContext, room_id: Any) -> None:
    if room_id and not db.query(models.Room).filter(
        models.Room.id == room_id, models.Room.tenant_id == context.tenant_id
    ).first():
        raise ValueError(f"Room ID '{room_id}' not found in tenant '{context.tenant_id}'. Call 'search_rooms' to resolve it.")


def _verified(db: Session, context: SecurityContext, item_id: str) -> models.InventoryItem:
    """Post-write verification: re-read the record from the database within the tenant."""
    db.expire_all()
    persisted = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id,
        models.InventoryItem.tenant_id == context.tenant_id,
    ).first()
    if not persisted:
        raise RuntimeError(f"Database persistence verification failed for inventory item '{item_id}'.")
    return persisted


def _room_name(db: Session, context: SecurityContext, room_id: Any) -> str:
    if not room_id:
        return "Central Supply"
    room = db.query(models.Room).filter(models.Room.id == room_id, models.Room.tenant_id == context.tenant_id).first()
    return f"Room {room.room_number}" if room else "Central Supply"


def _fmt(value: Any) -> str:
    return "(empty)" if value is None or value == "" else str(value)


def execute_get_inventory_status(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Retrieves real tenant inventory with server-computed stock status (In Stock / Low Stock / Out of Stock) and
    expiry state (Expired / Expiring Soon / Valid / No Expiry Date), kept separate. The `message` describes only
    what was returned; catalog-wide counts are reported separately and never as a claim about filtered results.
    """
    tenant_id = context.tenant_id
    low_stock_only = parse_bool_arg(args.get("low_stock_only"), default=False)
    room_id_filter = str(args.get("room_id") or "").strip()
    search_query = str(args.get("search_query") or "").strip()
    item_id_filter = str(args.get("item_id") or "").strip()
    expiry_filter = inventory_service.normalize_expiry_filter(args.get("expiry_filter"))
    sort_by = str(args.get("sort_by") or "").strip().lower()

    catalog = db.query(models.InventoryItem).filter(models.InventoryItem.tenant_id == tenant_id).all()
    if sort_by == "expiry":
        catalog.sort(key=inventory_service.expiry_sort_key)
    all_rooms = {r.id: r for r in db.query(models.Room).filter(models.Room.tenant_id == tenant_id).all()}
    today = date.today()
    needle = inventory_service.name_key(search_query)

    catalog_counts = {"Low Stock": 0, "Out of Stock": 0, "Expired": 0, "Expiring Soon": 0}
    returned: List[Dict[str, Any]] = []
    alerts: List[str] = []
    for item in catalog:
        s_status = inventory_service.stock_status(item.current_stock, item.min_threshold)
        e_state = inventory_service.expiry_state(item.expiry_date, today)
        for key in (s_status, e_state):
            if key in catalog_counts:
                catalog_counts[key] += 1

        if item_id_filter and item.id != item_id_filter:
            continue
        if room_id_filter and item.room_id != room_id_filter:
            continue
        if low_stock_only and s_status == "In Stock":
            continue
        if needle and needle not in inventory_service.name_key(item.item_name):
            continue
        if not inventory_service.matches_expiry_filter(item.expiry_date, expiry_filter, today):
            continue

        room_obj = all_rooms.get(item.room_id)
        location = f"Room {room_obj.room_number} ({room_obj.name})" if room_obj else "Central Supply"
        entry = inventory_service.item_summary(item, location)
        entry["is_low_stock"] = s_status != "In Stock"
        entry["is_out_of_stock"] = s_status == "Out of Stock"
        returned.append(entry)

        if s_status == "Out of Stock":
            alerts.append(f"OUT OF STOCK: '{item.item_name}' (0 {item.unit}) at {location}.")
        elif s_status == "Low Stock":
            alerts.append(f"LOW STOCK: '{item.item_name}' {item.current_stock}/{item.min_threshold} {item.unit} "
                          f"(shortfall {entry['shortfall']}) at {location}.")
        if e_state == "Expired":
            alerts.append(f"EXPIRED: '{item.item_name}' expired on {item.expiry_date}.")
        elif e_state == "Expiring Soon":
            alerts.append(f"EXPIRING SOON: '{item.item_name}' expires on {item.expiry_date} ({entry['days_to_expiry']} days).")

    filtered = bool(search_query or item_id_filter or room_id_filter or low_stock_only or expiry_filter != "all")
    ret_counts = {k: sum(1 for e in returned if k in (e["stock_status"], e["expiry_state"])) for k in catalog_counts}
    if (search_query or item_id_filter) and not returned:
        what = search_query or item_id_filter
        message = f"No inventory item matching '{what}' was found in the current clinic inventory. No stock changes were made."
    elif not returned:
        message = "No inventory items match the requested filter. No stock changes were made."
    else:
        message = (
            f"Returned {len(returned)} of {len(catalog)} inventory item(s): "
            f"{ret_counts['Low Stock']} low stock, {ret_counts['Out of Stock']} out of stock, "
            f"{ret_counts['Expired']} expired, {ret_counts['Expiring Soon']} expiring within 30 days."
        )

    return {
        "status": "SUCCESS",
        "tenant_id": tenant_id,
        "reference_date": today.isoformat(),
        "filters_applied": filtered,
        "expiry_filter": expiry_filter,
        "found": bool(returned),
        "total_catalog_items": len(catalog),
        "returned_items_count": len(returned),
        "items": returned,
        "alerts": alerts,
        "alerts_count": len(alerts),
        # Catalog-wide counts (whole clinic), independent of the filter above
        "low_stock_count": catalog_counts["Low Stock"],
        "out_of_stock_count": catalog_counts["Out of Stock"],
        "expired_count": catalog_counts["Expired"],
        "expiring_within_30_days_count": catalog_counts["Expiring Soon"],
        "message": message,
        "answer_rules": (
            "Answer only from 'items'. stock_status and expiry_state are independent server values: an item can be "
            "In Stock and Expiring Soon. Catalog-wide counts describe the whole clinic, not the returned items. "
            "Never claim all items are adequately stocked unless low_stock_count and out_of_stock_count are both 0."
        ),
    }


def execute_create_inventory_item(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """Creates one inventory record. Refuses an exact duplicate lot (same name, batch and expiry)."""
    _require_manage(context)
    clean, errors, warnings = inventory_service.validate_record(args, mode="create")
    if errors:
        raise ValueError("Inventory item not created: " + " ".join(errors))
    _validate_room(db, context, clean["room_id"])

    found = inventory_service.find_inventory_matches(
        db, context.tenant_id, clean["item_name"], clean["batch_number"], clean["expiry_date"]
    )
    if found["exact"]:
        hit = found["exact"][0]
        raise ValueError(
            f"Inventory item not created: '{hit.item_name}' with the same batch and expiry already exists as {hit.id} "
            f"({hit.current_stock} {hit.unit}). Use 'adjust_inventory_stock' to add stock to it instead."
        )

    practice = db.query(models.Practice).filter(models.Practice.tenant_id == context.tenant_id).first()
    item = models.InventoryItem(
        id=models.generate_id("inv"),
        item_name=clean["item_name"],
        current_stock=clean["quantity"],
        min_threshold=clean["min_threshold"] if clean["min_threshold"] is not None else inventory_service.DEFAULT_MIN_THRESHOLD,
        unit=clean["unit"],
        expiry_date=clean["expiry_date"],
        supplier=clean["supplier"],
        batch_number=clean["batch_number"],
        purchase_price=clean["purchase_price"],
        room_id=clean["room_id"],
        practice_id=practice.id if practice else f"prac-{context.tenant_id}",
        tenant_id=context.tenant_id,
    )
    try:
        db.add(item)
        db.commit()
    except Exception:
        db.rollback()
        raise
    persisted = _verified(db, context, item.id)
    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "create_inventory_item",
        "resource_type": "inventory_item",
        "resource_id": persisted.id,
        "action": "CREATE_INVENTORY_ITEM",
        "item": inventory_service.item_summary(persisted, _room_name(db, context, persisted.room_id)),
        "name": persisted.item_name,
        "warnings": warnings,
        "similar_existing_items": [s.id for s in found["similar"]],
        "tenant_id": context.tenant_id,
        "persisted": True,
        "message": f"Created inventory item '{persisted.item_name}' ({persisted.id}) with {persisted.current_stock} {persisted.unit}.",
    }


_UPDATABLE = ("item_name", "unit", "min_threshold", "expiry_date", "supplier", "batch_number", "purchase_price", "room_id")


def _requested_changes(db: Session, context: SecurityContext, item: models.InventoryItem,
                       args: Dict[str, Any]) -> Dict[str, Tuple[Any, Any]]:
    """Validated {field: (current, new)} for fields whose value actually changes."""
    requested = {k: args.get(k) for k in _UPDATABLE if args.get(k) is not None}
    if not requested:
        raise ValueError("No inventory fields to update were provided.")
    clean, errors, _warnings = inventory_service.validate_record(requested, mode="update")
    if "item_name" in requested and not clean["item_name"]:
        errors.append("Item name cannot be empty.")
    if "unit" in requested and not clean["unit"]:
        errors.append("Unit cannot be empty.")
    if errors:
        raise ValueError("Inventory item not updated: " + " ".join(errors))
    _validate_room(db, context, clean.get("room_id"))
    return {f: (getattr(item, f), clean[f]) for f in requested if str(getattr(item, f)) != str(clean[f])}


def prepare_inventory_update(db: Session, context: SecurityContext, args: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """
    Before approval: resolves the exact item, computes the real current -> new values, and pins the current
    values (expected_values) so execution refuses if someone changed them in the meantime.
    """
    _require_manage(context)
    item = _resolve(db, context, args)
    changes = _requested_changes(db, context, item, args)
    if not changes:
        raise ValueError(f"No changes: '{item.item_name}' ({item.id}) already has the requested values.")
    prepared = dict(args, item_id=item.id, item_query=None,
                    expected_values={f: (None if old is None else str(old)) for f, (old, _new) in changes.items()})
    lines = [f"Update inventory item '{item.item_name}' ({item.id}):"]
    lines += [f"• {f}: {_fmt(old)} → {_fmt(new)}" for f, (old, new) in changes.items()]
    lines.append("Stock quantity is not changed by this update.")
    return prepared, "\n".join(lines)


def execute_update_inventory_item(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Updates descriptive fields of one inventory record exactly as approved (stock levels change only through
    adjust_inventory_stock). Refuses if the approved 'from' values no longer match the database.
    """
    _require_manage(context)
    item = _resolve(db, context, args)
    changes = _requested_changes(db, context, item, args)
    expected = args.get("expected_values") or {}
    drift = [f for f, old in expected.items() if (None if getattr(item, f) is None else str(getattr(item, f))) != old]
    if drift:
        raise ValueError(
            f"'{item.item_name}' ({item.id}) was changed by someone else since this update was proposed "
            f"({', '.join(drift)}). Nothing was changed; review the current values and try again."
        )
    if not changes:
        return {
            "status": "SUCCESS", "execution_status": "NO_CHANGES", "tool_name": "update_inventory_item",
            "resource_type": "inventory_item", "resource_id": item.id, "name": item.item_name,
            "changes": [], "persisted": False, "tenant_id": context.tenant_id,
            "message": f"No changes: '{item.item_name}' ({item.id}) already has the requested values.",
        }
    for field, (_old, new) in changes.items():
        setattr(item, field, new)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    persisted = _verified(db, context, item.id)
    applied = [{"field": f, "from": None if old is None else str(old), "to": str(getattr(persisted, f))}
               for f, (old, _new) in changes.items()]
    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "update_inventory_item",
        "resource_type": "inventory_item",
        "resource_id": persisted.id,
        "action": "UPDATE_INVENTORY_ITEM",
        "name": persisted.item_name,
        "changes": applied,
        "item": inventory_service.item_summary(persisted, _room_name(db, context, persisted.room_id)),
        "tenant_id": context.tenant_id,
        "persisted": True,
        "message": f"Updated '{persisted.item_name}' ({persisted.id}): "
                   + "; ".join(f"{c['field']} {_fmt(c['from'])} → {_fmt(c['to'])}" for c in applied) + ".",
    }


def _stock_change(args: Dict[str, Any]) -> int:
    try:
        change = int(args.get("quantity_change"))
    except (TypeError, ValueError):
        raise ValueError("quantity_change must be a whole number (positive to add stock, negative to remove).")
    if change == 0:
        raise ValueError("quantity_change must not be zero.")
    return change


def prepare_stock_adjustment(db: Session, context: SecurityContext, args: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """Before approval: resolves the item and pins the current quantity the user is approving against."""
    _require_manage(context)
    item = _resolve(db, context, args)
    change = _stock_change(args)
    new_stock = item.current_stock + change
    if new_stock < 0:
        raise ValueError(
            f"Cannot remove {abs(change)} {item.unit} of '{item.item_name}' ({item.id}): only {item.current_stock} {item.unit} in stock."
        )
    if new_stock > inventory_service.MAX_QUANTITY:
        raise ValueError("Resulting stock would exceed the maximum quantity.")
    prepared = dict(args, item_id=item.id, item_query=None, quantity_change=change, expected_current_stock=item.current_stock)
    verb = "Restock" if change > 0 else "Reduce stock of"
    reason = f"\nReason: {args.get('reason')}" if args.get("reason") else ""
    description = (
        f"{verb} '{item.item_name}' ({item.id}):\n"
        f"• Current quantity: {item.current_stock} {item.unit}\n"
        f"• Adjustment: {change:+d} {item.unit}\n"
        f"• New quantity after approval: {new_stock} {item.unit}{reason}\n"
        f"If the stock changes before you approve, nothing is applied."
    )
    return prepared, description


def execute_adjust_inventory_stock(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """Adds (positive) or removes (negative) stock atomically. Stock can never go below zero."""
    _require_manage(context)
    item = _resolve(db, context, args)
    change = _stock_change(args)
    try:
        previous, new_stock = inventory_service.adjust_stock(
            db, context.tenant_id, item.id, change, expected_current_stock=args.get("expected_current_stock"))
    except inventory_service.StockConflictError as exc:
        raise ValueError(str(exc))
    persisted = _verified(db, context, item.id)
    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "adjust_inventory_stock",
        "resource_type": "inventory_item",
        "resource_id": persisted.id,
        "action": "ADJUST_INVENTORY_STOCK",
        "name": persisted.item_name,
        "previous_stock": previous,
        "quantity_change": change,
        "new_stock": persisted.current_stock,
        "unit": persisted.unit,
        "reason": str(args.get("reason") or "").strip() or None,
        "stock_status": inventory_service.stock_status(persisted.current_stock, persisted.min_threshold),
        "tenant_id": context.tenant_id,
        "persisted": True,
        "message": f"Adjusted '{persisted.item_name}' ({persisted.id}) stock from {previous} to {persisted.current_stock} {persisted.unit}.",
    }


def execute_preview_inventory_import(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Extracts inventory records from text the user pasted into chat and returns the review preview.
    Nothing is written; saving requires 'confirm_inventory_import' and explicit user approval.
    """
    _require_manage(context)
    try:
        source = inventory_service.prepare_source("text", text=args.get("text"))
        extracted = inventory_service.extract_inventory_records(source)
    except (inventory_service.ExtractionInputError, inventory_service.ExtractionUnavailableError) as exc:
        raise ValueError(f"Inventory import preview failed: {exc}")
    rows = inventory_service.build_preview(db, context.tenant_id, extracted["items"])
    confirm_rows = []
    for r in rows:
        v = r["values"]
        confirm_rows.append({
            "row_id": r["row_id"], "action": r["action"], "existing_item_id": r["match"].get("existing_item_id"),
            **{k: v.get(k) for k in ("item_name", "quantity", "unit", "expiry_date", "purchase_price", "supplier", "batch_number")},
        })
    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "preview_inventory_import",
        "persisted": False,
        "tenant_id": context.tenant_id,
        "rows": rows,
        "rows_with_errors": [r["row_id"] for r in rows if any(i["level"] == "error" for i in r["issues"])],
        "previous_imports": inventory_service.prior_imports(db, context.tenant_id, source["source_hash"]),
        "notes": extracted["notes"],
        "confirm_arguments": {
            "import_token": inventory_service.new_import_token(),
            "source_hash": source["source_hash"],
            "rows": confirm_rows,
        },
        "message": (
            f"Extracted {len(rows)} record(s) for review. Nothing has been saved. Show the user every row with its "
            f"issues; to save, call 'confirm_inventory_import' with confirm_arguments (after applying only the "
            f"corrections the user explicitly gave). The user must approve before anything is written."
        ),
    }


def execute_confirm_inventory_import(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """Applies reviewed import rows (runs only after explicit user approval through the Tool Gateway)."""
    _require_manage(context)
    practice = db.query(models.Practice).filter(models.Practice.tenant_id == context.tenant_id).first()
    rows: List[Dict[str, Any]] = [dict(r) for r in (args.get("rows") or [])]
    try:
        result = inventory_service.apply_import(
            db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            practice_id=practice.id if practice else f"prac-{context.tenant_id}",
            import_token=str(args.get("import_token") or ""),
            source_hash=str(args.get("source_hash") or ""),
            source_type="chat",
            rows=rows,
        )
    except inventory_service.ImportAlreadyProcessedError:
        raise ValueError("This inventory import was already confirmed; nothing was imported again.")
    counts = result["counts"]
    written = result["status"] == "IMPORTED"
    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS" if written else "NO_CHANGES",
        "tool_name": "confirm_inventory_import",
        "resource_type": "inventory_import",
        "resource_id": result.get("import_id"),
        "action": "IMPORT_INVENTORY",
        "persisted": bool(result.get("persisted")),
        "tenant_id": context.tenant_id,
        **{k: result[k] for k in ("created", "updated", "skipped", "rejected", "counts")},
        "message": (
            f"Inventory import: {counts['created']} created, {counts['updated']} updated, "
            f"{counts['skipped']} skipped, {counts['rejected']} rejected."
        ),
    }


# Approval text for imports: the user approves exactly these rows (the gateway hashes the arguments).

def describe_inventory_import(args: Dict[str, Any]) -> str:
    lines = ["Import inventory records (review every row before approving):"]
    for r in args.get("rows") or []:
        action = r.get("action")
        if action == "skip":
            lines.append(f"• {r.get('row_id')}: SKIP {r.get('item_name') or ''}".rstrip())
            continue
        details = ", ".join(
            f"{label} {r.get(key)}" for key, label in (
                ("expiry_date", "exp"), ("batch_number", "batch"), ("supplier", "supplier"), ("purchase_price", "price"))
            if r.get(key) not in (None, "")
        )
        verb = f"ADD TO {r.get('existing_item_id')}" if action == "restock" else "CREATE"
        lines.append(f"• {r.get('row_id')}: {verb} {r.get('item_name')} — {r.get('quantity')} {r.get('unit') or ''}".rstrip()
                     + (f" ({details})" if details else ""))
    return "\n".join(lines)
