import io
import zipfile
from datetime import date
import pandas as pd
import streamlit as st
import requests
import re

st.set_page_config(page_title="Stabler Family Finances", layout="wide")

# ----------------------------
# FX (live) – Frankfurter (ECB-based, no key)
# ----------------------------
@st.cache_data(ttl=60 * 60)
def get_fx_rate(frm: str, to: str) -> float:
    frm = frm.upper()
    to = to.upper()
    if frm == to:
        return 1.0
    url = f"https://api.frankfurter.dev/v1/latest?base={frm}&symbols={to}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return float(r.json()["rates"][to])

def parse_money_text(v) -> float:
    if v is None:
        return 0.0
    s = str(v).strip()
    if s == "" or s.lower() in {"nan", "none"}:
        return 0.0
    s = s.replace("£", "").replace("$", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    s = re.sub(r"[^0-9\.\-]", "", s)
    try:
        return float(s)
    except:
        return 0.0

def coerce_numeric(df: pd.DataFrame, cols):
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(parse_money_text)
    return df

# ----------------------------
# Defaults
# ----------------------------
DEFAULT_ASSETS = pd.DataFrame(
    [
        {"account": "HSBC", "balance": "0"},
        {"account": "Lloyds", "balance": "0"},
        {"account": "Apple Savings", "balance": "0"},
        {"account": "Cash", "balance": "0"},
    ]
)

DEFAULT_CARDS = pd.DataFrame(
    [
        {"card": "Amex", "currency": "GBP", "balance": "0", "due_this_cycle": "0", "is_due": False},
        {"card": "Apple Card", "currency": "USD", "balance": "0", "due_this_cycle": "0", "is_due": False},
    ]
)

DEFAULT_FIXED = pd.DataFrame(
    [
        {"item": "Savings", "amount": "5000.00", "due": True},
        {"item": "RAC", "amount": "300.00", "due": True},
        {"item": "Car Loan", "amount": "480.37", "due": True},
        {"item": "Marchon", "amount": "133.10", "due": True},
    ]
)

DEFAULT_REIMB = pd.DataFrame(
    [
        {"source": "Eric Work", "amount": "0", "include_this_month": True},
        {"source": "Gigi Work", "amount": "0", "include_this_month": True},
        {"source": "Misc", "amount": "0", "include_this_month": False},
    ]
)

def init_state():
    if "assets" not in st.session_state:
        st.session_state.assets = DEFAULT_ASSETS.copy()
    if "cards" not in st.session_state:
        st.session_state.cards = DEFAULT_CARDS.copy()
    if "fixed" not in st.session_state:
        st.session_state.fixed = DEFAULT_FIXED.copy()
    if "reimb" not in st.session_state:
        st.session_state.reimb = DEFAULT_REIMB.copy()
    if "manual_usd_gbp" not in st.session_state:
        st.session_state.manual_usd_gbp = "0.80"

init_state()

# ----------------------------
# Live FX (calculated silently)
# ----------------------------
try:
    usd_gbp = get_fx_rate("USD", "GBP")
    fx_source = "live"
except:
    usd_gbp = parse_money_text(st.session_state.manual_usd_gbp)
    fx_source = "manual"

# ----------------------------
# Calculations
# ----------------------------
assets_num = coerce_numeric(st.session_state.assets.copy(), ["balance"])
cards_num = st.session_state.cards.copy()

if "currency" not in cards_num.columns:
    cards_num["currency"] = "GBP"

cards_num["currency"] = cards_num["currency"].fillna("GBP").astype(str).str.upper()
cards_num = coerce_numeric(cards_num, ["balance", "due_this_cycle"])

def to_gbp(amount, currency):
    if currency == "USD":
        return amount * usd_gbp
    return amount

cards_num["balance_gbp"] = cards_num.apply(lambda r: to_gbp(r["balance"], r["currency"]), axis=1)
cards_num["due_gbp"] = cards_num.apply(lambda r: to_gbp(r["due_this_cycle"], r["currency"]), axis=1)

assets_total = float(assets_num["balance"].sum())
card_balance_total = float(cards_num["balance_gbp"].sum())
card_due_total = float(cards_num.loc[cards_num["is_due"] == True, "due_gbp"].sum())

net_cash = assets_total - card_balance_total
total_spend_rest = card_due_total

# ----------------------------
# UI
# ----------------------------
st.title("Stabler Family Finances")

k1, k2, k3 = st.columns(3)
k1.metric("Net Cash", f"£{net_cash:,.2f}")
k2.metric("Total Credit Card Bill Due (GBP)", f"£{card_due_total:,.2f}")
k3.metric("Total Spend Rest of Month (GBP)", f"£{total_spend_rest:,.2f}")

st.markdown("---")

c1, c2, c3 = st.columns(3)

with c1:
    st.subheader("Assets")
    st.session_state.assets = st.data_editor(
        st.session_state.assets,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "account": st.column_config.TextColumn("Account"),
            "balance": st.column_config.TextColumn("Balance (£)"),
        },
    )

with c2:
    st.subheader("Credit Cards")
    st.session_state.cards = st.data_editor(
        st.session_state.cards,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "card": st.column_config.TextColumn("Card"),
            "currency": st.column_config.SelectboxColumn("Currency", options=["GBP", "USD"]),
            "balance": st.column_config.TextColumn("Balance (native)"),
            "due_this_cycle": st.column_config.TextColumn("Due (native)"),
            "is_due": st.column_config.CheckboxColumn("Due?"),
        },
    )

with c3:
    st.subheader("Reimbursement Pending")
    st.session_state.reimb = st.data_editor(
        st.session_state.reimb,
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "source": st.column_config.TextColumn("Source"),
            "amount": st.column_config.TextColumn("Amount (£)"),
            "include_this_month": st.column_config.CheckboxColumn("Include?"),
        },
    )

st.markdown("---")

# ----------------------------
# FX Section (moved to bottom)
# ----------------------------
st.subheader("FX Settings (Apple Card USD Conversion)")
st.caption("USD balances are converted to GBP using ECB reference rates via Frankfurter.")

col1, col2 = st.columns([2, 1])

with col1:
    st.write(f"**Current USD→GBP rate:** `{usd_gbp:.6f}`")
    st.write(f"Source: {fx_source}")

with col2:
    st.session_state.manual_usd_gbp = st.text_input(
        "Manual fallback USD→GBP",
        value=st.session_state.manual_usd_gbp,
    )
