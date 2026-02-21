import io
import json
import zipfile
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Stabler Family Finances", layout="wide")

SCHEMA_VERSION = "2026-02-21-stabler-finances-stable-v6-fx-provider-erapi-timestamp"

GBP = "GBP"
USD = "USD"
CURRENCY_SYMBOL = {GBP: "£", USD: "$"}

# ------------------------
# Styling (restore KPI look)
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
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def current_month_yyyy_mm() -> str:
    return datetime.now().strftime("%Y-%m")

def month_options_yyyy_mm() -> list[str]:
    """
    Dropdown options: a rolling window of months (current year ± 2 years).
    Format: YYYY-MM
    Includes "" as first option to allow blank.
    """
    now = datetime.now()
    start_year = now.year - 2
    end_year = now.year + 2
    opts = [""]
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            opts.append(f"{y:04d}-{m:02d}")
    return opts

def cls(x: float) -> str:
    x = float(x)
    if x > 0:
        return "pos"
    if x < 0:
        return "neg"
    return "neu"

def badge(text: str, kind: str = "neutral"):
    klass = {"ok": "badge-ok", "warn": "badge-warn", "neutral": "badge-neutral"}.get(kind, "badge-neutral")
    st.markdown(f"<span class='badge {klass}'>{text}</span>", unsafe_allow_html=True)

def parse_money(value) -> float:
    """
    Accepts numbers or strings like "£1,234.50", "$8,803.50", "8803.5"
    Returns float. Empty/None -> 0.0
    """
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
        .replace("“", "")
        .replace("”", "")
        .replace('"', "")
        .replace("'", "")
    )

    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]

    try:
        v = float(s)
        return -v if neg else v
    except Exception:
        return 0.0

def fmt_money(amount: float, currency: str) -> str:
    sym = CURRENCY_SYMBOL.get((currency or GBP).upper(), "")
    return f"{sym}{float(amount):,.2f}"

# ------------------------
# FX feed (UPDATED PROVIDER + 60s cache)
# ------------------------
@st.cache_data(ttl=60)  # refresh at most once per minute
def fetch_usd_to_gbp() -> float:
    # ExchangeRate-API community endpoint (no key)
    r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
    r.raise_for_status()
    data = r.json()
    rates = data.get("rates", {})
    gbp = rates.get("GBP", None)
    if gbp is None:
        raise ValueError("GBP rate missing in FX response")
    return float(gbp)

def get_usd_to_gbp_rate() -> float:
    try:
        return fetch_usd_to_gbp()
    except Exception:
        return 0.80

def to_gbp(amount: float, currency: str, usd_to_gbp: float) -> float:
    cur = (currency or GBP).upper()
    if cur == GBP:
        return float(amount)
    if cur == USD:
        return float(amount) * float(usd_to_gbp)
    return float(amount)

def kpi(label: str, value_gbp: float, force_neutral: bool = False):
    css = "neu" if force_neutral else cls(value_gbp)
    st.markdown(
        f"""
<div class="kpi">
  <div class="label">{label}</div>
  <div class="value {css}">{fmt_money(value_gbp, GBP)}</div>
</div>
""",
        unsafe_allow_html=True,
    )

def totals_line(label: str, value_gbp: float):
    st.markdown(
        f"""<div class="totals">{label} <span class="{cls(value_gbp)}">{fmt_money(value_gbp, GBP)}</span></div>""",
        unsafe_allow_html=True,
    )

# ------------------------
# Fixed row templates
# ------------------------
ASSET_ROWS = [
    ("HSBC", GBP),
    ("Lloyds", GBP),
    ("Apple Savings", USD),
]

CARD_ROWS = [
    ("Amex", GBP),
    ("Apple Card", USD),
    ("Lloyds", GBP),
]

REIM_ROWS = [
    ("Eric Work", True),
    ("Gigi Work", True),
    ("Misc", False),
]

PAY_ROWS = [
    ("Eric", 6100.0),
    ("Gigi", 6000.0),
]

# ------------------------
# Defaults
# ------------------------
def defaults_assets():
    return pd.DataFrame([{"Account": a, "Currency": c, "Balance": 0.0} for a, c in ASSET_ROWS])

def defaults_cards():
    return pd.DataFrame([{"Card": n, "Currency": c, "Balance": 0.0, "Balance Due": 0.0} for n, c in CARD_ROWS])

def defaults_reim():
    return pd.DataFrame([{"Source": s, "Amount": 0.0, "Include?": inc} for s, inc in REIM_ROWS])

