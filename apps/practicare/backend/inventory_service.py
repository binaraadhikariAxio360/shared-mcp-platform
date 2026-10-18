"""
PractiCare Inventory Service
Single implementation of inventory expiry rules, record validation, duplicate detection, AI document
extraction and the confirmed import transaction. Used by the REST API and the AI tool handlers so both
paths apply identical rules. Authorization (who may write) stays in ai/policy.py and is checked by callers.

Import workflow:
  1. extract  -> Gemini reads a PDF, image or text and returns candidate records (never saved).
  2. preview  -> every record is validated, flagged (missing / ambiguous / low confidence) and matched
                 against existing inventory; nothing is written.
  3. confirm  -> the user's edited rows are validated again server-side and written in ONE transaction,
                 keyed by a single-use import_token so a repeated confirmation cannot import twice.
"""

import base64
import binascii
import hashlib
import json
import logging
import re
import secrets
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models

logger = logging.getLogger("practicare.inventory")

# ==============================================================================
# EXPIRY RULES
# ==============================================================================

EXPIRY_WINDOWS = (7, 30, 90)
EXPIRY_FILTERS = ("all", "expired", "within_7", "within_30", "within_90", "none")
EXPIRING_SOON_DAYS = 30  # dashboard "expiring soon" and InventoryRead.is_expiring_soon

_FILTER_ALIASES = {
    "": "all", "all": "all",
    "expired": "expired", "already_expired": "expired",
    "7": "within_7", "within_7": "within_7", "expiring_7": "within_7",
    "30": "within_30", "within_30": "within_30", "expiring_30": "within_30",
    "90": "within_90", "within_90": "within_90", "expiring_90": "within_90",
    "none": "none", "no_expiry": "none",
}


def parse_expiry(value: Any) -> Optional[date]:
    """Stored expiry dates are ISO YYYY-MM-DD strings. Anything else (empty, legacy free text) is 'no valid date'."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    clean = str(value).strip()[:10]
    try:
        return date.fromisoformat(clean)
    except ValueError:
        return None


def normalize_expiry_filter(raw: Optional[str]) -> str:
    key = str(raw or "").strip().lower()
    if key not in _FILTER_ALIASES:
        raise ValueError(f"Unknown expiry filter '{raw}'. Use one of: {', '.join(EXPIRY_FILTERS)}.")
    return _FILTER_ALIASES[key]


def expiry_info(expiry_value: Any, today: Optional[date] = None) -> Dict[str, Any]:
    """
    Expiry facts for one item, relative to `today` (server local date):
      expired     : expiry date before today
      within_N    : today <= expiry <= today + N days (smallest matching window)
      later       : beyond 90 days
      none        : no valid expiry date
    """
    today = today or date.today()
    exp = parse_expiry(expiry_value)
    if exp is None:
        return {"is_expired": False, "days_to_expiry": None, "expiry_status": "none", "is_expiring_soon": False}
    days = (exp - today).days
    if days < 0:
        status = "expired"
    else:
        status = next((f"within_{w}" for w in EXPIRY_WINDOWS if days <= w), "later")
    return {
        "is_expired": days < 0,
        "days_to_expiry": days,
        "expiry_status": status,
        "is_expiring_soon": 0 <= days <= EXPIRING_SOON_DAYS,
    }


STOCK_STATUSES = ("In Stock", "Low Stock", "Out of Stock")
EXPIRY_STATES = ("Expired", "Expiring Soon", "Valid", "No Expiry Date")


def stock_status(current_stock: Optional[int], min_threshold: Optional[int]) -> str:
    """Stock level only (independent of expiry): Out of Stock (0), Low Stock (<= threshold), In Stock."""
    stock = current_stock or 0
    if stock <= 0:
        return "Out of Stock"
    if stock <= (min_threshold or 0):
        return "Low Stock"
    return "In Stock"


def expiry_state(expiry_value: Any, today: Optional[date] = None) -> str:
    """Expiry only (independent of stock): Expired, Expiring Soon (within 30 days), Valid, No Expiry Date."""
    info = expiry_info(expiry_value, today)
    if info["expiry_status"] == "none":
        return "No Expiry Date"
    if info["is_expired"]:
        return "Expired"
    return "Expiring Soon" if info["is_expiring_soon"] else "Valid"


def matches_expiry_filter(expiry_value: Any, expiry_filter: str, today: Optional[date] = None) -> bool:
    """Windows are cumulative: 'within_30' includes items expiring within 7 days. Expired items are excluded from windows."""
    flt = normalize_expiry_filter(expiry_filter)
    if flt == "all":
        return True
    info = expiry_info(expiry_value, today)
    if flt == "none":
        return info["expiry_status"] == "none"
    if flt == "expired":
        return info["is_expired"]
    window = int(flt.split("_")[1])
    days = info["days_to_expiry"]
    return days is not None and 0 <= days <= window


def expiry_sort_key(item: Any) -> Tuple[int, date, str]:
    """Nearest expiry first (already-expired items lead); items without a valid expiry date go last."""
    exp = parse_expiry(getattr(item, "expiry_date", None))
    return (1 if exp is None else 0, exp or date.max, (getattr(item, "item_name", "") or "").lower())


# ==============================================================================
# FIELD NORMALIZATION & VALIDATION
# ==============================================================================

MAX_NAME = 150
MAX_UNIT = 40
MAX_SUPPLIER = 150
MAX_BATCH = 80
MAX_QUANTITY = 1_000_000
MAX_PRICE = Decimal("9999999999.99")
DEFAULT_MIN_THRESHOLD = 10

IMPORT_FIELDS = ("item_name", "quantity", "unit", "expiry_date", "purchase_price", "supplier", "batch_number", "min_threshold")

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    clean = " ".join(str(value).split())
    return clean or None


def name_key(name: Any) -> str:
    """Case/space-insensitive identity of an item name, used for duplicate detection."""
    return " ".join(str(name or "").casefold().split())


def _opt_key(value: Any) -> Optional[str]:
    clean = _text(value)
    return clean.casefold() if clean else None


def parse_quantity(value: Any) -> Tuple[Optional[int], Optional[str]]:
    """Whole, non-negative quantity. Returns (value, error)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if isinstance(value, bool):
        return None, "Quantity must be a whole number."
    try:
        num = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None, f"Quantity '{value}' is not a number."
    if num != num.to_integral_value():
        return None, f"Quantity '{value}' is not a whole number."
    qty = int(num)
    if qty < 0:
        return None, "Quantity cannot be negative."
    if qty > MAX_QUANTITY:
        return None, f"Quantity {qty} exceeds the maximum of {MAX_QUANTITY}."
    return qty, None


