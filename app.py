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

def normalize_assets(df: pd.DataFrame) -> pd.DataFrame:
    df = _clean_cols(df)
    if "Account" not in df.columns: df["Account"] = ""
    if "Currency" not in df.columns: df["Currency"] = "GBP"
    if "Balance (native)" not in df.columns:
        # common aliases
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
    """
    Backward compatible:
    - Old: Due this cycle (native) -> Balance Due (native)
    - Old: Currency column may exist; we ignore it now
    - Accept aliases: balance / due / amount
    """
    df = _clean_cols(df)

    # Rename common old/new names
    rename_map = {}

    # Card
    if "Card" not in df.columns:
        for a in ["card", "Name", "name"]:
            if a in df.columns:
                rename_map[a] = "Card"
                break

    # Balance
    if "Balance (native)" not in df.columns:
        for a in ["Balance", "balance", "Amount", "amount", "Value", "value"]:
            if a in df.columns:
                rename_map[a] = "Balance (native)"
                break

    # Balance Due (native) (your new field)
    if "Balance Due (native)" not in df.columns:
        # old schema uses this:
        if "Due this cycle (native)" in df.columns:
            rename_map["Due this cycle (native)"] = "Balance Due (native)"
        else:
            for a in ["Balance Due", "balance due", "Due", "due", "due_this_cycle"]:
                if a in df.columns:
                    rename_map[a] = "Balance Due (native)"
                    break

    if rename_map:
        df = df.rename(columns=rename_map)

    # Ensure required columns exist
    if "Card" not in df.columns:
        df["Card"] = ""
    if "Balance (native)" not in df.columns:
        df["Balance (native)"] = 0.0
    if "Balance Due (native)" not in df.columns:
        df["Balance Due (native)"] = 0.0

    # Coerce money
    df["Balance (native)"] = _to_float(df["Balance (native)"])
    df["Balance Due (native)"] = _to_float(df["Balance Due (native)"])

    # Keep ONLY the columns you want visible/used
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
    df["Include?"] = df["Include?"].astype(bool)
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
    df["Due?"] = df["Due?"].astype(bool)
    return df[["Item", "Amount (GBP)", "Due?"]]

def normalize_pay(df: pd.DataFrame) -> pd.DataFrame:
    df = _clean_cols(df)
    if "Person" not in df.columns: df["Person"] = ""
    if "Monthly pay (£)" not in df.columns:
        for a in ["Monthly pay", "Pay", "pay", "Amount", "amount"]:
            if a in df.columns:
                df = df.rename(columns={a: "Monthly pay (£)"})
                break
        if "Monthly pay (£)" not in df.columns:
            df["Monthly pay (£)"] = 0.0
    df["Monthly pay (£)"] = _to_float(df["Monthly pay (£)"])
    return df[["Person", "Monthly pay (£)"]]

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
    return pd.DataFrame(
        [{"Person": "Eric", "Monthly pay (£)": 0.0}, {"Person": "Gigi", "Monthly pay (£)": 0.0}]
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
    """
    IMPORTANT: We save using the CURRENT schema
    so restore is always clean going forward.
    """
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
    """
    Backward compatible restore:
    - Reads old files
    - Normalizes them into the CURRENT schema
    """
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
# Totals (USD->GBP conversion)
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

net_cash_gbp = total_assets_gbp - total_card_bal_gbp + included_reim_gbp
total_spend_rest_month_gbp = fixed_due_gbp + total_card_due_gbp

# ------------------------
# KPIs (coloured)
# ------------------------
k1, k2, k3 = st.columns(3)
with k1:
    kpi("Net Cash (GBP)", net_cash_gbp)
with k2:
    kpi("Total Credit Card Bill Due (GBP)", total_card_due_gbp, force_neutral=True)
with k3:
    kpi("Total Spend Rest of Month (GBP)", total_spend_rest_month_gbp, force_neutral=True)

st.divider()

# ------------------------
# Row 1: Assets | Cards | Reimbursements
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
# Row 2: Monthly Fixed | Pay Cycle
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
    totals_line("Fixed Due This Month (GBP):", fixed_due_gbp)

with e:
    st.subheader("Pay Cycle (setup)")
    st.caption("Optional – for future projections.")
    st.session_state.pay = normalize_pay(
        st.data_editor(
            st.session_state.pay,
            num_rows="dynamic",
            use_container_width=True,
            key="pay_editor",
            column_config={
                "Person": st.column_config.TextColumn("Person"),
                "Monthly pay (£)": st.column_config.NumberColumn("Monthly pay (£)", format="%.2f"),
            },
        )
    )

st.divider()

# ------------------------
# FX (bottom)
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
