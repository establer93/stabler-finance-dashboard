import io
import zipfile
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

# -----------------------------
# Page
# -----------------------------
st.set_page_config(page_title="Stabler Family Finances", layout="wide")
st.title("Stabler Family Finances")

# -----------------------------
# Utilities
# -----------------------------
def _to_float_series(s: pd.Series) -> pd.Series:
    """Coerce money-like strings to float safely."""
    if s is None:
        return pd.Series(dtype=float)
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

def fmt_gbp(x: float) -> str:
    return f"£{float(x):,.2f}"

def is_usd_name(name: str) -> bool:
    """Simple rule: Apple Savings + Apple Card are USD (as per your setup)."""
    if not isinstance(name, str):
        return False
    n = name.lower()
    return ("apple savings" in n) or ("apple card" in n)

@st.cache_data(ttl=60 * 30)
def fetch_usd_to_gbp_rate():
    """
    Lightweight FX fetch. Falls back safely if it fails.
    Source: open.er-api.com (free).
    """
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        data = r.json()
        rate = float(data["rates"]["GBP"])
        return rate, data.get("time_last_update_utc", None)
    except Exception:
        return None, None

def convert_to_gbp(amount_native: float, is_usd: bool, usd_to_gbp: float) -> float:
    return float(amount_native) * float(usd_to_gbp) if is_usd else float(amount_native)

# -----------------------------
# Defaults (keep your vibe)
# -----------------------------
def default_assets_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Account": "HSBC", "Currency": "GBP", "Balance (native)": 0.0},
            {"Account": "Lloyds", "Currency": "GBP", "Balance (native)": 0.0},
            {"Account": "Apple Savings", "Currency": "USD", "Balance (native)": 0.0},
            {"Account": "Cash", "Currency": "GBP", "Balance (native)": 0.0},
        ]
    )

def default_credit_cards_df() -> pd.DataFrame:
    # IMPORTANT: Only these columns (as you requested)
    return pd.DataFrame(
        [
            {"Card": "Amex", "Balance (native)": 0.0, "Balance Due (native)": 0.0},
            {"Card": "Apple Card", "Balance (native)": 0.0, "Balance Due (native)": 0.0},
        ]
    )

def default_reimbursements_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Source": "Eric Work", "Amount (GBP)": 0.0, "Include?": True},
            {"Source": "Gigi Work", "Amount (GBP)": 0.0, "Include?": True},
            {"Source": "Misc", "Amount (GBP)": 0.0, "Include?": False},
        ]
    )

def default_fixed_costs_df() -> pd.DataFrame:
    # Your list from the screenshot
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

def default_pay_cycle_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Person": "Eric", "Monthly pay (£)": 0.0},
            {"Person": "Gigi", "Monthly pay (£)": 0.0},
        ]
    )

# -----------------------------
# Session State init
# -----------------------------
if "assets" not in st.session_state:
    st.session_state.assets = default_assets_df()

if "credit_cards" not in st.session_state:
    st.session_state.credit_cards = default_credit_cards_df()

if "reimbursements" not in st.session_state:
    st.session_state.reimbursements = default_reimbursements_df()

if "fixed_costs" not in st.session_state:
    st.session_state.fixed_costs = default_fixed_costs_df()

if "pay_cycle" not in st.session_state:
    st.session_state.pay_cycle = default_pay_cycle_df()

# Manual FX override (optional)
if "fx_override_on" not in st.session_state:
    st.session_state.fx_override_on = False
if "fx_override_rate" not in st.session_state:
    st.session_state.fx_override_rate = 0.80

# -----------------------------
# Save / Load (ZIP backup) — keep this
# -----------------------------
def build_backup_zip_bytes() -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("assets.csv", st.session_state.assets.to_csv(index=False))
        z.writestr("credit_cards.csv", st.session_state.credit_cards.to_csv(index=False))
        z.writestr("reimbursements.csv", st.session_state.reimbursements.to_csv(index=False))
        z.writestr("fixed_costs.csv", st.session_state.fixed_costs.to_csv(index=False))
        z.writestr("pay_cycle.csv", st.session_state.pay_cycle.to_csv(index=False))

        meta = pd.DataFrame([{
            "saved_at": datetime.utcnow().isoformat() + "Z",
            "fx_override_on": st.session_state.fx_override_on,
            "fx_override_rate": st.session_state.fx_override_rate,
        }])
        z.writestr("meta.csv", meta.to_csv(index=False))
    return mem.getvalue()

