# app.py
# Stabler Family Finances — CSV-backed (download/restore ZIP) + live FX for USD -> GBP
# No Supabase. Data persists via downloaded ZIP backups you can restore anytime.

import io
import zipfile
from datetime import datetime
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Stabler Family Finances", layout="wide")

APP_TITLE = "Stabler Family Finances"

# -----------------------------
# Helpers
# -----------------------------
def _norm_currency(x) -> str:
    return str(x).strip().upper() if x is not None else "GBP"

def _coerce_money_series(s: pd.Series) -> pd.Series:
    # Handles "", None, "£1,234.50", "1,234.50", "1 234,50" (light cleanup), etc.
    s = s.astype(str)
    s = s.str.replace("£", "", regex=False).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(s, errors="coerce").fillna(0.0)

def _coerce_bool_series(s: pd.Series, default=False) -> pd.Series:
    if s is None:
        return pd.Series([default] * 0)
    if s.dtype == bool:
        return s.fillna(default)
    # Accept TRUE/FALSE, 1/0, yes/no
    ss = s.astype(str).str.strip().str.lower()
    return ss.isin(["true", "1", "yes", "y", "t"]).fillna(default)

@st.cache_data(ttl=60 * 30)  # 30 min
def fetch_usd_to_gbp() -> float | None:
    """
    Fetch USD->GBP. Returns None if unavailable.
    Uses a simple public endpoint. If it ever fails, you can still set manual FX below.
    """
    try:
        # exchangerate.host has been unreliable for some; this tends to be simple + stable:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        r.raise_for_status()
        data = r.json()
        rates = data.get("rates", {})
        gbp = rates.get("GBP")
        if gbp is None:
            return None
        return float(gbp)
    except Exception:
        return None

def convert_to_gbp(df: pd.DataFrame, currency_col: str, value_col: str, usd_to_gbp: float) -> pd.Series:
    cur = df[currency_col].astype(str).str.strip().str.upper()
    val = _coerce_money_series(df[value_col])
    fx = cur.map({"GBP": 1.0, "USD": float(usd_to_gbp)}).fillna(1.0)
    return val * fx

def fmt_gbp(x: float) -> str:
    try:
        return f"£{float(x):,.2f}"
    except Exception:
        return "£0.00"

# -----------------------------
# Default data
# -----------------------------
def default_assets() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Account": "HSBC", "Currency": "GBP", "Balance (native)": 0.0},
            {"Account": "Lloyds", "Currency": "GBP", "Balance (native)": 0.0},
            {"Account": "Apple Savings", "Currency": "USD", "Balance (native)": 0.0},
            {"Account": "Cash", "Currency": "GBP", "Balance (native)": 0.0},
        ]
    )

def default_credit_cards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Card": "Amex", "Currency": "GBP", "Balance (native)": 0.0, "Due this cycle (native)": 0.0, "Due?": False},
            {"Card": "Apple Card", "Currency": "USD", "Balance (native)": 0.0, "Due this cycle (native)": 0.0, "Due?": False},
        ]
    )

def default_reimbursements() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Source": "Eric Work", "Amount (GBP)": 0.0, "Include?": True},
            {"Source": "Gigi Work", "Amount (GBP)": 0.0, "Include?": True},
            {"Source": "Misc", "Amount (GBP)": 0.0, "Include?": False},
        ]
    )

def default_fixed_costs() -> pd.DataFrame:
    # From your screenshot
    rows = [
        ("Savings", 5000.00, True),
        ("RAC", 300.00, True),
        ("Car Loan", 480.37, True),
        ("Marchon", 133.10, True),
        ("Utilities", 425.00, True),
        ("Eric Vodafone", 38.00, True),
        ("Eric Haircut", 35.00, True),
        ("Eric iphone", 35.11, True),
        ("Cleaning", 72.00, True),
        ("Gigi Vodafone", 38.00, True),
        ("Gigi Gym", 79.00, True),
        ("Caroline Circuits", 35.00, True),
        ("Gigi Charity", 12.00, True),
        ("G+ E Contacts", 95.00, True),
    ]
    return pd.DataFrame([{"Item": i, "Amount (GBP)": a, "Due?": d} for i, a, d in rows])

def default_pay_cycle() -> pd.DataFrame:
    # Setup-only — optional
    return pd.DataFrame(
        [
            {"Person": "Eric", "Monthly pay (£)": 0.0},
            {"Person": "Gigi", "Monthly pay (£)": 0.0},
        ]
    )

