import os
import re
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Stabler Family Finances", layout="wide")
st.title("Stabler Family Finances")

# -------------------------
# Supabase config (from Streamlit Secrets)
# -------------------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
SUPABASE_SERVICE_ROLE_KEY = st.secrets.get(
    "SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
)

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    st.error("Missing Supabase secrets. Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in Streamlit Secrets.")
    st.stop()

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# -------------------------
# Helpers
# -------------------------
def money(x) -> str:
    try:
        return f"£{float(x):,.2f}"
    except Exception:
        return "£0.00"

def parse_money_cell(v) -> float:
    """
    Accepts: 123.45, 123,45, £123.45, 1,234.56, etc.
    """
    if v is None:
        return 0.0
    s = str(v).strip()
    if s == "" or s.lower() in {"nan", "none"}:
        return 0.0

    s = s.replace("£", "").replace(" ", "")
    # if both comma and dot, assume comma is thousand separator
    if "," in s and "." in s:
        s = s.replace(",", "")
    else:
        # otherwise treat comma as decimal
        s = s.replace(",", ".")
    s = re.sub(r"[^0-9\.\-]", "", s)

    try:
        return float(s)
    except Exception:
        return 0.0

def normalize_money_column(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col].apply(parse_money_cell)

def fetch_table(table: str) -> pd.DataFrame:
    res = sb.table(table).select("*").execute()
    data = res.data or []
    return pd.DataFrame(data)

def upsert_rows(table: str, df: pd.DataFrame, key_cols: list[str]):
    """
    Upsert by id if present, else insert.
    We keep it simple: if an 'id' column exists, we upsert the whole row.
    """
    if df.empty:
        return

    records = df.to_dict(orient="records")
    sb.table(table).upsert(records).execute()

def ensure_defaults():
    # Assets defaults
    assets = fetch_table("assets")
    if assets.empty:
        sb.table("assets").insert([
            {"account": "HSBC", "balance": 0},
            {"account": "Lloyds", "balance": 0},
            {"account": "Apple Savings", "balance": 0},
            {"account": "Cash", "balance": 0},
        ]).execute()

    # Credit cards defaults
    cards = fetch_table("credit_cards")
    if cards.empty:
        sb.table("credit_cards").insert([
            {"card": "Amex", "balance": 0, "due": 0, "is_due": False},
            {"card": "Apple", "balance": 0, "due": 0, "is_due": False},
        ]).execute()

    # Fixed costs defaults (from your list)
    fixed = fetch_table("fixed_costs")
    if fixed.empty:
        sb.table("fixed_costs").insert([
            {"item": "Savings", "amount": 5000.00, "monthly": True, "due_now": True},
            {"item": "RAC", "amount": 300.00, "monthly": True, "due_now": True},
            {"item": "Car Loan", "amount": 480.37, "monthly": True, "due_now": True},
            {"item": "Marchon", "amount": 133.10, "monthly": True, "due_now": True},
            {"item": "Utilities", "amount": 425.00, "monthly": True, "due_now": True},
            {"item": "Eric Vodafone", "amount": 38.00, "monthly": True, "due_now": True},
            {"item": "Eric Haircut", "amount": 35.00, "monthly": True, "due_now": True},
            {"item": "Eric iphone", "amount": 35.11, "monthly": True, "due_now": True},
            {"item": "Cleaning", "amount": 72.00, "monthly": True, "due_now": True},
            {"item": "Gigi Vodafone", "amount": 38.00, "monthly": True, "due_now": True},
            {"item": "Gigi Gym", "amount": 79.00, "monthly": True, "due_now": True},
            {"item": "Caroline Circuits", "amount": 35.00, "monthly": True, "due_now": True},
            {"item": "Gigi Charity", "amount": 12.00, "monthly": True, "due_now": True},
            {"item": "G+ E Contacts", "amount": 95.00, "monthly": True, "due_now": True},
        ]).execute()

    # Reimbursements defaults
    reimb = fetch_table("reimbursements")
    if reimb.empty:
        sb.table("reimbursements").insert([
            {"item": "Eric Work", "amount": 0, "include": True},
            {"item": "Gigi Work", "amount": 0, "include": True},
            {"item": "Misc", "amount": 0, "include": False},
        ]).execute()

# Make sure tables have starter rows
ensure_defaults()

# -------------------------
# Load tables
# -------------------------
assets = fetch_table("assets")
cards = fetch_table("credit_cards")
reimb = fetch_table("reimbursements")
fixed = fetch_table("fixed_costs")

# Ensure expected columns (safety)
for df, required in [
    (assets, ["id", "account", "balance"]),
    (cards, ["id", "card", "balance", "due", "is_due"]),
    (re
