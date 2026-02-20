import io
import zipfile
from datetime import date
import pandas as pd
import streamlit as st
import requests
import re

st.set_page_config(page_title="Stabler Family Finances", layout="wide")

# ============================
# FX (live) – Frankfurter (no key)
# ============================
@st.cache_data(ttl=60 * 60)  # 1 hour
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
    # handle thousands vs decimals
    if "," in s and "." in s:
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    s = re.sub(r"[^0-9\.\-]", "", s)
    try:
        return float(s)
    except:
        return 0.0

def fmt_gbp(x: float) -> str:
    return f"£{x:,.2f}"

# ============================
# Defaults
# ============================
DEFAULT_ASSETS = pd.DataFrame(
    [
        {"account": "HSBC", "currency": "GBP", "balance": 0.0},
        {"account": "Lloyds", "currency": "GBP", "balance": 0.0},
        {"account": "Apple Savings", "currency": "USD", "balance": 0.0},
        {"account": "Cash", "currency": "GBP", "balance": 0.0},
    ]
)

DEFAULT_CARDS = pd.DataFrame(
    [
        {"card": "Amex", "currency": "GBP", "balance": 0.0, "due_this_cycle": 0.0, "is_due": False},
        {"card": "Apple Card", "currency": "USD", "balance": 0.0, "due_this_cycle": 0.0, "is_due": False},
    ]
)

DEFAULT_FIXED = pd.DataFrame(
    [
        {"item": "Savings", "amount": 5000.00, "due": True},
        {"item": "RAC", "amount": 300.00, "due": True},
        {"item": "Car Loan", "amount": 480.37, "due": True},
        {"item": "Marchon", "amount": 133.10, "due": True},
        {"item": "Utilities", "amount": 425.00, "due": True},
        {"item": "Eric Vodafone", "amount": 38.00, "due": True},
        {"item": "Eric Haircut", "amount": 35.00, "due": True},
        {"item": "Eric iphone", "amount": 35.11, "due": True},
        {"item": "Cleaning", "amount": 72.00, "due": True},
        {"item": "Gigi Vodafone", "amount": 38.00, "due": True},
        {"item": "Gigi Gym", "amount": 79.00, "due": True},
        {"item": "Caroline Circuits", "amount": 35.00, "due": True},
        {"item": "Gigi Charity", "amount": 12.00, "due": True},
        {"item": "G+ E Contacts", "amount": 95.00, "due": True},
    ]
)

DEFAULT_REIMB = pd.DataFrame(
    [
        {"source": "Eric Work", "amount": 0.0, "include_this_month": True},
        {"source": "Gigi Work", "amount": 0.0, "include_this_month": True},
        {"source": "Misc", "amount": 0.0, "include_this_month": False},
    ]
)

DEFAULT_PAY = pd.DataFrame(
    [
        {"person": "Eric", "monthly_pay": 0.0},
        {"person": "Gigi", "monthly_pay": 0.0},
    ]
)

# ============================
# Normalisation (fixes your error)
# ============================
def ensure_cols(df: pd.DataFrame, cols_defaults: dict) -> pd.DataFrame:
    df = df.copy()
    for c, default_val in cols_defaults.items():
        if c not in df.columns:
            df[c] = default_val
    return df

