import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(page_title="Stabler Family Finances", layout="wide")
st.title("Stabler Family Finances")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_ANON_KEY"]

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch(table):
    res = sb.table(table).select("*").execute()
    return pd.DataFrame(res.data if res.data else [])

def save(table, df):
    if not df.empty:
        sb.table(table).upsert(df.to_dict(orient="records")).execute()

def money(x):
    try:
        return f"£{float(x):,.2f}"
    except:
        return "£0.00"

assets = fetch("assets")
cards = fetch("credit_cards")
reimbursements = fetch("reimbursements")
fixed = fetch("fixed_costs")

assets_total = assets["balance"].sum() if "balance" in assets else 0
cards_balance = cards["balance"].sum() if "balance" in cards else 0
cards_due = cards["due"].sum() if "due" in cards else 0

net_cash = assets_total - cards_balance

m1, m2, m3 = st.columns(3)
m1.metric("Net Cash", money(net_cash))
m2.metric("Total Credit Card Bill Due", money(cards_due))
m3.metric("Total Spend Rest of Month", money(cards_due))

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Assets")
    edited = st.data_editor(assets, use_container_width=True)
    if not edited.empty and "balance" in edited.columns:
        edited["balance"] = pd.to_numeric(edited["balance"], errors="coerce").fillna(0)
        save("assets", edited)

with col2:
    st.subheader("Credit Cards")
    edited = st.data_editor(cards, use_container_width=True)
    if not edited.empty:
        if "balance" in edited.columns:
            edited["balance"] = pd.to_numeric(edited["balance"], errors="coerce").fillna(0)
        if "due" in edited.columns:
            edited["due"] = pd.to_numeric(edited["due"], errors="coerce").fillna(0)
        save("credit_cards", edited)

with col3:
    st.subheader("Reimbursement Pending")
    edited = st.data_editor(reimbursements, use_container_width=True)
    if not edited.empty and "amount" in edited.columns:
        edited["amount"] = pd.to_numeric(edited["amount"], errors="coerce").fillna(0)
        save("reimbursements", edited)

st.divider()

st.subheader("Monthly Fixed")
edited = st.data_editor(fixed, use_container_width=True)
if not edited.empty and "amount" in edited.columns:
    edited["amount"] = pd.to_numeric(edited["amount"], errors="coerce").fillna(0)
    save("fixed_costs", edited)
