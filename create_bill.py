"""Create hybrid ZUGFeRD/Factur-X PDF invoices from nested EN 16931 parameters.

The public entry point is create_bill(params). params is a nested dict (typically
loaded from JSON, see data/input/ for examples) whose structure mirrors the business
groups of EN 16931 (seller, buyer, lines, VAT breakdown, totals, ...). Internally it
is flattened into the flat BT-nnn/BG-nnn dict expected by the `factur-x` library,
which builds and validates the actual Cross-Industry-Invoice XML against the official
EN 16931 XSD, then embeds it into a PDF/A-3 document as a proper Factur-X attachment.
"""

import datetime
from io import BytesIO

from facturx import generate_cii_xml, generate_from_binary
from PIL import ImageCms
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    StreamObject,
    TextStringObject,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_NAME = "BitstreamVeraSans"
FONT_NAME_BOLD = "BitstreamVeraSans-Bold"


def create_bill(params: dict) -> bytes:
    """Build a hybrid Factur-X/ZUGFeRD PDF invoice and return it as bytes.

    params is a nested dict following the EN 16931 business groups (see the example
    JSON files under data/input/). The resulting PDF is human-readable (rendered with
    reportlab) and machine-readable (a Factur-X XML invoice per EN 16931 embedded as
    a PDF attachment), i.e. a "hybrid" invoice document.
    """
    level = params.get("level", "en16931")

    data_dict = _to_facturx_dict(params, level)
    xml_bytes = generate_cii_xml(data_dict, level=level, check_xsd=True, check_schematron=False)

    visual_pdf = _render_visual_pdf(params)
    pdfa_pdf = _add_pdfa_output_intent(visual_pdf)

    pdf_metadata = _build_pdf_metadata(params)
    return generate_from_binary(
        pdfa_pdf,
        xml_bytes,
        level=level,
        check_xsd=False,
        pdf_metadata=pdf_metadata,
    )


# ---------------------------------------------------------------------------
# params (nested JSON) -> factur-x data_dict (flat BT-nnn/BG-nnn) mapping
# ---------------------------------------------------------------------------