def parse_price(value: Any) -> Tuple[Optional[Decimal], Optional[str]]:
    """Non-negative unit price with at most 2 decimals; currency symbols and thousands separators are ignored."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if isinstance(value, bool):
        return None, "Purchase price must be a number."
    raw = re.sub(r"[^\d.\-]", "", str(value).replace(",", ""))
    try:
        price = Decimal(raw)
    except InvalidOperation:
        return None, f"Purchase price '{value}' is not a number."
    if price < 0:
        return None, "Purchase price cannot be negative."
    if price > MAX_PRICE:
        return None, "Purchase price is too large."
    if price != price.quantize(Decimal("0.01")):
        return None, f"Purchase price '{value}' has more than 2 decimal places."
    return price.quantize(Decimal("0.01")), None


def parse_document_date(value: Any) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Interprets an expiry date as written in a document. Returns (iso_date, problem, ambiguous).
    Never guesses: day/month order that cannot be decided, or a month without a day, is ambiguous and
    is left for the user to resolve.
    """
    raw = _text(value)
    if not raw:
        return None, None, False
    s = raw.lower().replace(",", " ")
    s = " ".join(s.split())

    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)), raw)

    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 and b <= 12:
            return _iso(y, b, a, raw)
        if b > 12 and a <= 12:
            return _iso(y, a, b, raw)
        if a == b:
            return _iso(y, a, b, raw)
        return None, f"Expiry '{raw}' is ambiguous (day/month order unknown).", True

    m = re.fullmatch(r"(\d{1,2})\s+([a-z]{3})[a-z]*\.?\s+(\d{4})", s)
    if m and m.group(2) in _MONTHS:
        return _iso(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)), raw)
    m = re.fullmatch(r"([a-z]{3})[a-z]*\.?\s+(\d{1,2})\s+(\d{4})", s)
    if m and m.group(1) in _MONTHS:
        return _iso(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)), raw)

    if re.fullmatch(r"(\d{4})[-/.](\d{1,2})|(\d{1,2})[-/.](\d{4})|[a-z]{3}[a-z]*\.?\s+\d{4}", s):
        return None, f"Expiry '{raw}' has no day; enter the exact expiry date.", True

    return None, f"Expiry '{raw}' is not a recognizable date.", True


def _iso(y: int, mo: int, d: int, raw: str) -> Tuple[Optional[str], Optional[str], bool]:
    try:
        return date(y, mo, d).isoformat(), None, False
    except ValueError:
        return None, f"Expiry '{raw}' is not a valid calendar date.", False


