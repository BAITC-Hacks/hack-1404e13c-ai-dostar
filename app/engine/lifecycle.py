"""Assortment lifecycle signals: declining items, new items, likely model replacements.

Deterministic and advisory only: order quantities are never changed here. Signals are
added to ORDER_LINES.flags (`lifecycle:*`) and to the rationale so the manager sees them;
the LLM in app/assistant.py can review replacement candidates (replacement vs variant).

Signals, from the regular monthly demand of full months:
- declining: average of the last 3 months < DECLINE_SHARE of the 9 months before (with
  a meaningful base) — the 12-month forecast base still orders it, risk of overstock;
- new_item: «NEW» in the name, or the first sale within NEW_ITEM_MONTHS months;
- replacement: a declining item and a new/growing item of the same supplier and product
  group with similar names — demand may be moving from the old model to the new one.
  Names differing only by colour/size are usually variants, not successors: without the
  LLM review such pairs stay «unverified».
"""

from __future__ import annotations

import difflib
import re

import pandas as pd

from app import schema

KEYS = ["supplier", "sku"]
DECLINE_SHARE = 0.25
DECLINE_MIN_BASE = 3.0  # units per month in the 9-month base
NEW_ITEM_MONTHS = 12
NEW_ITEM_MIN_RECENT = 1.0  # units per month in the last 3 months
PAIR_SIMILARITY = 0.6
SAME_NAME_SIMILARITY = 0.97
CONFIRMED = "та же позиция под новым кодом"
UNVERIFIED = "не проверено: нужна проверка названий"

_NOISE = re.compile(r"\bnew\b|!+|\([\d/ ]+\)|\biek\b|иэк|systeme electric|schneider", re.I)


def _norm(name) -> str:
    return re.sub(r"\s+", " ", _NOISE.sub(" ", str(name).lower())).strip()


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _params(name: str) -> list[str]:
    """Numeric parameters of a name (sizes, currents, sections): '1,5мм2 15А' -> ['1.5', '2', '15']."""
    return sorted(t.replace(",", ".") for t in re.findall(r"\d+(?:[.,]\d+)?", name))


def pair_verdict(old_name: str, new_name: str, score: float) -> str:
    """Deterministic pre-check of a replacement pair (the LLM review can overrule «unverified»)."""
    a, b = _norm(old_name), _norm(new_name)
    if a == b or (score >= SAME_NAME_SIMILARITY and _params(a) == _params(b)):
        return CONFIRMED
    if _params(a) != _params(b):
        return "вероятно вариант исполнения: различаются параметры"
    return UNVERIFIED


