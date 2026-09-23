"""Systeme Electric export folder -> contract tables."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from app.adapters import common as c

SUPPLIER = "SE"


def read_manager_file(path: Path) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp | None]:
    """'Товар в пути_SystemElectric на DD.MM.YYYY': the manager's current calculation.

    Returns (rows, as_of date from the file name, eta from the 'СЭ в пути DD.MM' column).
    """
    as_of = pd.to_datetime(re.search(r"(\d{2}\.\d{2}\.\d{4})", c.nfc(path.name)).group(1), format="%d.%m.%Y")
    raw = c.read_xlsx(path, sheet_name=0, header=1, dtype=str).rename(columns=lambda col: c.nfc(col).strip())
    transit_col = next(col for col in raw.columns if col.startswith("СЭ в пути"))
    eta_match = re.search(r"(\d{2})\.(\d{2})", transit_col)
    eta = pd.Timestamp(year=as_of.year, month=int(eta_match.group(2)), day=int(eta_match.group(1))) if eta_match else None
    num = lambda col: c.to_number(raw[col])  # noqa: E731
    rows = pd.DataFrame({
        "sku": c.clean_sku(raw["Код 1с"]),
        "supplier_article": c.clean_text(raw["Артикул поставщика"]),
        "name": c.clean_text(raw["Наименование"]),
        "category_abc": c.clean_text(raw["Категория 2026"]),
        "avg_month_12": num("Ср мес за последние 12 мес"),
        "growth_coef": num("Кэф. Роста"),
        "season_coef": num("Кэф. Сез-ти"),
        "on_hand": num("Остаток"),
        "reserved_qty": num("Зарезервировано"),
        "free_qty": num("Свободный остаток"),
        "stock_months": num("Запас"),
        "manager_order": num("Заказ"),
        "in_transit": num(transit_col),
        "unit_cost": num("СС реал"),
    }).dropna(subset=["sku"]).drop_duplicates("sku")
    return rows, as_of, eta


def load(folder: Path) -> dict[str, pd.DataFrame]:
    sales = c.read_sales_lines(c.find_file(folder, "динамика продаж"), SUPPLIER)

    monthly_sales, sales_rows = c.read_monthly_wide(
        c.find_file(folder, "ежемесячные продажи"), "Номенклатура.Код", "qty", sheet_name=0, skip_rows=1)
    stock_monthly, stock_rows = c.read_monthly_wide(
        c.find_file(folder, "ежемесячные остатки"), "Номенклатура.Код", "qty_start", skip_rows=2)

    moq = c.read_xlsx(c.find_file(folder, "moq"), dtype=str)
    moq = pd.DataFrame({
        "sku": c.clean_sku(moq["Номенклатура.Код"]),
        "supplier_article": c.clean_text(moq["Артикул"]),
        "name": c.clean_text(moq["Номенклатура"]),
        "pack_multiple": c.to_number(moq["Кратность"]),
    }).dropna(subset=["sku"]).drop_duplicates("sku").set_index("sku")

    manager, as_of, eta = read_manager_file(c.find_file(folder, "товар в пути"))

    # Current stock: exact from the manager file, estimated for the remaining SKUs.
    exact = pd.DataFrame({
        "supplier": SUPPLIER, "sku": manager["sku"], "free_qty": manager["free_qty"].fillna(0).clip(lower=0),
        "reserved_qty": manager["reserved_qty"].fillna(0), "as_of": as_of, "source": "manager_file",
    })
    estimated = c.estimate_stock_now(stock_monthly, sales, SUPPLIER)
    stock_now = pd.concat([exact, estimated[~estimated["sku"].isin(exact["sku"])]], ignore_index=True)

    moving = manager[manager["in_transit"] > 0]
    in_transit = pd.DataFrame({
        "supplier": SUPPLIER, "sku": moving["sku"], "qty": moving["in_transit"],
        "eta": eta, "order_ref": "СЭ в пути",
    })

    stock_dir = pd.DataFrame({
        "sku": stock_rows["sku"],
        "name": c.clean_text(stock_rows["Номенклатура"]),
        "unit": c.clean_text(stock_rows["Ед.изм"]),
    }).drop_duplicates("sku").set_index("sku")
    sales_dir = sales.drop_duplicates("sku", keep="last").set_index("sku")[["name", "unit"]]
    sales_rows_dir = pd.DataFrame({
        "sku": sales_rows["sku"], "supplier_article": c.clean_text(sales_rows["Артикул"]),
    }).drop_duplicates("sku").set_index("sku")
    manager_dir = manager.set_index("sku")

    skus = pd.Index(sorted(set(sales["sku"]) | set(monthly_sales["sku"]) | set(stock_monthly["sku"])
                           | set(moq.index) | set(manager["sku"])), name="sku")
    products = pd.DataFrame(index=skus)
    products["name"] = c.first_non_null(*(d["name"].reindex(skus) for d in (sales_dir, stock_dir, moq, manager_dir)))
    products["unit"] = c.first_non_null(sales_dir["unit"].reindex(skus), stock_dir["unit"].reindex(skus)).fillna("шт")
    products["supplier_article"] = c.first_non_null(moq["supplier_article"].reindex(skus),
                                                    manager_dir["supplier_article"].reindex(skus),
                                                    sales_rows_dir["supplier_article"].reindex(skus))
    pack = moq["pack_multiple"].reindex(skus)
    products["pack_multiple"] = pack.where(pack >= 1, 1.0)
    products = products.reset_index()
    # Product group from the 1C code; the manager's "Категория 2026" (priority class)
    # stays in manager_baseline.category_abc.
    products["category"] = c.category_from_sku(products["sku"])
    products["supplier"] = SUPPLIER

    seasonality = c.read_company_seasonality(c.find_file(folder, "сезонность"), SUPPLIER)

    return {
        "sales_lines": sales,
        "monthly_sales": monthly_sales.assign(supplier=SUPPLIER),
        "stock_monthly": stock_monthly.assign(supplier=SUPPLIER),
        "stock_now": stock_now,
        "in_transit": in_transit,
        "products": products,
        "seasonality": seasonality,
        "manager_baseline": manager.drop(columns=["supplier_article", "name"]).assign(supplier=SUPPLIER),
    }
