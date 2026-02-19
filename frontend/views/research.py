"""frontend/views/research.py"""
import streamlit as st
import requests
import plotly.graph_objects as go

API_BASE = "http://localhost:8000"

POPULAR_COINS = {
    "Bitcoin (BTC)": "bitcoin",
    "Ethereum (ETH)": "ethereum",
    "Solana (SOL)": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "Cardano (ADA)": "cardano",
    "Avalanche (AVAX)": "avalanche-2",
    "Dogecoin (DOGE)": "dogecoin",
}


def render():
    st.markdown("# 🔮 Crypto Research")
    st.caption("AI-generated analyst briefs powered by quantitative signals + Claude")

    col1, col2 = st.columns([1, 2])
    with col1:
        selected_label = st.selectbox("Select Coin", list(POPULAR_COINS.keys()))
        coin_id = POPULAR_COINS[selected_label]
        custom_coin = st.text_input("Or enter CoinGecko ID", placeholder="e.g. polkadot, chainlink")
        if custom_coin:
            coin_id = custom_coin.lower().strip()

    with col2:
        question = st.text_input(
            "Optional: Ask a specific question",
            placeholder="Is Bitcoin overextended after its recent run?"
        )

    col_a, col_b = st.columns([1, 3])
    with col_a:
        generate = st.button("🔮 Generate Research Brief", type="primary")
    with col_b:
        signals_only = st.button("📊 Signal Scorecard Only")

    if signals_only or generate:
        # Load signals
        with st.spinner(f"Loading signals for {coin_id}..."):
            try:
                resp = requests.get(f"{API_BASE}/signals/{coin_id}", timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    st.warning(f"No signals found for **{coin_id}**. Seeding data first...")
                    try:
                        seed_resp = requests.post(f"{API_BASE}/coins/{coin_id}/seed", timeout=60)
                        seed_resp.raise_for_status()
                        comp_resp = requests.post(f"{API_BASE}/signals/{coin_id}/compute", timeout=60)
                        comp_resp.raise_for_status()
                        resp = requests.get(f"{API_BASE}/signals/{coin_id}", timeout=30)
                        resp.raise_for_status()
                        data = resp.json()
                        st.success("Data seeded successfully!")
                    except Exception as seed_err:
                        st.error(f"Could not seed {coin_id}: {seed_err}")
                        return
                else:
                    st.error(f"API error: {e}")
                    return
            except Exception as e:
                st.error(f"API error: {e}")
                return

        # Display signal scorecard
        ind = data.get("indicators", {})
        score = data.get("composite_score", 0)
        signal = data.get("signal", "NEUTRAL")

        signal_color = {
            "STRONG BUY": "#00c853",
            "BUY": "#69f0ae",
            "NEUTRAL": "#ffd740",
            "SELL": "#ff6d00",
            "STRONG SELL": "#d50000",
        }.get(signal, "#ffd740")

        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Price (USD)", f"${data['price_usd']:,.4f}")
        m2.metric("7d Change", f"{data.get('price_change_7d_pct', 0):+.1f}%")
        m3.metric("Composite Score", f"{score:+.3f}")
        m4.markdown(f"### Signal\n<span style='color:{signal_color}; font-size:1.4rem; font-weight:bold'>{signal}</span>", unsafe_allow_html=True)

        # Gauge chart
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": "Composite Signal Score"},
            gauge={
                "axis": {"range": [-1, 1]},
                "bar": {"color": signal_color},
                "steps": [
                    {"range": [-1, -0.5], "color": "#d50000"},
                    {"range": [-0.5, -0.15], "color": "#ff6d00"},
                    {"range": [-0.15, 0.15], "color": "#ffd740"},
                    {"range": [0.15, 0.5], "color": "#69f0ae"},
                    {"range": [0.5, 1], "color": "#00c853"},
                ],
                "threshold": {"line": {"color": "white", "width": 3}, "value": score},
            },
            number={"valueformat": "+.2f", "font": {"size": 20}},
        ))
        fig.update_layout(height=250, margin=dict(t=40, b=0, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)

        # Indicators table
        st.subheader("📊 Technical Indicators")
        c1, c2, c3 = st.columns(3)
        with c1:
            rsi = ind.get("rsi_14")
            rsi_color = "🔴" if rsi and rsi > 70 else "🟢" if rsi and rsi < 30 else "🟡"
            st.metric("RSI-14", f"{rsi:.1f}" if rsi else "N/A")
            st.caption(f"{rsi_color} {ind.get('rsi_interpretation', '')}")

        with c2:
            macd = ind.get("macd_hist")
            macd_color = "🟢" if macd and macd > 0 else "🔴"
            st.metric("MACD Histogram", f"{macd:.4f}" if macd else "N/A")
            st.caption(f"{macd_color} {ind.get('macd_interpretation', '')}")

        with c3:
            bb = ind.get("bb_pct")
            st.metric("Bollinger %B", f"{bb:.2f}" if bb else "N/A")
            st.caption(f"📊 {ind.get('bb_interpretation', '')}")

        c4, c5, c6 = st.columns(3)
        with c4:
            fg = ind.get("fear_greed_index")
            fg_label = ind.get("fear_greed_label", "")
            fg_color = "🟢" if fg and fg < 25 else "🔴" if fg and fg > 75 else "🟡"
            st.metric("Fear & Greed Index", f"{fg:.0f}/100" if fg else "N/A")
            st.caption(f"{fg_color} {fg_label}")

        with c5:
            vol_chg = ind.get("volume_change_24h")
            st.metric("Volume Change 24h", f"{vol_chg:+.1f}%" if vol_chg else "N/A")

        with c6:
            st.metric("Signal", signal)

    if generate:
        # Generate AI brief
        st.divider()
        st.subheader("🤖 AI Research Brief")
        with st.spinner("Claude is analyzing the data..."):
            try:
                params = {"question": question} if question else {}
                resp = requests.get(f"{API_BASE}/analyze/{coin_id}", params=params, timeout=60)
                resp.raise_for_status()
                brief_data = resp.json()
                st.markdown(brief_data["brief"])
                st.caption(f"Generated at {brief_data['generated_at']}")
            except Exception as e:
                st.error(f"API error: {e}")

    if not generate and not signals_only:
        st.divider()
        st.subheader("How it works")
        st.markdown("""
1. **Select a coin** and click Signal Scorecard to see technical indicators
2. **Click Generate** to get a full Claude-powered analyst brief
3. **Ask a question** for targeted analysis (e.g. "Is ETH undervalued right now?")

**Signals computed:**
| Indicator | What it measures |
|-----------|-----------------|
| RSI-14 | Momentum — overbought or oversold |
| MACD | Trend direction and momentum shifts |
| Bollinger %B | Price position relative to volatility bands |
| Fear & Greed | Market sentiment (contrarian signal) |
| Composite Score | Weighted aggregate of all signals (-1 to +1) |
        """)