def normalize_assets(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_cols(df, {"account": "", "currency": "GBP", "balance": 0.0})
    df["account"] = df["account"].fillna("").astype(str)
    df["currency"] = df["currency"].fillna("GBP").astype(str).str.upper()
    df["balance"] = df["balance"].apply(parse_money_text).astype(float)
    df = df[["account", "currency", "balance"]]
    return df

def normalize_cards(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_cols(df, {"card": "", "currency": "GBP", "balance": 0.0, "due_this_cycle": 0.0, "is_due": False})
    df["card"] = df["card"].fillna("").astype(str)
    df["currency"] = df["currency"].fillna("GBP").astype(str).str.upper()
    df["balance"] = df["balance"].apply(parse_money_text).astype(float)
    df["due_this_cycle"] = df["due_this_cycle"].apply(parse_money_text).astype(float)
    df["is_due"] = df["is_due"].fillna(False).astype(bool)
    df = df[["card", "currency", "balance", "due_this_cycle", "is_due"]]
    return df

def normalize_fixed(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_cols(df, {"item": "", "amount": 0.0, "due": True})
    df["item"] = df["item"].fillna("").astype(str)
    df["amount"] = df["amount"].apply(parse_money_text).astype(float)
    df["due"] = df["due"].fillna(True).astype(bool)
    df = df[["item", "amount", "due"]]
    return df

def normalize_reimb(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_cols(df, {"source": "", "amount": 0.0, "include_this_month": True})
    df["source"] = df["source"].fillna("").astype(str)
    df["amount"] = df["amount"].apply(parse_money_text).astype(float)
    df["include_this_month"] = df["include_this_month"].fillna(True).astype(bool)
    df = df[["source", "amount", "include_this_month"]]
    return df

def normalize_pay(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_cols(df, {"person": "", "monthly_pay": 0.0})
    df["person"] = df["person"].fillna("").astype(str)
    df["monthly_pay"] = df["monthly_pay"].apply(parse_money_text).astype(float)
    df = df[["person", "monthly_pay"]]
    return df

# ============================
# Session state init
# ============================
def init_state():
    if "assets" not in st.session_state:
        st.session_state.assets = normalize_assets(DEFAULT_ASSETS)
    if "cards" not in st.session_state:
        st.session_state.cards = normalize_cards(DEFAULT_CARDS)
    if "fixed" not in st.session_state:
        st.session_state.fixed = normalize_fixed(DEFAULT_FIXED)
    if "reimb" not in st.session_state:
        st.session_state.reimb = normalize_reimb(DEFAULT_REIMB)
    if "pay" not in st.session_state:
        st.session_state.pay = normalize_pay(DEFAULT_PAY)
    if "manual_usd_gbp" not in st.session_state:
        st.session_state.manual_usd_gbp = "0.80"

init_state()

# ============================
# Backup / Restore
# ============================
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
        z.writestr("fx_settings.csv", "manual_usd_gbp\n" + str(st.session_state.manual_usd_gbp) + "\n")
    buf.seek(0)
    return buf.read()

def load_backup_zip(zip_bytes: bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
        names = set(z.namelist())

        def read_df(name, default_df):
            if name in names:
                return pd.read_csv(z.open(name))
            return default_df.copy()

        st.session_state.assets = normalize_assets(read_df("assets.csv", DEFAULT_ASSETS))
        st.session_state.cards = normalize_cards(read_df("credit_cards.csv", DEFAULT_CARDS))
        st.session_state.fixed = normalize_fixed(read_df("fixed_costs.csv", DEFAULT_FIXED))
        st.session_state.reimb = normalize_reimb(read_df("reimbursements.csv", DEFAULT_REIMB))
        st.session_state.pay = normalize_pay(read_df("pay_cycle.csv", DEFAULT_PAY))

        if "fx_settings.csv" in names:
            fx_df = pd.read_csv(z.open("fx_settings.csv"))
            if "manual_usd_gbp" in fx_df.columns and len(fx_df) > 0:
                st.session_state.manual_usd_gbp = str(fx_df.loc[0, "manual_usd_gbp"])

# ============================
# Sidebar
# ============================
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
        st.session_state.assets = normalize_assets(DEFAULT_ASSETS)
        st.session_state.cards = normalize_cards(DEFAULT_CARDS)
        st.session_state.fixed = normalize_fixed(DEFAULT_FIXED)
        st.session_state.reimb = normalize_reimb(DEFAULT_REIMB)
        st.session_state.pay = normalize_pay(DEFAULT_PAY)
        st.session_state.manual_usd_gbp = "0.80"
        st.success("Reset done.")

# ============================
# FX (silent)
# ============================
try:
    usd_gbp = get_fx_rate("USD", "GBP")
    fx_source = "live"
except Exception:
    usd_gbp = parse_money_text(st.session_state.manual_usd_gbp)
    fx_source = "manual (live failed)"

# ============================
# Calculations
# ============================
assets_df = normalize_assets(st.session_state.assets)
cards_df = normalize_cards(st.session_state.cards)
fixed_df = normalize_fixed(st.session_state.fixed)
reimb_df = normalize_reimb(st.session_state.reimb)

def to_gbp(amount: float, currency: str) -> float:
    return amount * usd_gbp if str(currency).upper() == "USD" else amount

assets_df["balance_gbp"] = assets_df.apply(lambda r: to_gbp(r["balance"], r["currency"]), axis=1)
cards_df["balance_gbp"] = cards_df.apply(lambda r: to_gbp(r["balance"], r["currency"]), axis=1)
cards_df["due_gbp"] = cards_df.apply(lambda r: to_gbp(r["due_this_cycle"], r["currency"]), axis=1)

assets_total_gbp = float(assets_df["balance_gbp"].sum())
cards_total_balance_gbp = float(cards_df["balance_gbp"].sum())
cards_due_total_gbp = float(cards_df.loc[cards_df["is_due"] == True, "due_gbp"].sum())
fixed_total_gbp = float(fixed_df["amount"].sum())
fixed_due_total_gbp = float(fixed_df.loc[fixed_df["due"] == True, "amount"].sum())
reimb_included_total_gbp = float(reimb_df.loc[reimb_df["include_this_month"] == True, "amount"].sum())

net_cash_gbp = assets_total_gbp - cards_total_balance_gbp
total_spend_rest_gbp = fixed_due_total_gbp + cards_due_total_gbp

# ============================
# UI
# ============================
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
        normalize_assets(st.session_state.assets),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "account": st.column_config.TextColumn("Account"),
            "currency": st.column_config.SelectboxColumn("Currency", options=["GBP", "USD"]),
            "balance": st.column_config.NumberColumn("Balance (native)", format="%.2f", step=0.01),
        },
        key="assets_editor",
    )
    st.caption(f"Total Assets (GBP): {fmt_gbp(assets_total_gbp)}")

with c2:
    st.subheader("Credit Cards")
    st.session_state.cards = st.data_editor(
        normalize_cards(st.session_state.cards),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "card": st.column_config.TextColumn("Card"),
            "currency": st.column_config.SelectboxColumn("Currency", options=["GBP", "USD"]),
            "balance": st.column_config.NumberColumn("Balance (native)", format="%.2f", step=0.01),
            "due_this_cycle": st.column_config.NumberColumn("Due this cycle (native)", format="%.2f", step=0.01),
            "is_due": st.column_config.CheckboxColumn("Due?"),
        },
        key="cards_editor",
    )
    st.caption(
        f"Total Card Balances (GBP): {fmt_gbp(cards_total_balance_gbp)} · "
        f"Total Bills Due (GBP): {fmt_gbp(cards_due_total_gbp)}"
    )

with c3:
    st.subheader("Reimbursement Pending")
    st.session_state.reimb = st.data_editor(
        normalize_reimb(st.session_state.reimb),
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "source": st.column_config.TextColumn("Source"),
            "amount": st.column_config.NumberColumn("Amount (GBP)", format="%.2f", step=0.01),
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
        normalize_fixed(st.session_state.fixed),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "item": st.column_config.TextColumn("Item"),
            "amount": st.column_config.NumberColumn("Amount (GBP)", format="%.2f", step=0.01),
            "due": st.column_config.CheckboxColumn("Due?"),
        },
        key="fixed_editor",
    )
    st.caption(
        f"Fixed Monthly Total (GBP): {fmt_gbp(fixed_total_gbp)} · "
        f"Fixed Due (GBP): {fmt_gbp(fixed_due_total_gbp)}"
    )

with right:
    st.subheader("Pay Cycle (setup)")
    st.caption("Optional – for future projections.")
    st.session_state.pay = st.data_editor(
        normalize_pay(st.session_state.pay),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "person": st.column_config.TextColumn("Person"),
            "monthly_pay": st.column_config.NumberColumn("Monthly pay (£)", format="%.2f", step=0.01),
        },
        key="pay_editor",
    )

st.markdown("---")

# ============================
# FX Settings (BOTTOM)
# ============================
st.subheader("FX Settings (USD → GBP)")
st.caption("Used for Apple Card + Apple Savings. Live rate when available; fallback is manual.")
fx1, fx2 = st.columns([2, 1])
with fx1:
    st.write(f"**USD→GBP rate:** `{usd_gbp:.6f}`  _(source: {fx_source})_")
with fx2:
    st.session_state.manual_usd_gbp = st.text_input(
        "Manual USD→GBP (fallback)",
        value=str(st.session_state.manual_usd_gbp),
        key="manual_fx_input",
    )
