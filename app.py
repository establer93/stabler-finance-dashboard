import io
import json
import zipfile
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Stabler Family Finances", layout="wide")

SCHEMA_VERSION = "2026-02-21-stabler-finances-v6-pay-flipped"

GBP = "GBP"
USD = "USD"
CURRENCY_SYMBOL = {GBP: "£", USD: "$"}

# ------------------------
# Styling
# ------------------------
st.markdown(
    """
<style>
.kpi { padding: 6px 2px 18px 2px; }
.kpi .label { font-size: 14px; opacity: 0.75; margin-bottom: 6px; }
.kpi .value { font-size: 44px; font-weight: 700; line-height: 1.0; }
.kpi .pos { color: #2ECC71; }
.kpi .neg { color: #FF4B4B; }
.kpi .neu { color: rgba(255,255,255,0.85); }

.totals { opacity: 0.75; font-size: 13px; margin-top: 6px; }
.totals .pos { color: #2ECC71; font-weight: 650; }
.totals .neg { color: #FF4B4B; font-weight: 650; }
.totals .neu { color: rgba(255,255,255,0.90); font-weight: 650; }

.badge {
  display:inline-block; padding:2px 8px; border-radius:12px;
  font-size:12px; opacity:0.9; border:1px solid rgba(255,255,255,0.15);
}
.badge-ok { background: rgba(46, 204, 113, 0.15); }
.badge-warn { background: rgba(255, 75, 75, 0.15); }
.badge-neutral { background: rgba(255,255,255,0.08); }
</style>
""",
    unsafe_allow_html=True,
)

st.title("Stabler Family Finances")

# ------------------------
# Helpers
# ------------------------
def current_month():
    return datetime.now().strftime("%Y-%m")

def month_options():
    now = datetime.now()
    years = range(now.year - 2, now.year + 3)
    opts = [""]
    for y in years:
        for m in range(1, 13):
            opts.append(f"{y}-{m:02d}")
    return opts

def parse_money(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("£","").replace("$","").replace(",","").strip()
    try:
        return float(s)
    except:
        return 0.0

def fmt_money(v, cur):
    return f"{CURRENCY_SYMBOL[cur]}{float(v):,.2f}"

def cls(x):
    if x > 0:
        return "pos"
    if x < 0:
        return "neg"
    return "neu"

def kpi(label, value):
    st.markdown(
        f"""
<div class="kpi">
  <div class="label">{label}</div>
  <div class="value {cls(value)}">{fmt_money(value, GBP)}</div>
</div>
""",
        unsafe_allow_html=True,
    )

# ------------------------
# Defaults
# ------------------------
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
            {"Item": "Savings", "Amount": 5000.0, "Due?": True},
        ]),
        "pay": pd.DataFrame([
            {"Person": "Eric", "Monthly Pay": 6100.0, "Paid?": False},
            {"Person": "Gigi", "Monthly Pay": 6000.0, "Paid?": False},
        ]),
        "rac": pd.DataFrame(columns=["Purchase","Amount","Month"]),
    }

if "app_state" not in st.session_state:
    st.session_state.app_state = default_state()

state = st.session_state.app_state

# ------------------------
# Calculations
# ------------------------
THIS_MONTH = current_month()

assets_total = sum(parse_money(r["Balance"]) if r["Currency"]==GBP else parse_money(r["Balance"])*0.8
                   for _,r in state["assets"].iterrows())

cards_total = sum(parse_money(r["Balance"]) if r["Currency"]==GBP else parse_money(r["Balance"])*0.8
                  for _,r in state["credit_cards"].iterrows())

cards_due = sum(parse_money(r["Balance Due"]) if r["Currency"]==GBP else parse_money(r["Balance Due"])*0.8
                for _,r in state["credit_cards"].iterrows())

reim_total = state["reimbursements"].loc[state["reimbursements"]["Include?"]==True,"Amount"].apply(parse_money).sum()

fixed_total = state["fixed"].loc[state["fixed"]["Due?"]==True,"Amount"].apply(parse_money).sum()

# FLIPPED LOGIC
pay_total = state["pay"].loc[state["pay"]["Paid?"]==False,"Monthly Pay"].apply(parse_money).sum()

rac_month_total = state["rac"].loc[state["rac"]["Month"]==THIS_MONTH,"Amount"].apply(parse_money).sum()

net_cash = assets_total + reim_total - cards_total - rac_month_total
remaining = net_cash + (pay_total - fixed_total)

ability = assets_total >= cards_due

# ------------------------
# KPIs
# ------------------------
c1,c2,c3 = st.columns(3)
with c1: kpi("Net Cash (GBP)", net_cash)
with c2: kpi("Total Credit Card Bill Due (GBP)", cards_due)
with c3: kpi("Remaining spending this month (GBP)", remaining)

st.divider()

# ------------------------
# RAC Section
# ------------------------
st.subheader("RAC monthly bill")

rac_edit = state["rac"].copy()
rac_edit["Amount"] = rac_edit["Amount"].apply(lambda v: fmt_money(parse_money(v), GBP))

edited_rac = st.data_editor(
    rac_edit,
    hide_index=True,   # removed number column
    num_rows="dynamic",
    column_config={
        "Purchase": st.column_config.TextColumn("Purchase"),
        "Amount": st.column_config.TextColumn("Amount"),
        "Month": st.column_config.SelectboxColumn("Month", options=month_options()),
    },
)

if st.button("Apply RAC Changes"):
    new = edited_rac.copy()
    new["Amount"] = new["Amount"].apply(parse_money)
    new.loc[new["Month"]=="","Month"] = THIS_MONTH
    state["rac"] = new
    st.rerun()

st.write(f"RAC due this month: {fmt_money(rac_month_total,GBP)}")

st.divider()

# ------------------------
# Pay Section
# ------------------------
st.subheader("Monthly Pay")
st.caption("Unticked salaries are included in projection. Tick once received to exclude from forward budget.")

pay_edit = state["pay"].copy()
pay_edit["Monthly Pay"] = pay_edit["Monthly Pay"].apply(lambda v: fmt_money(parse_money(v), GBP))

edited_pay = st.data_editor(
    pay_edit,
    hide_index=True,
    num_rows="fixed"
)

if st.button("Apply Pay Changes"):
    new = edited_pay.copy()
    new["Monthly Pay"] = new["Monthly Pay"].apply(parse_money)
    state["pay"] = new
    st.rerun()
