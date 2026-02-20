import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Stabler Family Finances", layout="wide")
st.title("Stabler Family Finances")

FILES = {
    "assets": ("assets.csv", ["account", "balance"]),
    "liabilities": ("liabilities.csv", ["account", "balance"]),
    "cards": ("credit_cards.csv", ["card", "balance", "due", "is_due"]),
    "fixed": ("fixed_costs.csv", ["item", "amount", "is_due"]),
}

def load_df(key: str) -> pd.DataFrame:
    filename, cols = FILES[key]
    path = Path(filename)
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols].copy()

def save_df(key: str, df: pd.DataFrame) -> None:
    filename, cols = FILES[key]
    out = df.copy()[cols]
    out.to_csv(filename, index=False)

def money(x) -> str:
    try:
        return f"£{float(x):,.2f}"
    except Exception:
        return "£0.00"

# ---- Load data ----
assets = load_df("assets")
liabilities = load_df("liabilities")
cards = load_df("cards")
fixed = load_df("fixed")

# ---- Clean types ----
for df, col in [
    (assets, "balance"),
    (liabilities, "balance"),
    (cards, "balance"),
    (cards, "due"),
    (fixed, "amount"),
]:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

for df, col in [(cards, "is_due"), (fixed, "is_due")]:
    df[col] = df[col].fillna(False).astype(bool)

# ---- Layout: Top row ----
c1, c2, c3 = st.columns(3)

with c1:
    st.subheader("Assets")
    assets_edit = st.data_editor(
        assets,
        key="assets_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "balance": st.column_config.NumberColumn("Balance", format="£%.2f")
        },
    )
    save_df("assets", assets_edit)
    assets_total = float(assets_edit["balance"].sum()) if not assets_edit.empty else 0.0

with c2:
    st.subheader("Liabilities")
    liab_edit = st.data_editor(
        liabilities,
        key="liabilities_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "balance": st.column_config.NumberColumn("Balance", format="£%.2f")
        },
    )
    save_df("liabilities", liab_edit)
    liab_total = float(liab_edit["balance"].sum()) if not liab_edit.empty else 0.0

with c3:
    st.subheader("Credit Cards")
    cards_edit = st.data_editor(
        cards,
        key="cards_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "balance": st.column_config.NumberColumn("Balance", format="£%.2f"),
            "due": st.column_config.NumberColumn("Due this cycle", format="£%.2f"),
            "is_due": st.column_config.CheckboxColumn("Due?"),
        },
    )
    save_df("cards", cards_edit)
    cards_total = float(cards_edit["balance"].sum()) if not cards_edit.empty else 0.0
    cards_due = float(cards_edit.loc[cards_edit["is_due"] == True, "due"].sum()) if not cards_edit.empty else 0.0

st.divider()

# ---- Second row: Fixed + Summary ----
left, right = st.columns([1.3, 0.7])

with left:
    st.subheader("Monthly Fixed")
    fixed_edit = st.data_editor(
        fixed,
        key="fixed_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "amount": st.column_config.NumberColumn("Amount", format="£%.2f"),
            "is_due": st.column_config.CheckboxColumn("Due?"),
        },
    )
    save_df("fixed", fixed_edit)
    fixed_total = float(fixed_edit["amount"].sum()) if not fixed_edit.empty else 0.0
    fixed_due = float(fixed_edit.loc[fixed_edit["is_due"] == True, "amount"].sum()) if not fixed_edit.empty else 0.0

with right:
    st.subheader("Summary")
    due_now = cards_due + fixed_due
    net_position = assets_total - liab_total - cards_total
    cash_position = assets_total - cards_total  # quick "cash vs cards" view

    k1, k2 = st.columns(2)
    k1.metric("Due now", money(due_now))
    k2.metric("Net position", money(net_position))

    st.markdown("---")
    st.markdown("**Breakdown**")
    st.write(f"Assets total: {money(assets_total)}")
    st.write(f"Liabilities total: {money(liab_total)}")
    st.write(f"Card balances: {money(cards_total)}")
    st.write(f"Fixed monthly total: {money(fixed_total)}")
    st.write(f"Cash position (assets - cards): {money(cash_position)}")
    st.write(f"Cards due: {money(cards_due)}")
    st.write(f"Fixed due: {money(fixed_due)}")
