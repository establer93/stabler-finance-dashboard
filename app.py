import os
import re
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Stabler Family Finances", layout="wide")
st.title("Stabler Family Finances")

# -------------------------
# Supabase config
# -------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# Helpers
# -------------------------
def money(x):
    try:
        return f"£{float(x):,.2f}"
    except:
        return "£0.00"

def parse_money(v):
    if v is None:
        return 0.0
    s = str(v).replace("£", "").replace(",", "").strip()
    try:
        return float(s)
    except:
        return 0.0

def fetch(table):
    res = sb.table(table).select("*").execute()
    return pd.DataFrame(res.data if res.data else [])

def save(table, df):
    if not df.empty:
        sb.table(table).upsert(df.to_dict(orient="records")).execute()

# -------------------------
# Ensure default data
# -------------------------
if fetch("assets").empty:
    sb.table("assets").insert([
        {"account": "HSBC", "balance": 0},
        {"account": "Lloyds", "balance": 0},
        {"account": "Apple Savings", "balance": 0},
        {"account": "Cash", "balance": 0},
    ]).execute()

if fetch("credit_cards").empty:
    sb.table("credit_cards").insert([
        {"card": "Amex", "balance": 0, "due": 0, "is_due": False},
        {"card": "Apple", "balance": 0, "due": 0, "is_due": False},
    ]).execute()

if fetch("reimbursements").empty:
    sb.table("reimbursements").insert([
        {"item": "Eric Work", "amount": 0, "include": True},
        {"item": "Gigi Work", "amount": 0, "include": True},
        {"item": "Misc", "amount": 0, "include": False},
    ]).execute()

# -------------------------
# Load data
# -------------------------
assets = fetch("assets")
cards = fetch("credit_cards")
reimb = fetch("reimbursements")
fixed = fetch("fixed_costs")

# -------------------------
# Top calculations
# -------------------------
assets_total = assets["balance"].sum() if not assets.empty else 0
cards_balance_total = cards["balance"].sum() if not cards.empty else 0
cards_due_total = cards["due"].sum() if not cards.empty else 0

net_cash = assets_total - cards_balance_total

m1, m2, m3 = st.columns(3)
m1.metric("Net Cash", money(net_cash))
m2.metric("Total Credit Card Bill Due", money(cards_due_total))
m3.metric("Total Spend Rest of Month", money(cards_due_total))

st.divider()

# -------------------------
# Layout
# -------------------------
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Assets")
    edited = st.data_editor(assets, use_container_width=True)
    edited["balance"] = edited["balance"].apply(parse_money)
    save("assets", edited)

with col2:
    st.subheader("Credit Cards")
    edited = st.data_editor(cards, use_container_width=True)
    edited["balance"] = edited["balance"].apply(parse_money)
    edited["due"] = edited["due"].apply(parse_money)
    save("credit_cards", edited)

with col3:
    st.subheader("Reimbursement Pending")
    edited = st.data_editor(reimb, use_container_width=True)
    edited["amount"] = edited["amount"].apply(parse_money)
    save("reimbursements", edited)

st.divider()

st.subheader("Monthly Fixed")
edited = st.data_editor(fixed, use_container_width=True)
if not edited.empty and "amount" in edited.columns:
    edited["amount"] = edited["amount"].apply(parse_money)
    save("fixed_costs", edited)
