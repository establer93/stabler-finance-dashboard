import streamlit as st
import pandas as pd
from pathlib import Path
import re

st.set_page_config(page_title="Stabler Family Finances", layout="wide")
st.title("Stabler Family Finances")

FILES = {
    "assets": ("assets.csv", ["account", "balance"]),
    "cards": ("credit_cards.csv", ["card", "balance", "due", "is_due"]),
    "pending": ("expense_pending.csv", ["item", "amount", "include"]),
    "fixed": ("fixed_costs.csv", ["item", "amount", "is_due"]),
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

    df = df[cols].copy().dropna(how="all")
    return df

def save_df(key: str, df: pd.DataFrame) -> None:
    filename, cols = FILES[key]
    df.copy()[cols].to_csv(filename, index=False)

def money(x) -> str:
    try:
        return f"£{float(x):,.2f}"
    except Exception:
        return "£0.00"

def to_bool(series: pd.Series) -> pd.Series:
    s = series.copy()
    s = s.replace({"TRUE": True, "FALSE": False, "true": True, "false": False})
    return s.fillna(False).astype(bool)

def parse_money_cell(v) -> float:
    """
    Accepts:
      123.45
      123,45
      £123.45
      1,234.56
      1.234,56 (we'll best-effort)
    Returns float, default 0.0 if blank/invalid.
    """
    if v is None:
        return 0.0
    s = str(v).strip()
    if s == "" or s.lower() in {"nan", "none"}:
        return 0.0

    # Remove currency and spaces
    s = s.replace("£", "").replace(" ", "")

    # If both ',' and '.' exist, assume ',' are thousands separators -> remove commas
    if "," in s and "." in s:
        s = s.replace(",", "")
    else:
        # Otherwise treat comma as decimal separator
        s = s.replace(",", ".")

    # Keep only digits, minus, dot
    s = re.sub(r"[^0-9\.\-]", "", s)

    try:
        return float(s)
    except Exception:
        return 0.0

def normalize_money_column(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col].apply(parse_money_cell)

# -------------------------
# Load data
# -------------------------
assets = load_df("assets")
cards = load_df("cards")
pending = load_df("pending")
fixed = load_df("fixed")

# Ensure boolean cols behave
if "is_due" in cards.columns:
    cards["is_due"] = to_bool(cards["is_due"])
if "include" in pending.columns:
    pending["include"] = to_bool(pending["include"])
if "is_due" in fixed.columns:
    fixed["is_due"] = to_bool(fixed["is_due"])

# Convert money cols to strings for editing (so iPad can type '.' freely)
for df, col in [(assets, "balance"), (cards, "balance"), (cards, "due"), (pending, "amount"), (fixed, "amount")]:
    if col in df.columns:
        df[col] = df[col].fillna("").astype(str)

# -------------------------
# TOP ROW: Assets | Credit Cards | Expense Pending
# -------------------------
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Assets")
    assets_edit = st.data_editor(
        assets,
        key="assets_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "balance": st.column_config.TextColumn("Balance (£)", help="Type e.g. 123.45")
        },
    )

    # Normalize + save as numeric strings (clean CSV)
    assets_out = assets_edit.copy()
    assets_out["balance"] = normalize_money_column(assets_out, "balance")
    save_df("assets", assets_out)

    assets_total = float(assets_out["balance"].sum()) if not assets_out.empty else 0.0
    st.caption(f"Total Assets: {money(assets_total)}")

with col2:
    st.subheader("Credit Cards")
    cards_edit = st.data_editor(
        cards,
        key="cards_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "balance": st.column_config.TextColumn("Balance (£)", help="Type e.g. 123.45"),
            "due": st.column_config.TextColumn("Bill due this cycle (£)", help="Type e.g. 123.45"),
            "is_due": st.column_config.CheckboxColumn("Due?"),
        },
    )

    cards_out = cards_edit.copy()
    cards_out["is_due"] = to_bool(cards_out["is_due"])
    cards_out["balance"] = normalize_money_column(cards_out, "balance")
    cards_out["due"] = normalize_money_column(cards_out, "due")
    save_df("cards", cards_out)

    cards_total_balance = float(cards_out["balance"].sum()) if not cards_out.empty else 0.0
    cards_bill_due_total = float(cards_out["due"].sum()) if not cards_out.empty else 0.0
    st.caption(f"Total Card Balances: {money(cards_total_balance)} · Total Bills Due: {money(cards_bill_due_total)}")

with col3:
    st.subheader("Expense Pending")
    st.caption("One-off expenses to include in 'rest of month' spend.")
    pending_edit = st.data_editor(
        pending,
        key="pending_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "amount": st.column_config.TextColumn("Amount (£)", help="Type e.g. 123.45"),
            "include": st.column_config.CheckboxColumn("Include this month?"),
        },
    )

    pending_out = pending_edit.copy()
    pending_out["include"] = to_bool(pending_out["include"])
    pending_out["amount"] = normalize_money_column(pending_out, "amount")
    save_df("pending", pending_out)

    pending_total = float(pending_out.loc[pending_out["include"] == True, "amount"].sum()) if not pending_out.empty else 0.0
    st.caption(f"Included Pending: {money(pending_total)}")

st.divider()

# -------------------------
# SECOND ROW METRICS
# -------------------------
# Load fixed due from saved/normalized fixed_out below; for now compute after fixed editor.
net_cash = assets_total - cards_total_balance
cards_due_now = float(cards_out.loc[cards_out["is_due"] == True, "due"].sum()) if not cards_out.empty else 0.0

# Placeholder until we compute fixed_due_total
fixed_due_total = 0.0
total_spend_rest_month = fixed_due_total + pending_total + cards_due_now

m1, m2, m3 = st.columns(3)
m1.metric("Net Cash", money(net_cash))
m2.metric("Total Credit Card Bill Due", money(cards_bill_due_total))
m3.metric("Total Spend Rest of Month", money(total_spend_rest_month))

st.divider()

# -------------------------
# Monthly Fixed (supports totals)
# -------------------------
with st.expander("Monthly Fixed (Used in totals)", expanded=True):
    fixed_edit = st.data_editor(
        fixed,
        key="fixed_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "amount": st.column_config.TextColumn("Amount (£)", help="Type e.g. 123.45"),
            "is_due": st.column_config.CheckboxColumn("Due this month?"),
        },
    )

    fixed_out = fixed_edit.copy()
    fixed_out["is_due"] = to_bool(fixed_out["is_due"])
    fixed_out["amount"] = normalize_money_column(fixed_out, "amount")
    save_df("fixed", fixed_out)

    fixed_total = float(fixed_out["amount"].sum()) if not fixed_out.empty else 0.0
    fixed_due_total = float(fixed_out.loc[fixed_out["is_due"] == True, "amount"].sum()) if not fixed_out.empty else 0.0

    # Recompute spend rest of month with live fixed
    total_spend_rest_month_live = fixed_due_total + pending_total + cards_due_now

    st.caption(f"Total Monthly Fixed: {money(fixed_total)} · Fixed Due This Month: {money(fixed_due_total)}")
    st.caption(f"Spend Rest of Month (recalc): {money(total_spend_rest_month_live)}")