# -----------------------------
# Session state init
# -----------------------------
def ensure_state():
    if "assets" not in st.session_state:
        st.session_state.assets = default_assets()
    if "cards" not in st.session_state:
        st.session_state.cards = default_credit_cards()
    if "reimb" not in st.session_state:
        st.session_state.reimb = default_reimbursements()
    if "fixed" not in st.session_state:
        st.session_state.fixed = default_fixed_costs()
    if "pay" not in st.session_state:
        st.session_state.pay = default_pay_cycle()

    # FX settings
    if "usd_to_gbp_manual" not in st.session_state:
        st.session_state.usd_to_gbp_manual = 0.79  # reasonable default
    if "use_live_fx" not in st.session_state:
        st.session_state.use_live_fx = True

ensure_state()

# -----------------------------
# Sidebar: Save/Load ZIP backup
# -----------------------------
with st.sidebar:
    st.subheader("Save / Load")

    def build_backup_zip_bytes() -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("assets.csv", st.session_state.assets.to_csv(index=False))
            z.writestr("credit_cards.csv", st.session_state.cards.to_csv(index=False))
            z.writestr("reimbursements.csv", st.session_state.reimb.to_csv(index=False))
            z.writestr("fixed_costs.csv", st.session_state.fixed.to_csv(index=False))
            z.writestr("pay_cycle.csv", st.session_state.pay.to_csv(index=False))
            meta = f"created_at={datetime.utcnow().isoformat()}Z\napp={APP_TITLE}\n"
            z.writestr("META.txt", meta)
        return buf.getvalue()

    backup_bytes = build_backup_zip_bytes()
    st.download_button(
        "⬇️ Download backup (ZIP)",
        data=backup_bytes,
        file_name="stabler-finances-backup.zip",
        mime="application/zip",
        use_container_width=True,
    )

    st.write("")
    uploaded = st.file_uploader("⬆️ Restore from backup (ZIP)", type=["zip"], accept_multiple_files=False)

    if uploaded is not None:
        try:
            zdata = uploaded.read()
            with zipfile.ZipFile(io.BytesIO(zdata), "r") as z:
                def read_csv(name: str) -> pd.DataFrame:
                    with z.open(name) as f:
                        return pd.read_csv(f)

                st.session_state.assets = read_csv("assets.csv")
                st.session_state.cards = read_csv("credit_cards.csv")
                st.session_state.reimb = read_csv("reimbursements.csv")
                st.session_state.fixed = read_csv("fixed_costs.csv")
                st.session_state.pay = read_csv("pay_cycle.csv")

            st.success("Backup restored.")
            st.rerun()
        except Exception as e:
            st.error("That ZIP didn’t restore cleanly. Make sure it’s the backup ZIP from this app.")
            st.code(str(e))

    st.write("")
    if st.button("Reset to defaults", use_container_width=True):
        st.session_state.assets = default_assets()
        st.session_state.cards = default_credit_cards()
        st.session_state.reimb = default_reimbursements()
        st.session_state.fixed = default_fixed_costs()
        st.session_state.pay = default_pay_cycle()
        st.session_state.use_live_fx = True
        st.session_state.usd_to_gbp_manual = 0.79
        st.rerun()

# -----------------------------
# FX (bottom, but needed for totals)
# -----------------------------
live_fx = fetch_usd_to_gbp() if st.session_state.use_live_fx else None
usd_to_gbp = live_fx if (live_fx is not None and st.session_state.use_live_fx) else float(st.session_state.usd_to_gbp_manual)