def validate_record(values: Dict[str, Any], *, mode: str) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """
    Validates one inventory record. mode:
      'create'  : item_name, quantity and unit are required.
      'restock' : quantity (> 0) is required; other fields are optional.
      'update'  : nothing is required (partial update of descriptive fields).
      'preview' : nothing is required; problems are reported, not enforced.
    Expiry must be ISO YYYY-MM-DD except in preview, where document formats are interpreted.
    Returns (clean_values, errors, warnings). Missing optional values stay None (never invented).
    """
    errors: List[str] = []
    warnings: List[str] = []
    clean: Dict[str, Any] = {}

    name = _text(values.get("item_name"))
    if name and len(name) > MAX_NAME:
        errors.append(f"Item name exceeds {MAX_NAME} characters.")
    clean["item_name"] = name

    qty, q_err = parse_quantity(values.get("quantity"))
    if q_err:
        errors.append(q_err)
    clean["quantity"] = qty

    unit = _text(values.get("unit"))
    if unit and len(unit) > MAX_UNIT:
        errors.append(f"Unit exceeds {MAX_UNIT} characters.")
    clean["unit"] = unit

    raw_threshold = values.get("min_threshold")
    threshold, t_err = parse_quantity(raw_threshold)
    if t_err:
        errors.append(t_err.replace("Quantity", "Minimum threshold"))
    clean["min_threshold"] = threshold

    raw_exp = values.get("expiry_date")
    if mode == "preview":
        iso, problem, _ambiguous = parse_document_date(raw_exp)
        if problem:
            errors.append(problem)
        clean["expiry_date"] = iso
    else:
        raw_clean = _text(raw_exp)
        exp = parse_expiry(raw_clean) if raw_clean else None
        if raw_clean and (exp is None or len(raw_clean) != 10):
            errors.append(f"Expiry '{raw_clean}' must be a valid date in YYYY-MM-DD format.")
            exp = None
        clean["expiry_date"] = exp.isoformat() if exp else None
    if clean["expiry_date"] and expiry_info(clean["expiry_date"])["is_expired"]:
        warnings.append(f"Expiry date {clean['expiry_date']} is already in the past.")

    price, p_err = parse_price(values.get("purchase_price"))
    if p_err:
        errors.append(p_err)
    clean["purchase_price"] = price

    supplier = _text(values.get("supplier"))
    if supplier and len(supplier) > MAX_SUPPLIER:
        errors.append(f"Supplier exceeds {MAX_SUPPLIER} characters.")
    clean["supplier"] = supplier

    batch = _text(values.get("batch_number"))
    if batch and len(batch) > MAX_BATCH:
        errors.append(f"Batch number exceeds {MAX_BATCH} characters.")
    clean["batch_number"] = batch

    clean["room_id"] = _text(values.get("room_id"))

    if mode == "create":
        if not name:
            errors.append("Item name is required.")
        if qty is None and not q_err:
            errors.append("Quantity is required.")
        if not unit:
            errors.append("Unit is required.")
    elif mode == "restock":
        if qty is None and not q_err:
            errors.append("Quantity to add is required.")
        elif qty == 0:
            errors.append("Quantity to add must be greater than zero.")
    return clean, errors, warnings


# ==============================================================================
# DUPLICATE DETECTION
# ==============================================================================

def record_identity(item_name: Any, batch_number: Any, expiry_date: Any) -> Tuple[str, Optional[str], Optional[str]]:
    """Two records are the same stock lot when name, batch number and expiry all match (missing == missing)."""
    exp = parse_expiry(expiry_date)
    return name_key(item_name), _opt_key(batch_number), exp.isoformat() if exp else None


def find_inventory_matches(db: Session, tenant_id: str, item_name: Any, batch_number: Any, expiry_date: Any,
                           items: Optional[List[Any]] = None) -> Dict[str, List[Any]]:
    """Existing tenant items that are the same lot ('exact') or the same item name in another lot ('similar')."""
    key = record_identity(item_name, batch_number, expiry_date)
    if not key[0]:
        return {"exact": [], "similar": []}
    if items is None:
        items = db.query(models.InventoryItem).filter(models.InventoryItem.tenant_id == tenant_id).all()
    exact, similar = [], []
    for it in items:
        if name_key(it.item_name) != key[0]:
            continue
        if record_identity(it.item_name, it.batch_number, it.expiry_date) == key:
            exact.append(it)
        else:
            similar.append(it)
    return {"exact": exact, "similar": similar}


def item_summary(item: Any, room_name: Optional[str] = None) -> Dict[str, Any]:
    info = expiry_info(item.expiry_date)
    return {
        "item_id": item.id,
        "name": item.item_name,
        "current_stock": item.current_stock,
        "min_threshold": item.min_threshold,
        "unit": item.unit,
        "stock_status": stock_status(item.current_stock, item.min_threshold),
        "shortfall": max((item.min_threshold or 0) - (item.current_stock or 0), 0),
        "expiry_date": item.expiry_date,
        "expiry_state": expiry_state(item.expiry_date),
        "days_to_expiry": info["days_to_expiry"],
        "expiry_status": info["expiry_status"],
        "is_expired": info["is_expired"],
        "supplier": item.supplier,
        "batch_number": item.batch_number,
        "purchase_price": float(item.purchase_price) if item.purchase_price is not None else None,
        "room_id": item.room_id,
        "location": room_name or "Central Supply",
    }


