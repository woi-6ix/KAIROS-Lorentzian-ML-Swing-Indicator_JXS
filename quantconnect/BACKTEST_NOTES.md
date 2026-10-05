# DELPHI 3 Backtest Note

This DELPHI 3 implementation backtests **SPY stock/ETF shares only**. It does **not** backtest SPY options.

Applies to: [delphi_3_quant_connect_backtest_spy_3min.py](delphi_3_quant_connect_backtest_spy_3min.py).

- Long entries buy SPY shares; short entries sell SPY shares short.
- The $1,000 setting is a position allocation, rounded down to whole shares. It is not an options-premium budget or $1,000 of stop-loss risk.
- Reported profit, loss, drawdown, and fees are for the share trades. They do not represent call or put returns.

QuantConnect supports options backtesting, but options execution is not implemented in this script. An options version would need contract selection, strike and expiration rules, premium-based sizing, and options-specific execution and fee handling.
