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
@st.cache_data(ttl=60 * 60)  # cache for 1 hour
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
    """
    Accepts: 123.45, 123,45, £123.45, 1,234.56, -12.34 etc.
    """
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

def fmt_gbp(x: float) -> str:
    return f"£{x:,.2f}"

# ----------------------------
# Defaults
# ----------------------------
# Add currency to assets so Apple Savings can be USD
DEFAULT_ASSETS = pd.DataFrame(
    [
        {"account": "HSBC", "currency": "GBP", "balance": "0"},
        {"account": "Lloyds", "currency": "GBP", "balance": "0"},
        {"account": "Apple Savings", "currency": "USD", "balance": "0"},
        {"account": "Cash", "currency": "GBP", "balance": "0"},
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
# Session state init
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
    if "manual_usd_gbp" not in st.session_state:
        st.session_state.manual_usd_gbp = "0.80"

def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")

def make_backup_zip() -> bytes:
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

init_state()

# ----------------------------
# Sidebar Save/Load
# ----------------------------
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
            st.success("Backup restored.")
        except Exception as e:
            st.error(f"Couldn’t load that ZIP: {e}")

    st.divider()
    if st.button("Reset to defaults", use_container_width=True):
        st.session_state.assets = DEFAULT_ASSETS.copy()
        st.session_state.cards = DEFAULT_CARDS.copy()
        st.session_state.fixed = DEFAULT_FIXED.copy()
        st.session_state.reimb = DEFAULT_REIMB.copy()
        st.session_state.pay = DEFAULT_PAY.copy()
        st.session_state.manual_usd_gbp = "0.80"
        st.success("Reset done.")

# ----------------------------
# FX (silent)
# ----------------------------
try:
    usd_gbp = get_fx_rate("USD", "GBP")
    fx_source = "live"
except Exception:
    usd_gbp = parse_money_text(st.session_state.manual_usd_gbp)
    fx_source = "manual (live failed)"

# ----------------------------
# Calculations
# ----------------------------
assets_num = st.session_state.assets.copy()
if "currency" not in assets_num.columns:
    assets_num["currency"] = "GBP"
assets_num["currency"] = assets_num["currency"].fillna("GBP").astype(str).str.upper()
assets_num = coerce_numeric(assets_num, ["balance"])

cards_num = st.session_state.cards.copy()
if "currency" not in cards_num.columns:
    cards_num["currency"] = "GBP"
cards_num["currency"] = cards_num["currency"].fillna("GBP").astype(str).str.upper()
cards_num = coerce_numeric(cards_num, ["balance", "due_this_cycle"])

fixed_num = coerce_numeric(st.session_state.fixed.copy(), ["amount"])
reimb_num = coerce_numeric(st.session_state.reimb.copy(), ["amount"])

def to_gbp(amount: float, currency: str) -> float:
    return amount * usd_gbp if currency == "USD" else amount

assets_num["balance_gbp"] = assets_num.apply(lambda r: to_gbp(r["balance"], r["currency"]), axis=1)
cards_num["balance_gbp"] = cards_num.apply(lambda r: to_gbp(r["balance"], r["currency"]), axis=1)
cards_num["due_gbp"] = cards_num.apply(lambda r: to_gbp(r["due_this_cycle"], r["currency"]), axis=1)

assets_total_gbp = float(assets_num["balance_gbp"].sum())
cards_total_balance_gbp = float(cards_num["balance_gbp"].sum())
cards_due_total_gbp = float(cards_num.loc[cards_num["is_due"] == True, "due_gbp"].sum()) if "is_due" in cards_num.columns else 0.0
fixed_total_gbp = float(fixed_num["amount"].sum()) if "amount" in fixed_num.columns else 0.0
fixed_due_total_gbp = float(fixed_num.loc[fixed_num["due"] == True, "amount"].sum()) if "due" in fixed_num.columns else 0.0
reimb_included_total_gbp = float(reimb_num.loc[reimb_num["include_this_month"] == True, "amount"].sum()) if "include_this_month" in reimb_num.columns else 0.0

net_cash_gbp = assets_total_gbp - cards_total_balance_gbp
total_spend_rest_gbp = fixed_due_total_gbp + cards_due_total_gbp

# ----------------------------
# UI
# ----------------------------
st.title("Stabler Family Finances")

k1, k2, k3 = st.columns(3)
k1.metric("Net Cash (GBP)", fmt_gbp(net_cash_gbp))
k2.metric("Total Credit Card Bill Due (GBP)", fmt_gbp(cards_due_total_gbp))
k3.metric("Total Spend Rest of Month (GBP)", fmt_gbp(total_spend_rest_gbp))

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
            "currency": st.column_config.SelectboxColumn("Currency", options=["GBP", "USD"]),
            "balance": st.column_config.TextColumn("Balance (native)"),
        },
        key="assets_editor",
    )
    st.caption(f"Total Assets (GBP): {fmt_gbp(assets_total_gbp)}")

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
            "due_this_cycle": st.column_config.TextColumn("Due this cycle (native)"),
            "is_due": st.column_config.CheckboxColumn("Due?"),
        },
        key="cards_editor",
    )
    st.caption(f"Total Card Balances (GBP): {fmt_gbp(cards_total_balance_gbp)} · Total Bills Due (GBP): {fmt_gbp(cards_due_total_gbp)}")

with c3:
    st.subheader("Reimbursement Pending")
    st.session_state.reimb = st.data_editor(
        st.session_state.reimb,
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "source": st.column_config.TextColumn("Source"),
            "amount": st.column_config.TextColumn("Amount (GBP)"),
            "include_this_month": st.column_config.CheckboxColumn("Include?"),
        },
        key="reimb_editor",
    )
    st.caption(f"Included Reimbursements (GBP): {fmt_gbp(reimb_included_total_gbp)}")

st.markdown("---")

left, right = st.columns([2, 1])

with left:
    st.subheader("Monthly Fixed")
    st.session_state.fixed = st.data_editor(
        st.session_state.fixed,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "item": st.column_config.TextColumn("Item"),
            "amount": st.column_config.TextColumn("Amount (GBP)"),
            "due": st.column_config.CheckboxColumn("Due?"),
        },
        key="fixed_editor",
    )
    st.caption(f"Fixed Monthly Total (GBP): {fmt_gbp(fixed_total_gbp)} · Fixed Due (GBP): {fmt_gbp(fixed_due_total_gbp)}")

with right:
    st.subheader("Pay Cycle (setup)")
    st.caption("Optional – for future projections.")
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

st.markdown("---")

# ----------------------------
# FX Settings (BOTTOM)
# ----------------------------
st.subheader("FX Settings (USD → GBP)")
st.caption("Used for Apple Card + Apple Savings. Live rate from Frankfurter when available; fallback is manual.")
fx1, fx2 = st.columns([2, 1])
with fx1:
    st.write(f"**USD→GBP rate:** `{usd_gbp:.6f}`  _(source: {fx_source})_")
with fx2:
    st.session_state.manual_usd_gbp = st.text_input(
        "Manual USD→GBP (fallback)",
        value=st.session_state.manual_usd_gbp,
        key="manual_fx_input",
    )