# ==============================================================================
# ITEM RESOLUTION & STOCK ADJUSTMENT (shared by REST and AI)
# ==============================================================================

class ItemNotFoundError(ValueError):
    """No tenant item matches; callers must never create one implicitly."""


class AmbiguousItemError(ValueError):
    """Several tenant items match; the user must choose. `candidates` are item_summary dicts."""

    def __init__(self, message: str, candidates: List[Dict[str, Any]]):
        super().__init__(message)
        self.candidates = candidates


class StockConflictError(ValueError):
    """The stock changed after it was shown/approved, or the change would make it negative. Nothing was written."""


def resolve_inventory_item(db: Session, tenant_id: str, item_id: Any = None, item_name: Any = None) -> Any:
    """
    Resolves exactly one tenant item from an exact item_id, or else an item name:
    exact (case/space-insensitive) name matches win; otherwise a unique substring match.
    """
    query = db.query(models.InventoryItem).filter(models.InventoryItem.tenant_id == tenant_id)
    clean_id = _text(item_id)
    if clean_id:
        item = query.filter(models.InventoryItem.id == clean_id).first()
        if not item:
            raise ItemNotFoundError(f"No inventory item with ID '{clean_id}' exists in this clinic.")
        return item
    key = name_key(item_name)
    if not key:
        raise ItemNotFoundError("Specify the inventory item by its exact item_id or name.")
    items = query.all()
    matches = [i for i in items if name_key(i.item_name) == key] or [i for i in items if key in name_key(i.item_name)]
    if not matches:
        raise ItemNotFoundError(f"No inventory item matching '{_text(item_name)}' was found in this clinic.")
    if len(matches) > 1:
        raise AmbiguousItemError(
            f"{len(matches)} inventory items match '{_text(item_name)}'. Ask the user which one (by item_id).",
            [item_summary(i) for i in matches[:10]],
        )
    return matches[0]


def adjust_stock(db: Session, tenant_id: str, item_id: str, change: int,
                 expected_current_stock: Optional[int] = None) -> Tuple[int, int]:
    """
    Atomically adds `change` (negative removes) in one conditional UPDATE, so concurrent adjustments can
    never be lost and stock can never go negative. With expected_current_stock (the quantity the user saw or
    approved) the update only applies if the stock is still exactly that value.
    Returns (previous_stock, new_stock). Commits on success; raises StockConflictError and writes nothing otherwise.
    """
    if not isinstance(change, int) or isinstance(change, bool) or change == 0:
        raise ValueError("The quantity change must be a non-zero whole number.")
    table = models.InventoryItem.__table__
    cond = [table.c.id == item_id, table.c.tenant_id == tenant_id, table.c.current_stock + change >= 0,
            table.c.current_stock + change <= MAX_QUANTITY]
    if expected_current_stock is not None:
        cond.append(table.c.current_stock == expected_current_stock)
    try:
        updated = db.execute(
            table.update().where(*cond).values(current_stock=table.c.current_stock + change).returning(table.c.current_stock)
        ).first()
        if updated is None:
            db.rollback()
            row = db.query(models.InventoryItem).filter(
                models.InventoryItem.id == item_id, models.InventoryItem.tenant_id == tenant_id).first()
            if not row:
                raise ItemNotFoundError(f"No inventory item with ID '{item_id}' exists in this clinic.")
            if expected_current_stock is not None and row.current_stock != expected_current_stock:
                raise StockConflictError(
                    f"Stock of '{row.item_name}' changed from {expected_current_stock} to {row.current_stock} {row.unit} "
                    f"since it was shown. Nothing was changed; review the current quantity and try again.")
            if row.current_stock + change < 0:
                raise StockConflictError(
                    f"Cannot remove {abs(change)} {row.unit} of '{row.item_name}': only {row.current_stock} {row.unit} in stock.")
            raise StockConflictError("Resulting stock would exceed the maximum quantity.")
        db.commit()
    except (StockConflictError, ItemNotFoundError):
        raise
    except Exception:
        db.rollback()
        raise
    db.expire_all()  # ORM instances loaded earlier must not show the pre-update quantity
    new_stock = int(updated[0])
    return new_stock - change, new_stock


# ==============================================================================
# AI EXTRACTION (Gemini)
# ==============================================================================

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 20_000
MAX_EXTRACTED_ROWS = 200
IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
CONFIDENCE_LEVELS = ("high", "medium", "low")


class ExtractionInputError(ValueError):
    """The uploaded document or text is not acceptable (bad type, size, encoding). Maps to HTTP 400."""


class ExtractionUnavailableError(RuntimeError):
    """The AI provider is not configured or failed. Maps to HTTP 503; nothing is guessed instead."""


