# Comprehensive Strategy Research Results

Date: 2026-02-19
Symbol: `BTCUSDT`
Window: last 6 months
Starting equity: `$10,000`
Per-trade notional: `$1,000`
Costs modeled:
- Fee: `10 bps` per side
- Slippage: `5 bps` per side

## What Was Added
1. `cryptobot/backtest_research.py`
   - Long/short simulation
   - Stop-loss and take-profit
   - Trend filter (EMA 50/200)
   - RSI filter
   - Annualized volatility risk-off filter
   - Fee + slippage modeling
   - Annualized return, max drawdown, and Sharpe-like metrics
2. `tests/test_backtest_research.py`
   - Metric validation for annualization and max drawdown

## Multi-Interval Sweep (30m to 12h)
Best configurations found:

1. `6h` interval
   - Annualized return: `9.96%`
   - Total return (6 months): `4.79%`
   - Max drawdown: `0.71%`
   - Trades: `26`
   - Params: `macd=8/21/5`, `vol=1.0`, `SL=2%`, `TP=6%`, `trend_filter=false`, `short=true`, `rsi_filter=false`

2. `30m` interval
   - Annualized return: `9.61%`
   - Total return (6 months): `4.63%`
   - Max drawdown: `1.98%`
   - Trades: `98`
   - Params: `macd=12/26/9`, `vol=1.0`, `SL=2%`, `TP=6%`, `trend_filter=true`, `short=true`, `rsi_filter=false`

Configurations above annualized `8%`: `4`

## 15m Interval Coverage (Targeted Subset)
Top result:
- Annualized return: `1.67%`
- Total return: `0.82%`
- Max drawdown: `3.06%`
- Trades: `136`
- No configuration above annualized `8%` in this targeted set.

## Out-of-Sample Sanity Check (4 months train / 2 months test)
1. 6h winner
   - Train: `6.16%` annualized
   - Test: `-1.81%` annualized
2. 30m winner
   - Train: `5.58%` annualized
   - Test: `20.77%` annualized

Interpretation:
- The 30m profile shows stronger short-window robustness than the 6h profile.
- More walk-forward validation is still needed before any live deployment.

## Additional Model Families Requested
Specific models tested:
1. Regime-switching trend model (`regime_trend_macd`)
2. Breakout with ATR risk controls (`breakout_atr`)
3. Range-only mean reversion (`range_mean_reversion`)

Command used:
```sh
python3 -m cryptobot.backtest_regime_models --months 6 --intervals 30m,1h,2h,4h,6h,8h,12h --hurdle 8
```

Outcome:
- Best annualized result in this set: `1.27%` (`breakout_atr @ 8h`)
- Configurations above annualized `8%`: `0`

## Walk-Forward Optimization (Cataloged Follow-up)
To check robustness and avoid overfitting, a 3-fold walk-forward optimization was run:

Command used:
```sh
python3 -m cryptobot.backtest_regime_optimize --months 6 --intervals 30m,1h,2h,4h,6h,8h,12h --top 30
```

Result summary:
- Top-ranked candidates were still negative on average annualized return.
- Robust candidates meeting both:
  - average annualized return `>= 8%`
  - at least `2/3` folds `>= 8%`
  were: `0`.

Conclusion:
- Current data window and cost assumptions do not support robust `>8%` annualized performance for these three model families.
