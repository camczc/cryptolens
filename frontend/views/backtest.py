"""frontend/views/backtest.py"""
import streamlit as st
import requests
import plotly.graph_objects as go
import plotly.express as px

API_BASE = "http://localhost:8000"

POPULAR_COINS = {
    "Bitcoin (BTC)": "bitcoin",
    "Ethereum (ETH)": "ethereum",
    "Solana (SOL)": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "Dogecoin (DOGE)": "dogecoin",
}

STRATEGIES = {
    "Composite Score": "composite",
    "RSI Mean Reversion": "rsi",
    "Golden Cross (SMA50/200)": "golden_cross",
    "Fear & Greed Contrarian": "fear_greed",
}


def render():
    st.markdown("# 📊 Backtest")
    st.caption("Simulate a trading strategy on historical crypto data")

    with st.sidebar:
        st.subheader("Backtest Config")
        selected_label = st.selectbox("Coin", list(POPULAR_COINS.keys()))
        coin_id = POPULAR_COINS[selected_label]
        custom_coin = st.text_input("Or CoinGecko ID", placeholder="polkadot")
        if custom_coin:
            coin_id = custom_coin.lower().strip()

        strategy_label = st.selectbox("Strategy", list(STRATEGIES.keys()))
        strategy = STRATEGIES[strategy_label]

        st.caption({
            "composite": "Weighted aggregate of RSI + MACD + Bollinger + Fear&Greed. Most sophisticated.",
            "rsi": "Buy when RSI < 30 (oversold), sell when RSI > 70 (overbought).",
            "golden_cross": "Buy when SMA50 crosses above SMA200. Trend-following.",
            "fear_greed": "Buy on extreme fear (< 25), sell on extreme greed (> 75). Contrarian.",
        }.get(strategy, ""))

        start_date = st.date_input("Start", value=None)
        end_date = st.date_input("End", value=None)
        capital = st.number_input("Initial Capital ($)", value=10000, step=1000)
        run = st.button("🚀 Run Backtest", type="primary")

    if run:
        with st.spinner("Running backtest..."):
            try:
                payload = {
                    "coingecko_id": coin_id,
                    "strategy": strategy,
                    "initial_capital": capital,
                }
                if start_date:
                    payload["start_date"] = str(start_date)
                if end_date:
                    payload["end_date"] = str(end_date)

                resp = requests.post(f"{API_BASE}/backtest", json=payload, timeout=60)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                st.error(f"API error: {e}")
                return

        st.divider()

        # Metrics row
        m1, m2, m3, m4, m5 = st.columns(5)
        total_ret = data["total_return"]
        alpha = data["alpha"]
        m1.metric("Total Return", f"{total_ret:+.1%}", f"α {alpha:+.1%} vs BTC")
        m2.metric("Sharpe Ratio", f"{data['sharpe_ratio']:.2f}")
        m3.metric("Max Drawdown", f"{data['max_drawdown']:.1%}")
        m4.metric("Win Rate", f"{data['win_rate']:.1%}")
        m5.metric("Total Trades", data["total_trades"])

        # Equity curve
        st.subheader("📈 Equity Curve vs Benchmark")
        equity = data["equity_curve"]
        if equity:
            dates = [e["date"] for e in equity]
            values = [e["value"] for e in equity]
            bench = [e["benchmark_value"] for e in equity]

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dates, y=values, name=f"{strategy_label}", line=dict(color="#6c63ff", width=2)))
            fig.add_trace(go.Scatter(x=dates, y=bench, name="BTC Buy & Hold", line=dict(color="#ff9800", width=2, dash="dash")))
            fig.add_hline(y=capital, line_dash="dot", line_color="gray", opacity=0.5)
            fig.update_layout(
                height=400,
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(t=30, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)

        # Additional metrics
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Annualized Return", f"{data['annualized_return']:+.1%}")
            st.metric("Benchmark Return", f"{data['benchmark_return']:+.1%}")
        with c2:
            st.metric("Sortino Ratio", f"{data['sortino_ratio']:.2f}")
            st.metric("Calmar Ratio", f"{data['calmar_ratio']:.2f}")
        with c3:
            st.metric("Volatility (Ann.)", f"{data['volatility_annualized']:.1%}")
            st.metric("Avg Trade Duration", f"{data['avg_trade_duration_days']:.0f} days")

        # Trade log
        trades = data.get("trade_log", [])
        if trades:
            st.subheader(f"📋 Trade Log ({len(trades)} trades)")
            import pandas as pd
            df = pd.DataFrame(trades)
            df["return"] = df["return"].apply(lambda x: f"{x:+.2%}")
            df["profitable"] = df["profitable"].apply(lambda x: "✅" if x else "❌")
            st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.divider()
        st.markdown("### Configure a backtest in the sidebar to get started.")
        st.markdown("""
**Available strategies:**

| Strategy | Logic | Best for |
|----------|-------|----------|
| Composite | Multi-signal aggregate | General use |
| RSI Mean Reversion | Buy oversold, sell overbought | Sideways markets |
| Golden Cross | SMA50 vs SMA200 | Trending markets |
| Fear & Greed Contrarian | Buy fear, sell greed | High volatility crypto |
        """)
