import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date, datetime, timedelta
import calendar

st.set_page_config(page_title="Stabler Family Finances", layout="wide")
st.title("Stabler Family Finances")

FILES = {
    "assets": ("assets.csv", ["account", "balance"]),
    "cards": ("credit_cards.csv", ["card", "balance", "due", "is_due"]),
    "fixed": ("fixed_costs.csv", ["item", "amount", "is_due"]),
    "pay": ("pay_cycle.csv", ["person", "rule", "pay_day", "amount", "buffer"]),
}

def ensure_file(filename: str, cols: list[str]) -> None:
    path = Path(filename)
    if not path.exists():
        pd.DataFrame(columns=cols).to_csv(path, index=False)

def load_df(key: str) -> pd.DataFrame:
    filename, cols = FILES[key]
    ensure_file(filename, cols)
    df = pd.read_csv(filename)

    for c in cols:
        if c not in df.columns:
            df[c] = None

    df = df[cols].copy()
    df = df.dropna(how="all")
    return df

def save_df(key: str, df: pd.DataFrame) -> None:
    filename, cols = FILES[key]
    df.copy()[cols].to_csv(filename, index=False)

def money(x) -> str:
    try:
        return f"£{float(x):,.2f}"
    except Exception:
        return "£0.00"

def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)

def to_bool(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool)

def is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=Sat, 6=Sun

def previous_business_day(d: date) -> date:
    # Move back to Friday if weekend
    while is_weekend(d):
        d = d - timedelta(days=1)
    return d

def last_day_of_month(year: int, month: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last)

def next_pay_date_fixed_day(day_of_month: int, today: date) -> date:
    # Candidate in current month
    year, month = today.year, today.month
    last = calendar.monthrange(year, month)[1]
    dom = min(day_of_month, last)
    candidate = date(year, month, dom)
    candidate = previous_business_day(candidate)

    # If already passed (strictly < today), go to next month
    if candidate < today:
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        last = calendar.monthrange(year, month)[1]
        dom = min(day_of_month, last)
        candidate = date(year, month, dom)
        candidate = previous_business_day(candidate)

    return candidate

def next_pay_date_end_of_month(today: date) -> date:
    year, month = today.year, today.month
    candidate = last_day_of_month(year, month)
    candidate = previous_business_day(candidate)

    if candidate < today:
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        candidate = last_day_of_month(year, month)
        candidate = previous_business_day(candidate)

    return candidate

def days_until(d: date, today: date) -> int:
    return (d - today).days

# ---- Load data ----
assets = load_df("assets")
cards = load_df("cards")
fixed = load_df("fixed")
pay = load_df("pay")

# ---- Clean types ----
assets["balance"] = to_number(assets["balance"])
cards["balance"] = to_number(cards["balance"])
cards["due"] = to_number(cards["due"])
cards["is_due"] = to_bool(cards["is_due"])
fixed["amount"] = to_number(fixed["amount"])
fixed["is_due"] = to_bool(fixed["is_due"])

# Pay table types
pay["amount"] = to_number(pay["amount"]) if not pay.empty else pay.get("amount", pd.Series(dtype=float))
pay["buffer"] = to_number(pay["buffer"]) if not pay.empty else pay.get("buffer", pd.Series(dtype=float))
if "pay_day" in pay.columns:
    pay["pay_day"] = pd.to_numeric(pay["pay_day"], errors="coerce")

today = date.today()

# ---- Layout: Top row ----
c1, c2, c3 = st.columns([1, 1, 1])

with c1:
    st.subheader("Assets")
    assets_edit = st.data_editor(
        assets,
        key="assets_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "balance": st.column_config.NumberColumn("Balance", format="£%.2f")
        },
    )
    save_df("assets", assets_edit)
    assets_total = float(assets_edit["balance"].sum()) if not assets_edit.empty else 0.0

with c2:
    st.subheader("Credit Cards")
    cards_edit = st.data_editor(
        cards,
        key="cards_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "balance": st.column_config.NumberColumn("Balance", format="£%.2f"),
            "due": st.column_config.NumberColumn("Due this cycle", format="£%.2f"),
            "is_due": st.column_config.CheckboxColumn("Due?"),
        },
    )
    save_df("cards", cards_edit)
    cards_total = float(cards_edit["balance"].sum()) if not cards_edit.empty else 0.0
    cards_due = float(cards_edit.loc[cards_edit["is_due"] == True, "due"].sum()) if not cards_edit.empty else 0.0

with c3:
    st.subheader("Pay Cycle (setup)")
    st.caption("Enter monthly take-home pay + optional buffer. Dates auto-calc.")

    # Ensure pay has at least Eric + Gigi rows if blank
    if pay.empty:
        pay = pd.DataFrame([
            {"person": "Eric", "rule": "fixed_day", "pay_day": 24, "amount": 0, "buffer": 0},
            {"person": "Gigi", "rule": "end_of_month", "pay_day": None, "amount": 0, "buffer": 0},
        ])

    pay_edit = st.data_editor(
        pay,
        key="pay_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "person": st.column_config.TextColumn("Person"),
            "rule": st.column_config.SelectboxColumn(
                "Rule",
                options=["fixed_day", "end_of_month"],
                help="fixed_day = paid on a day-of-month (weekend -> previous business day). end_of_month = last day (weekend -> previous business day).",
            ),
            "pay_day": st.column_config.NumberColumn("Pay day (if fixed)", help="Used only for rule=fixed_day"),
            "amount": st.column_config.NumberColumn("Monthly pay", format="£%.2f"),
            "buffer": st.column_config.NumberColumn("Buffer", format="£%.2f"),
        },
    )
    save_df("pay", pay_edit)