def prepare_source(source_type: str, *, content_base64: Optional[str] = None, mime_type: Optional[str] = None,
                   text: Optional[str] = None) -> Dict[str, Any]:
    """Validates an import source and returns {source_type, mime_type, data|text, source_hash}."""
    if source_type == "text":
        clean = (text or "").strip()
        if not clean:
            raise ExtractionInputError("Enter the inventory text to import.")
        if len(clean) > MAX_TEXT_CHARS:
            raise ExtractionInputError(f"Text is too long (maximum {MAX_TEXT_CHARS} characters).")
        return {"source_type": "text", "text": clean,
                "source_hash": hashlib.sha256(clean.encode("utf-8")).hexdigest()}

    if source_type not in ("pdf", "image"):
        raise ExtractionInputError("source_type must be 'pdf', 'image' or 'text'.")
    if not content_base64:
        raise ExtractionInputError("No file content was provided.")
    payload = content_base64.split(",", 1)[1] if content_base64.startswith("data:") else content_base64
    if len(payload) > (MAX_FILE_BYTES * 4) // 3 + 8:
        raise ExtractionInputError("File is too large (maximum 10 MB).")
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise ExtractionInputError("File content is not valid base64.")
    if not data:
        raise ExtractionInputError("The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ExtractionInputError("File is too large (maximum 10 MB).")

    mime = (mime_type or "").strip().lower()
    if source_type == "pdf":
        if not data.startswith(b"%PDF-"):
            raise ExtractionInputError("The file is not a PDF document.")
        mime = "application/pdf"
    else:
        sniffed = _sniff_image(data)
        if sniffed:
            mime = sniffed
        if mime not in IMAGE_MIME_TYPES:
            raise ExtractionInputError("Unsupported image type. Use JPG, PNG, WEBP or HEIC.")
    return {"source_type": source_type, "mime_type": mime, "data": data,
            "source_hash": hashlib.sha256(data).hexdigest()}


def _sniff_image(data: bytes) -> Optional[str]:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


EXTRACTION_PROMPT = """You extract medical-supply inventory records from a clinic document (invoice, delivery note, stock list, label photo or typed text).

Return ONLY a JSON object, no prose, in exactly this shape:
{"items": [{"item_name": F, "quantity": F, "unit": F, "expiry_date": F, "purchase_price": F, "supplier": F, "batch_number": F}], "notes": "short note on unreadable or skipped parts, or empty"}
where every F is {"value": <string|number|null>, "confidence": "high"|"medium"|"low"}.

Rules:
- One entry per distinct product line. Do not merge or split lines.
- Copy values exactly as written. NEVER guess, infer, calculate or fill in a value that is not visible in the source. If a value is absent or unreadable use {"value": null, "confidence": "low"}.
- quantity: the received/stocked count as a number, exactly as written. unit: the unit as written (e.g. "boxes", "vials", "units").
- expiry_date: if the day, month and year are unambiguous return YYYY-MM-DD; otherwise return the date text exactly as written (e.g. "03/04/2027", "2027-05") so a person can resolve it.
- purchase_price: the UNIT price as a number without currency symbols. If only a line total is shown, use null.
- supplier: the vendor/supplier name if shown (it may apply to all lines of the document). batch_number: lot/batch number if shown.
- confidence: "high" only when the value is clearly printed and unambiguous; "medium" when partially legible or inferred from layout; "low" when uncertain.
- If the document contains no inventory lines, return {"items": [], "notes": "..."}.
"""


def get_extraction_llm():
    """Gemini model used for document extraction (same configuration as the PractiCare agent)."""
    from ai.agent import get_gemini_llm
    llm, model_name = get_gemini_llm(temperature=0.0)
    return llm, model_name


def extract_inventory_records(source: Dict[str, Any]) -> Dict[str, Any]:
    """Runs Gemini over a prepared source. Returns {"items": [raw rows], "notes": str, "model": str}."""
    try:
        from langchain_core.messages import HumanMessage
        from ai.agent import invoke_gemini_with_retry
        llm, model_name = get_extraction_llm()
    except ValueError as exc:  # missing GOOGLE_API_KEY
        raise ExtractionUnavailableError(f"AI extraction is not configured: {exc}")
    except ImportError as exc:
        raise ExtractionUnavailableError(f"AI runtime is not installed on the backend: {exc}")

    if source["source_type"] == "text":
        content: Any = [{"type": "text", "text": EXTRACTION_PROMPT + "\n\nSOURCE TEXT:\n<<<\n" + source["text"] + "\n>>>"}]
    else:
        content = [
            {"type": "text", "text": EXTRACTION_PROMPT},
            {"type": "file", "source_type": "base64", "mime_type": source["mime_type"],
             "data": base64.b64encode(source["data"]).decode("ascii")},
        ]
    try:
        response = invoke_gemini_with_retry(llm, [HumanMessage(content=content)])
    except Exception as exc:
        logger.error("Inventory extraction failed: %s", exc)
        msg = str(exc)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            raise ExtractionUnavailableError("Gemini quota is exhausted. Try again later.")
        raise ExtractionUnavailableError("The AI provider could not process this document. Try again or enter the items as text.")

    parsed = _parse_model_json(_response_text(response))
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        raise ExtractionUnavailableError("The AI response was not in the expected format. Nothing was extracted.")
    notes = parsed.get("notes") if isinstance(parsed.get("notes"), str) else ""
    truncated = len(items) > MAX_EXTRACTED_ROWS
    return {"items": [i for i in items[:MAX_EXTRACTED_ROWS] if isinstance(i, dict)], "notes": notes,
            "model": model_name, "truncated": truncated}


def _response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content or "")


