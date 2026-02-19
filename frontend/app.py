"""
frontend/app.py — CryptoLens Dashboard
Run: python -m streamlit run frontend/app.py
"""
import streamlit as st

st.set_page_config(
    page_title="CryptoLens",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.image("https://img.icons8.com/fluency/96/cryptocurrency.png", width=60)
st.sidebar.title("CryptoLens")
st.sidebar.caption("AI-Powered Crypto Research")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigate",
    ["🔍 Research", "📊 Backtest", "⚖️ Compare Strategies"],
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.caption("Powered by Claude · Built by Cameron Cooper")

if page == "🔍 Research":
    from frontend.views.research import render
    render()
elif page == "📊 Backtest":
    from frontend.views.backtest import render
    render()
elif page == "⚖️ Compare Strategies":
    from frontend.views.compare import render
    render()
