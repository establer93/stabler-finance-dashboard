import io
import zipfile
from datetime import datetime, timezone
import hashlib

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Stabler Family Finances", layout="wide")

SCHEMA_VERSION = "2026-02-21-zip-polish-v7-main-currency-display"

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

.badge {
  display:inline-block; padding:2px 8px; border-radius:12px;
  font-size:12px; opacity:0.9; border:1px solid rgba(255,255,255,0.15);
}
.badge-ok { background: rgba(46, 204, 113, 0.15); }
.badge-warn { background: rgba(255, 75, 75, 0.15); }
.badge-neutral { background: rgba(255,255,255,0.08); }

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
def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()

def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()

def safe_float(x, default=0.0):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default

def fmt_money(value: float, currency: str) -> str:
    cur = (currency or "GBP").upper().strip()
    sym = "£" if cur == "GBP" else "$" if cur == "USD" else f"{cur} "
    try:
        return f"{sym}{value:,.2f}"
    except Exception:
        return f"{sym}{value}"

@st.cache_data(ttl=60 * 60 * 12)  # cache for 12h
def get_usd_to_gbp_rate() -> float:
    # Simple public source; cached so it doesn't hammer requests.
    # If it ever fails, we fall back to 0.80-ish rather than break the app.
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        data = r.json()
        gbp = data["rates"]["GBP"]
        return float(gbp)
    except Exception:
        return 0.80

def to_gbp(amount: float, currency: str, usd_to_gbp: float) -> float:
    cur = (currency or "GBP").upper().strip()
    if cur == "GBP":
        return amount
    if cur == "USD":
        return amount * usd_to_gbp
    # Unknown currency: treat as GBP to avoid surprising zeros
    return amount

def ensure_columns(df: pd.DataFrame, cols_with_defaults: dict) -> pd.DataFrame:
    df = df.copy()
    for c, d in cols_with_defaults.items():
        if c not in df.columns:
            df[c] = d
    return df

def coerce_schema_state(state: dict) -> dict:
    # Ensure DataFrames exist and have expected columns.
    state = dict(state)

    assets = state.get("assets", pd.DataFrame())
    cards = state.get("credit_cards", pd.DataFrame())
    reimb = state.get("reimbursements", pd.DataFrame())
    fixed = state.get("fixed_costs", pd.DataFrame())
    pay = state.get("pay_cycle", pd.DataFrame())
    fx = state.get("fx_settings", {"usd_to_gbp_manual": None, "use_live": True})

    # Assets
    assets = ensure_columns(
        assets,
        {
            "Account": "",
            "Currency": "GBP",
            "Balance (native)": 0.0,
        },
    )
    # Credit cards
    cards = ensure_columns(
        cards,
        {
            "Card": "",
            "Currency": "GBP",
            "Balance (native)": 0.0,
            "Balance Due (native)": 0.0,
        },
    )
    # Reimbursements (GBP)
    reimb = ensure_columns(
        reimb,
        {
            "Source": "",
            "Amount (GBP)": 0.0,
            "Include?": True,
        },
    )
    # Fixed
    fixed = ensure_columns(
        fixed,
        {
            "Item": "",
            "Amount (GBP)": 0.0,
            "Due?": True,
        },
    )
    # Pay cycle
    pay = ensure_columns(
        pay,
        {
            "Person": "",
            "Monthly pay": 0.0,
            "Paid?": False,
        },
    )

    # Clean types
    assets["Currency"] = assets["Currency"].astype(str).str.upper()
    cards["Currency"] = cards["Currency"].astype(str).str.upper()

    state["assets"] = assets
    state["credit_cards"] = cards
    state["reimbursements"] = reimb
    state["fixed_costs"] = fixed
    state["pay_cycle"] = pay
    state["fx_settings"] = fx

    return state