def restore_from_backup_zip(uploaded_bytes: bytes):
    mem = io.BytesIO(uploaded_bytes)
    with zipfile.ZipFile(mem, "r") as z:
        def read_csv(name: str) -> pd.DataFrame:
            with z.open(name) as f:
                return pd.read_csv(f)

        # Load tables if present (fallback to defaults if not)
        st.session_state.assets = read_csv("assets.csv") if "assets.csv" in z.namelist() else default_assets_df()
        st.session_state.credit_cards = read_csv("credit_cards.csv") if "credit_cards.csv" in z.namelist() else default_credit_cards_df()
        st.session_state.reimbursements = read_csv("reimbursements.csv") if "reimbursements.csv" in z.namelist() else default_reimbursements_df()
        st.session_state.fixed_costs = read_csv("fixed_costs.csv") if "fixed_costs.csv" in z.namelist() else default_fixed_costs_df()
        st.session_state.pay_cycle = read_csv("pay_cycle.csv") if "pay_cycle.csv" in z.namelist() else default_pay_cycle_df()

        if "meta.csv" in z.namelist():
            meta = read_csv("meta.csv")
            try:
                st.session_state.fx_override_on = bool(meta.loc[0, "fx_override_on"])
                st.session_state.fx_override_rate = float(meta.loc[0, "fx_override_rate"])
            except Exception:
                pass

with st.sidebar:
    st.subheader("Save / Load")

    backup_bytes = build_backup_zip_bytes()
    st.download_button(
        "⬇️ Download backup (ZIP)",
        data=backup_bytes,
        file_name="stabler-finances-backup.zip",
        mime="application/zip",
        use_container_width=True,
    )

    uploaded = st.file_uploader("⬆️ Restore from backup (ZIP)", type=["zip"])
    if uploaded is not None:
        try:
            restore_from_backup_zip(uploaded.getvalue())
            st.success("Backup restored.")
            st.rerun()
        except Exception as e:
            st.error("That ZIP didn’t look like a valid backup.")
            st.code(str(e))

    if st.button("Reset to defaults", use_container_width=True):
        st.session_state.assets = default_assets_df()
        st.session_state.credit_cards = default_credit_cards_df()
        st.session_state.reimbursements = default_reimbursements_df()
        st.session_state.fixed_costs = default_fixed_costs_df()
        st.session_state.pay_cycle = default_pay_cycle_df()
        st.session_state.fx_override_on = False
        st.session_state.fx_override_rate = 0.80
        st.rerun()

# -----------------------------
# FX (live + override)
# -----------------------------
live_rate, live_ts = fetch_usd_to_gbp_rate()
usd_to_gbp = live_rate if live_rate else 0.80

if st.session_state.fx_override_on:
    usd_to_gbp = float(st.session_state.fx_override_rate)

# -----------------------------
# Compute totals (proper GBP conversion)
# -----------------------------
assets_df = st.session_state.assets.copy()
assets_df["Balance (native)"] = _to_float_series(assets_df.get("Balance (native)", pd.Series(dtype=str)))

assets_gbp_vals = []
for _, r in assets_df.iterrows():
    cur = str(r.get("Currency", "GBP")).upper()
    native = float(r.get("Balance (native)", 0.0))
    is_usd = (cur == "USD") or is_usd_name(str(r.get("Account", "")))
    assets_gbp_vals.append(convert_to_gbp(native, is_usd, usd_to_gbp))
total_assets_gbp = float(sum(assets_gbp_vals))

cards_df = st.session_state.credit_cards.copy()
cards_df["Balance (native)"] = _to_float_series(cards_df.get("Balance (native)", pd.Series(dtype=str)))
cards_df["Balance Due (native)"] = _to_float_series(cards_df.get("Balance Due (native)", pd.Series(dtype=str)))

card_bal_gbp_vals = []
card_due_gbp_vals = []
for _, r in cards_df.iterrows():
    name = str(r.get("Card", ""))
    is_usd = is_usd_name(name)
    card_bal_gbp_vals.append(convert_to_gbp(float(r.get("Balance (native)", 0.0)), is_usd, usd_to_gbp))
    card_due_gbp_vals.append(convert_to_gbp(float(r.get("Balance Due (native)", 0.0)), is_usd, usd_to_gbp))

total_card_balance_gbp = float(sum(card_bal_gbp_vals))
total_card_due_gbp = float(sum(card_due_gbp_vals))

reim_df = st.session_state.reimbursements.copy()
reim_df["Amount (GBP)"] = _to_float_series(reim_df.get("Amount (GBP)", pd.Series(dtype=str)))
included_reim_gbp = float(reim_df.loc[reim_df.get("Include?") == True, "Amount (GBP)"].sum())  # noqa: E712

fixed_df = st.session_state.fixed_costs.copy()
fixed_df["Amount (GBP)"] = _to_float_series(fixed_df.get("Amount (GBP)", pd.Series(dtype=str)))
fixed_due_gbp = float(fixed_df.loc[fixed_df.get("Due?") == True, "Amount (GBP)"].sum())  # noqa: E712

