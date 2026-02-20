import streamlit as st
import pandas as pd
from pathlib import Path
import re
import json

st.set_page_config(page_title="Stabler Family Finances", layout="wide")
st.title("Stabler Family Finances")

FILES = {
    "assets": ("assets.csv", ["account", "balance"]),
    "cards": ("credit_cards.csv", ["card", "balance", "due", "is_due"]),
    "reimb": ("reimbursement_pending.csv", ["item", "amount", "include"]),
    "fixed": ("fixed_costs.csv", ["item", "amount", "monthly", "due_now"]),
}

# -------------------------
# Helpers
# -------------------------
def ensure_file(filename: str, cols: list[str]) -> None:
    path = Path(filename)
    if not path.exists():
        pd.DataFrame(columns=cols).to_csv(path, index=False)

def load_df(key: str) -> pd.DataFrame:
    filename, cols = FILES[key]
    ensure_file(filename, cols)
    df = pd.read_csv(filename)

    for c in cols:
        if c not in df.columns:
            df[c] = None

    return df[cols].copy().dropna(how="all")

def save_df(key: str, df: pd.DataFrame) -> None:
    filename, cols = FILES[key]
    df.copy()[cols].to_csv(filename, index=False)

def money(x) -> str:
    try:
        return f"£{float(x):,.2f}"
    except:
        return "£0.00"

def to_bool(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool)

def parse_money(v) -> float:
    if v is None:
        return 0.0
    s = str(v).replace("£", "").replace(",", "").strip()
    try:
        return float(s)
    except:
        return 0.0

def normalize_money_column(df, col):
    return df[col].apply(parse_money)

# -------------------------
# Load Data
# -------------------------
assets = load_df("assets")
cards = load_df("cards")
reimb = load_df("reimb")
fixed = load_df("fixed")

cards["is_due"] = to_bool(cards["is_due"])
reimb["include"] = to_bool(reimb["include"])
fixed["monthly"] = to_bool(fixed["monthly"])
fixed["due_now"] = to_bool(fixed["due_now"])

for df, col in [
    (assets, "balance"),
    (cards, "balance"),
    (cards, "due"),
    (reimb, "amount"),
    (fixed, "amount"),
]:
    df[col] = df[col].fillna("").astype(str)

# -------------------------
# CALCULATIONS (moved BEFORE UI)
# -------------------------
assets_total = normalize_money_column(assets, "balance").sum()
cards_total_balance = normalize_money_column(cards, "balance").sum()
cards_bill_due_total = normalize_money_column(cards, "due").sum()
cards_due_now = normalize_money_column(cards[cards["is_due"] == True], "due").sum()

reimb_total = normalize_money_column(
    reimb[reimb["include"] == True], "amount"
).sum()

fixed_due_now_total = normalize_money_column(
    fixed[fixed["due_now"] == True], "amount"
).sum()

net_cash = assets_total - cards_total_balance
total_spend_rest_month = fixed_due_now_total + reimb_total + cards_due_now

# -------------------------
# 🔥 TOP METRICS (NOW AT TOP)
# -------------------------
m1, m2, m3 = st.columns(3)
m1.metric("Net Cash", money(net_cash))
m2.metric("Total Credit Card Bill Due", money(cards_bill_due_total))
m3.metric("Total Spend Rest of Month", money(total_spend_rest_month))

st.divider()

# -------------------------
# TOP ROW TABLES
# -------------------------
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Assets")
    edit = st.data_editor(
        assets,
        key="assets",
        num_rows="dynamic",
        use_container_width=True,
        column_config={"balance": st.column_config.TextColumn("Balance (£)")},
    )
    edit["balance"] = normalize_money_column(edit, "balance")
    save_df("assets", edit)

with col2:
    st.subheader("Credit Cards")
    edit = st.data_editor(
        cards,
        key="cards",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "balance": st.column_config.TextColumn("Balance (£)"),
            "due": st.column_config.TextColumn("Bill due this cycle (£)"),
            "is_due": st.column_config.CheckboxColumn("Due?"),
        },
    )
    edit["balance"] = normalize_money_column(edit, "balance")
    edit["due"] = normalize_money_column(edit, "due")
    save_df("cards", edit)

with col3:
    st.subheader("Reimbursement Pending")
    edit = st.data_editor(
        reimb,
        key="reimb",
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "amount": st.column_config.TextColumn("Amount (£)"),
            "include": st.column_config.CheckboxColumn("Include this month?"),
        },
    )
    edit["amount"] = normalize_money_column(edit, "amount")
    save_df("reimb", edit)

st.divider()

# -------------------------
# MONTHLY FIXED
# -------------------------
st.subheader("Monthly Fixed")

edit = st.data_editor(
    fixed,
    key="fixed",
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "amount": st.column_config.TextColumn("Amount (£)"),
        "monthly": st.column_config.CheckboxColumn("Monthly?"),
        "due_now": st.column_config.CheckboxColumn("Due Now?"),
    },
)

edit["amount"] = normalize_money_column(edit, "amount")
save_df("fixed", edit)