def _to_facturx_dict(params: dict, level: str) -> dict:
    data = {}
    invoice = params["invoice"]

    data["BT-1"] = invoice["id"]
    data["BT-2"] = _date(invoice["issue_date"])
    data["BT-3"] = invoice["type_code"]
    data["BT-5"] = params["totals"]["currency"]

    if params.get("business_process_id"):
        data["BT-23"] = params["business_process_id"]

    if invoice.get("notes"):
        data["BG-1"] = [
            {"BT-22": note["text"], "BT-21": note.get("subject_code")}
            for note in invoice["notes"]
        ]

    if invoice.get("buyer_reference"):
        data["BT-10"] = invoice["buyer_reference"]
    if invoice.get("project_reference"):
        data["BT-11"] = invoice["project_reference"]["id"]
        data["BT-11-0"] = invoice["project_reference"]["name"]
    if invoice.get("contract_reference"):
        data["BT-12"] = invoice["contract_reference"]
    if invoice.get("purchase_order_reference"):
        data["BT-13"] = invoice["purchase_order_reference"]
    if invoice.get("sales_order_reference"):
        data["BT-14"] = invoice["sales_order_reference"]
    if invoice.get("receiving_advice_reference"):
        data["BT-15"] = invoice["receiving_advice_reference"]
    if invoice.get("despatch_advice_reference"):
        data["BT-16"] = invoice["despatch_advice_reference"]
    if invoice.get("tender_or_lot_reference"):
        data["BT-17"] = invoice["tender_or_lot_reference"]
    if invoice.get("object_references"):
        data["BT-18-00"] = {
            ref["reference_type_code"]: ref["value"] for ref in invoice["object_references"]
        }
    if invoice.get("buyer_accounting_reference"):
        data["BT-19"] = invoice["buyer_accounting_reference"]

    if invoice.get("preceding_invoices"):
        data["BG-3"] = [
            {
                "BT-25": pi["number"],
                "BT-26": _date(pi["issue_date"]) if pi.get("issue_date") else None,
            }
            for pi in invoice["preceding_invoices"]
        ]

    if invoice.get("invoicing_period"):
        period = invoice["invoicing_period"]
        data["BT-73"] = _date(period["start"])
        data["BT-74"] = _date(period["end"])

    if invoice.get("supporting_documents"):
        data["BG-24"] = [
            {
                "BT-122": doc["id"],
                "BT-123": doc.get("description"),
                "BT-124": doc.get("uri"),
                "BT-125": doc.get("attached_file_base64"),
                "BT-125-1": doc.get("attached_file_mimecode"),
                "BT-125-2": doc.get("attached_file_name"),
            }
            for doc in invoice["supporting_documents"]
        ]

    data.update(_map_seller(params["seller"]))
    data.update(_map_buyer(params["buyer"]))
    if params.get("payee"):
        data.update(_map_payee(params["payee"]))
    if params.get("seller_tax_representative"):
        data.update(_map_tax_representative(params["seller_tax_representative"]))

    delivery = params.get("delivery")
    if delivery:
        if delivery.get("ship_to"):
            data.update(_map_ship_to(delivery["ship_to"]))
        if delivery.get("actual_delivery_date"):
            data["BT-72"] = _date(delivery["actual_delivery_date"])
        if delivery.get("despatch_advice_reference"):
            data["BT-16"] = delivery["despatch_advice_reference"]
        if delivery.get("receiving_advice_reference"):
            data["BT-15"] = delivery["receiving_advice_reference"]

    payment = params.get("payment")
    if payment:
        data.update(_map_payment(payment))

    if params.get("document_allowances"):
        data["BG-20"] = [_map_document_allowance(a) for a in params["document_allowances"]]
    if params.get("document_charges"):
        data["BG-21"] = [_map_document_charge(c) for c in params["document_charges"]]

    data["BG-23"] = [_map_vat_breakdown_entry(v) for v in params["vat_breakdown"]]
    tax_point_dates = [v.get("tax_point_date") for v in params["vat_breakdown"] if v.get("tax_point_date")]
    if tax_point_dates:
        data["BT-7"] = _date(tax_point_dates[0])
    due_date_types = [v.get("due_date_type") for v in params["vat_breakdown"] if v.get("due_date_type")]
    if due_date_types:
        data["BT-8"] = due_date_types[0]

    data["BG-25"] = [_map_line(line) for line in params["lines"]]

    data.update(_map_totals(params["totals"]))

    return data


def _map_seller(seller: dict) -> dict:
    address = seller.get("address", {})
    result = {
        "BT-27": seller["name"],
        "BT-40": address["country_code"],
        "BT-35": address.get("line1"),
        "BT-36": address.get("line2"),
        "BT-162": address.get("line3"),
        "BT-37": address.get("city"),
        "BT-38": address.get("postcode"),
        "BT-39": address.get("country_subdivision"),
    }
    if seller.get("identifiers"):
        result["BT-29"] = _map_identifiers(seller["identifiers"])
    if seller.get("legal_form"):
        result["BT-33"] = seller["legal_form"]
    if seller.get("legal_registration_id"):
        result["BT-30"] = seller["legal_registration_id"]["id"]
        result["BT-30-1"] = seller["legal_registration_id"]["scheme_id"]
    if seller.get("trading_name"):
        result["BT-28"] = seller["trading_name"]
    contact = seller.get("contact")
    if contact:
        result.update(
            {
                "BT-41": contact.get("name"),
                "BT-41-0": contact.get("department"),
                "BT-42": contact.get("phone"),
                "BT-43": contact.get("email"),
            }
        )
    if seller.get("electronic_address"):
        result["BT-34"] = seller["electronic_address"]["id"]
        result["BT-34-1"] = seller["electronic_address"]["scheme_id"]
    if seller.get("vat_id"):
        result["BT-31"] = seller["vat_id"]
    if seller.get("local_tax_id"):
        result["BT-32"] = seller["local_tax_id"]
    return result