# Your headline metrics (kept consistent + simple)
net_cash_gbp = total_assets_gbp - total_card_balance_gbp
total_spend_rest_month_gbp = max(0.0, fixed_due_gbp + total_card_due_gbp - included_reim_gbp)

# -----------------------------
# TOP METRICS (Net cash turns red if negative)
# -----------------------------
m1, m2, m3 = st.columns(3)

with m1:
    color = "#ff4b4b" if net_cash_gbp < 0 else "#dfe6ef"
    st.markdown("Net Cash (GBP)")
    st.markdown(
        f"<div style='font-size:34px; font-weight:700; color:{color}; margin-top:-8px'>{fmt_gbp(net_cash_gbp)}</div>",
        unsafe_allow_html=True,
    )

with m2:
    st.metric("Total Credit Card Bill Due (GBP)", fmt_gbp(total_card_due_gbp))

with m3:
    st.metric("Total Spend Rest of Month (GBP)", fmt_gbp(total_spend_rest_month_gbp))

st.divider()

# -----------------------------
# ROW 1: Assets | Credit Cards | Reimbursement Pending
# -----------------------------
c1, c2, c3 = st.columns(3)

with c1:
    st.subheader("Assets")
    st.session_state.assets = st.data_editor(
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
    st.caption(f"Total Assets (GBP): {fmt_gbp(total_assets_gbp)}")

with c2:
    st.subheader("Credit Cards")
    # Only columns you asked for:
    st.session_state.credit_cards = st.data_editor(
        st.session_state.credit_cards[["Card", "Balance (native)", "Balance Due (native)"]],
        num_rows="dynamic",
        use_container_width=True,
        key="cards_editor",
        column_config={
            "Card": st.column_config.TextColumn("Card"),
            "Balance (native)": st.column_config.NumberColumn("Balance", format="%.2f"),
            "Balance Due (native)": st.column_config.NumberColumn("Balance Due", format="%.2f"),
        },
    )
    st.caption(
        f"Total Card Balances (GBP): {fmt_gbp(total_card_balance_gbp)} • "
        f"Total Bills Due (GBP): {fmt_gbp(total_card_due_gbp)}"
    )

with c3:
    st.subheader("Reimbursement Pending")
    st.session_state.reimbursements = st.data_editor(
        st.session_state.reimbursements,
        num_rows="dynamic",
        use_container_width=True,
        key="reim_editor",
        column_config={
            "Source": st.column_config.TextColumn("Source"),
            "Amount (GBP)": st.column_config.NumberColumn("Amount (GBP)", format="%.2f"),
            "Include?": st.column_config.CheckboxColumn("Include?"),
        },
    )
    st.caption(f"Included Reimbursements (GBP): {fmt_gbp(included_reim_gbp)}")

st.divider()

# -----------------------------
# ROW 2: Monthly Fixed | Pay Cycle (setup)
# -----------------------------
r1, r2 = st.columns([2, 1])

with r1:
    st.subheader("Monthly Fixed")
    st.session_state.fixed_costs = st.data_editor(
        st.session_state.fixed_costs,
        num_rows="dynamic",
        use_container_width=True,
        key="fixed_editor",
        column_config={
            "Item": st.column_config.TextColumn("Item"),
            "Amount (GBP)": st.column_config.NumberColumn("Amount (GBP)", format="%.2f"),
            "Due?": st.column_config.CheckboxColumn("Due?"),
        },
    )
    st.caption(f"Fixed Due (GBP): {fmt_gbp(fixed_due_gbp)}")

with r2:
    st.subheader("Pay Cycle (setup)")
    st.caption("Optional – for future projections.")
    st.session_state.pay_cycle = st.data_editor(
        st.session_state.pay_cycle,
        num_rows="fixed",
        use_container_width=True,
        key="pay_editor",
        column_config={
            "Person": st.column_config.TextColumn("Person"),
            "Monthly pay (£)": st.column_config.NumberColumn("Monthly pay (£)", format="%.2f"),
        },
    )

# -----------------------------
# FX SECTION (Bottom — as requested)
# -----------------------------
st.divider()
st.subheader("FX (USD → GBP)")

fxc1, fxc2, fxc3 = st.columns([1, 1, 2])

with fxc1:
    st.metric("Live USD→GBP", f"{usd_to_gbp:.4f}")

with fxc2:
    st.checkbox("Override rate", key="fx_override_on")
    st.number_input("Override USD→GBP", key="fx_override_rate", value=float(st.session_state.fx_override_rate), step=0.0001, format="%.4f")

with fxc3:
    if live_rate is None:
        st.info("Live rate fetch failed (using fallback / override).")
    else:
        st.caption(f"Last update: {live_ts or 'unknown'} • Source: open.er-api.com")

st.caption(
    "Notes: Apple Savings (Assets) and Apple Card (Credit Cards) are treated as USD and auto-converted to GBP in totals."
)
