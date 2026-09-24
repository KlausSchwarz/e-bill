"""Language/locale profiles for the human-readable invoice rendering.

Supported languages: "de" (German, default) and "en" (English). Each profile
bundles the visible labels together with the locale conventions the EN 16931
standard leaves up to national/company convention when rendering the
human-readable page: date format, number format, paper size, and address
line order.

This only affects the *visual* PDF page. The embedded Factur-X/ZUGFeRD XML
(the machine-readable side) always uses the EN 16931-mandated ISO date
format and plain decimal amounts, regardless of language, so invoices stay
interoperable no matter which language they were rendered in.

Note on the "en" profile: it uses US-style conventions (Letter paper,
MM/DD/YYYY dates) since that is the more common "English" default in
European business software. If your use case needs UK/international
conventions (A4, DD/MM/YYYY) instead, adjust the "en" LocaleProfile below.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from reportlab.lib.pagesizes import A4, LETTER

DEFAULT_LANGUAGE = "de"


@dataclass(frozen=True)
class LocaleProfile:
    language: str
    rfc3066_code: str  # for the PDF /Lang entry and the Factur-X `lang` option
    page_size: tuple
    date_format: str  # strftime pattern used to display ISO dates
    decimal_separator: str
    thousands_separator: str
    address_order: str  # "postcode_city" (DE-style) or "city_postcode" (US-style)
    labels: dict


LOCALE_PROFILES = {
    "de": LocaleProfile(
        language="de",
        rfc3066_code="de-DE",
        page_size=A4,
        date_format="%d.%m.%Y",
        decimal_separator=",",
        thousands_separator=".",
        address_order="postcode_city",
        labels={
            "invoice": "Rechnung",
            "issue_date": "Rechnungsdatum",
            "seller": "Verkäufer",
            "buyer": "Käufer",
            "vat_id": "USt-IdNr.",
            "col_pos": "Pos.",
            "col_description": "Beschreibung",
            "col_qty": "Menge",
            "col_unit_price": "Einzelpreis",
            "col_vat_percent": "USt %",
            "col_line_total": "Gesamtpreis",
            "sum_of_line_amounts": "Zwischensumme (netto)",
            "tax_basis_total": "Steuerbemessungsgrundlage",
            "tax_total": "Umsatzsteuer gesamt",
            "allowance_total": "Abzüge gesamt",
            "charge_total": "Zuschläge gesamt",
            "prepaid_amount": "Bereits gezahlter Betrag",
            "grand_total": "Rechnungsbetrag (brutto)",
            "due_payable_amount": "Zu zahlender Betrag",
            "payment": "Zahlung",
            "due_date": "Fällig am",
            "notes": "Anmerkungen",
            "pdf_title": "{seller}: Rechnung {id}",
            "pdf_subject": "Rechnung {id} vom {date}, ausgestellt von {seller}",
            "pdf_keywords": "Rechnung, Factur-X, ZUGFeRD",
        },
    ),
    "en": LocaleProfile(
        language="en",
        rfc3066_code="en-US",
        page_size=LETTER,
        date_format="%m/%d/%Y",
        decimal_separator=".",
        thousands_separator=",",
        address_order="city_postcode",
        labels={
            "invoice": "Invoice",
            "issue_date": "Issue date",
            "seller": "Seller",
            "buyer": "Buyer",
            "vat_id": "VAT ID",
            "col_pos": "#",
            "col_description": "Description",
            "col_qty": "Qty",
            "col_unit_price": "Unit price",
            "col_vat_percent": "VAT %",
            "col_line_total": "Line total",
            "sum_of_line_amounts": "Sum of line amounts",
            "tax_basis_total": "Tax basis total",
            "tax_total": "Tax total",
            "allowance_total": "Allowance total",
            "charge_total": "Charge total",
            "prepaid_amount": "Prepaid amount",
            "grand_total": "Grand total",
            "due_payable_amount": "Due payable amount",
            "payment": "Payment",
            "due_date": "Due date",
            "notes": "Notes",
            "pdf_title": "{seller}: Invoice {id}",
            "pdf_subject": "Invoice {id} dated {date}, issued by {seller}",
            "pdf_keywords": "Invoice, Factur-X, ZUGFeRD",
        },
    ),
}


def get_locale_profile(language: str | None) -> LocaleProfile:
    key = (language or DEFAULT_LANGUAGE).lower()
    try:
        return LOCALE_PROFILES[key]
    except KeyError:
        raise ValueError(
            f"Unsupported language '{language}'. Supported languages: "
            f"{', '.join(sorted(LOCALE_PROFILES))}"
        )


def format_date(iso_date: str, profile: LocaleProfile) -> str:
    return datetime.date.fromisoformat(iso_date).strftime(profile.date_format)


def format_amount(value, profile: LocaleProfile) -> str:
    """Format a plain decimal amount (e.g. "1234.5") per the locale profile."""
    amount = Decimal(str(value))
    sign = "-" if amount < 0 else ""
    int_part, _, frac_part = f"{abs(amount):.2f}".partition(".")
    groups = []
    while len(int_part) > 3:
        groups.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    groups.insert(0, int_part)
    grouped_int = profile.thousands_separator.join(groups)
    return f"{sign}{grouped_int}{profile.decimal_separator}{frac_part}"
