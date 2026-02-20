import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(layout="wide")
st.title("Stabler Family Finances")

DATA = Path("credit_cards.csv")

def load_cards():
    try:
        return pd.read_csv(DATA)
    except:
        return pd.DataFrame(columns=["card","balance","due","is_due"])

def save_cards(df):
    df.to_csv(DATA, index=False)

df = load_cards()

st.subheader("Credit Cards")

edited = st.data_editor(
    df,
    num_rows="dynamic",
    use_container_width=True
)

save_cards(edited)

total_balance = edited["balance"].sum() if not edited.empty else 0
due_balance = edited.loc[edited["is_due"] == True, "balance"].sum() if not edited.empty else 0
not_due_balance = total_balance - due_balance

col1, col2, col3 = st.columns(3)
col1.metric("Total Card Balance", f"£{total_balance:,.2f}")
col2.metric("Due Now", f"£{due_balance:,.2f}")
col3.metric("Not Due", f"£{not_due_balance:,.2f}")