def _map_buyer(buyer: dict) -> dict:
    address = buyer.get("address", {})
    result = {
        "BT-44": buyer["name"],
        "BT-55": address["country_code"],
        "BT-50": address.get("line1"),
        "BT-51": address.get("line2"),
        "BT-163": address.get("line3"),
        "BT-52": address.get("city"),
        "BT-53": address.get("postcode"),
        "BT-54": address.get("country_subdivision"),
    }
    if buyer.get("identifiers"):
        result["BT-46"] = _map_identifiers(buyer["identifiers"])
    if buyer.get("legal_registration_id"):
        result["BT-47"] = buyer["legal_registration_id"]["id"]
        result["BT-47-1"] = buyer["legal_registration_id"]["scheme_id"]
    if buyer.get("trading_name"):
        result["BT-45"] = buyer["trading_name"]
    contact = buyer.get("contact")
    if contact:
        result.update(
            {
                "BT-56": contact.get("name"),
                "BT-56-0": contact.get("department"),
                "BT-57": contact.get("phone"),
                "BT-58": contact.get("email"),
            }
        )
    if buyer.get("electronic_address"):
        result["BT-49"] = buyer["electronic_address"]["id"]
        result["BT-49-1"] = buyer["electronic_address"]["scheme_id"]
    if buyer.get("vat_id"):
        result["BT-48"] = buyer["vat_id"]
    return result


def _map_payee(payee: dict) -> dict:
    result = {"BT-59": payee["name"]}
    if payee.get("identifiers"):
        result["BT-60"] = _map_identifiers(payee["identifiers"])
    if payee.get("legal_registration_id"):
        result["BT-61"] = payee["legal_registration_id"]["id"]
        result["BT-61-1"] = payee["legal_registration_id"]["scheme_id"]
    return result


def _map_tax_representative(rep: dict) -> dict:
    address = rep.get("address", {})
    result = {
        "BT-62": rep["name"],
        "BT-69": address["country_code"],
        "BT-64": address.get("line1"),
        "BT-65": address.get("line2"),
        "BT-164": address.get("line3"),
        "BT-66": address.get("city"),
        "BT-67": address.get("postcode"),
        "BT-68": address.get("country_subdivision"),
    }
    if rep.get("vat_id"):
        result["BT-63"] = rep["vat_id"]
    return result


def _map_ship_to(ship_to: dict) -> dict:
    address = ship_to.get("address", {})
    result = {
        "BT-70": ship_to.get("name"),
        "BT-80": address.get("country_code"),
        "BT-75": address.get("line1"),
        "BT-76": address.get("line2"),
        "BT-165": address.get("line3"),
        "BT-77": address.get("city"),
        "BT-78": address.get("postcode"),
        "BT-79": address.get("country_subdivision"),
    }
    if ship_to.get("identifiers"):
        result["BT-71"] = _map_identifiers(ship_to["identifiers"])
    return result


def _map_identifiers(identifiers: list) -> dict:
    return {(ident.get("scheme_id") or ""): ident["id"] for ident in identifiers}


def _map_payment(payment: dict) -> dict:
    result = {}
    if payment.get("payment_reference"):
        result["BT-83"] = payment["payment_reference"]
    if payment.get("creditor_reference_id"):
        result["BT-90"] = payment["creditor_reference_id"]
    if payment.get("tax_currency_code"):
        result["BT-6"] = payment["tax_currency_code"]
    if payment.get("payment_terms"):
        result["BT-20"] = payment["payment_terms"]
    if payment.get("due_date"):
        result["BT-9"] = _date(payment["due_date"])
    if payment.get("direct_debit_mandate_id"):
        result["BT-89"] = payment["direct_debit_mandate_id"]

    means = payment.get("means")
    if means and means.get("type_code"):
        result["BT-81"] = means["type_code"]
        if means.get("information"):
            result["BT-82"] = means["information"]
        card = means.get("card")
        if card:
            result["BT-87"] = card["id"]
            if card.get("holder_name"):
                result["BT-88"] = card["holder_name"]
        if means.get("payer_iban"):
            result["BT-91"] = means["payer_iban"]
        payee_account = means.get("payee_account")
        if payee_account:
            if payee_account.get("iban"):
                result["BT-84"] = payee_account["iban"]
            if payee_account.get("account_name"):
                result["BT-85"] = payee_account["account_name"]
            if payee_account.get("bic"):
                result["BT-86"] = payee_account["bic"]
    return result