def _parse_model_json(text: str) -> Any:
    clean = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", clean, re.DOTALL)
    if fence:
        clean = fence.group(1).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        start, end = clean.find("{"), clean.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(clean[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise ExtractionUnavailableError("The AI response could not be read as JSON. Nothing was extracted.")


def _field(raw_row: Dict[str, Any], name: str) -> Tuple[Any, str]:
    """Accepts {"value", "confidence"} objects or bare values (treated as medium confidence)."""
    cell = raw_row.get(name)
    if isinstance(cell, dict):
        value = cell.get("value")
        conf = str(cell.get("confidence") or "low").lower()
    else:
        value, conf = cell, "medium"
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, "missing"
    return value, conf if conf in CONFIDENCE_LEVELS else "low"


# ==============================================================================
# PREVIEW (validation + flags + duplicate matching; never writes)
# ==============================================================================

def build_preview(db: Session, tenant_id: str, raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Turns extracted rows into reviewable preview rows:
      values      : editable field values (missing ones stay null)
      confidence  : per field 'high' | 'medium' | 'low' | 'missing'
      issues      : [{field, level: 'error'|'warning'|'info', message}]
      match       : duplicate status against existing inventory and earlier rows of the same import
      action      : suggested action ('create' | 'restock' | 'skip'); the user decides before confirming
    """
    existing = db.query(models.InventoryItem).filter(models.InventoryItem.tenant_id == tenant_id).all()
    seen: Dict[Tuple, str] = {}
    preview = []
    for idx, raw in enumerate(raw_rows, start=1):
        row_id = f"row-{idx}"
        raw_values, confidence = {}, {}
        for f in ("item_name", "quantity", "unit", "expiry_date", "purchase_price", "supplier", "batch_number"):
            raw_values[f], confidence[f] = _field(raw, f)
        clean, errors, warnings = validate_record(raw_values, mode="preview")
        values = {f: clean.get(f) for f in ("item_name", "quantity", "unit", "expiry_date", "supplier", "batch_number")}
        values["purchase_price"] = float(clean["purchase_price"]) if clean["purchase_price"] is not None else None
        values["min_threshold"] = None
        values["room_id"] = None
        # Keep the document's text for values the server could not interpret, so the user can correct it
        for f in ("expiry_date", "quantity", "purchase_price"):
            if values[f] is None and raw_values[f] is not None:
                values[f] = str(raw_values[f])

        issues = [{"field": _issue_field(e), "level": "error", "message": e} for e in errors]
        issues += [{"field": "expiry_date", "level": "warning", "message": w} for w in warnings]
        for f in ("item_name", "quantity", "unit"):
            if raw_values[f] is None:
                issues.append({"field": f, "level": "error", "message": f"{_label(f)} was not found in the document; enter it before importing."})
        for f in ("expiry_date", "purchase_price", "supplier", "batch_number"):
            if raw_values[f] is None:
                issues.append({"field": f, "level": "info", "message": f"{_label(f)} not found in the document; it will be left empty."})
        for f, conf in confidence.items():
            if conf in ("low", "medium") and raw_values[f] is not None:
                issues.append({"field": f, "level": "warning", "message": f"{_label(f)} read with {conf} confidence; please verify."})
        issues.append({"field": "min_threshold", "level": "info",
                       "message": f"Minimum threshold is not part of the document; the system default ({DEFAULT_MIN_THRESHOLD}) applies unless you set it."})

        match = {"status": "new", "existing_item_id": None, "existing": None, "similar": []}
        action = "create"
        if clean["item_name"]:
            ident = record_identity(clean["item_name"], clean["batch_number"], clean["expiry_date"])
            found = find_inventory_matches(db, tenant_id, clean["item_name"], clean["batch_number"], clean["expiry_date"], items=existing)
            if ident in seen:
                match = {"status": "duplicate_in_import", "duplicate_of_row": seen[ident], "existing_item_id": None, "existing": None, "similar": []}
                action = "skip"
                issues.append({"field": "item_name", "level": "warning", "message": f"Same item, batch and expiry as {seen[ident]} in this import; skipped by default."})
            elif found["exact"]:
                hit = found["exact"][0]
                match = {"status": "existing_match", "existing_item_id": hit.id, "existing": item_summary(hit), "similar": []}
                action = "skip"
                issues.append({"field": "item_name", "level": "warning",
                               "message": f"Matches existing record {hit.id} (same item, batch and expiry). Skipped by default; choose 'Add to stock' to restock it."})
            elif found["similar"]:
                match["status"] = "similar_exists"
                match["similar"] = [item_summary(s) for s in found["similar"][:5]]
                issues.append({"field": "item_name", "level": "info",
                               "message": "An item with this name exists with a different batch or expiry; a separate record will be created."})
            seen.setdefault(ident, row_id)

        # Rows with errors keep their suggested action; confirmation rejects them until the user fixes the errors
        preview.append({"row_id": row_id, "values": values, "confidence": confidence, "issues": issues,
                        "match": match, "action": action})
    return preview


def _issue_field(message: str) -> str:
    lower = message.lower()
    for f, key in (("expiry_date", "expiry"), ("purchase_price", "price"), ("min_threshold", "threshold"),
                   ("quantity", "quantity"), ("unit", "unit"), ("supplier", "supplier"),
                   ("batch_number", "batch"), ("item_name", "name")):
        if key in lower:
            return f
    return "item_name"


def _label(field: str) -> str:
    return {"item_name": "Item name", "quantity": "Quantity", "unit": "Unit", "expiry_date": "Expiry date",
            "purchase_price": "Purchase price", "supplier": "Supplier", "batch_number": "Batch number",
            "min_threshold": "Minimum threshold"}.get(field, field)


def new_import_token() -> str:
    return secrets.token_urlsafe(24)


def prior_imports(db: Session, tenant_id: str, source_hash: str) -> List[Dict[str, Any]]:
    rows = db.query(models.InventoryImport).filter(
        models.InventoryImport.tenant_id == tenant_id,
        models.InventoryImport.source_hash == source_hash,
    ).order_by(models.InventoryImport.created_at.desc()).limit(5).all()
    return [{"import_id": r.id, "imported_at": r.created_at.isoformat() if r.created_at else None,
             "created_count": r.created_count, "updated_count": r.updated_count} for r in rows]


# ==============================================================================
# CONFIRMED IMPORT (single transaction, idempotent)
# ==============================================================================

class ImportAlreadyProcessedError(Exception):
    """The import_token was already used. `result` is the earlier result when it belongs to the same tenant."""

    def __init__(self, result: Optional[Dict[str, Any]]):
        super().__init__("This import was already confirmed.")
        self.result = result


def apply_import(db: Session, *, tenant_id: str, user_id: str, practice_id: str, import_token: str,
                 source_hash: str, source_type: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Applies user-confirmed rows. Every row is validated again here (the preview is never trusted):
      create  : new record; rejected if an identical lot (name + batch + expiry) already exists.
      restock : adds the quantity to existing_item_id. Existing values are never overwritten: empty fields
                are filled from the row, differing non-empty values are kept and reported. A different batch,
                expiry or unit means a different lot and is rejected.
      skip    : nothing is written.
    All writes happen in one transaction with the InventoryImport record, whose unique import_token makes a
    repeated confirmation fail instead of importing twice. If no row is written, nothing is recorded and the
    same token can be confirmed again after corrections.
    """
    previous = db.query(models.InventoryImport).filter(models.InventoryImport.import_token == import_token).first()
    if previous:
        raise ImportAlreadyProcessedError(json.loads(previous.result_json) if previous.tenant_id == tenant_id else None)

    rooms = {r.id for r in db.query(models.Room.id).filter(models.Room.tenant_id == tenant_id).all()}
    items = db.query(models.InventoryItem).filter(models.InventoryItem.tenant_id == tenant_id).all()
    by_id = {i.id: i for i in items}
    created, updated, skipped, rejected = [], [], [], []
    seen_ids = set()

    try:
        for row in rows:
            row_id = str(row.get("row_id") or "")
            action = row.get("action")
            label = _text(row.get("item_name")) or "(unnamed)"
            if row_id in seen_ids:
                rejected.append({"row_id": row_id, "item_name": label, "errors": ["Duplicate row_id in request."]})
                continue
            seen_ids.add(row_id)

            if action == "skip":
                skipped.append({"row_id": row_id, "item_name": label, "reason": "Skipped by user."})
                continue
            if action not in ("create", "restock"):
                rejected.append({"row_id": row_id, "item_name": label, "errors": [f"Unknown action '{action}'."]})
                continue

            clean, errors, _warnings = validate_record(row, mode=action)
            if clean["room_id"] and clean["room_id"] not in rooms:
                errors.append("Room not found in this practice.")
            if errors:
                rejected.append({"row_id": row_id, "item_name": label, "errors": errors})
                continue

            if action == "create":
                found = find_inventory_matches(db, tenant_id, clean["item_name"], clean["batch_number"], clean["expiry_date"], items=items)
                if found["exact"]:
                    hit = found["exact"][0]
                    rejected.append({"row_id": row_id, "item_name": clean["item_name"], "errors": [
                        f"Duplicate of existing record {hit.id} (same item, batch and expiry). Choose 'Add to stock' or skip it."]})
                    continue
                item = models.InventoryItem(
                    id=models.generate_id("inv"),
                    item_name=clean["item_name"],
                    current_stock=clean["quantity"],
                    min_threshold=clean["min_threshold"] if clean["min_threshold"] is not None else DEFAULT_MIN_THRESHOLD,
                    unit=clean["unit"],
                    expiry_date=clean["expiry_date"],
                    supplier=clean["supplier"],
                    batch_number=clean["batch_number"],
                    purchase_price=clean["purchase_price"],
                    room_id=clean["room_id"],
                    practice_id=practice_id,
                    tenant_id=tenant_id,
                )
                db.add(item)
                items.append(item)
                by_id[item.id] = item
                created.append({"row_id": row_id, "item_id": item.id, "item_name": item.item_name,
                                "quantity": item.current_stock, "unit": item.unit})
                continue

            # restock
            target = by_id.get(str(row.get("existing_item_id") or ""))
            if not target:
                rejected.append({"row_id": row_id, "item_name": label, "errors": ["Existing item to restock was not found in this practice."]})
                continue
            lot_errors = []
            if clean["item_name"] and name_key(clean["item_name"]) != name_key(target.item_name):
                lot_errors.append(f"Item name '{clean['item_name']}' does not match existing record '{target.item_name}'.")
            if clean["batch_number"] and target.batch_number and _opt_key(clean["batch_number"]) != _opt_key(target.batch_number):
                lot_errors.append(f"Batch {clean['batch_number']} differs from existing batch {target.batch_number}; import it as a new record.")
            if clean["expiry_date"] and parse_expiry(target.expiry_date) and clean["expiry_date"] != parse_expiry(target.expiry_date).isoformat():
                lot_errors.append(f"Expiry {clean['expiry_date']} differs from existing expiry {target.expiry_date}; import it as a new record.")
            if clean["unit"] and target.unit and clean["unit"].casefold() != target.unit.casefold():
                lot_errors.append(f"Unit '{clean['unit']}' differs from the existing unit '{target.unit}'; quantities cannot be added.")
            if target.current_stock + clean["quantity"] > MAX_QUANTITY:
                lot_errors.append("Resulting stock would exceed the maximum quantity.")
            if lot_errors:
                rejected.append({"row_id": row_id, "item_name": label, "errors": lot_errors})
                continue

            filled, kept = [], []
            for f in ("expiry_date", "supplier", "batch_number", "purchase_price"):  # location is never changed by a restock
                new_val = clean.get(f)
                if new_val is None:
                    continue
                old_val = getattr(target, f)
                if old_val is None or (isinstance(old_val, str) and not old_val.strip()):
                    setattr(target, f, new_val)
                    filled.append(f)
                elif str(old_val) != str(new_val) and f != "expiry_date":
                    kept.append({"field": f, "kept": str(old_val), "document_value": str(new_val)})
            previous_stock = target.current_stock
            target.current_stock = previous_stock + clean["quantity"]
            updated.append({"row_id": row_id, "item_id": target.id, "item_name": target.item_name,
                            "quantity_added": clean["quantity"], "previous_stock": previous_stock,
                            "new_stock": target.current_stock, "fields_filled": filled, "kept_existing": kept})

        result = {
            "import_token": import_token,
            "created": created, "updated": updated, "skipped": skipped, "rejected": rejected,
            "counts": {"created": len(created), "updated": len(updated), "skipped": len(skipped), "rejected": len(rejected)},
        }
        if not created and not updated:
            db.rollback()
            result["import_id"] = None
            result["status"] = "NOTHING_IMPORTED"
            return result

        record = models.InventoryImport(
            id=models.generate_id("imp"), tenant_id=tenant_id, user_id=user_id, import_token=import_token,
            source_type=source_type, source_hash=source_hash,
            created_count=len(created), updated_count=len(updated), skipped_count=len(skipped), rejected_count=len(rejected),
        )
        result["import_id"] = record.id
        result["status"] = "IMPORTED"
        record.result_json = json.dumps(result, default=str)
        db.add(record)
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.query(models.InventoryImport).filter(models.InventoryImport.import_token == import_token).first()
        raise ImportAlreadyProcessedError(json.loads(previous.result_json) if previous and previous.tenant_id == tenant_id else None)
    except Exception:
        db.rollback()
        raise

    # Post-commit verification: report only what PostgreSQL actually holds
    written_ids = [c["item_id"] for c in created] + [u["item_id"] for u in updated]
    persisted = {i.id for i in db.query(models.InventoryItem.id).filter(
        models.InventoryItem.tenant_id == tenant_id, models.InventoryItem.id.in_(written_ids)).all()}
    if persisted != set(written_ids):
        raise RuntimeError("Inventory import persistence verification failed.")
    result["persisted"] = True
    return result
