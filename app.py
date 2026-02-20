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

def ensure_file(filename: str, cols: list[str]) -> None:
    """Create the file with just headers if it doesn't exist."""
    path = Path(filename)
    if not path.exists():
        pd.DataFrame(columns=cols).to_csv(path, index=False)

def load_df(key: str) -> pd.DataFrame:
    filename, cols = FILES[key]
    ensure_file(filename, cols)
    df = pd.read_csv(filename)

    # Ensure required columns exist (in case you edited CSVs manually)
    for c in cols:
        if c not in df.columns:
            df[c] = None

    df = df[cols].copy()

    # If a CSV got polluted with a None row, drop fully-empty rows
    df = df.dropna(how="all")

    return df

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
def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)

def to_bool(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool)

assets["balance"] = to_number(assets["balance"])
liabilities["balance"] = to_number(liabilities["balance"])
cards["balance"] = to_number(cards["balance"])
cards["due"] = to_number(cards["due"])
fixed["amount"] = to_number(fixed["amount"])

cards["is_due"] = to_bool(cards["is_due"])
fixed["is_due"] = to_bool(fixed["is_due"])

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

# ---- Second row: Fixed + Overview ----
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
    st.subheader("Cash & Due Overview")

    due_now = cards_due + fixed_due

    not_due_cards = max(cards_total - cards_due, 0.0)
    not_due_fixed = max(fixed_total - fixed_due, 0.0)
    total_not_due = not_due_cards + not_due_fixed

    net_position = assets_total - liab_total - cards_total
    cash_position = assets_total - cards_total

    r1, r2 = st.columns(2)
    r1.metric("Due now", money(due_now))
    r2.metric("Not due", money(total_not_due))

    st.markdown("---")
    st.metric("Net position", money(net_position))
    st.metric("Cash position (assets - cards)", money(cash_position))

    st.markdown("---")
    st.markdown("### Due Items")

    due_cards_df = cards_edit[cards_edit["is_due"] == True].copy()
    due_fixed_df = fixed_edit[fixed_edit["is_due"] == True].copy()

    if due_cards_df.empty and due_fixed_df.empty:
        st.write("Nothing currently marked as due ✅")
    else:
        if not due_cards_df.empty:
            st.write("**Cards due:**")
            st.dataframe(due_cards_df[["card", "due"]], use_container_width=True)
        if not due_fixed_df.empty:
            st.write("**Fixed due:**")
            st.dataframe(due_fixed_df[["item", "amount"]], use_container_width=True)