def defaults_fixed():
    return pd.DataFrame(
        [
            {"Item": "Savings", "Amount": 5000.00, "Due?": True},
            {"Item": "RAC", "Amount": 300.00, "Due?": True},
            {"Item": "Car Loan", "Amount": 480.37, "Due?": True},
            {"Item": "Marchon", "Amount": 133.10, "Due?": True},
            {"Item": "Utilities", "Amount": 425.00, "Due?": True},
            {"Item": "Eric Vodafone", "Amount": 38.00, "Due?": True},
            {"Item": "Eric Haircut", "Amount": 35.00, "Due?": True},
            {"Item": "Eric iphone", "Amount": 35.11, "Due?": True},
            {"Item": "Cleaning", "Amount": 72.00, "Due?": True},
            {"Item": "Gigi Vodafone", "Amount": 38.00, "Due?": True},
            {"Item": "Gigi Gym", "Amount": 79.00, "Due?": True},
            {"Item": "Caroline Circuits", "Amount": 35.00, "Due?": True},
            {"Item": "Gigi Charity", "Amount": 12.00, "Due?": True},
            {"Item": "G+ E Contacts", "Amount": 95.00, "Due?": True},
        ]
    )

def defaults_pay():
    # Paid? checkbox is used as "exclude from projection" (ticked => excluded)
    return pd.DataFrame([{"Person": p, "Monthly Pay": amt, "Paid?": False} for p, amt in PAY_ROWS])

def defaults_rac_bills():
    return pd.DataFrame(columns=["Purchase", "Amount", "Month"])

def default_state():
    return {
        "assets": defaults_assets(),
        "credit_cards": defaults_cards(),
        "reimbursements": defaults_reim(),
        "fixed_costs": defaults_fixed(),
        "pay_cycle": defaults_pay(),
        "rac_bills": defaults_rac_bills(),
        "fx": {"use_live": True, "manual_usd_gbp": 0.80},
    }

