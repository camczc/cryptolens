"""frontend/views/compare.py"""
import streamlit as st
import requests
import plotly.graph_objects as go
import pandas as pd

API_BASE = "http://localhost:8000"

POPULAR_COINS = {
    "Bitcoin (BTC)": "bitcoin",
    "Ethereum (ETH)": "ethereum",
    "Solana (SOL)": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "Dogecoin (DOGE)": "dogecoin",
}


def render():
    st.markdown("# ⚖️ Compare Strategies")
    st.caption("Run all 4 strategies on the same coin and see which wins")

    with st.sidebar:
        st.subheader("Compare Config")
        selected_label = st.selectbox("Coin", list(POPULAR_COINS.keys()))
        coin_id = POPULAR_COINS[selected_label]
        custom_coin = st.text_input("Or CoinGecko ID", placeholder="polkadot")
        if custom_coin:
            coin_id = custom_coin.lower().strip()

        start_date = st.date_input("Start", value=None)
        end_date = st.date_input("End", value=None)
        capital = st.number_input("Initial Capital ($)", value=10000, step=1000)
        run = st.button("⚖️ Compare All Strategies", type="primary")

    if run:
        with st.spinner("Running all 4 strategies..."):
            try:
                params = {"coingecko_id": coin_id, "initial_capital": capital}
                if start_date:
                    params["start_date"] = str(start_date)
                if end_date:
                    params["end_date"] = str(end_date)

                resp = requests.post(f"{API_BASE}/backtest/compare", params=params, timeout=120)
                resp.raise_for_status()
                results = resp.json()
            except Exception as e:
                st.error(f"API error: {e}")
                return

        if not results:
            st.error("No results returned.")
            return

        st.divider()

        # Leaderboard
        st.subheader("🏆 Strategy Leaderboard")
        medals = ["🥇", "🥈", "🥉", "4️⃣"]
        leaderboard = []
        for i, r in enumerate(results):
            leaderboard.append({
                "Rank": medals[i] if i < len(medals) else str(i+1),
                "Strategy": r["strategy_name"].replace("_", " ").title(),
                "Total Return": f"{r['total_return']:+.1%}",
                "vs Benchmark": f"{r['alpha']:+.1%}",
                "Sharpe": f"{r['sharpe_ratio']:.2f}",
                "Sortino": f"{r['sortino_ratio']:.2f}",
                "Max Drawdown": f"{r['max_drawdown']:.1%}",
                "Win Rate": f"{r['win_rate']:.1%}",
                "Trades": r["total_trades"],
            })

        df = pd.DataFrame(leaderboard)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Combined equity curves
        st.subheader("📈 All Strategies vs BTC Benchmark")
        colors = ["#6c63ff", "#00c853", "#ff9800", "#f44336"]
        fig = go.Figure()

        bench_added = False
        for i, r in enumerate(results):
            equity = r.get("equity_curve", [])
            if not equity:
                continue
            dates = [e["date"] for e in equity]
            values = [e["value"] for e in equity]
            bench = [e["benchmark_value"] for e in equity]

            strategy_name = r["strategy_name"].replace("_", " ").title()
            fig.add_trace(go.Scatter(
                x=dates, y=values,
                name=strategy_name,
                line=dict(color=colors[i % len(colors)], width=2)
            ))

            if not bench_added:
                fig.add_trace(go.Scatter(
                    x=dates, y=bench,
                    name="BTC Buy & Hold",
                    line=dict(color="#aaaaaa", width=2, dash="dash")
                ))
                bench_added = True

        fig.add_hline(y=capital, line_dash="dot", line_color="gray", opacity=0.4)
        fig.update_layout(
            height=450,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(t=30, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Side-by-side metric cards
        st.subheader("📊 Detailed Metrics")
        cols = st.columns(len(results))
        for i, (col, r) in enumerate(zip(cols, results)):
            with col:
                medal = medals[i] if i < len(medals) else ""
                st.markdown(f"**{medal} {r['strategy_name'].replace('_', ' ').title()}**")
                st.metric("Total Return", f"{r['total_return']:+.1%}")
                st.metric("Sharpe", f"{r['sharpe_ratio']:.2f}")
                st.metric("Max DD", f"{r['max_drawdown']:.1%}")
                st.metric("Win Rate", f"{r['win_rate']:.1%}")
    else:
        st.divider()
        st.markdown("### Select a coin in the sidebar and click Compare to run all 4 strategies head-to-head.")
        st.markdown("""
This view runs all strategies simultaneously on the same coin and time period, then ranks them by **Sharpe ratio** (risk-adjusted return).

**Benchmark:** BTC buy-and-hold (or ETH if testing BTC)
        """)