# -----------------------------
# Clean + coerce dataframes (prevents Streamlit schema errors / text numbers)
# -----------------------------
def sanitize_assets(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["Account", "Currency", "Balance (native)"]:
        if col not in df.columns:
            df[col] = "" if col in ["Account", "Currency"] else 0.0
    df["Currency"] = df["Currency"].map(_norm_currency)
    df["Balance (native)"] = _coerce_money_series(df["Balance (native)"])
    return df[["Account", "Currency", "Balance (native)"]]

def sanitize_cards(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["Card", "Currency", "Balance (native)", "Due this cycle (native)", "Due?"]:
        if col not in df.columns:
            df[col] = 0.0 if "native" in col else (False if col == "Due?" else "")
    df["Currency"] = df["Currency"].map(_norm_currency)
    df["Balance (native)"] = _coerce_money_series(df["Balance (native)"])
    df["Due this cycle (native)"] = _coerce_money_series(df["Due this cycle (native)"])
    df["Due?"] = _coerce_bool_series(df["Due?"], default=False)
    return df[["Card", "Currency", "Balance (native)", "Due this cycle (native)", "Due?"]]

def sanitize_reimb(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["Source", "Amount (GBP)", "Include?"]:
        if col not in df.columns:
            df[col] = 0.0 if col == "Amount (GBP)" else (False if col == "Include?" else "")
    df["Amount (GBP)"] = _coerce_money_series(df["Amount (GBP)"])
    df["Include?"] = _coerce_bool_series(df["Include?"], default=False)
    return df[["Source", "Amount (GBP)", "Include?"]]

def sanitize_fixed(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["Item", "Amount (GBP)", "Due?"]:
        if col not in df.columns:
            df[col] = 0.0 if col == "Amount (GBP)" else (False if col == "Due?" else "")
    df["Amount (GBP)"] = _coerce_money_series(df["Amount (GBP)"])
    df["Due?"] = _coerce_bool_series(df["Due?"], default=True)
    return df[["Item", "Amount (GBP)", "Due?"]]

def sanitize_pay(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["Person", "Monthly pay (£)"]:
        if col not in df.columns:
            df[col] = 0.0 if col == "Monthly pay (£)" else ""
    df["Monthly pay (£)"] = _coerce_money_series(df["Monthly pay (£)"])
    return df[["Person", "Monthly pay (£)"]]

st.session_state.assets = sanitize_assets(st.session_state.assets)
st.session_state.cards = sanitize_cards(st.session_state.cards)
st.session_state.reimb = sanitize_reimb(st.session_state.reimb)
st.session_state.fixed = sanitize_fixed(st.session_state.fixed)
st.session_state.pay = sanitize_pay(st.session_state.pay)

# -----------------------------
# Calculations (GBP)
# -----------------------------
assets_gbp = convert_to_gbp(st.session_state.assets, "Currency", "Balance (native)", usd_to_gbp)
total_assets_gbp = float(assets_gbp.sum())

card_bal_gbp = convert_to_gbp(st.session_state.cards, "Currency", "Balance (native)", usd_to_gbp)
total_card_bal_gbp = float(card_bal_gbp.sum())

card_due_gbp = convert_to_gbp(st.session_state.cards, "Currency", "Due this cycle (native)", usd_to_gbp)
total_card_bill_due_gbp = float(card_due_gbp[st.session_state.cards["Due?"] == True].sum())

reimb_included_gbp = float(st.session_state.reimb.loc[st.session_state.reimb["Include?"] == True, "Amount (GBP)"].sum())

fixed_due_gbp = float(st.session_state.fixed.loc[st.session_state.fixed["Due?"] == True, "Amount (GBP)"].sum())

# Your top-line metrics
net_cash_gbp = total_assets_gbp - total_card_bal_gbp + reimb_included_gbp
total_spend_rest_month_gbp = fixed_due_gbp + total_card_bill_due_gbp  # simple + consistent

# -----------------------------
# UI
# -----------------------------
st.title(APP_TITLE)

# TOP METRICS (at top of sheet)
m1, m2, m3 = st.columns(3)
with m1:
    st.metric("Net Cash (GBP)", fmt_gbp(net_cash_gbp))
with m2:
    st.metric("Total Credit Card Bill Due (GBP)", fmt_gbp(total_card_bill_due_gbp))
with m3:
    st.metric("Total Spend Rest of Month (GBP)", fmt_gbp(total_spend_rest_month_gbp))

st.divider()

# TOP ROW: Assets, Credit Cards, Reimbursement Pending
c_assets, c_cards, c_reimb = st.columns(3)

with c_assets:
    st.subheader("Assets")

    assets_edit = st.data_editor(
        st.session_state.assets,
        num_rows="dynamic",
        use_container_width=True,
        key="assets_editor",
        column_config={
            "Account": st.column_config.TextColumn("Account"),
            "Currency": st.column_config.SelectboxColumn("Currency", options=["GBP", "USD"]),
            "Balance (native)": st.column_config.NumberColumn("Balance (native)", format="%.2f", step=0.01),
        },
    )
    st.session_state.assets = sanitize_assets(assets_edit)

    # totals under each
    assets_gbp2 = convert_to_gbp(st.session_state.assets, "Currency", "Balance (native)", usd_to_gbp)
    st.caption(f"Total Assets (GBP): {fmt_gbp(float(assets_gbp2.sum()))}")

with c_cards:
    st.subheader("Credit Cards")

    cards_edit = st.data_editor(
        st.session_state.cards,
        num_rows="dynamic",
        use_container_width=True,
        key="cards_editor",
        column_config={
            "Card": st.column_config.TextColumn("Card"),
            "Currency": st.column_config.SelectboxColumn("Currency", options=["GBP", "USD"]),
            "Balance (native)": st.column_config.NumberColumn("Balance (native)", format="%.2f", step=0.01),
            "Due this cycle (native)": st.column_config.NumberColumn("Due this cycle (native)", format="%.2f", step=0.01),
            "Due?": st.column_config.CheckboxColumn("Due?"),
        },
    )
    st.session_state.cards = sanitize_cards(cards_edit)

    card_bal_gbp2 = convert_to_gbp(st.session_state.cards, "Currency", "Balance (native)", usd_to_gbp)
    card_due_gbp2 = convert_to_gbp(st.session_state.cards, "Currency", "Due this cycle (native)", usd_to_gbp)
    total_bal = float(card_bal_gbp2.sum())
    total_due = float(card_due_gbp2[st.session_state.cards["Due?"] == True].sum())
    st.caption(f"Total Card Balances (GBP): {fmt_gbp(total_bal)} · Total Bills Due (GBP): {fmt_gbp(total_due)}")

with c_reimb:
    st.subheader("Reimbursement Pending")

    reimb_edit = st.data_editor(
        st.session_state.reimb,
        num_rows="dynamic",
        use_container_width=True,
        key="reimb_editor",
        column_config={
            "Source": st.column_config.TextColumn("Source"),
            "Amount (GBP)": st.column_config.NumberColumn("Amount (GBP)", format="%.2f", step=0.01),
            "Include?": st.column_config.CheckboxColumn("Include?"),
        },
    )
    st.session_state.reimb = sanitize_reimb(reimb_edit)

    included = float(st.session_state.reimb.loc[st.session_state.reimb["Include?"] == True, "Amount (GBP)"].sum())
    st.caption(f"Included Reimbursements (GBP): {fmt_gbp(included)}")

st.divider()

# SECOND ROW: Monthly Fixed (LEFT) + Pay Cycle (RIGHT)
left, right = st.columns([2, 1])

with left:
    st.subheader("Monthly Fixed")

    fixed_edit = st.data_editor(
        st.session_state.fixed,
        num_rows="dynamic",
        use_container_width=True,
        key="fixed_editor",
        column_config={
            "Item": st.column_config.TextColumn("Item"),
            "Amount (GBP)": st.column_config.NumberColumn("Amount (GBP)", format="%.2f", step=0.01),
            "Due?": st.column_config.CheckboxColumn("Due?"),
        },
    )
    st.session_state.fixed = sanitize_fixed(fixed_edit)

    fixed_due2 = float(st.session_state.fixed.loc[st.session_state.fixed["Due?"] == True, "Amount (GBP)"].sum())
    fixed_all2 = float(st.session_state.fixed["Amount (GBP)"].sum())
    st.caption(f"Fixed due (GBP): {fmt_gbp(fixed_due2)} · Fixed total (GBP): {fmt_gbp(fixed_all2)}")

with right:
    st.subheader("Pay Cycle (setup)")
    st.caption("Optional — for future projections.")
    pay_edit = st.data_editor(
        st.session_state.pay,
        num_rows="dynamic",
        use_container_width=True,
        key="pay_editor",
        column_config={
            "Person": st.column_config.TextColumn("Person"),
            "Monthly pay (£)": st.column_config.NumberColumn("Monthly pay (£)", format="%.2f", step=0.01),
        },
    )
    st.session_state.pay = sanitize_pay(pay_edit)

st.divider()

# FX SECTION (BOTTOM) — requested
st.subheader("FX (USD → GBP)")

fx_left, fx_right = st.columns([2, 1])

with fx_left:
    st.toggle("Use live FX (updates every ~30 min)", key="use_live_fx")
    if st.session_state.use_live_fx and live_fx is None:
        st.warning("Live FX fetch failed right now. Using manual rate until it’s back.")
    st.number_input("Manual USD→GBP rate", min_value=0.0, max_value=5.0, step=0.01, key="usd_to_gbp_manual")
    st.caption(f"Using USD→GBP rate: **{usd_to_gbp:.6f}**")

with fx_right:
    if st.button("Refresh FX now", use_container_width=True):
        fetch_usd_to_gbp.clear()
        st.rerun()

st.caption(
    "USD accounts/cards (e.g. Apple Savings, Apple Card) are converted to GBP using the USD→GBP rate above. "
    "Totals everywhere are shown in GBP."
)