st.divider()

# ---- Second row: Monthly Fixed | Overview ----
left, right = st.columns([1.3, 0.7])

with left:
    st.subheader("Monthly Fixed")
    fixed_edit = st.data_editor(
        fixed,
        key="fixed_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "amount": st.column_config.NumberColumn("Amount", format="£%.2f"),
            "is_due": st.column_config.CheckboxColumn("Due?"),
        },
    )
    save_df("fixed", fixed_edit)

    fixed_total = float(fixed_edit["amount"].sum()) if not fixed_edit.empty else 0.0
    fixed_due = float(fixed_edit.loc[fixed_edit["is_due"] == True, "amount"].sum()) if not fixed_edit.empty else 0.0

with right:
    st.subheader("Cash & Due Overview")

    due_now = cards_due + fixed_due
    not_due_cards = max(cards_total - cards_due, 0.0)
    not_due_fixed = max(fixed_total - fixed_due, 0.0)
    total_not_due = not_due_cards + not_due_fixed

    net_position = assets_total - cards_total
    cash_position = assets_total - cards_total  # same meaning in this simplified model

    r1, r2 = st.columns(2)
    r1.metric("Due now", money(due_now))
    r2.metric("Not due", money(total_not_due))

    st.markdown("---")
    st.metric("Net position (assets - cards)", money(net_position))
    st.metric("Cash position (assets - cards)", money(cash_position))

    st.markdown("---")
    st.markdown("### Due Items")

    due_cards_df = cards_edit[cards_edit["is_due"] == True].copy()
    due_fixed_df = fixed_edit[fixed_edit["is_due"] == True].copy()

    if due_cards_df.empty and due_fixed_df.empty:
        st.write("Nothing currently marked as due ✅")
    else:
        if not due_cards_df.empty:
            st.write("**Cards due:**")
            st.dataframe(due_cards_df[["card", "due"]], use_container_width=True)
        if not due_fixed_df.empty:
            st.write("**Fixed due:**")
            st.dataframe(due_fixed_df[["item", "amount"]], use_container_width=True)

st.divider()

# ---- Pay Cycle Forecast (full panel) ----
st.subheader("Pay Cycle Forecast")

pay_rows = []
total_income_before_next = 0.0
total_buffer = 0.0

pay_clean = pay_edit.copy()
pay_clean["amount"] = to_number(pay_clean["amount"])
pay_clean["buffer"] = to_number(pay_clean["buffer"])
pay_clean["pay_day"] = pd.to_numeric(pay_clean["pay_day"], errors="coerce")

for _, row in pay_clean.iterrows():
    person = str(row.get("person", "")).strip() or "Person"
    rule = str(row.get("rule", "fixed_day")).strip()
    amt = float(row.get("amount", 0.0))
    buf = float(row.get("buffer", 0.0))
    pay_day = row.get("pay_day", None)

    if rule == "end_of_month":
        next_pay = next_pay_date_end_of_month(today)
    else:
        # default fixed_day
        dom = int(pay_day) if pd.notna(pay_day) else 24
        next_pay = next_pay_date_fixed_day(dom, today)

    d_left = days_until(next_pay, today)

    pay_rows.append({
        "Person": person,
        "Rule": rule,
        "Next pay date": next_pay.isoformat(),
        "Days remaining": d_left,
        "Monthly pay": amt,
        "Buffer": buf,
    })

# Determine the *earliest* upcoming pay date across both of you
pay_df = pd.DataFrame(pay_rows)
if not pay_df.empty:
    pay_df["Next pay date"] = pd.to_datetime(pay_df["Next pay date"]).dt.date
    earliest_pay_date = min(pay_df["Next pay date"])
    # Income expected before or on that earliest pay date:
    income_before = pay_df.loc[pay_df["Next pay date"] == earliest_pay_date, "Monthly pay"].sum()
    buffer_before = pay_df.loc[pay_df["Next pay date"] == earliest_pay_date, "Buffer"].sum()
else:
    earliest_pay_date = None
    income_before = 0.0
    buffer_before = 0.0

# Forecast: current cash position + incoming pay (+buffer) - due now
forecast_after_due = cash_position + income_before + buffer_before - due_now

cA, cB, cC, cD = st.columns(4)
if earliest_pay_date:
    cA.metric("Next pay event", earliest_pay_date.strftime("%Y-%m-%d"))
    cB.metric("Days to next pay", str((earliest_pay_date - today).days))
else:
    cA.metric("Next pay event", "—")
    cB.metric("Days to next pay", "—")

cC.metric("Income before next pay", money(income_before))
cD.metric("Forecast (after paying Due now)", money(forecast_after_due))

st.dataframe(pay_df, use_container_width=True)
