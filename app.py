import io
import zipfile
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Stabler Family Finances", layout="wide")

# ------------------------
# Styling (colours)
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

.totals { opacity: 0.75; font-size: 13px; }
.totals .pos { color: #2ECC71; font-weight: 650; }
.totals .neg { color: #FF4B4B; font-weight: 650; }
.totals .neu { color: rgba(255,255,255,0.90); font-weight: 650; }

div[data-testid="stSidebar"] .stButton button,
div[data-testid="stSidebar"] .stDownloadButton button {
    width: 100%;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("Stabler Family Finances")

# ------------------------
# Helpers
# ------------------------
def _to_float(s: pd.Series) -> pd.Series:
    s = s.astype(str)
    s = (
        s.str.replace("£", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("—", "", regex=False)
        .str.replace("None", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(s, errors="coerce").fillna(0.0)

def gbp(x: float) -> str:
    return f"£{float(x):,.2f}"

def cls(x: float) -> str:
    x = float(x)
    if x > 0:
        return "pos"
    if x < 0:
        return "neg"
    return "neu"

def kpi(label: str, value: float, force_neutral: bool = False):
    css = "neu" if force_neutral else cls(value)
    st.markdown(
        f"""
<div class="kpi">
  <div class="label">{label}</div>
  <div class="value {css}">{gbp(value)}</div>
</div>
""",
        unsafe_allow_html=True,
    )

def totals_line(label: str, value: float):
    st.markdown(
        f"""<div class="totals">{label} <span class="{cls(value)}">{gbp(value)}</span></div>""",
        unsafe_allow_html=True,
    )

def is_usd_item(name: str) -> bool:
    if not isinstance(name, str):
        return False
    n = name.lower()
    return ("apple card" in n) or ("apple savings" in n)

@st.cache_data(ttl=1800)
def usd_to_gbp_live():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        j = r.json()
        return float(j["rates"]["GBP"]), j.get("time_last_update_utc")
    except Exception:
        return None, None

def to_gbp(amount_native: float, is_usd: bool, rate: float) -> float:
    return float(amount_native) * float(rate) if is_usd else float(amount_native)

def _clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _coerce_bool_col(s: pd.Series, default=False) -> pd.Series:
    if s is None:
        return pd.Series([], dtype=bool)
    if s.dtype == bool:
        return s.fillna(default)
    ss = s.astype(str).str.strip().str.lower()
    return ss.isin(["true", "1", "yes", "y", "t", "checked"]).fillna(default)

# ------------------------
# Normalizers (backward compatible)
# ------------------------
def normalize_assets(df: pd.DataFrame) -> pd.DataFrame:
    df = _clean_cols(df)
    if "Account" not in df.columns: df["Account"] = ""
    if "Currency" not in df.columns: df["Currency"] = "GBP"
    if "Balance (native)" not in df.columns:
        for a in ["Balance", "balance", "Amount", "amount", "Value", "value"]:
            if a in df.columns:
                df = df.rename(columns={a: "Balance (native)"})
                break
        if "Balance (native)" not in df.columns:
            df["Balance (native)"] = 0.0
    df["Currency"] = df["Currency"].astype(str).str.strip().str.upper()
    df["Balance (native)"] = _to_float(df["Balance (native)"])
    return df[["Account", "Currency", "Balance (native)"]]

def normalize_cards(df: pd.DataFrame) -> pd.DataFrame:
    df = _clean_cols(df)

    rename_map = {}
    if "Card" not in df.columns:
        for a in ["card", "Name", "name"]:
            if a in df.columns:
                rename_map[a] = "Card"
                break

    if "Balance (native)" not in df.columns:
        for a in ["Balance", "balance", "Amount", "amount", "Value", "value"]:
            if a in df.columns:
                rename_map[a] = "Balance (native)"
                break

    if "Balance Due (native)" not in df.columns:
        if "Due this cycle (native)" in df.columns:
            rename_map["Due this cycle (native)"] = "Balance Due (native)"
        else:
            for a in ["Balance Due", "balance due", "Due", "due", "due_this_cycle"]:
                if a in df.columns:
                    rename_map[a] = "Balance Due (native)"
                    break

    if rename_map:
        df = df.rename(columns=rename_map)

    if "Card" not in df.columns:
        df["Card"] = ""
    if "Balance (native)" not in df.columns:
        df["Balance (native)"] = 0.0
    if "Balance Due (native)" not in df.columns:
        df["Balance Due (native)"] = 0.0

    df["Balance (native)"] = _to_float(df["Balance (native)"])
    df["Balance Due (native)"] = _to_float(df["Balance Due (native)"])

    return df[["Card", "Balance (native)", "Balance Due (native)"]]

def normalize_reim(df: pd.DataFrame) -> pd.DataFrame:
    df = _clean_cols(df)
    if "Source" not in df.columns: df["Source"] = ""
    if "Amount (GBP)" not in df.columns:
        for a in ["Amount", "amount", "Value", "value"]:
            if a in df.columns:
                df = df.rename(columns={a: "Amount (GBP)"})
                break
        if "Amount (GBP)" not in df.columns:
            df["Amount (GBP)"] = 0.0
    if "Include?" not in df.columns:
        df["Include?"] = False
    df["Amount (GBP)"] = _to_float(df["Amount (GBP)"])
    df["Include?"] = _coerce_bool_col(df["Include?"], default=False)
    return df[["Source", "Amount (GBP)", "Include?"]]

def normalize_fixed(df: pd.DataFrame) -> pd.DataFrame:
    df = _clean_cols(df)
    if "Item" not in df.columns: df["Item"] = ""
    if "Amount (GBP)" not in df.columns:
        for a in ["Amount", "amount", "Value", "value"]:
            if a in df.columns:
                df = df.rename(columns={a: "Amount (GBP)"})
                break
        if "Amount (GBP)" not in df.columns:
            df["Amount (GBP)"] = 0.0
    if "Due?" not in df.columns:
        df["Due?"] = True
    df["Amount (GBP)"] = _to_float(df["Amount (GBP)"])
    df["Due?"] = _coerce_bool_col(df["Due?"], default=True)
    return df[["Item", "Amount (GBP)", "Due?"]]

def normalize_pay(df: pd.DataFrame) -> pd.DataFrame:
    """
    New schema:
      Person | Monthly Pay (GBP) | Paid?
    Backward compatible:
      - If old column Monthly pay (£) exists, rename
      - If Paid? missing, default False
    """
    df = _clean_cols(df)

    # rename old monthly pay col -> new
    if "Monthly Pay (GBP)" not in df.columns:
        if "Monthly pay (£)" in df.columns:
            df = df.rename(columns={"Monthly pay (£)": "Monthly Pay (GBP)"})
        else:
            for a in ["Monthly pay", "Pay", "pay", "Amount", "amount", "salary"]:
                if a in df.columns:
                    df = df.rename(columns={a: "Monthly Pay (GBP)"})
                    break

    if "Person" not in df.columns:
        df["Person"] = ""

    if "Monthly Pay (GBP)" not in df.columns:
        df["Monthly Pay (GBP)"] = 0.0

    if "Paid?" not in df.columns:
        # old schemas sometimes had 'Paid' / 'paid'
        if "Paid" in df.columns:
            df = df.rename(columns={"Paid": "Paid?"})
        elif "paid" in df.columns:
            df = df.rename(columns={"paid": "Paid?"})
        else:
            df["Paid?"] = False

    df["Monthly Pay (GBP)"] = _to_float(df["Monthly Pay (GBP)"])
    df["Paid?"] = _coerce_bool_col(df["Paid?"], default=False)

    return df[["Person", "Monthly Pay (GBP)", "Paid?"]]

# ------------------------
# Defaults
# ------------------------
def defaults_assets():
    return pd.DataFrame(
        [
            {"Account": "HSBC", "Currency": "GBP", "Balance (native)": 0.0},
            {"Account": "Lloyds", "Currency": "GBP", "Balance (native)": 0.0},
            {"Account": "Apple Savings", "Currency": "USD", "Balance (native)": 0.0},
            {"Account": "Cash", "Currency": "GBP", "Balance (native)": 0.0},
        ]
    )

def defaults_cards():
    return pd.DataFrame(
        [
            {"Card": "Amex", "Balance (native)": 0.0, "Balance Due (native)": 0.0},
            {"Card": "Apple Card", "Balance (native)": 0.0, "Balance Due (native)": 0.0},
        ]
    )

def defaults_reim():
    return pd.DataFrame(
        [
            {"Source": "Eric Work", "Amount (GBP)": 0.0, "Include?": True},
            {"Source": "Gigi Work", "Amount (GBP)": 0.0, "Include?": True},
            {"Source": "Misc", "Amount (GBP)": 0.0, "Include?": False},
        ]
    )

def defaults_fixed():
    return pd.DataFrame(
        [
            {"Item": "Savings", "Amount (GBP)": 5000.00, "Due?": True},
            {"Item": "RAC", "Amount (GBP)": 300.00, "Due?": True},
            {"Item": "Car Loan", "Amount (GBP)": 480.37, "Due?": True},
            {"Item": "Marchon", "Amount (GBP)": 133.10, "Due?": True},
            {"Item": "Utilities", "Amount (GBP)": 425.00, "Due?": True},
            {"Item": "Eric Vodafone", "Amount (GBP)": 38.00, "Due?": True},
            {"Item": "Eric Haircut", "Amount (GBP)": 35.00, "Due?": True},
            {"Item": "Eric iphone", "Amount (GBP)": 35.11, "Due?": True},
            {"Item": "Cleaning", "Amount (GBP)": 72.00, "Due?": True},
            {"Item": "Gigi Vodafone", "Amount (GBP)": 38.00, "Due?": True},
            {"Item": "Gigi Gym", "Amount (GBP)": 79.00, "Due?": True},
            {"Item": "Caroline Circuits", "Amount (GBP)": 35.00, "Due?": True},
            {"Item": "Gigi Charity", "Amount (GBP)": 12.00, "Due?": True},
            {"Item": "G+ E Contacts", "Amount (GBP)": 95.00, "Due?": True},
        ]
    )

def defaults_pay():
    # Requested defaults: Eric 6100, Gigi 6000
    return pd.DataFrame(
        [
            {"Person": "Eric", "Monthly Pay (GBP)": 6100.0, "Paid?": False},
            {"Person": "Gigi", "Monthly Pay (GBP)": 6000.0, "Paid?": False},
        ]
    )

# ------------------------
# State init (always normalized)
# ------------------------
if "assets" not in st.session_state:
    st.session_state.assets = defaults_assets()
if "cards" not in st.session_state:
    st.session_state.cards = defaults_cards()
if "reim" not in st.session_state:
    st.session_state.reim = defaults_reim()
if "fixed" not in st.session_state:
    st.session_state.fixed = defaults_fixed()
if "pay" not in st.session_state:
    st.session_state.pay = defaults_pay()
if "fx_override_on" not in st.session_state:
    st.session_state.fx_override_on = False
if "fx_override_rate" not in st.session_state:
    st.session_state.fx_override_rate = 0.80

st.session_state.assets = normalize_assets(st.session_state.assets)
st.session_state.cards = normalize_cards(st.session_state.cards)
st.session_state.reim = normalize_reim(st.session_state.reim)
st.session_state.fixed = normalize_fixed(st.session_state.fixed)
st.session_state.pay = normalize_pay(st.session_state.pay)

# ------------------------
# Backup ZIP
# ------------------------
def make_zip() -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("assets.csv", st.session_state.assets.to_csv(index=False))
        z.writestr("credit_cards.csv", st.session_state.cards.to_csv(index=False))
        z.writestr("reimbursements.csv", st.session_state.reim.to_csv(index=False))
        z.writestr("fixed_costs.csv", st.session_state.fixed.to_csv(index=False))
        z.writestr("pay_cycle.csv", st.session_state.pay.to_csv(index=False))
        meta = pd.DataFrame([{
            "saved_at": datetime.utcnow().isoformat() + "Z",
            "fx_override_on": st.session_state.fx_override_on,
            "fx_override_rate": st.session_state.fx_override_rate,
        }])
        z.writestr("meta.csv", meta.to_csv(index=False))
    return mem.getvalue()

def restore_zip(blob: bytes):
    mem = io.BytesIO(blob)
    with zipfile.ZipFile(mem, "r") as z:
        def read(name):
            with z.open(name) as f:
                return pd.read_csv(f)

        st.session_state.assets = normalize_assets(read("assets.csv")) if "assets.csv" in z.namelist() else defaults_assets()
        st.session_state.cards = normalize_cards(read("credit_cards.csv")) if "credit_cards.csv" in z.namelist() else defaults_cards()
        st.session_state.reim = normalize_reim(read("reimbursements.csv")) if "reimbursements.csv" in z.namelist() else defaults_reim()
        st.session_state.fixed = normalize_fixed(read("fixed_costs.csv")) if "fixed_costs.csv" in z.namelist() else defaults_fixed()
        st.session_state.pay = normalize_pay(read("pay_cycle.csv")) if "pay_cycle.csv" in z.namelist() else defaults_pay()

        if "meta.csv" in z.namelist():
            meta = read("meta.csv")
            try:
                st.session_state.fx_override_on = bool(meta.loc[0, "fx_override_on"])
                st.session_state.fx_override_rate = float(meta.loc[0, "fx_override_rate"])
            except Exception:
                pass

with st.sidebar:
    st.subheader("Save / Load")

    st.download_button(
        "⬇️ Download backup (ZIP)",
        data=make_zip(),
        file_name="stabler-finances-backup.zip",
        mime="application/zip",
        use_container_width=True,
    )

    up = st.file_uploader("⬆️ Restore from backup (ZIP)", type=["zip"])
    if up is not None:
        restore_zip(up.getvalue())
        st.success("Backup restored (fields mapped).")
        st.rerun()

    if st.button("Reset to defaults", use_container_width=True):
        st.session_state.assets = defaults_assets()
        st.session_state.cards = defaults_cards()
        st.session_state.reim = defaults_reim()
        st.session_state.fixed = defaults_fixed()
        st.session_state.pay = defaults_pay()
        st.session_state.fx_override_on = False
        st.session_state.fx_override_rate = 0.80
        st.rerun()

# ------------------------
# FX
# ------------------------
live_rate, live_ts = usd_to_gbp_live()
rate = live_rate if live_rate else 0.80
if st.session_state.fx_override_on:
    rate = float(st.session_state.fx_override_rate)

# ------------------------
# Totals
# ------------------------
assets_df = st.session_state.assets.copy()
assets_gbp = []
for _, r in assets_df.iterrows():
    cur = str(r.get("Currency", "GBP")).upper()
    usd = (cur == "USD") or is_usd_item(str(r.get("Account", "")))
    assets_gbp.append(to_gbp(float(r["Balance (native)"]), usd, rate))
total_assets_gbp = float(sum(assets_gbp))

cards_df = st.session_state.cards.copy()
card_bal_gbp = []
card_due_gbp = []
for _, r in cards_df.iterrows():
    usd = is_usd_item(str(r.get("Card", "")))
    card_bal_gbp.append(to_gbp(float(r["Balance (native)"]), usd, rate))
    card_due_gbp.append(to_gbp(float(r["Balance Due (native)"]), usd, rate))
total_card_bal_gbp = float(sum(card_bal_gbp))
total_card_due_gbp = float(sum(card_due_gbp))

reim_df = st.session_state.reim.copy()
included_reim_gbp = float(reim_df.loc[reim_df["Include?"] == True, "Amount (GBP)"].sum())  # noqa: E712

fixed_df = st.session_state.fixed.copy()
fixed_due_gbp = float(fixed_df.loc[fixed_df["Due?"] == True, "Amount (GBP)"].sum())  # noqa: E712
fixed_total_gbp = float(fixed_df["Amount (GBP)"].sum())

pay_df = st.session_state.pay.copy()
# ✅ only count pay lines where Paid? is ticked
paid_pay_gbp = float(pay_df.loc[pay_df["Paid?"] == True, "Monthly Pay (GBP)"].sum())  # noqa: E712

net_cash_gbp = total_assets_gbp - total_card_bal_gbp + included_reim_gbp

# ✅ Your formula (but with Paid? controlling pay inclusion)
projected_available_gbp = net_cash_gbp + (paid_pay_gbp - fixed_total_gbp)

# ------------------------
# KPIs
# ------------------------
k1, k2, k3 = st.columns(3)
with k1:
    kpi("Net Cash (GBP)", net_cash_gbp)
with k2:
    kpi("Total Credit Card Bill Due (GBP)", total_card_due_gbp, force_neutral=True)
with k3:
    kpi("Projected Available This Month (GBP)", projected_available_gbp)

st.divider()

# ------------------------
# Row 1
# ------------------------
a, b, c = st.columns([1.2, 1.1, 1.1])

with a:
    st.subheader("Assets")
    st.session_state.assets = normalize_assets(
        st.data_editor(
            st.session_state.assets,
            num_rows="dynamic",
            use_container_width=True,
            key="assets_editor",
            column_config={
                "Account": st.column_config.TextColumn("Account"),
                "Currency": st.column_config.SelectboxColumn("Currency", options=["GBP", "USD"]),
                "Balance (native)": st.column_config.NumberColumn("Balance (native)", format="%.2f"),
            },
        )
    )
    totals_line("Total Assets (GBP):", total_assets_gbp)

with b:
    st.subheader("Credit Cards")
    st.session_state.cards = normalize_cards(
        st.data_editor(
            st.session_state.cards,
            num_rows="dynamic",
            use_container_width=True,
            key="cards_editor",
            column_config={
                "Card": st.column_config.TextColumn("Card"),
                "Balance (native)": st.column_config.NumberColumn("Balance", format="%.2f"),
                "Balance Due (native)": st.column_config.NumberColumn("Balance Due", format="%.2f"),
            },
        )
    )
    st.markdown(
        f"""
<div class="totals">
  Total Card Balances (GBP): <span class="{cls(total_card_bal_gbp)}">{gbp(total_card_bal_gbp)}</span>
  &nbsp;&nbsp;•&nbsp;&nbsp;
  Total Bills Due (GBP): <span class="neu">{gbp(total_card_due_gbp)}</span>
</div>
""",
        unsafe_allow_html=True,
    )

with c:
    st.subheader("Reimbursement Pending")
    st.session_state.reim = normalize_reim(
        st.data_editor(
            st.session_state.reim,
            num_rows="dynamic",
            use_container_width=True,
            key="reim_editor",
            column_config={
                "Source": st.column_config.TextColumn("Source"),
                "Amount (GBP)": st.column_config.NumberColumn("Amount (GBP)", format="%.2f"),
                "Include?": st.column_config.CheckboxColumn("Include?"),
            },
        )
    )
    totals_line("Included Reimbursements (GBP):", included_reim_gbp)

st.divider()

# ------------------------
# Row 2
# ------------------------
d, e = st.columns([2.1, 1.0])

with d:
    st.subheader("Monthly Fixed")
    st.session_state.fixed = normalize_fixed(
        st.data_editor(
            st.session_state.fixed,
            num_rows="dynamic",
            use_container_width=True,
            key="fixed_editor",
            column_config={
                "Item": st.column_config.TextColumn("Item"),
                "Amount (GBP)": st.column_config.NumberColumn("Amount (GBP)", format="%.2f"),
                "Due?": st.column_config.CheckboxColumn("Due?"),
            },
        )
    )
    st.markdown(
        f"""
<div class="totals">
  Fixed Due This Month: <span class="neu">{gbp(fixed_due_gbp)}</span>
  &nbsp;&nbsp;•&nbsp;&nbsp;
  Fixed Total Monthly: <span class="neu">{gbp(fixed_total_gbp)}</span>
</div>
""",
        unsafe_allow_html=True,
    )

with e:
    st.subheader("Monthly Pay")
    st.caption("Tick Paid? when the salary has landed (only ticked rows count in the projection).")
    st.session_state.pay = normalize_pay(
        st.data_editor(
            st.session_state.pay,
            num_rows="dynamic",
            use_container_width=True,
            key="pay_editor",
            column_config={
                "Person": st.column_config.TextColumn("Person"),
                "Monthly Pay (GBP)": st.column_config.NumberColumn("Monthly Pay", format="%.2f"),
                "Paid?": st.column_config.CheckboxColumn("Paid?"),
            },
        )
    )
    totals_line("Total Pay Counted (Paid only):", paid_pay_gbp)

st.divider()

# ------------------------
# FX bottom
# ------------------------
st.subheader("FX (USD → GBP)")
st.caption("Apple Savings + Apple Card are treated as USD and converted to GBP for totals.")

fxl, fxr = st.columns([1.2, 1.0])

with fxl:
    if live_rate:
        st.markdown(
            f"""<div class="totals">Live USD→GBP rate: <span class="neu">{live_rate:.4f}</span> (timestamp: {live_ts})</div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""<div class="totals">Live FX unavailable right now. Using fallback/override rate: <span class="neu">{rate:.4f}</span></div>""",
            unsafe_allow_html=True,
        )

with fxr:
    st.session_state.fx_override_on = st.toggle("Override FX rate", value=st.session_state.fx_override_on)
    st.session_state.fx_override_rate = st.number_input(
        "Manual USD→GBP rate",
        value=float(st.session_state.fx_override_rate),
        step=0.0001,
        format="%.4f",
        disabled=not st.session_state.fx_override_on,
    )

st.caption(f"Current rate used for totals: {rate:.4f}")
