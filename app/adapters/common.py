"""Parsers for the 1C Excel exports shared by all suppliers."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

MONTHS_RU = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}


def nfc(text: str) -> str:
    # macOS stores Cyrillic file names decomposed (й -> и + ̆).
    return unicodedata.normalize("NFC", str(text))


def find_file(folder: Path, *keywords: str) -> Path:
    """The single .xlsx in `folder` whose name contains every keyword (case-insensitive)."""
    keys = [nfc(k).lower() for k in keywords]
    hits = [p for p in folder.glob("*.xlsx") if all(k in nfc(p.name).lower() for k in keys)]
    if len(hits) != 1:
        raise FileNotFoundError(f"{folder}: expected one file matching {keywords}, found {hits}")
    return hits[0]


def read_xlsx(path: Path, **kwargs) -> pd.DataFrame:
    try:
        return pd.read_excel(path, engine="calamine", **kwargs)
    except ImportError:
        return pd.read_excel(path, engine="openpyxl", **kwargs)


def clean_sku(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip().replace("", pd.NA)


def clean_text(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)


def to_number(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce")


def parse_month(header) -> str | None:
    """'янв. 2024' / 'Январь 2024 г.' -> '2024-01'; anything else -> None."""
    match = re.match(r"\s*([а-яё]+)\.?\s+(\d{4})", nfc(header).lower())
    if not match:
        return None
    month = MONTHS_RU.get(match.group(1)[:3])
    return f"{match.group(2)}-{month:02d}" if month else None


def month_columns(columns) -> dict:
    """Map original column label -> YYYY-MM for every month column."""
    out = {}
    for col in columns:
        month = parse_month(col)
        if month:
            out[col] = month
    return out


def read_sales_lines(path: Path, supplier: str) -> pd.DataFrame:
    """'Динамика продаж': invoice lines. Keeps only 'Расходная накладная'."""
    raw = read_xlsx(path, dtype=str)
    raw = raw[raw["Документ"].astype("string").str.startswith("Расходная накладная", na=False)]
    return pd.DataFrame({
        "supplier": supplier,
        "sku": clean_sku(raw["Код"]),
        "date": pd.to_datetime(raw["Дата"], format="%d.%m.%Y %H:%M:%S", errors="coerce"),
        "doc_id": clean_sku(raw["Номер"]),
        "qty": to_number(raw["Количество"]),
        "unit": clean_text(raw["Ед."]),
        "warehouse": clean_text(raw["Склад"]),
        "name": clean_text(raw["Номенклатура"]),
    }).dropna(subset=["sku", "date", "qty"])


def read_monthly_wide(path: Path, sku_col: str, value_name: str, sheet_name=0,
                      skip_rows: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Wide SKU x month report -> (long table [sku, month, value], row attributes).

    `skip_rows` is the number of sub-header rows ('Количество', 'нач. остаток')
    right below the header. The trailing 'Итого' row and column are dropped.
    """
    raw = read_xlsx(path, sheet_name=sheet_name, dtype=str)
    raw = raw.iloc[skip_rows:]
    raw = raw.rename(columns=lambda c: nfc(c).strip())
    raw["sku"] = clean_sku(raw[sku_col])
    raw = raw.dropna(subset=["sku"])
    months = month_columns(raw.columns)
    long = raw.melt(id_vars=["sku"], value_vars=list(months), var_name="col", value_name=value_name)
    long["month"] = long["col"].map(months)
    long[value_name] = to_number(long[value_name]).fillna(0.0)
    long = long.groupby(["sku", "month"], as_index=False)[value_name].sum()
    return long, raw


def read_company_seasonality(path: Path, supplier: str, sheet_name=0) -> pd.DataFrame:
    """'Сезонность': the 'СЕЗОННОСТЬ' column of the 'Месяц' block (average of years)."""
    raw = read_xlsx(path, sheet_name=sheet_name, header=None, dtype=str)
    header_row = next(i for i, row in raw.iterrows() if (row.astype("string") == "Месяц").any())
    header = raw.iloc[header_row].astype("string")
    month_col = header[header == "Месяц"].index[0]
    coef_col = header[header.str.upper() == "СЕЗОННОСТЬ"].index[0]
    rows = []
    for _, row in raw.iloc[header_row + 1:].iterrows():
        month = MONTHS_RU.get(str(row[month_col]).strip().lower()[:3])
        coef = pd.to_numeric(row[coef_col], errors="coerce")
        if month and pd.notna(coef):
            rows.append({"supplier": supplier, "month_num": month, "coef": float(coef)})
    return pd.DataFrame(rows)


def estimate_stock_now(stock_monthly: pd.DataFrame, sales: pd.DataFrame, supplier: str) -> pd.DataFrame:
    """Latest start-of-month stock minus net sales since then (receipts unknown)."""
    last_month = stock_monthly["month"].max()
    start = pd.Timestamp(f"{last_month}-01")
    as_of = sales["date"].max().normalize()
    base = stock_monthly[stock_monthly["month"] == last_month].set_index("sku")["qty_start"]
    sold = sales[sales["date"] >= start].groupby("sku")["qty"].sum()
    free = base.sub(sold, fill_value=0).clip(lower=0)
    return pd.DataFrame({
        "supplier": supplier,
        "sku": free.index,
        "free_qty": free.values,
        "reserved_qty": float("nan"),
        "as_of": as_of,
        "source": "estimated",
    })


def first_non_null(*series: pd.Series) -> pd.Series:
    out = series[0]
    for s in series[1:]:
        out = out.combine_first(s)
    return out


def category_from_sku(sku: pd.Series) -> pd.Series:
    """1C codes are hierarchical: the first 4 digits are the product group."""
    prefix = sku.str.extract(r"^(\d{4})", expand=False)
    return prefix.fillna("прочее")
