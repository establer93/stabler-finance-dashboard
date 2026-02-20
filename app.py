import io
import zipfile
from datetime import date
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Stabler Family Finances", layout="wide")

# ----------------------------
# Defaults (used if no backup uploaded yet)
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
        {"card": "Amex", "balance": "0", "due_this_cycle": "0", "is_due": False},
        {"card": "Apple", "balance": "0", "due_this_cycle": "0", "is_due": False},
    ]
)

DEFAULT_FIXED = pd.DataFrame(
    [
        {"item": "Savings", "amount": "5000.00", "due": True},
        {"item": "RAC", "amount": "300.00", "due": True},
        {"item": "Car Loan", "amount": "480.37", "due": True},
        {"item": "Marchon", "amount": "133.10", "due": True},
        {"item": "Utilities", "amount": "425.00", "due": True},
        {"item": "Eric Vodafone", "amount": "38.00", "due": True},
        {"item": "Eric Haircut", "amount": "35.00", "due": True},
        {"item": "Eric iphone", "amount": "35.11", "due": True},
        {"item": "Cleaning", "amount": "72.00", "due": True},
        {"item": "Gigi Vodafone", "amount": "38.00", "due": True},
        {"item": "Gigi Gym", "amount": "79.00", "due": True},
        {"item": "Caroline Circuits", "amount": "35.00", "due": True},
        {"item": "Gigi Charity", "amount": "12.00", "due": True},
        {"item": "G+ E Contacts", "amount": "95.00", "due": True},
    ]
)

# “Reimbursement pending” with 3 rows
DEFAULT_REIMB = pd.DataFrame(
    [
        {"source": "Eric Work", "amount": "0", "include_this_month": True},
        {"source": "Gigi Work", "amount": "0", "include_this_month": True},
        {"source": "Misc", "amount": "0", "include_this_month": False},
    ]
)

DEFAULT_PAY = pd.DataFrame(
    [
        {"person": "Eric", "monthly_pay": "0"},
        {"person": "Gigi", "monthly_pay": "0"},
    ]
)

# ----------------------------
# Helpers: in-session "database"
# ----------------------------
def init_state():
    if "assets" not in st.session_state:
        st.session_state.assets = DEFAULT_ASSETS.copy()
    if "cards" not in st.session_state:
        st.session_state.cards = DEFAULT_CARDS.copy()
    if "fixed" not in st.session_state:
        st.session_state.fixed = DEFAULT_FIXED.copy()
    if "reimb" not in st.session_state:
        st.session_state.reimb = DEFAULT_REIMB.copy()
    if "pay" not in st.session_state:
        st.session_state.pay = DEFAULT_PAY.copy()

def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")

def make_backup_zip() -> bytes:
    """Create an in-memory ZIP containing all tables as CSV."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("assets.csv", df_to_csv_bytes(st.session_state.assets))
        z.writestr("credit_cards.csv", df_to_csv_bytes(st.session_state.cards))
        z.writestr("fixed_costs.csv", df_to_csv_bytes(st.session_state.fixed))
        z.writestr("reimbursements.csv", df_to_csv_bytes(st.session_state.reimb))
        z.writestr("pay_cycle.csv", df_to_csv_bytes(st.session_state.pay))
    buf.seek(0)
    return buf.read()

def load_backup_zip(zip_bytes: bytes):
    """Load CSVs from a ZIP into session_state. Missing files fall back to defaults."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
        names = set(z.namelist())

        def read_df(name, default_df):
            if name in names:
                return pd.read_csv(z.open(name))
            return default_df.copy()

        st.session_state.assets = read_df("assets.csv", DEFAULT_ASSETS)
        st.session_state.cards = read_df("credit_cards.csv", DEFAULT_CARDS)
        st.session_state.fixed = read_df("fixed_costs.csv", DEFAULT_FIXED)
        st.session_state.reimb = read_df("reimbursements.csv", DEFAULT_REIMB)
        st.session_state.pay = read_df("pay_cycle.csv", DEFAULT_PAY)

def coerce_numeric(df: pd.DataFrame, cols):
    """
    Converts text inputs to numbers safely.
    Accepts: 123.45, 123,45, £123.45, 1,234.56
    """
    def parse(v):
        if v is None:
            return 0.0
        s = str(v).strip()
        if s == "" or s.lower() in {"nan", "none"}:
            return 0.0
        s = s.replace("£", "").replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
        s = re.sub(r"[^0-9\.\-]", "", s)
        try:
            return float(s)
        except:
            return 0.0

    import re
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(parse)
    return df

