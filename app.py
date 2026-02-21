# app.py
import io
import json
import zipfile
from dataclasses import dataclass
from typing import Dict, Tuple

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Stabler Family Finances", layout="wide")

# -----------------------------
# Helpers
# -----------------------------
GBP = "GBP"
USD = "USD"

CURRENCY_SYMBOL = {GBP: "£", USD: "$"}


def parse_money(value) -> float:
    """
    Accepts numbers or strings like "£1,234.50" / "$8,803.5" / "8803.50"
    Returns float. Empty/None -> 0.0
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s == "":
        return 0.0
    # remove currency symbols and spaces
    s = (
        s.replace("£", "")
        .replace("$", "")
        .replace(",", "")
        .replace(" ", "")
        .replace("\u00A0", "")
    )
    # handle weird quotes
    s = s.replace("“", "").replace("”", "").replace('"', "").replace("'", "")
    # allow parentheses for negatives
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
    sym = CURRENCY_SYMBOL.get(currency, "")
    # accounting style: negative shown as -£1,234.56 (keeps your red/green logic separate)
    return f"{sym}{amount:,.2f}"


def get_usd_to_gbp_rate() -> Tuple[float, str]:
    """
    Tries to fetch live USD->GBP FX.
    Falls back to last cached rate or 0.79 if none exists.
    """
    # cache in session
    if "fx_rate_usd_gbp" not in st.session_state:
        st.session_state.fx_rate_usd_gbp = 0.79
        st.session_state.fx_rate_source = "fallback"

    try:
        # exchangerate.host is simple and free for basic usage
        r = requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "USD", "symbols": "GBP"},
            timeout=6,
        )
        r.raise_for_status()
        data = r.json()
        rate = float(data["rates"]["GBP"])
        st.session_state.fx_rate_usd_gbp = rate
        st.session_state.fx_rate_source = "exchangerate.host"
    except Exception:
        # keep cached
        pass

    return st.session_state.fx_rate_usd_gbp, st.session_state.fx_rate_source


def to_gbp(amount: float, currency: str, usd_gbp: float) -> float:
    if currency == GBP:
        return amount
    if currency == USD:
        return amount * usd_gbp
    return amount


def colored_metric(label: str, value_str: str, is_negative: bool, help_text: str | None = None):
    color = "#e85a5a" if is_negative else "#6bd68f"
    st.markdown(
        f"""
        <div style="padding: 10px 4px;">
          <div style="font-size: 12px; opacity: 0.75;">{label}</div>
          <div style="font-size: 34px; font-weight: 700; color: {color}; line-height: 1.1;">
            {value_str}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if help_text:
        st.caption(help_text)


# -----------------------------
# Default data (fixed rows)
# -----------------------------
def default_state() -> Dict[str, pd.DataFrame]:
    assets = pd.DataFrame(
        [
            {"Account": "HSBC", "Currency": GBP, "Balance": 0.0},
            {"Account": "Lloyds", "Currency": GBP, "Balance": 0.0},
            {"Account": "Apple Savings", "Currency": USD, "Balance": 0.0},
        ]
    )

    credit_cards = pd.DataFrame(
        [
            {"Card": "Amex", "Currency": GBP, "Balance": 0.0, "Balance Due": 0.0},
            {"Card": "Apple Card", "Currency": USD, "Balance": 0.0, "Balance Due": 0.0},
            {"Card": "Lloyds", "Currency": GBP, "Balance": 0.0, "Balance Due": 0.0},
        ]
    )

    reimbursements = pd.DataFrame(
        [
            {"Source": "Eric Work", "Amount": 0.0, "Include?": True},
            {"Source": "Gigi Work", "Amount": 0.0, "Include?": True},
            {"Source": "Misc", "Amount": 0.0, "Include?": False},
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
            {"Person": "Eric", "Monthly pay (GBP)": 6100.00, "Paid?": False},
            {"Person": "Gigi", "Monthly pay (GBP)": 6000.00, "Paid?": False},
        ]
    )

    return {
        "assets": assets,
        "credit_cards": credit_cards,
        "reimbursements": reimbursements,
        "fixed": fixed,
        "pay": pay,
    }