def default_state():
    # Defaults based on your current setup
    assets = pd.DataFrame(
        [
            {"Account": "HSBC", "Currency": "GBP", "Balance (native)": 0.0},
            {"Account": "Lloyds", "Currency": "GBP", "Balance (native)": 0.0},
            {"Account": "Apple Savings", "Currency": "USD", "Balance (native)": 0.0},
        ]
    )

    cards = pd.DataFrame(
        [
            {"Card": "Amex", "Currency": "GBP", "Balance (native)": 0.0, "Balance Due (native)": 0.0},
            {"Card": "Apple Card", "Currency": "USD", "Balance (native)": 0.0, "Balance Due (native)": 0.0},
            {"Card": "Lloyds", "Currency": "GBP", "Balance (native)": 0.0, "Balance Due (native)": 0.0},
        ]
    )

    reimb = pd.DataFrame(
        [
            {"Source": "Eric Work", "Amount (GBP)": 0.0, "Include?": True},
            {"Source": "Gigi Work", "Amount (GBP)": 0.0, "Include?": True},
            {"Source": "Misc", "Amount (GBP)": 0.0, "Include?": False},
        ]
    )

    fixed = pd.DataFrame(
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

    pay = pd.DataFrame(
        [
            {"Person": "Eric", "Monthly pay": 6100.0, "Paid?": False},
            {"Person": "Gigi", "Monthly pay": 6000.0, "Paid?": False},
        ]
    )

    fx = {"usd_to_gbp_manual": None, "use_live": True}

    return {
        "schema_version": SCHEMA_VERSION,
        "saved_at": utc_now_iso(),
        "assets": assets,
        "credit_cards": cards,
        "reimbursements": reimb,
        "fixed_costs": fixed,
        "pay_cycle": pay,
        "fx_settings": fx,
    }

# ------------------------
# Backup / Restore (ZIP)
# ------------------------
def state_to_zip_bytes(state: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        meta = {
            "schema_version": state.get("schema_version", SCHEMA_VERSION),
            "saved_at": utc_now_iso(),
            "fx_settings": state.get("fx_settings", {"usd_to_gbp_manual": None, "use_live": True}),
        }
        z.writestr("meta.json", pd.Series(meta).to_json())

        for name, df in [
            ("assets.csv", state["assets"]),
            ("credit_cards.csv", state["credit_cards"]),
            ("reimbursements.csv", state["reimbursements"]),
            ("fixed_costs.csv", state["fixed_costs"]),
            ("pay_cycle.csv", state["pay_cycle"]),
        ]:
            z.writestr(name, df.to_csv(index=False))
    return buf.getvalue()

def zip_bytes_to_state(b: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(b), "r") as z:
        state = default_state()
        try:
            meta_raw = z.read("meta.json")
            meta = pd.read_json(io.BytesIO(meta_raw), typ="series")
            fx_settings = meta.get("fx_settings", state["fx_settings"])
            state["fx_settings"] = fx_settings if isinstance(fx_settings, dict) else state["fx_settings"]
        except Exception:
            pass

        def read_csv(name):
            try:
                return pd.read_csv(io.BytesIO(z.read(name)))
            except Exception:
                return None

        for key, fname in [
            ("assets", "assets.csv"),
            ("credit_cards", "credit_cards.csv"),
            ("reimbursements", "reimbursements.csv"),
            ("fixed_costs", "fixed_costs.csv"),
            ("pay_cycle", "pay_cycle.csv"),
        ]:
            df = read_csv(fname)
            if df is not None:
                state[key] = df

        state["schema_version"] = state.get("schema_version", SCHEMA_VERSION)
        state["saved_at"] = utc_now_iso()
        return coerce_schema_state(state)

# ------------------------
# Init session state
# ------------------------
if "app_state" not in st.session_state:
    st.session_state.app_state = coerce_schema_state(default_state())

# ------------------------
# Sidebar: Save / Load
# ------------------------
with st.sidebar:
    st.subheader("Save / Load")

    backup_bytes = state_to_zip_bytes(st.session_state.app_state)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    st.download_button(
        "⬇️ Download backup (ZIP)",
        data=backup_bytes,
        file_name=f"stabler-finances-backup-{stamp}.zip",
        mime="application/zip",
    )

    uploaded = st.file_uploader("Restore from backup (ZIP)", type=["zip"])
    if uploaded is not None:
        try:
            b = uploaded.read()
            st.session_state.app_state = zip_bytes_to_state(b)
            st.success("Backup restored.")
        except Exception as e:
            st.error(f"Restore failed: {e}")

    st.divider()
    if st.button("Reset to defaults"):
        st.session_state.app_state = coerce_schema_state(default_state())
        st.success("Reset complete.")

# ------------------------
# FX settings
# ------------------------
state = st.session_state.app_state
fx = state.get("fx_settings", {"usd_to_gbp_manual": None, "use_live": True})
use_live = bool(fx.get("use_live", True))
manual_rate = fx.get("usd_to_gbp_manual", None)

live_rate = get_usd_to_gbp_rate()
usd_to_gbp = live_rate if use_live else (safe_float(manual_rate, live_rate) if manual_rate is not None else live_rate)

# ------------------------
# Compute totals
# ------------------------
assets_df = state["assets"].copy()
cards_df = state["credit_cards"].copy()
reimb_df = state["reimbursements"].copy()
fixed_df = state["fixed_costs"].copy()
pay_df = state["pay_cycle"].copy()

# Coerce numeric columns
assets_df["Balance (native)"] = assets_df["Balance (native)"].apply(safe_float)
cards_df["Balance (native)"] = cards_df["Balance (native)"].apply(safe_float)
cards_df["Balance Due (native)"] = cards_df["Balance Due (native)"].apply(safe_float)
reimb_df["Amount (GBP)"] = reimb_df["Amount (GBP)"].apply(safe_float)
fixed_df["Amount (GBP)"] = fixed_df["Amount (GBP)"].apply(safe_float)
pay_df["Monthly pay"] = pay_df["Monthly pay"].apply(safe_float)
pay_df["Paid?"] = pay_df["Paid?"].fillna(False).astype(bool)

assets_total_gbp = float(
    sum(
        to_gbp(row["Balance (native)"], row["Currency"], usd_to_gbp)
        for _, row in assets_df.iterrows()
    )
)

card_balances_gbp = float(
    sum(
        to_gbp(row["Balance (native)"], row["Currency"], usd_to_gbp)
        for _, row in cards_df.iterrows()
    )
)
card_due_gbp = float(
    sum(
        to_gbp(row["Balance Due (native)"], row["Currency"], usd_to_gbp)
        for _, row in cards_df.iterrows()
    )
)

included_reimb_gbp = float(reimb_df.loc[reimb_df["Include?"] == True, "Amount (GBP)"].sum())
fixed_due_gbp = float(fixed_df.loc[fixed_df["Due?"] == True, "Amount (GBP)"].sum())
paid_income_gbp = float(pay_df.loc[pay_df["Paid?"] == True, "Monthly pay"].sum())

# KPIs:
net_cash_gbp = assets_total_gbp - card_balances_gbp
remaining_spend_gbp = net_cash_gbp + (paid_income_gbp - fixed_due_gbp)

ability_to_repay = "Yes" if (assets_total_gbp - card_due_gbp) >= 0 else "No"

# ------------------------
# KPIs UI
# ------------------------
k1, k2, k3 = st.columns(3)

def kpi(label, value, is_money=True):
    if is_money:
        text = fmt_money(value, "GBP")
    else:
        text = str(value)

    cls = "neu"
    if is_money:
        if value > 0:
            cls = "pos"
        elif value < 0:
            cls = "neg"

    st.markdown(
        f"""
<div class="kpi">
  <div class="label">{label}</div>
  <div class="value {cls}">{text}</div>
</div>
""",
        unsafe_allow_html=True,
    )

with k1:
    kpi("Net Cash (GBP)", net_cash_gbp)

with k2:
    st.markdown(
        f"""
<div class="kpi">
  <div class="label">Total Credit Card Bill Due (GBP)</div>
  <div class="value neu">{fmt_money(card_due_gbp, "GBP")}</div>
  <div style="margin-top:8px;">
    <span class="badge {'badge-ok' if ability_to_repay=='Yes' else 'badge-warn'}">
      Ability to repay: {ability_to_repay}
    </span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

with k3:
    # Remaining spending this month
    cls = "pos" if remaining_spend_gbp > 0 else "neg" if remaining_spend_gbp < 0 else "neu"
    st.markdown(
        f"""
<div class="kpi">
  <div class="label">Remaining spending this month (GBP)</div>
  <div class="value {cls}">{fmt_money(remaining_spend_gbp, "GBP")}</div>
</div>
""",
        unsafe_allow_html=True,
    )

st.divider()

# ------------------------
# Editable tables (NO row add for Assets/Cards/Reimb)
# Show currency symbol in main area via read-only display columns
# ------------------------
a_col, c_col, r_col = st.columns(3)

# Prepare display columns
assets_display = assets_df.copy()
assets_display["Balance"] = assets_display.apply(
    lambda r: fmt_money(r["Balance (native)"], r["Currency"]), axis=1
)

cards_display = cards_df.copy()
cards_display["Balance"] = cards_display.apply(
    lambda r: fmt_money(r["Balance (native)"], r["Currency"]), axis=1
)
cards_display["Balance Due"] = cards_display.apply(
    lambda r: fmt_money(r["Balance Due (native)"], r["Currency"]), axis=1
)

reimb_display = reimb_df.copy()
reimb_display["Amount"] = reimb_display["Amount (GBP)"].apply(lambda v: fmt_money(v, "GBP"))

# ASSETS
with a_col:
    st.subheader("Assets")

    edited_assets = st.data_editor(
        assets_display[["Account", "Currency", "Balance", "Balance (native)"]],
        hide_index=True,
        num_rows="fixed",
        key="assets_editor",
        disabled=["Balance"],  # read-only formatted display
        column_config={
            "Account": st.column_config.TextColumn("Account", required=True),
            "Currency": st.column_config.SelectboxColumn("Currency", options=["GBP", "USD"], required=True),
            "Balance": st.column_config.TextColumn("Balance", help="Formatted display (read-only)"),
            # IMPORTANT: no commas here, Streamlit NumberColumn format cannot support %,.
            "Balance (native)": st.column_config.NumberColumn("Balance (native)", format="%.2f"),
        },
        use_container_width=True,
    )

    if st.button("Apply Assets Changes", key="apply_assets"):
        # Write back only editable numeric + currency/account
        new_assets = edited_assets.copy()
        new_assets = ensure_columns(new_assets, {"Account": "", "Currency": "GBP", "Balance (native)": 0.0})
        # Drop display column if present
        if "Balance" in new_assets.columns:
            new_assets = new_assets.drop(columns=["Balance"])
        st.session_state.app_state["assets"] = new_assets
        st.rerun()

    total_assets_cls = "pos" if assets_total_gbp > 0 else "neg" if assets_total_gbp < 0 else "neu"
    st.markdown(
        f"""<div class="totals">Total Assets (GBP): <span class="{total_assets_cls}">{fmt_money(assets_total_gbp, "GBP")}</span></div>""",
        unsafe_allow_html=True,
    )

# CREDIT CARDS (only: Card, Balance, Balance Due — plus Currency kept but you can hide it if you want)
with c_col:
    st.subheader("Credit Cards")

    # You asked: columns should be card, balance, balance due.
    # We keep Currency hidden in the editor by not displaying it, but we still store/use it.
    # To allow changing currency later, swap the displayed columns to include Currency.
    cards_for_editor = cards_display[["Card", "Balance", "Balance Due", "Currency", "Balance (native)", "Balance Due (native)"]].copy()

    edited_cards = st.data_editor(
        cards_for_editor[["Card", "Balance", "Balance Due", "Balance (native)", "Balance Due (native)"]],
        hide_index=True,
        num_rows="fixed",
        key="cards_editor",
        disabled=["Balance", "Balance Due"],  # read-only formatted display
        column_config={
            "Card": st.column_config.TextColumn("Card", required=True),
            "Balance": st.column_config.TextColumn("Balance", help="Formatted display (read-only)"),
            "Balance Due": st.column_config.TextColumn("Balance Due", help="Formatted display (read-only)"),
            "Balance (native)": st.column_config.NumberColumn("Balance (native)", format="%.2f"),
            "Balance Due (native)": st.column_config.NumberColumn("Balance Due (native)", format="%.2f"),
        },
        use_container_width=True,
    )

    if st.button("Apply Credit Card Changes", key="apply_cards"):
        # Merge edits back into original to keep Currency per row
        merged = cards_df.copy()
        # assume same row order/length (fixed rows)
        merged["Card"] = edited_cards["Card"]
        merged["Balance (native)"] = edited_cards["Balance (native)"]
        merged["Balance Due (native)"] = edited_cards["Balance Due (native)"]
        st.session_state.app_state["credit_cards"] = merged
        st.rerun()

    st.markdown(
        f"""<div class="totals">
Total Card Balances (GBP): <span class="neu">{fmt_money(card_balances_gbp, "GBP")}</span> ·
Total Bills Due (GBP): <span class="neu">{fmt_money(card_due_gbp, "GBP")}</span>
</div>""",
        unsafe_allow_html=True,
    )

# REIMBURSEMENTS
with r_col:
    st.subheader("Reimbursement Pending")

    edited_reimb = st.data_editor(
        reimb_display[["Source", "Amount", "Amount (GBP)", "Include?"]],
        hide_index=True,
        num_rows="fixed",
        key="reimb_editor",
        disabled=["Amount"],  # formatted display read-only
        column_config={
            "Source": st.column_config.TextColumn("Source", required=True),
            "Amount": st.column_config.TextColumn("Amount", help="Formatted display (read-only)"),
            "Amount (GBP)": st.column_config.NumberColumn("Amount (GBP)", format="%.2f"),
            "Include?": st.column_config.CheckboxColumn("Include?"),
        },
        use_container_width=True,
    )

    if st.button("Apply Reimbursement Changes", key="apply_reimb"):
        new_reimb = edited_reimb.copy()
        if "Amount" in new_reimb.columns:
            new_reimb = new_reimb.drop(columns=["Amount"])
        st.session_state.app_state["reimbursements"] = new_reimb
        st.rerun()

    cls = "pos" if included_reimb_gbp > 0 else "neg" if included_reimb_gbp < 0 else "neu"
    st.markdown(
        f"""<div class="totals">Included Reimbursements (GBP): <span class="{cls}">{fmt_money(included_reimb_gbp, "GBP")}</span></div>""",
        unsafe_allow_html=True,
    )

st.divider()

# ------------------------
# Monthly Fixed + Pay Cycle
# ------------------------
left, right = st.columns([2, 1])

with left:
    st.subheader("Monthly Fixed")

    edited_fixed = st.data_editor(
        fixed_df,
        hide_index=True,
        num_rows="dynamic",
        key="fixed_editor",
        column_config={
            "Item": st.column_config.TextColumn("Item", required=True),
            "Amount (GBP)": st.column_config.NumberColumn("Amount (GBP)", format="%.2f"),
            "Due?": st.column_config.CheckboxColumn("Due?"),
        },
        use_container_width=True,
    )

    if st.button("Apply Monthly Fixed Changes", key="apply_fixed"):
        st.session_state.app_state["fixed_costs"] = edited_fixed
        st.rerun()

    cls = "neg" if fixed_due_gbp > 0 else "neu"
    st.markdown(
        f"""<div class="totals">Fixed due this month (GBP): <span class="{cls}">{fmt_money(fixed_due_gbp, "GBP")}</span></div>""",
        unsafe_allow_html=True,
    )

with right:
    st.subheader("Pay Cycle (setup)")
    st.caption("Monthly pay — tick Paid? to include in this month’s calculations.")

    edited_pay = st.data_editor(
        pay_df[["Person", "Monthly pay", "Paid?"]],
        hide_index=True,
        num_rows="fixed",
        key="pay_editor",
        column_config={
            "Person": st.column_config.TextColumn("Person", required=True),
            "Monthly pay": st.column_config.NumberColumn("Monthly pay", format="%.2f"),
            "Paid?": st.column_config.CheckboxColumn("Paid?"),
        },
        use_container_width=True,
    )

    if st.button("Apply Pay Cycle Changes", key="apply_pay"):
        st.session_state.app_state["pay_cycle"] = edited_pay
        st.rerun()

    cls = "pos" if paid_income_gbp > 0 else "neu"
    st.markdown(
        f"""<div class="totals">Included paid income (GBP): <span class="{cls}">{fmt_money(paid_income_gbp, "GBP")}</span></div>""",
        unsafe_allow_html=True,
    )

st.divider()

# ------------------------
# FX (bottom)
# ------------------------
st.subheader("FX (USD → GBP)")
st.caption("Used to convert USD balances (Apple Savings / Apple Card) into GBP for totals.")

fx1, fx2, fx3 = st.columns([1, 1, 2])
with fx1:
    use_live_new = st.toggle("Use live USD→GBP rate", value=use_live, key="fx_use_live")
with fx2:
    manual = st.number_input("Manual USD→GBP rate (if not live)", value=float(usd_to_gbp), step=0.01, format="%.4f")
with fx3:
    st.write(f"Live rate (cached): **{live_rate:.4f}**")
    st.write(f"Currently using: **{(live_rate if use_live_new else manual):.4f}**")

if st.button("Apply FX Settings"):
    st.session_state.app_state["fx_settings"] = {
        "use_live": bool(use_live_new),
        "usd_to_gbp_manual": float(manual),
    }
    st.rerun()
