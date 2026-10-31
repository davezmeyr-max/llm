"""Turn an uploaded CSV or Excel file into (company, hints) rows.

Header names are matched loosely. One column becomes the company name; city, state, website,
industry and similar columns are folded into the hints string the agent uses to disambiguate.
Without a recognisable header, the first column is the company and the rest become hints.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

MAX_ROWS = 5000
MAX_BYTES = 5_000_000

COMPANY_HEADERS = [
    "company", "company name", "companyname", "business", "business name", "account", "account name",
    "organization", "organisation", "org", "name", "client", "prospect", "lead",
]
HINT_HEADERS = [
    "website", "url", "domain", "web", "city", "town", "state", "province", "st", "zip", "zipcode", "postal code",
    "address", "street", "industry", "sector", "vertical", "phone", "notes", "note", "hints", "hint", "country",
    "county", "description",
]


@dataclass
class ImportResult:
    rows: list[tuple[str, str]] = field(default_factory=list)
    skipped: int = 0
    duplicates: int = 0
    truncated: bool = False
    company_column: str = ""
    hint_columns: list[str] = field(default_factory=list)


class ImportError_(ValueError):
    pass


def _norm(h: object) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(h or "").strip().lower().replace("_", " ")).strip()


def _read_table(filename: str, data: bytes) -> list[list[str]]:
    if len(data) > MAX_BYTES:
        raise ImportError_(f"file is larger than {MAX_BYTES // 1_000_000} MB")
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        try:
            from openpyxl import load_workbook

            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001
            raise ImportError_(f"could not read the Excel file: {exc}") from exc
        ws = wb.worksheets[0]
        table = []
        for row in ws.iter_rows(values_only=True):
            table.append(["" if v is None else str(v).strip() for v in row])
            if len(table) > MAX_ROWS + 1:
                break
        wb.close()
        return table
    if name.endswith(".xls"):
        raise ImportError_("old .xls files are not supported; save as .xlsx or .csv")
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), dialect)]


def parse_upload(filename: str, data: bytes) -> ImportResult:
    table = [r for r in _read_table(filename, data) if any(c for c in r)]
    if not table:
        raise ImportError_("the file is empty")

    header = [_norm(h) for h in table[0]]
    company_idx = next((header.index(h) for h in COMPANY_HEADERS if h in header), None)
    res = ImportResult()
    if company_idx is not None:
        body = table[1:]
        hint_idx = [i for i, h in enumerate(header) if i != company_idx and h in HINT_HEADERS]
        res.company_column = table[0][company_idx]
        res.hint_columns = [table[0][i] for i in hint_idx]
    else:
        body = table
        company_idx = 0
        hint_idx = list(range(1, max(len(r) for r in table)))
        res.company_column = "column 1"
        res.hint_columns = [f"column {i + 1}" for i in hint_idx]

    if len(body) > MAX_ROWS:
        body = body[:MAX_ROWS]
        res.truncated = True

    seen: set[tuple[str, str]] = set()
    for row in body:
        company = row[company_idx].strip() if company_idx < len(row) else ""
        if len(company) < 2:
            res.skipped += 1
            continue
        parts = [row[i].strip() for i in hint_idx if i < len(row) and row[i].strip()]
        hints = ", ".join(parts)[:500]
        key = (company.lower(), hints.lower())
        if key in seen:
            res.duplicates += 1
            continue
        seen.add(key)
        res.rows.append((company[:200], hints))
    return res
