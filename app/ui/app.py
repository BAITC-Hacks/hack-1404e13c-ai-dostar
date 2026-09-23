"""Streamlit UI. Owner: Person 3 «Продукт» (tasks 3.1–3.7).

    .venv/bin/streamlit run app/ui/app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from app.mock import mock_order_lines  # noqa: E402

st.set_page_config(page_title="Заказы поставщикам", layout="wide")
st.title("Рекомендованные заказы поставщикам")

use_mock = st.sidebar.toggle("Мок-данные", value=True)
if use_mock:
    lines = mock_order_lines()
else:
    from app.pipeline import run
    lines = st.cache_data(lambda: run().order_lines)()

for supplier, group in lines.groupby("supplier"):
    st.subheader(f"{supplier}: {int((group['recommended_qty'] > 0).sum())} позиций к заказу")
    st.dataframe(group, hide_index=True)
