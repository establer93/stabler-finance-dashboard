import io
import json
import zipfile
from datetime import datetime
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Stabler Family Finances", layout="wide")

GBP = "GBP"
USD = "USD"

CURRENCY_SYMBOL = {GBP: "£", USD: "$"}


# =========================
# Utility Functions
# =========================

def parse_money(value):
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if s == "":
        return 0.0

    s = (
        s.replace("£", "")
        .replace("$", "")
        .replace(",", "")
        .replace(" ", "")
        .replace("\u00A0", "")
    )

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]

    try:
        v = float(s)
        return -v if negative else v
    except:
        return 0.0


def fmt_money(amount, currency):
    symbol = CURRENCY_SYMBOL.get(currency, "")
    return f"{symbol}{amount:,.2f}"


def get_fx_rate():
    if "fx_rate" not in st.session_state:
        st.session_state.fx_rate = 0.79
        st.session_state.fx_source = "fallback"

    try:
        r = requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "USD", "symbols": "GBP"},
            timeout=5,
        )
        r.raise_for_status()
        rate = float(r.json()["rates"]["GBP"])
        st.session_state.fx_rate = rate
        st.session_state.fx_source = "exchangerate.host"
    except:
        pass

    return st.session_state.fx_rate, st.session_state.fx_source


def to_gbp(amount, currency, fx):
    if currency == GBP:
        return amount
    if currency == USD:
        return amount * fx
    return amount


# =========================
# Default State
# =========================

def default_state():
    return {
        "assets": pd.DataFrame([
            {"Account": "HSBC", "Currency": GBP, "Balance": 0.0},
            {"Account": "Lloyds", "Currency": GBP, "Balance": 0.0},
            {"Account": "Apple Savings", "Currency": USD, "Balance": 0.0},
        ]),
        "credit_cards": pd.DataFrame([
            {"Card": "Amex", "Currency": GBP, "Balance": 0.0, "Balance Due": 0.0},
            {"Card": "Apple Card", "Currency": USD, "Balance": 0.0, "Balance Due": 0.0},
            {"Card": "Lloyds", "Currency": GBP, "Balance": 0.0, "Balance Due": 0.0},
        ]),
        "reimbursements": pd.DataFrame([
            {"Source": "Eric Work", "Amount": 0.0, "Include?": True},
            {"Source": "Gigi Work", "Amount": 0.0, "Include?": True},
            {"Source": "Misc", "Amount": 0.0, "Include?": False},
        ]),
        "fixed": pd.DataFrame([
            {"Item": "Savings", "Amount": 5000.00, "Due?": True},
            {"Item": "RAC", "Amount": 300.00, "Due?": True},
            {"Item": "Car Loan", "Amount": 480.37, "Due?": True},
            {"Item": "Utilities", "Amount": 425.00, "Due?": True},
        ]),
        "pay": pd.DataFrame([
            {"Person": "Eric", "Monthly Pay": 6100.00, "Paid?": False},
            {"Person": "Gigi", "Monthly Pay": 6000.00, "Paid?": False},
        ])
    }


if "app_state" not in st.session_state:
    st.session_state.app_state = default_state()


# =========================
# Backup / Restore ZIP
# =========================

def state_to_zip(state):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, df in state.items():
            z.writestr(f"{name}.csv", df.to_csv(index=False))
        z.writestr("meta.json", json.dumps({
            "saved_at": datetime.utcnow().isoformat()
        }))
    return buffer.getvalue()


def load_zip(uploaded):
    try:
        with zipfile.ZipFile(uploaded, "r") as z:
            new_state = {}
            for key in ["assets", "credit_cards", "reimbursements", "fixed", "pay"]:
                new_state[key] = pd.read_csv(z.open(f"{key}.csv"))
            return new_state
    except:
        return None


# =========================
# Sidebar
# =========================

with st.sidebar:
    st.subheader("Save / Load")

    zip_bytes = state_to_zip(st.session_state.app_state)

    st.download_button(
        "⬇️ Download Backup (ZIP)",
        zip_bytes,
        "stabler-finances-backup.zip",
        "application/zip",
        use_container_width=True
    )

    uploaded = st.file_uploader("Restore from ZIP", type=["zip"])
    if uploaded:
        new_state = load_zip(uploaded)
        if new_state:
            st.session_state.app_state = new_state
            st.success("Backup restored.")
            st.rerun()
        else:
            st.error("Invalid backup file.")

    if st.button("Reset to Defaults", use_container_width=True):
        st.session_state.app_state = default_state()
        st.rerun()


# =========================
# FX
# =========================

fx_rate, fx_source = get_fx_rate()

# =========================
# Load Data
# =========================

assets_df = st.session_state.app_state["assets"]
cards_df = st.session_state.app_state["credit_cards"]
reimb_df = st.session_state.app_state["reimbursements"]
fixed_df = st.session_state.app_state["fixed"]
pay_df = st.session_state.app_state["pay"]

# =========================
# Calculations
# =========================

assets_total_gbp = sum(
    to_gbp(parse_money(r["Balance"]), r["Currency"], fx_rate)
    for _, r in assets_df.iterrows()
)

