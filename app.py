import io
import json
import zipfile
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title=“Stabler Family Finances”, layout=“wide”)

SCHEMA_VERSION = “2026-02-21-stabler-finances-stable-v10-snapshot-fix”

GBP = “GBP”
USD = “USD”
CURRENCY_SYMBOL = {GBP: “£”, USD: “$”}

# ————————

# Styling

# ————————

st.markdown(
“””

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

/* Snapshot panel */
.snapshot-panel {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 10px;
  padding: 16px 20px 14px 20px;
  margin: 4px 0 12px 0;
}
.snapshot-panel .sp-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.55;
  margin-bottom: 12px;
}
.snapshot-panel .sp-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  font-size: 13px;
}
.snapshot-panel .sp-row:last-child { border-bottom: none; }
.snapshot-panel .sp-label { opacity: 0.65; }
.snapshot-panel .sp-val { font-weight: 600; }
.snapshot-panel .pos { color: #2ECC71; }
.snapshot-panel .neg { color: #FF4B4B; }
.snapshot-panel .neu { color: rgba(255,255,255,0.85); }

.snapshot-delta-bar {
  background: rgba(255,255,255,0.04);
  border-left: 3px solid rgba(255,255,255,0.15);
  border-radius: 0 8px 8px 0;
  padding: 10px 16px;
  margin: 6px 0 10px 0;
  font-size: 13px;
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  align-items: center;
}
.snapshot-delta-bar .sd-item { display: flex; flex-direction: column; gap: 2px; }
.snapshot-delta-bar .sd-label { font-size: 11px; opacity: 0.55; text-transform: uppercase; letter-spacing: 0.06em; }
.snapshot-delta-bar .sd-val { font-weight: 700; font-size: 15px; }

div[data-testid="stSidebar"] .stButton button,
div[data-testid="stSidebar"] .stDownloadButton button {
    width: 100%;
}
</style>

“””,
unsafe_allow_html=True,
)

st.title(“Stabler Family Finances”)

# ————————

# Helpers

# ————————

def utc_now_iso():
return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def local_now_str():
return datetime.now().strftime(”%Y-%m-%d %H:%M:%S”)

def current_month_yyyy_mm() -> str:
return datetime.now().strftime(”%Y-%m”)

def month_options_yyyy_mm() -> list[str]:
now = datetime.now()
start_year = now.year - 2
end_year = now.year + 2
opts = [””]
for y in range(start_year, end_year + 1):
for m in range(1, 13):
opts.append(f”{y:04d}-{m:02d}”)
return opts

def cls(x: float) -> str:
x = float(x)
if x > 0:
return “pos”
if x < 0:
return “neg”
return “neu”

def badge(text: str, kind: str = “neutral”):
klass = {“ok”: “badge-ok”, “warn”: “badge-warn”, “neutral”: “badge-neutral”}.get(kind, “badge-neutral”)
st.markdown(f”<span class='badge {klass}'>{text}</span>”, unsafe_allow_html=True)

def fmt_money(amount: float, currency: str) -> str:
sym = CURRENCY_SYMBOL.get((currency or GBP).upper(), “”)
return f”{sym}{float(amount):,.2f}”

def fmt_money_signed(amount: float, currency: str) -> str:
sym = CURRENCY_SYMBOL.get((currency or GBP).upper(), “”)
if amount >= 0:
return f”+{sym}{float(amount):,.2f}”
return f”-{sym}{abs(float(amount)):,.2f}”

def kpi(label: str, value_gbp: float, force_neutral: bool = False):
css = “neu” if force_neutral else cls(value_gbp)
st.markdown(
f”””

<div class="kpi">
  <div class="label">{label}</div>
  <div class="value {css}">{fmt_money(value_gbp, GBP)}</div>
</div>
""",
        unsafe_allow_html=True,
    )

def totals_line(label: str, value_gbp: float):
st.markdown(
f”””<div class="totals">{label} <span class="{cls(value_gbp)}">{fmt_money(value_gbp, GBP)}</span></div>”””,
unsafe_allow_html=True,
)

# ————————

# Money parsing

# ————————

def parse_money(value) -> float:
“”“Silent parser for saved/loaded values (ZIP/CSV).”””
if value is None:
return 0.0
if isinstance(value, (int, float)):
return float(value)

```
s = str(value).strip()
if s == "":
    return 0.0

s = (
    s.replace("£", "")
    .replace("$", "")
    .replace(",", "")
    .replace(" ", "")
    .replace("\u00A0", "")
    .replace("\u201c", "")
    .replace("\u201d", "")
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
```

def _parse_plus_minus_expr(value) -> tuple[float, bool]:
“”“Supports + and - only. Returns (value, ok).”””
if value is None:
return 0.0, True
if isinstance(value, (int, float)):
return float(value), True

```
s = str(value).strip()
if s == "":
    return 0.0, True

s = (
    s.replace("£", "")
    .replace("$", "")
    .replace(",", "")
    .replace(" ", "")
    .replace("\u00A0", "")
    .replace("\u201c", "")
    .replace("\u201d", "")
    .replace('"', "")
    .replace("'", "")
    .strip()
)

allowed = set("0123456789+-.")
if not set(s).issubset(allowed):
    return 0.0, False
if not any(ch.isdigit() for ch in s):
    return 0.0, False

try:
    total = 0.0
    current = ""
    operator = "+"

    for ch in s + "+":
        if ch in "+-":
            if current == "":
                return 0.0, False
            num = float(current)
            total = total + num if operator == "+" else total - num
            current = ""
            operator = ch
        else:
            current += ch

    return total, True
except Exception:
    return 0.0, False
```

def parse_money_user(value, context: str, errors: list[str]) -> float:
“”“Parser for user edits. Logs context on invalid values.”””
num, ok = _parse_plus_minus_expr(value)
if not ok:
errors.append(context)
return 0.0
return float(num)

# ————————

# FX feed (provider + 60s cache)

# ————————

@st.cache_data(ttl=60)
def fetch_usd_to_gbp() -> float:
r = requests.get(“https://open.er-api.com/v6/latest/USD”, timeout=8)
r.raise_for_status()
data = r.json()
rates = data.get(“rates”, {})
gbp = rates.get(“GBP”, None)
if gbp is None:
raise ValueError(“GBP rate missing in FX response”)
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

# ————————

# Fixed row templates

# ————————

ASSET_ROWS = [
(“HSBC”, GBP),
(“Lloyds”, GBP),
(“Apple Savings”, USD),
]

CARD_ROWS = [
(“Amex”, GBP),
(“Apple Card”, USD),
(“Lloyds”, GBP),
]

REIM_ROWS = [
(“Eric Work”, True),
(“Gigi Work”, True),
(“Misc”, False),
]

PAY_ROWS = [
(“Eric”, 6100.0),
(“Gigi”, 6000.0),
]

# ————————

# Defaults

# ————————

def defaults_assets():
return pd.DataFrame([{“Account”: a, “Currency”: c, “Balance”: 0.0} for a, c in ASSET_ROWS])

def defaults_cards():
return pd.DataFrame([{“Card”: n, “Currency”: c, “Balance”: 0.0, “Balance Due”: 0.0} for n, c in CARD_ROWS])

def defaults_reim():
return pd.DataFrame([{“Source”: s, “Amount”: 0.0, “Include?”: inc} for s, inc in REIM_ROWS])

def defaults_fixed():
return pd.DataFrame(
[
{“Item”: “Savings”, “Amount”: 5000.00, “Due?”: True},
{“Item”: “RAC”, “Amount”: 300.00, “Due?”: True},
{“Item”: “Car Loan”, “Amount”: 480.37, “Due?”: True},
{“Item”: “Marchon”, “Amount”: 133.10, “Due?”: True},
{“Item”: “Utilities”, “Amount”: 425.00, “Due?”: True},
{“Item”: “Eric Vodafone”, “Amount”: 38.00, “Due?”: True},
{“Item”: “Eric Haircut”, “Amount”: 35.00, “Due?”: True},
{“Item”: “Eric iphone”, “Amount”: 35.11, “Due?”: True},
{“Item”: “Cleaning”, “Amount”: 72.00, “Due?”: True},
{“Item”: “Gigi Vodafone”, “Amount”: 38.00, “Due?”: True},
{“Item”: “Gigi Gym”, “Amount”: 79.00, “Due?”: True},
{“Item”: “Caroline Circuits”, “Amount”: 35.00, “Due?”: True},
{“Item”: “Gigi Charity”, “Amount”: 12.00, “Due?”: True},
{“Item”: “G+ E Contacts”, “Amount”: 95.00, “Due?”: True},
]
)

def defaults_pay():
return pd.DataFrame([{“Person”: p, “Monthly Pay”: amt, “Paid?”: False} for p, amt in PAY_ROWS])

def defaults_rac_bills():
return pd.DataFrame(columns=[“Purchase”, “Amount”, “Month”])

def default_state():
return {
“assets”: defaults_assets(),
“credit_cards”: defaults_cards(),
“reimbursements”: defaults_reim(),
“fixed_costs”: defaults_fixed(),
“pay_cycle”: defaults_pay(),
“rac_bills”: defaults_rac_bills(),
“fx”: {“use_live”: True, “manual_usd_gbp”: 0.80},
“snapshot”: None,
}

# ————————

# Enforce / Normalize

# ————————

def enforce_assets(df: pd.DataFrame) -> pd.DataFrame:
df = df.copy()
if “Balance” not in df.columns:
df[“Balance”] = 0.0
out = []
for name, cur in ASSET_ROWS:
m = df[df[“Account”].astype(str).str.lower() == name.lower()]
bal = parse_money(m[“Balance”].iloc[0]) if len(m) else 0.0
out.append({“Account”: name, “Currency”: cur, “Balance”: bal})
return pd.DataFrame(out)

def enforce_cards(df: pd.DataFrame) -> pd.DataFrame:
df = df.copy()
for col in [“Balance”, “Balance Due”]:
if col not in df.columns:
df[col] = 0.0
out = []
for name, cur in CARD_ROWS:
m = df[df[“Card”].astype(str).str.lower() == name.lower()]
bal = parse_money(m[“Balance”].iloc[0]) if len(m) else 0.0
due = parse_money(m[“Balance Due”].iloc[0]) if len(m) else 0.0
out.append({“Card”: name, “Currency”: cur, “Balance”: bal, “Balance Due”: due})
return pd.DataFrame(out)

def enforce_reim(df: pd.DataFrame) -> pd.DataFrame:
df = df.copy()
if “Amount” not in df.columns:
df[“Amount”] = 0.0
if “Include?” not in df.columns:
df[“Include?”] = False
out = []
for src, default_inc in REIM_ROWS:
m = df[df[“Source”].astype(str).str.lower() == src.lower()]
amt = parse_money(m[“Amount”].iloc[0]) if len(m) else 0.0
inc = bool(m[“Include?”].iloc[0]) if len(m) else bool(default_inc)
out.append({“Source”: src, “Amount”: amt, “Include?”: inc})
return pd.DataFrame(out)

def enforce_pay(df: pd.DataFrame) -> pd.DataFrame:
df = df.copy()
if “Monthly Pay” not in df.columns:
df[“Monthly Pay”] = 0.0
if “Paid?” not in df.columns:
df[“Paid?”] = False
out = []
for person, default_pay in PAY_ROWS:
m = df[df[“Person”].astype(str).str.lower() == person.lower()]
pay = parse_money(m[“Monthly Pay”].iloc[0]) if len(m) else float(default_pay)
paid = bool(m[“Paid?”].iloc[0]) if len(m) else False
out.append({“Person”: person, “Monthly Pay”: pay, “Paid?”: paid})
return pd.DataFrame(out)

def normalize_fixed(df: pd.DataFrame) -> pd.DataFrame:
df = df.copy()
if “Item” not in df.columns:
df[“Item”] = “”
if “Amount” not in df.columns:
if “Amount (GBP)” in df.columns:
df = df.rename(columns={“Amount (GBP)”: “Amount”})
else:
df[“Amount”] = 0.0
if “Due?” not in df.columns:
df[“Due?”] = True

```
df["Item"] = df["Item"].astype(str).str.strip()
df["Amount"] = df["Amount"].apply(parse_money)
df["Due?"] = df["Due?"].fillna(True).astype(bool)
return df[["Item", "Amount", "Due?"]]
```

def normalize_rac_bills(df: pd.DataFrame) -> pd.DataFrame:
df = df.copy()
if “Purchase” not in df.columns:
df[“Purchase”] = “”
if “Amount” not in df.columns:
df[“Amount”] = 0.0
if “Month” not in df.columns:
df[“Month”] = “”

```
df["Purchase"] = df["Purchase"].astype(str).str.strip()
df["Amount"] = df["Amount"].apply(parse_money)
df["Month"] = df["Month"].fillna("").astype(str).str.strip()
return df[["Purchase", "Amount", "Month"]]
```

# ————————

# ZIP backup / restore

# ————————

def state_to_zip_bytes(state: dict) -> bytes:
meta = {“schema_version”: SCHEMA_VERSION, “saved_at_utc”: utc_now_iso()}
buf = io.BytesIO()
with zipfile.ZipFile(buf, “w”, compression=zipfile.ZIP_DEFLATED) as z:
z.writestr(“meta.json”, json.dumps(meta, indent=2))
z.writestr(“assets.csv”, state[“assets”].to_csv(index=False))
z.writestr(“credit_cards.csv”, state[“credit_cards”].to_csv(index=False))
z.writestr(“reimbursements.csv”, state[“reimbursements”].to_csv(index=False))
z.writestr(“fixed_costs.csv”, state[“fixed_costs”].to_csv(index=False))
z.writestr(“pay_cycle.csv”, state[“pay_cycle”].to_csv(index=False))
z.writestr(“rac_bills.csv”, state.get(“rac_bills”, defaults_rac_bills()).to_csv(index=False))
z.writestr(“fx.json”, json.dumps(state.get(“fx”, {“use_live”: True, “manual_usd_gbp”: 0.80}), indent=2))
z.writestr(“snapshot.json”, json.dumps(state.get(“snapshot”, None), indent=2))
return buf.getvalue()

def zip_bytes_to_state(b: bytes) -> dict | None:
try:
with zipfile.ZipFile(io.BytesIO(b), “r”) as z:
names = set(z.namelist())
required = {“assets.csv”, “credit_cards.csv”, “reimbursements.csv”, “fixed_costs.csv”, “pay_cycle.csv”}
if not required.issubset(names):
return None

```
        assets = pd.read_csv(z.open("assets.csv"))
        cards = pd.read_csv(z.open("credit_cards.csv"))
        reim = pd.read_csv(z.open("reimbursements.csv"))
        fixed = pd.read_csv(z.open("fixed_costs.csv"))
        pay = pd.read_csv(z.open("pay_cycle.csv"))
        rac = pd.read_csv(z.open("rac_bills.csv")) if "rac_bills.csv" in names else defaults_rac_bills()

        fx = {"use_live": True, "manual_usd_gbp": 0.80}
        if "fx.json" in names:
            try:
                fx = json.loads(z.read("fx.json").decode("utf-8"))
            except Exception:
                pass

        snapshot = None
        if "snapshot.json" in names:
            try:
                snapshot = json.loads(z.read("snapshot.json").decode("utf-8"))
            except Exception:
                snapshot = None

        return {
            "assets": enforce_assets(assets),
            "credit_cards": enforce_cards(cards),
            "reimbursements": enforce_reim(reim),
            "fixed_costs": normalize_fixed(fixed),
            "pay_cycle": enforce_pay(pay),
            "rac_bills": normalize_rac_bills(rac),
            "fx": {"use_live": bool(fx.get("use_live", True)), "manual_usd_gbp": float(fx.get("manual_usd_gbp", 0.80))},
            "snapshot": snapshot,
        }
except Exception:
    return None
```

# ————————

# Session init

# ————————

if “app_state” not in st.session_state:
st.session_state.app_state = default_state()
if “pending_zip_bytes” not in st.session_state:
st.session_state.pending_zip_bytes = None
if “fx_last_refresh_local” not in st.session_state:
st.session_state.fx_last_refresh_local = None
if “last_apply_errors” not in st.session_state:
st.session_state.last_apply_errors = []
if “last_apply_success” not in st.session_state:
st.session_state.last_apply_success = False

# ————————

# Pull current FX early (needed by snapshot save too)

# ————————

state = st.session_state.app_state
fx_cfg = state.get(“fx”, {“use_live”: True, “manual_usd_gbp”: 0.80})

usd_to_gbp_live = get_usd_to_gbp_rate()
usd_to_gbp = usd_to_gbp_live if fx_cfg.get(“use_live”, True) else float(fx_cfg.get(“manual_usd_gbp”, 0.80))

assets_df = state[“assets”].copy()
cards_df = state[“credit_cards”].copy()
reim_df = state[“reimbursements”].copy()
fixed_df = normalize_fixed(state[“fixed_costs”].copy())
pay_df = state[“pay_cycle”].copy()
rac_df = normalize_rac_bills(state.get(“rac_bills”, defaults_rac_bills()).copy())

# RAC current month

THIS_MONTH = current_month_yyyy_mm()
rac_df[“Month”] = rac_df[“Month”].fillna(””).astype(str).str.strip()
rac_due_this_month_gbp = float(rac_df.loc[rac_df[“Month”] == THIS_MONTH, “Amount”].apply(parse_money).sum())

# Core calculations

assets_total_gbp = float(sum(to_gbp(parse_money(r[“Balance”]), r[“Currency”], usd_to_gbp) for _, r in assets_df.iterrows()))
cards_balance_total_gbp = float(sum(to_gbp(parse_money(r[“Balance”]), r[“Currency”], usd_to_gbp) for _, r in cards_df.iterrows()))
cards_due_total_gbp = float(sum(to_gbp(parse_money(r[“Balance Due”]), r[“Currency”], usd_to_gbp) for _, r in cards_df.iterrows()))

reim_all_gbp = float(reim_df[“Amount”].apply(parse_money).sum())
reim_included_for_repay_gbp = float(reim_df.loc[reim_df[“Include?”] == True, “Amount”].apply(parse_money).sum())  # noqa: E712

fixed_due_gbp = float(fixed_df.loc[fixed_df[“Due?”] == True, “Amount”].sum())  # noqa: E712
pay_included_gbp = float(pay_df.loc[pay_df[“Paid?”] == False, “Monthly Pay”].apply(parse_money).sum())  # noqa: E712

net_cash_gbp = assets_total_gbp + reim_all_gbp - cards_balance_total_gbp - rac_due_this_month_gbp
remaining_spending_gbp = net_cash_gbp + (pay_included_gbp - fixed_due_gbp)

ability_surplus_gbp = (assets_total_gbp + reim_included_for_repay_gbp) - cards_due_total_gbp
ability_to_repay = ability_surplus_gbp >= 0

# Snapshot delta

snapshot = state.get(“snapshot”, None)
snapshot_net_cash = None
snapshot_time = None
snapshot_assets = None
snapshot_cards_bal = None
snapshot_cards_due = None
snapshot_reim = None
snapshot_remaining = None
spent_since_snapshot_gbp = None
delta_since_snapshot_gbp = None

if isinstance(snapshot, dict):
snapshot_net_cash = snapshot.get(“net_cash_gbp”, None)
snapshot_time = snapshot.get(“saved_at_local”, None)
snapshot_assets = snapshot.get(“assets_total_gbp”, None)
snapshot_cards_bal = snapshot.get(“cards_balance_total_gbp”, None)
snapshot_cards_due = snapshot.get(“cards_due_total_gbp”, None)
snapshot_reim = snapshot.get(“reim_all_gbp”, None)
snapshot_remaining = snapshot.get(“remaining_spending_gbp”, None)
try:
if snapshot_net_cash is not None:
snapshot_net_cash = float(snapshot_net_cash)
delta_since_snapshot_gbp = float(net_cash_gbp - snapshot_net_cash)
spent_since_snapshot_gbp = float(snapshot_net_cash - net_cash_gbp)
except Exception:
snapshot_net_cash = None
snapshot_time = None
spent_since_snapshot_gbp = None
delta_since_snapshot_gbp = None

# ————————

# Sidebar: Save / Load + Snapshot

# ————————

with st.sidebar:
st.subheader(“Save / Load”)

```
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
    st.caption("Tap \"Update sheet from uploaded ZIP\" to apply it.")

if st.button("Update sheet from uploaded ZIP", use_container_width=True):
    if st.session_state.pending_zip_bytes is None:
        st.warning("Upload a ZIP first.")
    else:
        restored = zip_bytes_to_state(st.session_state.pending_zip_bytes)
        if restored is None:
            st.error("That ZIP doesn't match the expected backup format.")
        else:
            st.session_state.app_state = restored
            st.session_state.pending_zip_bytes = None
            st.success("Backup restored.")
            st.rerun()

st.divider()
st.subheader("Snapshot")

if snapshot_net_cash is None:
    badge("No snapshot saved yet", "neutral")
else:
    badge("Snapshot saved", "ok")
    st.caption(f"Saved: {snapshot_time}")
    st.caption(f"Net Cash at snapshot: {fmt_money(float(snapshot_net_cash), GBP)}")

# ✅ FIX: Save the CURRENT computed net_cash_gbp and all key figures, not the old snapshot value
if st.button("📸 Save snapshot (Net Cash)", use_container_width=True):
    state["snapshot"] = {
        "saved_at_local": local_now_str(),
        "saved_at_utc": utc_now_iso(),
        "net_cash_gbp": net_cash_gbp,
        "assets_total_gbp": assets_total_gbp,
        "cards_balance_total_gbp": cards_balance_total_gbp,
        "cards_due_total_gbp": cards_due_total_gbp,
        "reim_all_gbp": reim_all_gbp,
        "remaining_spending_gbp": remaining_spending_gbp,
        "fixed_due_gbp": fixed_due_gbp,
        "pay_included_gbp": pay_included_gbp,
    }
    st.success("Snapshot saved.")
    st.rerun()

if st.button("🧹 Clear snapshot", use_container_width=True):
    state["snapshot"] = None
    st.rerun()

st.write("")
if st.button("Reset to defaults", use_container_width=True):
    st.session_state.app_state = default_state()
    st.session_state.pending_zip_bytes = None
    st.rerun()
```

# ————————

# Show apply results (from last run)

# ————————

if st.session_state.last_apply_success:
st.success(“Applied all changes.”)
st.session_state.last_apply_success = False

if st.session_state.last_apply_errors:
st.warning(
“Some values were invalid and were saved as £0.00:\n- “ + “\n- “.join(st.session_state.last_apply_errors)
)
st.session_state.last_apply_errors = []

# ————————

# KPIs

# ————————

k1, k2, k3 = st.columns(3)
with k1:
kpi(“Net Cash (GBP)”, net_cash_gbp)

with k2:
st.markdown(
f”””

<div class="kpi">
  <div class="label">Total Credit Card Bill Due (GBP)</div>
  <div class="value neu">{fmt_money(cards_due_total_gbp, GBP)}</div>

  <div style="margin-top:10px;">
    <span class="badge {'badge-ok' if ability_to_repay else 'badge-warn'}">
      Ability to repay (incl. selected reimbursements): {'Yes' if ability_to_repay else 'No'}
    </span>
  </div>

  <div class="totals" style="margin-top:8px;">
    Left over / (Shortfall):
    <span class="{cls(ability_surplus_gbp)}">{fmt_money(ability_surplus_gbp, GBP)}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

with k3:
kpi(“Remaining spending this month (GBP)”, remaining_spending_gbp)

# ————————

# Snapshot comparison panel

# ————————

if (
snapshot_net_cash is not None
and spent_since_snapshot_gbp is not None
and delta_since_snapshot_gbp is not None
):
# Build comparison rows — only include fields that were in the snapshot
snap = state.get(“snapshot”, {})

```
rows_html = ""

def snap_row(label, current_val, snap_key):
    snap_val = snap.get(snap_key)
    if snap_val is None:
        return ""
    snap_val = float(snap_val)
    delta = current_val - snap_val
    sign = "+" if delta >= 0 else ""
    delta_css = cls(delta)
    return f"""
    <div class="sp-row">
      <span class="sp-label">{label}</span>
      <span class="sp-val">
        {fmt_money(current_val, GBP)}
        <span style="font-size:11px; font-weight:400; opacity:0.7; margin-left:8px;" class="{delta_css}">
          ({sign}{fmt_money(delta, GBP)})
        </span>
      </span>
    </div>"""

rows_html += snap_row("Net Cash", net_cash_gbp, "net_cash_gbp")
rows_html += snap_row("Assets Total", assets_total_gbp, "assets_total_gbp")
rows_html += snap_row("Card Balances", cards_balance_total_gbp, "cards_balance_total_gbp")
rows_html += snap_row("Cards Due", cards_due_total_gbp, "cards_due_total_gbp")
rows_html += snap_row("Reimbursements", reim_all_gbp, "reim_all_gbp")
rows_html += snap_row("Remaining Spending", remaining_spending_gbp, "remaining_spending_gbp")

# Net spend headline in a bar
delta_css = cls(delta_since_snapshot_gbp)
spent_css = cls(-spent_since_snapshot_gbp)

st.markdown(
    f"""
```

<div class="snapshot-delta-bar">
  <div class="sd-item">
    <span class="sd-label">Snapshot taken</span>
    <span class="sd-val" style="font-size:13px; font-weight:500; opacity:0.8;">{snapshot_time}</span>
  </div>
  <div class="sd-item">
    <span class="sd-label">Net Cash change</span>
    <span class="sd-val {delta_css}">{fmt_money_signed(delta_since_snapshot_gbp, GBP)}</span>
  </div>
  <div class="sd-item">
    <span class="sd-label">Net spent since snapshot</span>
    <span class="sd-val {spent_css}">{fmt_money(spent_since_snapshot_gbp, GBP)}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

```
with st.expander("📊 Full snapshot comparison", expanded=False):
    st.markdown(
        f"""
```

<div class="snapshot-panel">
  <div class="sp-title">📸 Snapshot vs. Now &nbsp;·&nbsp; taken {snapshot_time}</div>
  {rows_html}
</div>
""",
            unsafe_allow_html=True,
        )

st.divider()

# ————————

# Editors

# ————————

a, b, c = st.columns([1.2, 1.1, 1.1])

with a:
st.subheader(“Assets”)
assets_edit = assets_df.copy()
assets_edit[“Balance”] = assets_edit.apply(lambda r: fmt_money(parse_money(r[“Balance”]), r[“Currency”]), axis=1)

```
st.data_editor(
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
totals_line("Total Assets (GBP):", assets_total_gbp)
```

with b:
st.subheader(“Credit Cards”)
cards_edit = cards_df.copy()
cards_edit[“Balance”] = cards_edit.apply(lambda r: fmt_money(parse_money(r[“Balance”]), r[“Currency”]), axis=1)
cards_edit[“Balance Due”] = cards_edit.apply(lambda r: fmt_money(parse_money(r[“Balance Due”]), r[“Currency”]), axis=1)

```
st.data_editor(
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

st.markdown(
    f"""
```

<div class="totals">
  Total Card Balances (GBP): <span class="{cls(cards_balance_total_gbp)}">{fmt_money(cards_balance_total_gbp, GBP)}</span>
  &nbsp;&nbsp;•&nbsp;&nbsp;
  Total Bills Due (GBP): <span class="neu">{fmt_money(cards_due_total_gbp, GBP)}</span>
</div>
""",
        unsafe_allow_html=True,
    )

with c:
st.subheader(“Reimbursement Pending”)
st.caption(“Always included in Net Cash. Use Include? only for Ability to repay.”)

```
reim_edit = reim_df.copy()
reim_edit["Amount"] = reim_edit["Amount"].apply(lambda v: fmt_money(parse_money(v), GBP))

st.data_editor(
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

totals_line("Total Reimbursements (GBP):", reim_all_gbp)
totals_line("Included for Ability to repay (GBP):", reim_included_for_repay_gbp)
```

st.divider()

d, e = st.columns([2.1, 1.0])

with d:
st.subheader(“Monthly Fixed”)
fixed_edit = fixed_df.copy()
fixed_edit[“Amount”] = fixed_edit[“Amount”].apply(lambda v: fmt_money(parse_money(v), GBP))

```
st.data_editor(
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

st.markdown(
    f"""
```

<div class="totals">
  Fixed Due This Month: <span class="neu">{fmt_money(fixed_due_gbp, GBP)}</span>
</div>
""",
        unsafe_allow_html=True,
    )

with e:
st.subheader(“RAC monthly bill”)
rac_edit = rac_df.copy()
rac_edit[“Amount”] = rac_edit[“Amount”].apply(lambda v: fmt_money(parse_money(v), GBP))

```
st.data_editor(
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

totals_line(f"RAC due this month ({THIS_MONTH}):", rac_due_this_month_gbp)

st.write("")
st.subheader("Monthly Pay")
st.caption("Unticked salaries are included in projection. Tick Paid? once received to exclude from projection.")

pay_edit = pay_df.copy()
pay_edit["Monthly Pay"] = pay_edit["Monthly Pay"].apply(lambda v: fmt_money(parse_money(v), GBP))

st.data_editor(
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

totals_line("Total Pay Included (Unticked):", pay_included_gbp)
```

st.divider()

# ————————

# FX

# ————————

st.subheader(“FX (USD → GBP)”)
st.caption(“Used only for converting USD balances (Apple Savings / Apple Card) into GBP totals.”)

fxl, fxr = st.columns([1.2, 1.0])

with fxl:
st.markdown(
f”””<div class="totals">Live USD→GBP (cached): <span class="neu">{usd_to_gbp_live:.4f}</span></div>”””,
unsafe_allow_html=True,
)
if st.session_state.fx_last_refresh_local is not None:
st.caption(f”Last refreshed: {st.session_state.fx_last_refresh_local}”)

```
if st.button("🔄 Pull current rate", use_container_width=True):
    fetch_usd_to_gbp.clear()
    st.session_state.fx_last_refresh_local = local_now_str()
    st.rerun()
```

with fxr:
st.toggle(“Use live FX”, value=bool(fx_cfg.get(“use_live”, True)), key=“fx_use_live”)
st.number_input(
“Manual USD→GBP”,
value=float(fx_cfg.get(“manual_usd_gbp”, 0.80)),
step=0.0001,
format=”%.4f”,
key=“fx_manual”,
)

st.divider()

# ————————

# ONE MAIN APPLY BUTTON

# ————————

if st.button(“✅ Apply all changes”, type=“primary”, use_container_width=True):
errors: list[str] = []

```
edited_assets = st.session_state.get("assets_editor", assets_df[["Account", "Currency", "Balance"]].copy())
edited_cards = st.session_state.get("cards_editor", cards_df[["Card", "Balance", "Balance Due"]].copy())
edited_reim = st.session_state.get("reim_editor", reim_df[["Source", "Amount", "Include?"]].copy())
edited_fixed = st.session_state.get("fixed_editor", fixed_df[["Item", "Amount", "Due?"]].copy())
edited_rac = st.session_state.get("rac_editor", rac_df[["Purchase", "Amount", "Month"]].copy())
edited_pay = st.session_state.get("pay_editor", pay_df[["Person", "Monthly Pay", "Paid?"]].copy())

# Assets
new_assets = assets_df.copy()
new_assets["Balance"] = [
    parse_money_user(v, f"Assets → {acc} (Balance)", errors)
    for acc, v in zip(assets_df["Account"], edited_assets["Balance"])
]
st.session_state.app_state["assets"] = enforce_assets(new_assets)

# Cards
new_cards = cards_df.copy()
new_cards["Balance"] = [
    parse_money_user(v, f"Credit Cards → {card} (Balance)", errors)
    for card, v in zip(cards_df["Card"], edited_cards["Balance"])
]
new_cards["Balance Due"] = [
    parse_money_user(v, f"Credit Cards → {card} (Balance Due)", errors)
    for card, v in zip(cards_df["Card"], edited_cards["Balance Due"])
]
st.session_state.app_state["credit_cards"] = enforce_cards(new_cards)

# Reimbursements
new_reim = reim_df.copy()
new_reim["Amount"] = [
    parse_money_user(v, f"Reimbursements → {src} (Amount)", errors)
    for src, v in zip(reim_df["Source"], edited_reim["Amount"])
]
new_reim["Include?"] = edited_reim["Include?"].fillna(False).astype(bool)
st.session_state.app_state["reimbursements"] = enforce_reim(new_reim)

# Fixed
new_fixed = edited_fixed.copy()
new_fixed["Amount"] = [
    parse_money_user(v, f"Monthly Fixed → {item} (Amount)", errors)
    for item, v in zip(new_fixed["Item"].astype(str), new_fixed["Amount"])
]
new_fixed["Due?"] = new_fixed["Due?"].fillna(True).astype(bool)
st.session_state.app_state["fixed_costs"] = normalize_fixed(new_fixed)

# RAC
new_rac = edited_rac.copy()
new_rac["Amount"] = [
    parse_money_user(v, f"RAC → {pur} (Amount)", errors)
    for pur, v in zip(new_rac["Purchase"].astype(str), new_rac["Amount"])
]
default_m = current_month_yyyy_mm()
new_rac["Month"] = new_rac["Month"].fillna("").astype(str).str.strip()
new_rac.loc[new_rac["Month"] == "", "Month"] = default_m
st.session_state.app_state["rac_bills"] = normalize_rac_bills(new_rac)

# Pay
new_pay = pay_df.copy()
new_pay["Monthly Pay"] = [
    parse_money_user(v, f"Monthly Pay → {p} (Monthly Pay)", errors)
    for p, v in zip(pay_df["Person"], edited_pay["Monthly Pay"])
]
new_pay["Paid?"] = edited_pay["Paid?"].fillna(False).astype(bool)
st.session_state.app_state["pay_cycle"] = enforce_pay(new_pay)

# FX settings
use_live = bool(st.session_state.get("fx_use_live", True))
manual = float(st.session_state.get("fx_manual", 0.80))
st.session_state.app_state["fx"] = {"use_live": use_live, "manual_usd_gbp": manual}

st.session_state.last_apply_errors = errors
st.session_state.last_apply_success = True

st.rerun()
```
