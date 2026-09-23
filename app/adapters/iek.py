"""IEK export folder -> contract tables."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from app.adapters import common as c

SUPPLIER = "IEK"


def read_in_transit(path: Path) -> pd.DataFrame:
    """'Путь ИЭК': one column per supplier order, header '... (поступление до DD.MM.YYYY)'."""
    raw = c.read_xlsx(path, dtype=str).rename(columns=lambda col: c.nfc(col).strip())
    raw["sku"] = c.clean_sku(raw["Код 1с"])
    rows = []
    for col in raw.columns:
        eta = re.search(r"поступление до\s*(\d{2}\.\d{2}\.\d{4})", col)
        if not eta:
            continue
        qty = c.to_number(raw[col])
        part = raw.loc[qty > 0, ["sku"]].assign(
            qty=qty[qty > 0],
            eta=pd.to_datetime(eta.group(1), format="%d.%m.%Y"),
            order_ref=col.split("(")[0].replace("\xa0", " ").strip(),
        )
        rows.append(part)
    out = pd.concat(rows, ignore_index=True).dropna(subset=["sku"])
    return out.assign(supplier=SUPPLIER)


def load(folder: Path) -> dict[str, pd.DataFrame]:
    sales = c.read_sales_lines(c.find_file(folder, "динамика продаж"), SUPPLIER)

    monthly_sales, sales_rows = c.read_monthly_wide(
        c.find_file(folder, "ежемесячные продажи"), "Номенклатура.Код", "qty", skip_rows=1)
    stock_monthly, stock_rows = c.read_monthly_wide(
        c.find_file(folder, "ежемесячные остатки"), "Номенклатура.Код", "qty_start", skip_rows=2)

    moq = c.read_xlsx(c.find_file(folder, "moq"), dtype=str)
    moq = pd.DataFrame({
        "sku": c.clean_sku(moq["Код 1с"]),
        "supplier_article": c.clean_text(moq["Артикул поставщика"]),
        "name": c.clean_text(moq["Наименование"]),
        "pack_multiple": c.to_number(moq["Мин. разр. к отгр."]),
    }).dropna(subset=["sku"]).drop_duplicates("sku").set_index("sku")

    transit_raw = c.read_xlsx(c.find_file(folder, "путь"), dtype=str).rename(columns=lambda col: c.nfc(col).strip())
    transit_dir = pd.DataFrame({
        "sku": c.clean_sku(transit_raw["Код 1с"]),
        "supplier_article": c.clean_text(transit_raw["Артикул ИЭК"]),
        "name": c.clean_text(transit_raw["Наименование"]),
    }).dropna(subset=["sku"]).drop_duplicates("sku").set_index("sku")
    in_transit = read_in_transit(c.find_file(folder, "путь"))

    stock_dir = pd.DataFrame({
        "sku": stock_rows["sku"],
        "name": c.clean_text(stock_rows["Номенклатура"]),
        "unit": c.clean_text(stock_rows["Ед."]),
    }).drop_duplicates("sku").set_index("sku")
    sales_dir = sales.drop_duplicates("sku", keep="last").set_index("sku")[["name", "unit"]]

    skus = pd.Index(sorted(set(sales["sku"]) | set(monthly_sales["sku"]) | set(stock_monthly["sku"])
                           | set(moq.index) | set(in_transit["sku"])), name="sku")
    products = pd.DataFrame(index=skus)
    products["name"] = c.first_non_null(*(d["name"].reindex(skus) for d in (sales_dir, stock_dir, moq, transit_dir)))
    products["unit"] = c.first_non_null(sales_dir["unit"].reindex(skus), stock_dir["unit"].reindex(skus)).fillna("шт")
    products["supplier_article"] = c.first_non_null(moq["supplier_article"].reindex(skus),
                                                    transit_dir["supplier_article"].reindex(skus))
    pack = moq["pack_multiple"].reindex(skus)
    products["pack_multiple"] = pack.where(pack >= 1, 1.0)
    products = products.reset_index()
    products["category"] = c.category_from_sku(products["sku"])
    products["supplier"] = SUPPLIER

    seasonality = c.read_company_seasonality(c.find_file(folder, "сезонность"), SUPPLIER)

    return {
        "sales_lines": sales,
        "monthly_sales": monthly_sales.assign(supplier=SUPPLIER),
        "stock_monthly": stock_monthly.assign(supplier=SUPPLIER),
        "stock_now": c.estimate_stock_now(stock_monthly, sales, SUPPLIER),
        "in_transit": in_transit,
        "products": products,
        "seasonality": seasonality,
    }