# ------------------------
# Enforce / Normalize
# ------------------------
def enforce_assets(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "Balance" not in df.columns:
        df["Balance"] = 0.0
    out = []
    for name, cur in ASSET_ROWS:
        m = df[df.get("Account", "").astype(str).str.lower() == name.lower()]
        bal = parse_money(m["Balance"].iloc[0]) if len(m) else 0.0
        out.append({"Account": name, "Currency": cur, "Balance": bal})
    return pd.DataFrame(out)

def enforce_cards(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["Balance", "Balance Due"]:
        if col not in df.columns:
            df[col] = 0.0
    out = []
    for name, cur in CARD_ROWS:
        m = df[df.get("Card", "").astype(str).str.lower() == name.lower()]
        bal = parse_money(m["Balance"].iloc[0]) if len(m) else 0.0
        due = parse_money(m["Balance Due"].iloc[0]) if len(m) else 0.0
        out.append({"Card": name, "Currency": cur, "Balance": bal, "Balance Due": due})
    return pd.DataFrame(out)

def enforce_reim(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "Amount" not in df.columns:
        df["Amount"] = 0.0
    if "Include?" not in df.columns:
        df["Include?"] = False
    out = []
    for src, default_inc in REIM_ROWS:
        m = df[df.get("Source", "").astype(str).str.lower() == src.lower()]
        amt = parse_money(m["Amount"].iloc[0]) if len(m) else 0.0
        inc = bool(m["Include?"].iloc[0]) if len(m) else bool(default_inc)
        out.append({"Source": src, "Amount": amt, "Include?": inc})
    return pd.DataFrame(out)

def enforce_pay(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "Monthly Pay" not in df.columns:
        df["Monthly Pay"] = 0.0
    if "Paid?" not in df.columns:
        df["Paid?"] = False
    out = []
    for person, default_pay in PAY_ROWS:
        m = df[df.get("Person", "").astype(str).str.lower() == person.lower()]
        pay = parse_money(m["Monthly Pay"].iloc[0]) if len(m) else float(default_pay)
        paid = bool(m["Paid?"].iloc[0]) if len(m) else False
        out.append({"Person": person, "Monthly Pay": pay, "Paid?": paid})
    return pd.DataFrame(out)

def normalize_fixed(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "Item" not in df.columns:
        df["Item"] = ""
    if "Amount" not in df.columns:
        if "Amount (GBP)" in df.columns:
            df = df.rename(columns={"Amount (GBP)": "Amount"})
        else:
            df["Amount"] = 0.0
    if "Due?" not in df.columns:
        df["Due?"] = True

    df["Item"] = df["Item"].astype(str).str.strip()
    df["Amount"] = df["Amount"].apply(parse_money)
    df["Due?"] = df["Due?"].fillna(True).astype(bool)
    return df[["Item", "Amount", "Due?"]]

def normalize_rac_bills(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "Purchase" not in df.columns:
        df["Purchase"] = ""
    if "Amount" not in df.columns:
        df["Amount"] = 0.0
    if "Month" not in df.columns:
        df["Month"] = ""

    df["Purchase"] = df["Purchase"].astype(str).str.strip()
    df["Amount"] = df["Amount"].apply(parse_money)
    df["Month"] = df["Month"].fillna("").astype(str).str.strip()
    return df[["Purchase", "Amount", "Month"]]

# ------------------------
# ZIP backup / restore (compatible)
# ------------------------
def state_to_zip_bytes(state: dict) -> bytes:
    meta = {
        "schema_version": SCHEMA_VERSION,
        "saved_at_utc": utc_now_iso(),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("meta.json", json.dumps(meta, indent=2))
        z.writestr("assets.csv", state["assets"].to_csv(index=False))
        z.writestr("credit_cards.csv", state["credit_cards"].to_csv(index=False))
        z.writestr("reimbursements.csv", state["reimbursements"].to_csv(index=False))
        z.writestr("fixed_costs.csv", state["fixed_costs"].to_csv(index=False))
        z.writestr("pay_cycle.csv", state["pay_cycle"].to_csv(index=False))
        z.writestr("rac_bills.csv", state.get("rac_bills", defaults_rac_bills()).to_csv(index=False))
        z.writestr("fx.json", json.dumps(state.get("fx", {"use_live": True, "manual_usd_gbp": 0.80}), indent=2))
    return buf.getvalue()

def zip_bytes_to_state(b: bytes) -> dict | None:
    try:
        with zipfile.ZipFile(io.BytesIO(b), "r") as z:
            names = set(z.namelist())
            required = {"assets.csv", "credit_cards.csv", "reimbursements.csv", "fixed_costs.csv", "pay_cycle.csv"}
            if not required.issubset(names):
                return None

            assets = pd.read_csv(z.open("assets.csv"))
            cards = pd.read_csv(z.open("credit_cards.csv"))
            reim = pd.read_csv(z.open("reimbursements.csv"))
            fixed = pd.read_csv(z.open("fixed_costs.csv"))
            pay = pd.read_csv(z.open("pay_cycle.csv"))

            if "rac_bills.csv" in names:
                rac = pd.read_csv(z.open("rac_bills.csv"))
            else:
                rac = defaults_rac_bills()

            fx = {"use_live": True, "manual_usd_gbp": 0.80}
            if "fx.json" in names:
                try:
                    fx = json.loads(z.read("fx.json").decode("utf-8"))
                except Exception:
                    pass

            state = {
                "assets": enforce_assets(assets),
                "credit_cards": enforce_cards(cards),
                "reimbursements": enforce_reim(reim),
                "fixed_costs": normalize_fixed(fixed),
                "pay_cycle": enforce_pay(pay),
                "rac_bills": normalize_rac_bills(rac),
                "fx": {
                    "use_live": bool(fx.get("use_live", True)),
                    "manual_usd_gbp": float(fx.get("manual_usd_gbp", 0.80)),
                },
            }
            return state
    except Exception:
        return None

# ------------------------
# Session init
# ------------------------
if "app_state" not in st.session_state:
    st.session_state.app_state = default_state()

if "pending_zip_bytes" not in st.session_state:
    st.session_state.pending_zip_bytes = None

# ------------------------
# Sidebar: Save / Load
# ------------------------
with st.sidebar:
    st.subheader("Save / Load")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_bytes = state_to_zip_bytes(st.session_state.app_state)

    st.download_button(
        "⬇️ Download backup (ZIP)",
        data=zip_bytes,
        file_name=f"stabler-finances-backup-{stamp}.zip",
        mime="application/zip",
        use_container_width=True,
    )

    up = st.file_uploader("Restore from backup (ZIP)", type=["zip"])
    if up is not None:
        st.session_state.pending_zip_bytes = up.read()

    if st.session_state.pending_zip_bytes is not None:
        badge("Pending ZIP loaded (not applied)", "warn")
        st.caption("Tap “Update sheet from uploaded ZIP” to apply it.")

    if st.button("Update sheet from uploaded ZIP", use_container_width=True):
        if st.session_state.pending_zip_bytes is None:
            st.warning("Upload a ZIP first.")
        else:
            restored = zip_bytes_to_state(st.session_state.pending_zip_bytes)
            if restored is None:
                st.error("That ZIP doesn’t match the expected backup format.")
            else:
                st.session_state.app_state = restored
                st.session_state.pending_zip_bytes = None
                st.success("Backup restored.")
                st.rerun()

    st.write("")
    if st.button("Reset to defaults", use_container_width=True):
        st.session_state.app_state = default_state()
        st.session_state.pending_zip_bytes = None
        st.rerun()

# ------------------------
# FX
# ------------------------
state = st.session_state.app_state
fx_cfg = state.get("fx", {"use_live": True, "manual_usd_gbp": 0.80})

# Store a "last refreshed" timestamp in session when we actually *pull* FX.
# - It will still auto-refresh via cache every 60s, but this gives you a visible "last pull".
if "fx_last_refresh_local" not in st.session_state:
    st.session_state.fx_last_refresh_local = None

usd_to_gbp_live = get_usd_to_gbp_rate()

# If you are using live FX, totals use usd_to_gbp_live. Otherwise manual.
usd_to_gbp = usd_to_gbp_live if fx_cfg.get("use_live", True) else float(fx_cfg.get("manual_usd_gbp", 0.80))

# ------------------------
# Load tables
# ------------------------
assets_df = state["assets"].copy()
cards_df = state["credit_cards"].copy()
reim_df = state["reimbursements"].copy()
fixed_df = normalize_fixed(state["fixed_costs"].copy())
pay_df = state["pay_cycle"].copy()
rac_df = normalize_rac_bills(state.get("rac_bills", defaults_rac_bills()).copy())

# ------------------------
# RAC (current month liability)
# ------------------------
THIS_MONTH = current_month_yyyy_mm()
rac_df["Month"] = rac_df["Month"].fillna("").astype(str).str.strip()
rac_due_this_month_gbp = float(rac_df.loc[rac_df["Month"] == THIS_MONTH, "Amount"].apply(parse_money).sum())

# ------------------------
# Calculations
# ------------------------
assets_total_gbp = float(
    sum(to_gbp(parse_money(r["Balance"]), r["Currency"], usd_to_gbp) for _, r in assets_df.iterrows())
)
cards_balance_total_gbp = float(
    sum(to_gbp(parse_money(r["Balance"]), r["Currency"], usd_to_gbp) for _, r in cards_df.iterrows())
)
cards_due_total_gbp = float(
    sum(to_gbp(parse_money(r["Balance Due"]), r["Currency"], usd_to_gbp) for _, r in cards_df.iterrows())
)

reim_included_gbp = float(reim_df.loc[reim_df["Include?"] == True, "Amount"].apply(parse_money).sum())  # noqa: E712
fixed_due_gbp = float(fixed_df.loc[fixed_df["Due?"] == True, "Amount"].sum())  # noqa: E712

# FLIPPED LOGIC:
# Unticked (Paid? == False) salaries are INCLUDED in projection.
# Ticked (Paid? == True) are EXCLUDED from projection.
pay_included_gbp = float(pay_df.loc[pay_df["Paid?"] == False, "Monthly Pay"].apply(parse_money).sum())  # noqa: E712

# RAC is a bill/liability -> subtract it (current month only)
net_cash_gbp = assets_total_gbp + reim_included_gbp - cards_balance_total_gbp - rac_due_this_month_gbp
remaining_spending_gbp = net_cash_gbp + (pay_included_gbp - fixed_due_gbp)

ability_to_repay = assets_total_gbp >= cards_due_total_gbp

# ------------------------
# KPIs
# ------------------------
k1, k2, k3 = st.columns(3)
with k1:
    kpi("Net Cash (GBP)", net_cash_gbp)

with k2:
    st.markdown(
        f"""
<div class="kpi">
  <div class="label">Total Credit Card Bill Due (GBP)</div>
  <div class="value neu">{fmt_money(cards_due_total_gbp, GBP)}</div>
  <div style="margin-top:8px;">
    <span class="badge {'badge-ok' if ability_to_repay else 'badge-warn'}">
      Ability to repay: {'Yes' if ability_to_repay else 'No'}
    </span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

with k3:
    kpi("Remaining spending this month (GBP)", remaining_spending_gbp)

st.divider()

# ------------------------
# Row 1: Assets | Credit Cards | Reimbursements
# ------------------------
a, b, c = st.columns([1.2, 1.1, 1.1])

with a:
    st.subheader("Assets")

    assets_edit = assets_df.copy()
    assets_edit["Balance"] = assets_edit.apply(lambda r: fmt_money(parse_money(r["Balance"]), r["Currency"]), axis=1)

    edited_assets = st.data_editor(
        assets_edit[["Account", "Currency", "Balance"]],
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "Account": st.column_config.TextColumn("Account", disabled=True),
            "Currency": st.column_config.TextColumn("Currency", disabled=True),
            "Balance": st.column_config.TextColumn("Balance"),
        },
        key="assets_editor",
    )

    if st.button("Apply Assets Changes", use_container_width=True):
        new_assets = assets_df.copy()
        new_assets["Balance"] = edited_assets["Balance"].apply(parse_money)
        st.session_state.app_state["assets"] = enforce_assets(new_assets)
        st.rerun()

    totals_line("Total Assets (GBP):", assets_total_gbp)

with b:
    st.subheader("Credit Cards")

    cards_edit = cards_df.copy()
    cards_edit["Balance"] = cards_edit.apply(lambda r: fmt_money(parse_money(r["Balance"]), r["Currency"]), axis=1)
    cards_edit["Balance Due"] = cards_edit.apply(lambda r: fmt_money(parse_money(r["Balance Due"]), r["Currency"]), axis=1)

    edited_cards = st.data_editor(
        cards_edit[["Card", "Balance", "Balance Due"]],
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "Card": st.column_config.TextColumn("Card", disabled=True),
            "Balance": st.column_config.TextColumn("Balance"),
            "Balance Due": st.column_config.TextColumn("Balance Due"),
        },
        key="cards_editor",
    )

    if st.button("Apply Credit Card Changes", use_container_width=True):
        new_cards = cards_df.copy()
        new_cards["Balance"] = edited_cards["Balance"].apply(parse_money)
        new_cards["Balance Due"] = edited_cards["Balance Due"].apply(parse_money)
        st.session_state.app_state["credit_cards"] = enforce_cards(new_cards)
        st.rerun()

    st.markdown(
        f"""
<div class="totals">
  Total Card Balances (GBP): <span class="{cls(cards_balance_total_gbp)}">{fmt_money(cards_balance_total_gbp, GBP)}</span>
  &nbsp;&nbsp;•&nbsp;&nbsp;
  Total Bills Due (GBP): <span class="neu">{fmt_money(cards_due_total_gbp, GBP)}</span>
</div>
""",
        unsafe_allow_html=True,
    )

with c:
    st.subheader("Reimbursement Pending")

    reim_edit = reim_df.copy()
    reim_edit["Amount"] = reim_edit["Amount"].apply(lambda v: fmt_money(parse_money(v), GBP))

    edited_reim = st.data_editor(
        reim_edit[["Source", "Amount", "Include?"]],
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "Source": st.column_config.TextColumn("Source", disabled=True),
            "Amount": st.column_config.TextColumn("Amount"),
            "Include?": st.column_config.CheckboxColumn("Include?"),
        },
        key="reim_editor",
    )

    if st.button("Apply Reimbursement Changes", use_container_width=True):
        new_reim = reim_df.copy()
        new_reim["Amount"] = edited_reim["Amount"].apply(parse_money)
        new_reim["Include?"] = edited_reim["Include?"].fillna(False).astype(bool)
        st.session_state.app_state["reimbursements"] = enforce_reim(new_reim)
        st.rerun()

    totals_line("Included Reimbursements (GBP):", reim_included_gbp)

st.divider()

# ------------------------
# Row 2: Monthly Fixed | (Right column stacks RAC Bills then Pay)
# ------------------------
d, e = st.columns([2.1, 1.0])

with d:
    st.subheader("Monthly Fixed")

    fixed_edit = fixed_df.copy()
    fixed_edit["Amount"] = fixed_edit["Amount"].apply(lambda v: fmt_money(parse_money(v), GBP))

    edited_fixed = st.data_editor(
        fixed_edit[["Item", "Amount", "Due?"]],
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Item": st.column_config.TextColumn("Item"),
            "Amount": st.column_config.TextColumn("Amount"),
            "Due?": st.column_config.CheckboxColumn("Due?"),
        },
        key="fixed_editor",
    )

    if st.button("Apply Monthly Fixed Changes", use_container_width=True):
        new_fixed = edited_fixed.copy()
        new_fixed["Amount"] = new_fixed["Amount"].apply(parse_money)
        new_fixed["Due?"] = new_fixed["Due?"].fillna(True).astype(bool)
        st.session_state.app_state["fixed_costs"] = normalize_fixed(new_fixed)
        st.rerun()

    st.markdown(
        f"""
<div class="totals">
  Fixed Due This Month: <span class="neu">{fmt_money(fixed_due_gbp, GBP)}</span>
</div>
""",
        unsafe_allow_html=True,
    )

with e:
    st.subheader("RAC monthly bill")

    rac_edit = rac_df.copy()
    rac_edit["Amount"] = rac_edit["Amount"].apply(lambda v: fmt_money(parse_money(v), GBP))

    edited_rac = st.data_editor(
        rac_edit[["Purchase", "Amount", "Month"]],
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Purchase": st.column_config.TextColumn("Purchase"),
            "Amount": st.column_config.TextColumn("Amount"),
            "Month": st.column_config.SelectboxColumn("Month", options=month_options_yyyy_mm()),
        },
        key="rac_editor",
    )

    if st.button("Apply RAC Bill Changes", use_container_width=True):
        new_rac = edited_rac.copy()
        new_rac["Amount"] = new_rac["Amount"].apply(parse_money)

        default_m = current_month_yyyy_mm()
        new_rac["Month"] = new_rac["Month"].fillna("").astype(str).str.strip()
        new_rac.loc[new_rac["Month"] == "", "Month"] = default_m

        st.session_state.app_state["rac_bills"] = normalize_rac_bills(new_rac)
        st.rerun()

    totals_line(f"RAC due this month ({THIS_MONTH}):", rac_due_this_month_gbp)

    st.write("")

    st.subheader("Monthly Pay")
    st.caption("Unticked salaries are included in projection. Tick Paid? once received to exclude from projection.")

    pay_edit = pay_df.copy()
    pay_edit["Monthly Pay"] = pay_edit["Monthly Pay"].apply(lambda v: fmt_money(parse_money(v), GBP))

    edited_pay = st.data_editor(
        pay_edit[["Person", "Monthly Pay", "Paid?"]],
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "Person": st.column_config.TextColumn("Person", disabled=True),
            "Monthly Pay": st.column_config.TextColumn("Monthly Pay"),
            "Paid?": st.column_config.CheckboxColumn("Paid?"),
        },
        key="pay_editor",
    )

    if st.button("Apply Pay Changes", use_container_width=True):
        new_pay = pay_df.copy()
        new_pay["Monthly Pay"] = edited_pay["Monthly Pay"].apply(parse_money)
        new_pay["Paid?"] = edited_pay["Paid?"].fillna(False).astype(bool)
        st.session_state.app_state["pay_cycle"] = enforce_pay(new_pay)
        st.rerun()

    totals_line("Total Pay Included (Unticked):", pay_included_gbp)

st.divider()

# ------------------------
# FX bottom (UPDATED: refresh button + timestamp)
# ------------------------
st.subheader("FX (USD → GBP)")
st.caption("Used only for converting USD balances (Apple Savings / Apple Card) into GBP totals.")

fxl, fxr = st.columns([1.2, 1.0])

with fxl:
    st.markdown(
        f"""<div class="totals">Live USD→GBP (cached): <span class="neu">{usd_to_gbp_live:.4f}</span></div>""",
        unsafe_allow_html=True,
    )

    if st.session_state.fx_last_refresh_local is not None:
        st.caption(f"Last refreshed: {st.session_state.fx_last_refresh_local}")

    if st.button("🔄 Pull current rate", use_container_width=True):
        # Force a fresh HTTP call on next run
        fetch_usd_to_gbp.clear()
        # Record local timestamp (London-ish display; no tz lib needed)
        st.session_state.fx_last_refresh_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.rerun()

with fxr:
    use_live = st.toggle("Use live FX", value=bool(fx_cfg.get("use_live", True)))
    manual = st.number_input("Manual USD→GBP", value=float(fx_cfg.get("manual_usd_gbp", 0.80)), step=0.0001, format="%.4f")

    if st.button("Apply FX Settings", use_container_width=True):
        st.session_state.app_state["fx"] = {"use_live": bool(use_live), "manual_usd_gbp": float(manual)}
        st.rerun()