def ensure_state():
    if "app_state" not in st.session_state:
        st.session_state.app_state = default_state()


def state_to_zip_bytes(state: Dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        meta = {"version": 1, "tables": list(state.keys())}
        zf.writestr("meta.json", json.dumps(meta, indent=2))
        for name, df in state.items():
            zf.writestr(f"{name}.csv", df.to_csv(index=False))
    return buf.getvalue()


def zip_bytes_to_state(b: bytes) -> Dict[str, pd.DataFrame] | None:
    try:
        with zipfile.ZipFile(io.BytesIO(b), "r") as zf:
            names = set(zf.namelist())
            required = {"assets.csv", "credit_cards.csv", "reimbursements.csv", "fixed.csv", "pay.csv"}
            if not required.issubset(names):
                return None

            def read_csv(path: str) -> pd.DataFrame:
                return pd.read_csv(io.BytesIO(zf.read(path)))

            s = {
                "assets": read_csv("assets.csv"),
                "credit_cards": read_csv("credit_cards.csv"),
                "reimbursements": read_csv("reimbursements.csv"),
                "fixed": read_csv("fixed.csv"),
                "pay": read_csv("pay.csv"),
            }

            # light normalization
            # assets
            s["assets"]["Balance"] = s["assets"]["Balance"].apply(parse_money)
            # credit cards
            s["credit_cards"]["Balance"] = s["credit_cards"]["Balance"].apply(parse_money)
            s["credit_cards"]["Balance Due"] = s["credit_cards"]["Balance Due"].apply(parse_money)
            # reimbursements
            s["reimbursements"]["Amount"] = s["reimbursements"]["Amount"].apply(parse_money)
            s["reimbursements"]["Include?"] = s["reimbursements"]["Include?"].astype(bool)
            # fixed
            s["fixed"]["Amount (GBP)"] = s["fixed"]["Amount (GBP)"].apply(parse_money)
            s["fixed"]["Due?"] = s["fixed"]["Due?"].astype(bool)
            # pay
            s["pay"]["Monthly pay (GBP)"] = s["pay"]["Monthly pay (GBP)"].apply(parse_money)
            s["pay"]["Paid?"] = s["pay"]["Paid?"].astype(bool)

            return s
    except Exception:
        return None


# -----------------------------
# App
# -----------------------------
ensure_state()

st.title("Stabler Family Finances")

# Sidebar: Save / Load
with st.sidebar:
    st.subheader("Save / Load")

    backup_bytes = state_to_zip_bytes(st.session_state.app_state)
    st.download_button(
        "⬇️ Download backup (ZIP)",
        data=backup_bytes,
        file_name="stabler-finances-backup.zip",
        mime="application/zip",
        use_container_width=True,
    )

    uploaded = st.file_uploader("Restore from backup (ZIP)", type=["zip"])
    if uploaded is not None:
        restored = zip_bytes_to_state(uploaded.read())
        if restored is None:
            st.error("That ZIP doesn’t match the expected backup format.")
        else:
            st.session_state.app_state = restored
            st.success("Backup restored.")
            st.rerun()

    st.divider()
    if st.button("Reset to defaults", use_container_width=True):
        st.session_state.app_state = default_state()
        st.success("Reset.")
        st.rerun()

# FX
usd_gbp, fx_source = get_usd_to_gbp_rate()

assets_df = st.session_state.app_state["assets"].copy()
cards_df = st.session_state.app_state["credit_cards"].copy()
reimb_df = st.session_state.app_state["reimbursements"].copy()
fixed_df = st.session_state.app_state["fixed"].copy()
pay_df = st.session_state.app_state["pay"].copy()

# Compute totals in GBP
assets_total_gbp = float(
    assets_df.apply(lambda r: to_gbp(parse_money(r["Balance"]), r["Currency"], usd_gbp), axis=1).sum()
)

cards_balance_total_gbp = float(
    cards_df.apply(lambda r: to_gbp(parse_money(r["Balance"]), r["Currency"], usd_gbp), axis=1).sum()
)

cards_due_total_gbp = float(
    cards_df.apply(lambda r: to_gbp(parse_money(r["Balance Due"]), r["Currency"], usd_gbp), axis=1).sum()
)

reimb_included_gbp = float(
    reimb_df[reimb_df["Include?"] == True]["Amount"].apply(parse_money).sum()
)

net_cash_gbp = assets_total_gbp + reimb_included_gbp - cards_balance_total_gbp

fixed_due_total_gbp = float(fixed_df[fixed_df["Due?"] == True]["Amount (GBP)"].apply(parse_money).sum())

pay_selected_total_gbp = float(pay_df[pay_df["Paid?"] == True]["Monthly pay (GBP)"].apply(parse_money).sum())

remaining_spend_gbp = net_cash_gbp + (pay_selected_total_gbp - fixed_due_total_gbp)

ability_to_repay = (assets_total_gbp - cards_due_total_gbp) >= 0

# Top metrics row
c1, c2, c3 = st.columns(3)

with c1:
    colored_metric(
        "Net Cash (GBP)",
        fmt_money(net_cash_gbp, GBP),
        is_negative=(net_cash_gbp < 0),
    )

with c2:
    st.markdown(
        f"""
        <div style="padding: 10px 4px;">
          <div style="font-size: 12px; opacity: 0.75;">Total Credit Card Bill Due (GBP)</div>
          <div style="font-size: 34px; font-weight: 700; line-height: 1.1;">
            {fmt_money(cards_due_total_gbp, GBP)}
          </div>
          <div style="margin-top: 6px; font-size: 12px; opacity: 0.85;">
            Ability to repay: <b>{"Yes" if ability_to_repay else "No"}</b>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    colored_metric(
        "Remaining spending this month (GBP)",
        fmt_money(remaining_spend_gbp, GBP),
        is_negative=(remaining_spend_gbp < 0),
    )

st.divider()

# -----------------------------
# Editable tables (NO native views; symbols shown directly)
# We store numeric values, but display/edit as formatted strings to get £/$ per row.
# Apply buttons commit parsed numbers back into state.
# -----------------------------

row1a, row1b, row1c = st.columns(3)

# ASSETS
with row1a:
    st.subheader("Assets")

    assets_edit = assets_df.copy()
    # Display string with symbol (editable text so each row can show its own symbol)
    assets_edit["Balance"] = assets_edit.apply(
        lambda r: fmt_money(parse_money(r["Balance"]), r["Currency"]),
        axis=1,
    )

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
        # parse the edited text back into numeric
        new_assets["Balance"] = edited_assets["Balance"].apply(parse_money)
        st.session_state.app_state["assets"] = new_assets
        st.rerun()

    st.caption(f"Total Assets (GBP): **{fmt_money(assets_total_gbp, GBP)}**")

# CREDIT CARDS
with row1b:
    st.subheader("Credit Cards")

    cards_edit = cards_df.copy()

    cards_edit["Balance"] = cards_edit.apply(
        lambda r: fmt_money(parse_money(r["Balance"]), r["Currency"]),
        axis=1,
    )
    cards_edit["Balance Due"] = cards_edit.apply(
        lambda r: fmt_money(parse_money(r["Balance Due"]), r["Currency"]),
        axis=1,
    )

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
        st.session_state.app_state["credit_cards"] = new_cards
        st.rerun()

    st.caption(
        f"Total Card Balances (GBP): **{fmt_money(cards_balance_total_gbp, GBP)}** · "
        f"Total Bills Due (GBP): **{fmt_money(cards_due_total_gbp, GBP)}**"
    )

# REIMBURSEMENTS
with row1c:
    st.subheader("Reimbursement Pending")

    reimb_edit = reimb_df.copy()
    reimb_edit["Amount"] = reimb_edit["Amount"].apply(lambda v: fmt_money(parse_money(v), GBP))

    edited_reimb = st.data_editor(
        reimb_edit[["Source", "Amount", "Include?"]],
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "Source": st.column_config.TextColumn("Source", disabled=True),
            "Amount": st.column_config.TextColumn("Amount"),
            "Include?": st.column_config.CheckboxColumn("Include?"),
        },
        key="reimb_editor",
    )

    if st.button("Apply Reimbursement Changes", use_container_width=True):
        new_reimb = reimb_df.copy()
        new_reimb["Amount"] = edited_reimb["Amount"].apply(parse_money)
        new_reimb["Include?"] = edited_reimb["Include?"].astype(bool)
        st.session_state.app_state["reimbursements"] = new_reimb
        st.rerun()

    st.caption(f"Included Reimbursements (GBP): **{fmt_money(reimb_included_gbp, GBP)}**")

st.divider()

# Row 2: Monthly Fixed (left) + Pay Cycle (right)
row2a, row2b = st.columns([2, 1])

with row2a:
    st.subheader("Monthly Fixed")

    fixed_edit = fixed_df.copy()
    fixed_edit["Amount (GBP)"] = fixed_edit["Amount (GBP)"].apply(lambda v: float(parse_money(v)))

    edited_fixed = st.data_editor(
        fixed_edit[["Item", "Amount (GBP)", "Due?"]],
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "Item": st.column_config.TextColumn("Item", disabled=True),
            "Amount (GBP)": st.column_config.NumberColumn("Amount (GBP)", format="%,.2f"),
            "Due?": st.column_config.CheckboxColumn("Due?"),
        },
        key="fixed_editor",
    )

    if st.button("Apply Monthly Fixed Changes", use_container_width=True):
        new_fixed = fixed_df.copy()
        new_fixed["Amount (GBP)"] = edited_fixed["Amount (GBP)"].apply(parse_money)
        new_fixed["Due?"] = edited_fixed["Due?"].astype(bool)
        st.session_state.app_state["fixed"] = new_fixed
        st.rerun()

    st.caption(f"Fixed due total (GBP): **{fmt_money(fixed_due_total_gbp, GBP)}**")

with row2b:
    st.subheader("Pay Cycle (setup)")

    pay_edit = pay_df.copy()
    pay_edit["Monthly pay (GBP)"] = pay_edit["Monthly pay (GBP)"].apply(lambda v: float(parse_money(v)))

    edited_pay = st.data_editor(
        pay_edit[["Person", "Monthly pay (GBP)", "Paid?"]],
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "Person": st.column_config.TextColumn("Person", disabled=True),
            "Monthly pay (GBP)": st.column_config.NumberColumn("Monthly pay (GBP)", format="%,.2f"),
            "Paid?": st.column_config.CheckboxColumn("Paid?"),
        },
        key="pay_editor",
    )

    if st.button("Apply Pay Changes", use_container_width=True):
        new_pay = pay_df.copy()
        new_pay["Monthly pay (GBP)"] = edited_pay["Monthly pay (GBP)"].apply(parse_money)
        new_pay["Paid?"] = edited_pay["Paid?"].astype(bool)
        st.session_state.app_state["pay"] = new_pay
        st.rerun()

    st.caption(f"Included pay this month (GBP): **{fmt_money(pay_selected_total_gbp, GBP)}**")

st.divider()

# FX section at bottom (as requested)
st.subheader("FX (for USD accounts/cards)")
col_fx1, col_fx2 = st.columns([1, 3])
with col_fx1:
    if st.button("Refresh FX rate", use_container_width=True):
        # force refresh attempt
        st.session_state.fx_rate_usd_gbp = None  # type: ignore
        # re-init in getter
        if "fx_rate_usd_gbp" in st.session_state:
            del st.session_state["fx_rate_usd_gbp"]
        if "fx_rate_source" in st.session_state:
            del st.session_state["fx_rate_source"]
        usd_gbp, fx_source = get_usd_to_gbp_rate()
        st.rerun()

with col_fx2:
    st.write(f"USD→GBP rate used: **{usd_gbp:.6f}** (source: {fx_source})")
    st.caption("This rate is used only for GBP totals and top summary calculations.")