def _map_document_allowance(entry: dict) -> dict:
    return {
        "BT-92": entry["amount"],
        "BT-93": entry.get("base_amount"),
        "BT-94": entry.get("percent"),
        "BT-95": entry["tax_category"],
        "BT-96": entry.get("tax_rate"),
        "BT-97": entry.get("reason"),
        "BT-98": entry.get("reason_code"),
    }


def _map_document_charge(entry: dict) -> dict:
    return {
        "BT-99": entry["amount"],
        "BT-100": entry.get("base_amount"),
        "BT-101": entry.get("percent"),
        "BT-102": entry["tax_category"],
        "BT-103": entry.get("tax_rate"),
        "BT-104": entry.get("reason"),
        "BT-105": entry.get("reason_code"),
    }


def _map_line_allowance(entry: dict) -> dict:
    return {
        "BT-136": entry["amount"],
        "BT-137": entry.get("base_amount"),
        "BT-138": entry.get("percent"),
        "BT-139": entry.get("reason"),
        "BT-140": entry.get("reason_code"),
    }


def _map_line_charge(entry: dict) -> dict:
    return {
        "BT-141": entry["amount"],
        "BT-142": entry.get("base_amount"),
        "BT-143": entry.get("percent"),
        "BT-144": entry.get("reason"),
        "BT-145": entry.get("reason_code"),
    }


def _map_vat_breakdown_entry(entry: dict) -> dict:
    return {
        "BT-116": entry["taxable_amount"],
        "BT-117": entry["tax_amount"],
        "BT-118": entry["category_code"],
        "BT-119": entry.get("rate"),
        "BT-120": entry.get("exemption_reason"),
        "BT-121": entry.get("exemption_reason_code"),
    }


def _map_line(line: dict) -> dict:
    product = line["product"]
    price = line["price"]
    quantity = line["quantity"]
    vat = line["vat"]

    result = {
        "BT-126": line["line_id"],
        "BT-153": product["name"],
        "BT-146": price["net_unit_price"],
        "BT-129": quantity["value"],
        "BT-130": quantity["unit_code"],
        "BT-151": vat["category_code"],
        "BT-152": vat.get("rate"),
        "BT-131": line["line_total_amount"],
    }
    if line.get("notes"):
        result["BT-127"] = line["notes"]
    if product.get("description"):
        result["BT-154"] = product["description"]
    if product.get("global_id"):
        result["BT-157"] = product["global_id"]["id"]
        result["BT-157-1"] = product["global_id"]["scheme_id"]
    if product.get("seller_assigned_id"):
        result["BT-155"] = product["seller_assigned_id"]
    if product.get("buyer_assigned_id"):
        result["BT-156"] = product["buyer_assigned_id"]
    if product.get("attributes"):
        result["BG-32"] = {attr["name"]: attr["value"] for attr in product["attributes"]}
    if product.get("classifications"):
        result["BT-158-00"] = {
            (cls["list_id"], cls.get("list_version_id")): cls["code"]
            for cls in product["classifications"]
        }
    if product.get("origin_country_code"):
        result["BT-159"] = product["origin_country_code"]
    if price.get("gross_unit_price"):
        result["BT-148"] = price["gross_unit_price"]
    if price.get("base_quantity"):
        result["BT-149-1"] = price["base_quantity"]["value"]
        result["BT-150-1"] = price["base_quantity"]["unit_code"]
    if price.get("discount_amount"):
        result["BT-147"] = price["discount_amount"]
    if price.get("net_base_quantity"):
        result["BT-149"] = price["net_base_quantity"]["value"]
        result["BT-150"] = price["net_base_quantity"]["unit_code"]
    if line.get("invoicing_period"):
        period = line["invoicing_period"]
        result["BT-134"] = _date(period["start"])
        result["BT-135"] = _date(period["end"])
    if line.get("allowances"):
        result["BG-27"] = [_map_line_allowance(a) for a in line["allowances"]]
    if line.get("charges"):
        result["BG-28"] = [_map_line_charge(c) for c in line["charges"]]
    if line.get("object_references"):
        result["BT-128-00"] = {
            ref["reference_type_code"]: ref["value"] for ref in line["object_references"]
        }
    if line.get("buyer_accounting_reference"):
        result["BT-133"] = line["buyer_accounting_reference"]
    return result