# ----------------------------
# UI: Save / Load controls
# ----------------------------
init_state()

with st.sidebar:
    st.header("Save / Load")

    backup_name = f"stabler-finances-backup-{date.today().isoformat()}.zip"
    st.download_button(
        label="⬇️ Download backup (ZIP)",
        data=make_backup_zip(),
        file_name=backup_name,
        mime="application/zip",
        use_container_width=True,
    )

    uploaded = st.file_uploader("⬆️ Restore from backup (ZIP)", type=["zip"])
    if uploaded is not None:
        try:
            load_backup_zip(uploaded.read())
            st.success("Backup restored. (Your tables are now loaded from the ZIP.)")
        except Exception as e:
            st.error(f"Couldn’t load that ZIP: {e}")

    st.divider()
    if st.button("Reset to defaults", use_container_width=True):
        st.session_state.assets = DEFAULT_ASSETS.copy()
        st.session_state.cards = DEFAULT_CARDS.copy()
        st.session_state.fixed = DEFAULT_FIXED.copy()
        st.session_state.reimb = DEFAULT_REIMB.copy()
        st.session_state.pay = DEFAULT_PAY.copy()
        st.success("Reset done.")

# ----------------------------
# Main app
# ----------------------------
st.title("Stabler Family Finances")

# Convert text -> numeric for calculations
assets_num = coerce_numeric(st.session_state.assets.copy(), ["balance"])
cards_num = coerce_numeric(st.session_state.cards.copy(), ["balance", "due_this_cycle"])
fixed_num = coerce_numeric(st.session_state.fixed.copy(), ["amount"])
reimb_num = coerce_numeric(st.session_state.reimb.copy(), ["amount"])

assets_total = float(assets_num["balance"].sum()) if "balance" in assets_num else 0.0
card_bal_total = float(cards_num["balance"].sum()) if "balance" in cards_num else 0.0

if "is_due" in cards_num.columns and "due_this_cycle" in cards_num.columns:
    card_due_total = float(cards_num.loc[cards_num["is_due"] == True, "due_this_cycle"].sum())
else:
    card_due_total = 0.0

if "due" in fixed_num.columns and "amount" in fixed_num.columns:
    fixed_due_total = float(fixed_num.loc[fixed_num["due"] == True, "amount"].sum())
else:
    fixed_due_total = 0.0

net_cash = assets_total - card_bal_total
total_spend_rest_of_month = fixed_due_total + card_due_total

# ---- Top KPI row
k1, k2, k3 = st.columns(3)
k1.metric("Net Cash", f"£{net_cash:,.2f}")
k2.metric("Total Credit Card Bill Due", f"£{card_due_total:,.2f}")
k3.metric("Total Spend Rest of Month", f"£{total_spend_rest_of_month:,.2f}")

st.markdown("---")

# ---- Tables row
c1, c2, c3 = st.columns(3)

with c1:
    st.subheader("Assets")
    st.session_state.assets = st.data_editor(
        st.session_state.assets,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "account": st.column_config.TextColumn("account"),
            "balance": st.column_config.TextColumn("Balance (£)"),
        },
        key="assets_editor",
    )

with c2:
    st.subheader("Credit Cards")
    st.session_state.cards = st.data_editor(
        st.session_state.cards,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "card": st.column_config.TextColumn("card"),
            "balance": st.column_config.TextColumn("Balance (£)"),
            "due_this_cycle": st.column_config.TextColumn("Due this cycle (£)"),
            "is_due": st.column_config.CheckboxColumn("Due?"),
        },
        key="cards_editor",
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
        key="reimb_editor",
    )

st.markdown("---")

left, right = st.columns([2, 1])

with left:
    st.subheader("Monthly Fixed")
    st.session_state.fixed = st.data_editor(
        st.session_state.fixed,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "item": st.column_config.TextColumn("item"),
            "amount": st.column_config.TextColumn("Amount (£)"),
            "due": st.column_config.CheckboxColumn("Due?"),
        },
        key="fixed_editor",
    )

with right:
    st.subheader("Pay Cycle (setup)")
    st.caption("Enter monthly take-home pay. (Dates can be added later.)")
    st.session_state.pay = st.data_editor(
        st.session_state.pay,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "person": st.column_config.TextColumn("Person"),
            "monthly_pay": st.column_config.TextColumn("Monthly pay (£)"),
        },
        key="pay_editor",
    )
