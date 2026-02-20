import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Stabler Family Finances", layout="wide")
st.title("Stabler Family Finances")

FILES = {
    "assets": ("assets.csv", ["account", "balance"]),
    "cards": ("credit_cards.csv", ["card", "balance", "due", "is_due"]),
    "pending": ("expense_pending.csv", ["item", "amount", "include"]),
    "fixed": ("fixed_costs.csv", ["item", "amount", "is_due"]),
}

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

    df = df[cols].copy()
    df = df.dropna(how="all")
    return df

def save_df(key: str, df: pd.DataFrame) -> None:
    filename, cols = FILES[key]
    df.copy()[cols].to_csv(filename, index=False)

def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)

def to_bool(series: pd.Series) -> pd.Series:
    s = series.replace({"TRUE": True, "FALSE": False})
    return s.fillna(False).astype(bool)

def money(x) -> str:
    try:
        return f"£{float(x):,.2f}"
    except:
        return "£0.00"

# -------------------------
# Load data
# -------------------------
assets = load_df("assets")
cards = load_df("cards")
pending = load_df("pending")
fixed = load_df("fixed")

assets["balance"] = to_number(assets["balance"])

cards["balance"] = to_number(cards["balance"])
cards["due"] = to_number(cards["due"])
cards["is_due"] = to_bool(cards["is_due"])

pending["amount"] = to_number(pending["amount"])
pending["include"] = to_bool(pending["include"])

fixed["amount"] = to_number(fixed["amount"])
fixed["is_due"] = to_bool(fixed["is_due"])

# -------------------------
# TOP ROW
# -------------------------
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Assets")
    assets_edit = st.data_editor(
        assets,
        key="assets_editor",
        num_rows="dynamic",
        use_container_width=True,
    )
    save_df("assets", assets_edit)
    assets_total = float(assets_edit["balance"].sum()) if not assets_edit.empty else 0.0
    st.caption(f"Total Assets: {money(assets_total)}")

with col2:
    st.subheader("Credit Cards")
    cards_edit = st.data_editor(
        cards,
        key="cards_editor",
        num_rows="dynamic",
        use_container_width=True,
    )
    save_df("cards", cards_edit)

    cards_total_balance = float(cards_edit["balance"].sum()) if not cards_edit.empty else 0.0
    cards_bill_due_total = float(cards_edit["due"].sum()) if not cards_edit.empty else 0.0
    st.caption(f"Total Card Balances: {money(cards_total_balance)}")

with col3:
    st.subheader("Expense Pending")
    pending_edit = st.data_editor(
        pending,
        key="pending_editor",
        num_rows="dynamic",
        use_container_width=True,
    )
    save_df("pending", pending_edit)

    pending_total = float(pending_edit.loc[pending_edit["include"] == True, "amount"].sum()) if not pending_edit.empty else 0.0
    st.caption(f"Included Pending: {money(pending_total)}")

st.divider()

# -------------------------
# SECOND ROW METRICS
# -------------------------
fixed_due_total = float(fixed.loc[fixed["is_due"] == True, "amount"].sum()) if not fixed.empty else 0.0
cards_due_now = float(cards_edit.loc[cards_edit["is_due"] == True, "due"].sum()) if not cards_edit.empty else 0.0

net_cash = assets_total - cards_total_balance
total_spend_rest_month = fixed_due_total + pending_total + cards_due_now

m1, m2, m3 = st.columns(3)
m1.metric("Net Cash", money(net_cash))
m2.metric("Total Credit Card Bill Due", money(cards_bill_due_total))
m3.metric("Total Spend Rest of Month", money(total_spend_rest_month))

st.divider()

with st.expander("Monthly Fixed (Used in totals)", expanded=True):
    fixed_edit = st.data_editor(
        fixed,
        key="fixed_editor",
        num_rows="dynamic",
        use_container_width=True,
    )
    save_df("fixed", fixed_edit)

    fixed_total = float(fixed_edit["amount"].sum()) if not fixed_edit.empty else 0.0
    fixed_due_total_live = float(fixed_edit.loc[fixed_edit["is_due"] == True, "amount"].sum()) if not fixed_edit.empty else 0.0
    st.caption(f"Total Monthly Fixed: {money(fixed_total)}")