def _map_totals(totals: dict) -> dict:
    result = {
        "BT-106": totals["sum_of_line_amounts"],
        "BT-109": totals["tax_basis_total"],
        "BT-110": totals["tax_total"],
        "BT-110-1": totals["currency"],
        "BT-112": totals["grand_total"],
        "BT-115": totals["due_payable_amount"],
    }
    if totals.get("allowance_total"):
        result["BT-107"] = totals["allowance_total"]
    if totals.get("charge_total"):
        result["BT-108"] = totals["charge_total"]
    if totals.get("tax_total_in_accounting_currency"):
        entry = totals["tax_total_in_accounting_currency"]
        result["BT-111"] = entry["amount"]
        result["BT-111-1"] = entry["currency"]
    if totals.get("rounding_amount"):
        result["BT-114"] = totals["rounding_amount"]
    if totals.get("prepaid_amount"):
        result["BT-113"] = totals["prepaid_amount"]
    return result


def _date(value) -> datetime.date:
    return datetime.date.fromisoformat(value)


# ---------------------------------------------------------------------------
# Visual (human-readable) PDF rendering
# ---------------------------------------------------------------------------

def _register_fonts():
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return
    base_dir = pdfmetrics.__file__.rsplit("pdfbase", 1)[0]
    pdfmetrics.registerFont(TTFont(FONT_NAME, base_dir + "fonts/Vera.ttf"))
    pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, base_dir + "fonts/VeraBd.ttf"))


def _render_visual_pdf(params: dict) -> bytes:
    _register_fonts()

    invoice = params["invoice"]
    seller = params["seller"]
    buyer = params["buyer"]
    totals = params["totals"]

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Invoice {invoice['id']}")
    width, height = A4
    left = 20 * mm
    y = height - 20 * mm

    c.setFont(FONT_NAME_BOLD, 16)
    c.drawString(left, y, f"Invoice {invoice['id']}")
    y -= 8 * mm

    c.setFont(FONT_NAME, 10)
    c.drawString(left, y, f"Issue date: {invoice['issue_date']}")
    y -= 10 * mm

    c.setFont(FONT_NAME_BOLD, 11)
    c.drawString(left, y, "Seller")
    c.drawString(left + 90 * mm, y, "Buyer")
    y -= 6 * mm
    y_parties_start = y
    c.setFont(FONT_NAME, 10)
    for text in _party_lines(seller):
        c.drawString(left, y, text)
        y -= 5 * mm
    y_after_seller = y
    y = y_parties_start
    for text in _party_lines(buyer):
        c.drawString(left + 90 * mm, y, text)
        y -= 5 * mm
    y = min(y, y_after_seller) - 10 * mm

    c.setFont(FONT_NAME_BOLD, 10)
    headers = ["#", "Description", "Qty", "Unit price", "VAT %", "Line total"]
    col_x = [left, left + 12 * mm, left + 95 * mm, left + 115 * mm, left + 145 * mm, left + 165 * mm]
    for header, x in zip(headers, col_x):
        c.drawString(x, y, header)
    y -= 5 * mm
    c.line(left, y, width - 20 * mm, y)
    y -= 5 * mm

    c.setFont(FONT_NAME, 9)
    for line in params["lines"]:
        product = line["product"]
        quantity = line["quantity"]
        price = line["price"]
        vat = line["vat"]
        row = [
            line["line_id"],
            product["name"],
            f"{quantity['value']} {quantity['unit_code']}",
            f"{price['net_unit_price']} {totals['currency']}",
            f"{vat.get('rate', '-')}",
            f"{line['line_total_amount']} {totals['currency']}",
        ]
        for value, x in zip(row, col_x):
            c.drawString(x, y, str(value))
        y -= 5 * mm
        if y < 40 * mm:
            c.showPage()
            c.setFont(FONT_NAME, 9)
            y = height - 20 * mm

    y -= 5 * mm
    c.line(left, y, width - 20 * mm, y)
    y -= 8 * mm

    c.setFont(FONT_NAME, 10)
    totals_rows = [
        ("Sum of line amounts", totals["sum_of_line_amounts"]),
        ("Tax basis total", totals["tax_basis_total"]),
        ("Tax total", totals["tax_total"]),
    ]
    if totals.get("allowance_total"):
        totals_rows.append(("Allowance total", totals["allowance_total"]))
    if totals.get("charge_total"):
        totals_rows.append(("Charge total", totals["charge_total"]))
    if totals.get("prepaid_amount"):
        totals_rows.append(("Prepaid amount", totals["prepaid_amount"]))
    totals_rows.append(("Grand total", totals["grand_total"]))
    totals_rows.append(("Due payable amount", totals["due_payable_amount"]))

    for label, value in totals_rows:
        c.drawString(left + 110 * mm, y, label)
        c.drawRightString(width - 20 * mm, y, f"{value} {totals['currency']}")
        y -= 5 * mm

    payment = params.get("payment") or {}
    if payment.get("payment_terms") or payment.get("due_date"):
        y -= 8 * mm
        c.setFont(FONT_NAME_BOLD, 10)
        c.drawString(left, y, "Payment")
        y -= 5 * mm
        c.setFont(FONT_NAME, 9)
        if payment.get("payment_terms"):
            c.drawString(left, y, payment["payment_terms"])
            y -= 5 * mm
        if payment.get("due_date"):
            c.drawString(left, y, f"Due date: {payment['due_date']}")
            y -= 5 * mm

    if invoice.get("notes"):
        y -= 5 * mm
        c.setFont(FONT_NAME_BOLD, 10)
        c.drawString(left, y, "Notes")
        y -= 5 * mm
        c.setFont(FONT_NAME, 9)
        for note in invoice["notes"]:
            c.drawString(left, y, note["text"])
            y -= 5 * mm

    c.showPage()
    c.save()
    return buf.getvalue()


