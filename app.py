# app.py
# Stabler Family Finances
# Credit Cards simplified + Negative Net Cash in red

import io
import zipfile
from datetime import datetime
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Stabler Family Finances", layout="wide")

APP_TITLE = "Stabler Family Finances"

# -----------------------------
# Helpers
# -----------------------------
def _coerce_money_series(s: pd.Series) -> pd.Series:
    s = s.astype(str)
    s = (
        s.str.replace("£", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(s, errors="coerce").fillna(0.0)

def fmt_gbp(x: float) -> str:
    return f"£{float(x):,.2f}"

@st.cache_data(ttl=60 * 30)
def fetch_usd_to_gbp():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        return float(r.json()["rates"]["GBP"])
    except:
        return None

def convert_usd_if_needed(card_name: str, value: float, usd_to_gbp: float):
    if "apple" in card_name.lower():
        return value * usd_to_gbp
    return value

# -----------------------------
# Defaults
# -----------------------------
def default_assets():
    return pd.DataFrame([
        {"Account": "HSBC", "Currency": "GBP", "Balance (native)": 0.0},
        {"Account": "Lloyds", "Currency": "GBP", "Balance (native)": 0.0},
        {"Account": "Apple Savings", "Currency": "USD", "Balance (native)": 0.0},
    ])

def default_cards():
    return pd.DataFrame([
        {"Card": "Amex", "Balance": 0.0, "Balance Due": 0.0},
        {"Card": "Apple Card", "Balance": 0.0, "Balance Due": 0.0},
    ])

def default_fixed():
    return pd.DataFrame([
        {"Item": "Savings", "Amount (GBP)": 5000.00, "Due?": True},
        {"Item": "RAC", "Amount (GBP)": 300.00, "Due?": True},
    ])

if "assets" not in st.session_state:
    st.session_state.assets = default_assets()
if "cards" not in st.session_state:
    st.session_state.cards = default_cards()
if "fixed" not in st.session_state:
    st.session_state.fixed = default_fixed()

# -----------------------------
# FX
# -----------------------------
live_fx = fetch_usd_to_gbp()
usd_to_gbp = live_fx if live_fx else 0.79

# -----------------------------
# Calculations
# -----------------------------
assets = st.session_state.assets.copy()
assets["Balance (native)"] = _coerce_money_series(assets["Balance (native)"])

assets_gbp = []
for _, row in assets.iterrows():
    if row["Currency"] == "USD":
        assets_gbp.append(row["Balance (native)"] * usd_to_gbp)
    else:
        assets_gbp.append(row["Balance (native)"])

total_assets = sum(assets_gbp)

cards = st.session_state.cards.copy()
cards["Balance"] = _coerce_money_series(cards["Balance"])
cards["Balance Due"] = _coerce_money_series(cards["Balance Due"])

card_balances_gbp = [
    convert_usd_if_needed(row["Card"], row["Balance"], usd_to_gbp)
    for _, row in cards.iterrows()
]

card_due_gbp = [
    convert_usd_if_needed(row["Card"], row["Balance Due"], usd_to_gbp)
    for _, row in cards.iterrows()
]

total_card_balance = sum(card_balances_gbp)
total_card_due = sum(card_due_gbp)

fixed = st.session_state.fixed.copy()
fixed["Amount (GBP)"] = _coerce_money_series(fixed["Amount (GBP)"])
total_fixed_due = fixed.loc[fixed["Due?"] == True, "Amount (GBP)"].sum()

net_cash = total_assets - total_card_balance
total_spend_rest_month = total_fixed_due + total_card_due

# -----------------------------
# UI
# -----------------------------
st.title(APP_TITLE)

col1, col2, col3 = st.columns(3)

# ---- Net Cash with Red if Negative ----
with col1:
    color = "#ff4b4b" if net_cash < 0 else "#00cc96"
    st.markdown("Net Cash (GBP)")
    st.markdown(
        f"<h2 style='color:{color}; margin-top:-10px'>{fmt_gbp(net_cash)}</h2>",
        unsafe_allow_html=True
    )

with col2:
    st.metric("Total Credit Card Bill Due (GBP)", fmt_gbp(total_card_due))

with col3:
    st.metric("Total Spend Rest of Month (GBP)", fmt_gbp(total_spend_rest_month))

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Assets")
    assets_edit = st.data_editor(
        st.session_state.assets,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Account": st.column_config.TextColumn("Account"),
            "Currency": st.column_config.SelectboxColumn("Currency", options=["GBP", "USD"]),
            "Balance (native)": st.column_config.NumberColumn("Balance (native)", format="%.2f"),
        },
    )
    st.session_state.assets = assets_edit
    st.caption(f"Total Assets (GBP): {fmt_gbp(total_assets)}")

with right:
    st.subheader("Credit Cards")
    cards_edit = st.data_editor(
        st.session_state.cards,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Card": st.column_config.TextColumn("Card"),
            "Balance": st.column_config.NumberColumn("Balance", format="%.2f"),
            "Balance Due": st.column_config.NumberColumn("Balance Due", format="%.2f"),
        },
    )
    st.session_state.cards = cards_edit
    st.caption(f"Total Card Balances (GBP): {fmt_gbp(total_card_balance)}")

st.divider()

st.subheader("Monthly Fixed")
fixed_edit = st.data_editor(
    st.session_state.fixed,
    num_rows="dynamic",
    use_container_width=True,
)
st.session_state.fixed = fixed_edit
st.caption(f"Fixed Due (GBP): {fmt_gbp(total_fixed_due)}")

st.divider()
st.caption(f"Using USD→GBP rate: {usd_to_gbp:.4f}")