def detect(demand_monthly: pd.DataFrame, products: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """-> LIFECYCLE rows, one per (supplier, sku, signal)."""
    current = as_of.strftime("%Y-%m")
    monthly = demand_monthly[demand_monthly["month"] < current].pivot_table(
        index=KEYS, columns="month", values="qty_regular", aggfunc="sum").fillna(0)
    if monthly.shape[1] < 12:
        return schema.empty(schema.LIFECYCLE)
    last3 = monthly.iloc[:, -3:].mean(axis=1)
    prev9 = monthly.iloc[:, -12:-3].mean(axis=1)
    sold = monthly.gt(0)
    first = sold.idxmax(axis=1).where(sold.any(axis=1))
    info = products.set_index(KEYS)[["name", "category"]]
    names = info["name"].reindex(monthly.index)
    new_cutoff = (pd.Period(current, freq="M") - NEW_ITEM_MONTHS).strftime("%Y-%m")

    marked_new = names.str.contains(r"\bNEW\b", case=False, na=False)
    fresh = first.notna() & (first > new_cutoff)
    # A fresh item's first months are a launch, not a baseline: it is not called «declining».
    declining = monthly.index[(prev9 >= DECLINE_MIN_BASE) & (last3 < DECLINE_SHARE * prev9) & ~fresh]
    new_items = monthly.index[(marked_new | fresh) & (last3 >= NEW_ITEM_MIN_RECENT)]

    def row(key, signal, related=None, similarity=float("nan"), note=""):
        return {
            "supplier": key[0], "sku": key[1], "name": names.get(key, ""), "signal": signal,
            "related_sku": related[1] if related else "", "related_name": names.get(related, "") if related else "",
            "similarity": similarity, "avg_last3": float(last3[key]), "avg_prev9": float(prev9[key]),
            "first_month": first.get(key) or "", "note": note,
        }

    rows = []
    for key in declining:
        change = 1 - last3[key] / prev9[key]
        rows.append(row(key, "declining", note=f"спрос за 3 мес. ниже на {change:.0%} к 9 предыдущим"))
    for key in new_items:
        why = "пометка NEW" if marked_new.get(key, False) else f"первая продажа {first[key]}"
        rows.append(row(key, "new_item", note=why))

    # Replacement candidates: best-matching new item for each declining item in the same group.
    new_by_group: dict[tuple, list] = {}
    for key in new_items:
        group = (key[0], info["category"].get(key))
        new_by_group.setdefault(group, []).append(key)
    # A re-coded item often moves to another product group: exact names match across the supplier.
    new_by_name = {(k[0], _norm(names[k])): k for k in new_items}
    for old in declining:
        same = new_by_name.get((old[0], _norm(names[old])))
        if same is not None and same != old:
            score, new = 1.0, same
        else:
            candidates = [k for k in new_by_group.get((old[0], info["category"].get(old)), []) if k != old]
            if not candidates:
                continue
            score, new = max((_similarity(_norm(names[old]), _norm(names[k])), k) for k in candidates)
        if score < PAIR_SIMILARITY:
            continue
        verdict = pair_verdict(names[old], names[new], score)
        rows.append(row(old, "replaced_by", new, score, verdict))
        rows.append(row(new, "replaces", old, score, verdict))
    if not rows:
        return schema.empty(schema.LIFECYCLE)
    return schema.conform(pd.DataFrame(rows), schema.LIFECYCLE, "lifecycle")


LABELS = {
    "declining": "Угасающий спрос",
    "new_item": "Новинка",
    "replaced_by": "Возможная замена",
    "replaces": "Возможная новая модель",
}

RECOMMENDATIONS = {
    "declining": "заказать минимум или не пополнять после сверки с категорийным менеджером.",
    "new_item": "история короткая, прогноз ненадёжен — сверить ожидания продаж.",
    "replaced_by": "не пополнять старую модель сверх остатка, спрос переносить на новую модель.",
    "replaces": "продолжает спрос старой модели — учесть её историю, прогноз может быть занижен.",
}


def recommendation(signal: str, related_sku: str = "") -> str:
    text = RECOMMENDATIONS.get(signal, "")
    if related_sku:
        text = text.replace("на новую модель", f"на новую модель {related_sku}").replace(
            "старой модели —", f"старой модели {related_sku} —")
    return text


def annotate(order_lines: pd.DataFrame, signals: pd.DataFrame, verdicts: dict | None = None) -> pd.DataFrame:
    """Add `lifecycle:*` flags and one advisory sentence to the rationale. Quantities unchanged.

    Replacement pairs reach the order line only when confirmed (same item under a new code,
    or `verdicts[(supplier, old_sku, new_sku)] == "replacement"` from the LLM review);
    unverified pairs stay in the assistant tab.
    """
    if signals.empty or order_lines.empty:
        return order_lines
    verdicts = verdicts or {}
    out = order_lines.copy()
    by_key: dict[tuple, list] = {}
    for s in signals.itertuples():
        if s.signal in ("replaced_by", "replaces"):
            old, new = (s.sku, s.related_sku) if s.signal == "replaced_by" else (s.related_sku, s.sku)
            if s.note != CONFIRMED and verdicts.get((s.supplier, old, new)) != "replacement":
                continue
        by_key.setdefault((s.supplier, s.sku), []).append(s)
    flags, rationale = out["flags"].astype(str).tolist(), out["rationale"].astype(str).tolist()
    for i, key in enumerate(zip(out["supplier"], out["sku"])):
        for s in by_key.get(key, []):
            code = f"lifecycle:{s.signal}" + (f":{s.related_sku}" if s.related_sku else "")
            flags[i] = f"{flags[i]},{code}" if flags[i] else code
            rationale[i] += f". {LABELS[s.signal]} ({s.note}): {recommendation(s.signal, s.related_sku)}"
    out["flags"], out["rationale"] = flags, rationale
    return out