def _party_lines(party: dict) -> list:
    address = party.get("address", {})
    lines = [party["name"]]
    if address.get("line1"):
        lines.append(address["line1"])
    if address.get("line2"):
        lines.append(address["line2"])
    postcode_city = " ".join(filter(None, [address.get("postcode"), address.get("city")]))
    if postcode_city:
        lines.append(postcode_city)
    if address.get("country_code"):
        lines.append(address["country_code"])
    if party.get("vat_id"):
        lines.append(f"VAT ID: {party['vat_id']}")
    return lines


# ---------------------------------------------------------------------------
# PDF/A-3 OutputIntent (required for a conformant Factur-X/ZUGFeRD hybrid PDF)
# ---------------------------------------------------------------------------

def _add_pdfa_output_intent(pdf_bytes: bytes) -> bytes:
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.append(reader)

    icc_bytes = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    icc_stream = StreamObject()
    icc_stream.set_data(icc_bytes)
    icc_stream.update(
        {
            NameObject("/N"): NumberObject(3),
            NameObject("/Alternate"): NameObject("/DeviceRGB"),
        }
    )
    icc_stream = icc_stream.flate_encode()
    icc_ref = writer._add_object(icc_stream)

    output_intent = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/OutputIntent"),
            NameObject("/S"): NameObject("/GTS_PDFA1"),
            NameObject("/OutputConditionIdentifier"): TextStringObject("sRGB IEC61966-2.1"),
            NameObject("/Info"): TextStringObject("sRGB IEC61966-2.1"),
            NameObject("/DestOutputProfile"): icc_ref,
        }
    )
    oi_ref = writer._add_object(output_intent)
    writer._root_object[NameObject("/OutputIntents")] = ArrayObject([oi_ref])

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def _build_pdf_metadata(params: dict) -> dict:
    invoice = params["invoice"]
    seller = params["seller"]
    return {
        "author": seller["name"],
        "keywords": "Invoice, Factur-X, ZUGFeRD",
        "title": f"{seller['name']}: Invoice {invoice['id']}",
        "subject": f"Factur-X invoice {invoice['id']} dated {invoice['issue_date']} issued by {seller['name']}",
    }