cards_balance_total_gbp = sum(
    to_gbp(parse_money(r["Balance"]), r["Currency"], fx_rate)
    for _, r in cards_df.iterrows()
)

cards_due_total_gbp = sum(
    to_gbp(parse_money(r["Balance Due"]), r["Currency"], fx_rate)
    for _, r in cards_df.iterrows()
)

included_reimb_gbp = reimb_df[reimb_df["Include?"]]["Amount"].apply(parse_money).sum()

net_cash_gbp = assets_total_gbp + included_reimb_gbp - cards_balance_total_gbp

fixed_due_gbp = fixed_df[fixed_df["Due?"]]["Amount"].apply(parse_money).sum()

paid_income_gbp = pay_df[pay_df["Paid?"]]["Monthly Pay"].apply(parse_money).sum()

remaining_spend_gbp = net_cash_gbp + (paid_income_gbp - fixed_due_gbp)

ability_to_repay = assets_total_gbp >= cards_due_total_gbp

# =========================
# Top KPIs
# =========================

c1, c2, c3 = st.columns(3)

with c1:
    st.metric("Net Cash (GBP)", fmt_money(net_cash_gbp, GBP))

with c2:
    st.metric("Total Credit Card Bill Due (GBP)", fmt_money(cards_due_total_gbp, GBP))
    st.caption(f"Ability to repay: {'Yes' if ability_to_repay else 'No'}")

with c3:
    st.metric("Remaining spending this month (GBP)", fmt_money(remaining_spend_gbp, GBP))

st.divider()

# =========================
# Tables
# =========================

col1, col2, col3 = st.columns(3)

# Assets
with col1:
    st.subheader("Assets")

    edit = assets_df.copy()
    edit["Balance"] = edit.apply(lambda r: fmt_money(parse_money(r["Balance"]), r["Currency"]), axis=1)

    edited = st.data_editor(
        edit[["Account", "Currency", "Balance"]],
        hide_index=True,
        num_rows="fixed",
        key="assets_editor"
    )

    if st.button("Apply Assets Changes"):
        assets_df["Balance"] = edited["Balance"].apply(parse_money)
        st.session_state.app_state["assets"] = assets_df
        st.rerun()

# Credit Cards
with col2:
    st.subheader("Credit Cards")

    edit = cards_df.copy()
    edit["Balance"] = edit.apply(lambda r: fmt_money(parse_money(r["Balance"]), r["Currency"]), axis=1)
    edit["Balance Due"] = edit.apply(lambda r: fmt_money(parse_money(r["Balance Due"]), r["Currency"]), axis=1)

    edited = st.data_editor(
        edit[["Card", "Balance", "Balance Due"]],
        hide_index=True,
        num_rows="fixed",
        key="cards_editor"
    )

    if st.button("Apply Credit Card Changes"):
        cards_df["Balance"] = edited["Balance"].apply(parse_money)
        cards_df["Balance Due"] = edited["Balance Due"].apply(parse_money)
        st.session_state.app_state["credit_cards"] = cards_df
        st.rerun()

# Reimbursements
with col3:
    st.subheader("Reimbursement Pending")

    edit = reimb_df.copy()
    edit["Amount"] = edit["Amount"].apply(lambda v: fmt_money(parse_money(v), GBP))

    edited = st.data_editor(
        edit,
        hide_index=True,
        num_rows="fixed",
        key="reimb_editor"
    )

    if st.button("Apply Reimbursement Changes"):
        reimb_df["Amount"] = edited["Amount"].apply(parse_money)
        reimb_df["Include?"] = edited["Include?"]
        st.session_state.app_state["reimbursements"] = reimb_df
        st.rerun()

st.divider()

# Monthly Fixed
st.subheader("Monthly Fixed")

fixed_edit = fixed_df.copy()
fixed_edit["Amount"] = fixed_edit["Amount"].apply(lambda v: fmt_money(parse_money(v), GBP))

edited_fixed = st.data_editor(
    fixed_edit,
    hide_index=True,
    key="fixed_editor"
)

if st.button("Apply Monthly Fixed Changes"):
    fixed_df["Amount"] = edited_fixed["Amount"].apply(parse_money)
    fixed_df["Due?"] = edited_fixed["Due?"]
    st.session_state.app_state["fixed"] = fixed_df
    st.rerun()

st.divider()

# Pay Cycle
st.subheader("Pay Cycle (setup)")

pay_edit = pay_df.copy()
pay_edit["Monthly Pay"] = pay_edit["Monthly Pay"].apply(lambda v: fmt_money(parse_money(v), GBP))

edited_pay = st.data_editor(
    pay_edit,
    hide_index=True,
    key="pay_editor"
)

if st.button("Apply Pay Changes"):
    pay_df["Monthly Pay"] = edited_pay["Monthly Pay"].apply(parse_money)
    pay_df["Paid?"] = edited_pay["Paid?"]
    st.session_state.app_state["pay"] = pay_df
    st.rerun()

st.divider()

st.subheader("FX (USD → GBP)")
st.write(f"Rate used: **{fx_rate:.6f}** (source: {fx_source})")
if st.button("Refresh FX Rate"):
    if "fx_rate" in st.session_state:
        del st.session_state["fx_rate"]
    st.rerun()
