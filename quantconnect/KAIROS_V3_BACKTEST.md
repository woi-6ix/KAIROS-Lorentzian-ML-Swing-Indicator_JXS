# KAIROS V3 — QuantConnect backtest

Copy all of `kairos_v3_spy_3min_backtest.py` into `main.py` in a new **Python** QuantConnect cloud project, save, and run a backtest. Use the current cloud LEAN engine: shares mode uses native one-cancels-other (OCO) orders. The file is under the 32,000-character editor limit.

This port uses `KAIROS_LC_Swing_Engine_V3_JXS_918.pine` at commit `079ca3fc4e30eaa4eebb6cbc9dbfa628b52150b2`. It preserves v3's Rational Quadratic/Gaussian kernel flip, slope, directional Volatility Push, fixed entry ATR risk, and qualified reversal rules. Pine's chart appearance and alerts are omitted. The existing Pine files and repository README are unchanged.

## Requested defaults

| Parameter | Setting |
|---|---|
| Symbol | SPY |
| Default execution | SPY shares, long or short |
| Signal timeframe | 3 minutes |
| Data / exit fill resolution | 1 minute |
| Allocation per new long/short | USD 2,500; `floor(2500 / signal close)` shares |
| One-year backtest | ON |
| Default test dates | October 7, 2025 – October 6, 2026, inclusive |
| Exit on unconfirmed opposite kernel flip | OFF |
| Enhanced smoothing | ON |
| Smoothing lag | 6 |
| Slope filter | OFF |
| Volatility Push required | ON |
| VP confirmation window | 10 completed 3-minute bars, backward-looking |
| Profit target | 0.45R |
| Stop | 1.5 × ATR(14), fixed at entry |
| Trading session | 09:30–15:00 America/New_York, with DST |
| Close at session end | ON |
| Maximum cash loss toggle | OFF |
| Initial account cash | USD 100,000 |

**Sizing clarification:** The user selected **$2,500 in SPY shares**, rather than 2,500 shares. Pine's `Entry Quantity / Shares = 2500` would mean **2,500 shares**. This Python version deliberately uses the selected dollar allocation: at $600, it opens four shares ($2,400 signal notional). Fill-price differences and fees can change actual cost. The allocation is neither stop-loss risk nor account starting cash.

**R clarification:** Stop distance is `entry ATR(14) × 1.5`. One R equals that distance; target distance is `0.45 × stop distance = 0.675 × ATR`. With an entry at $600 and ATR $2, a long has stop $597 and target $601.35; a short has stop $603 and target $598.65. Levels are rounded to the stock's tick size and anchored to actual stock entry fills. Enabling the separate cash cap can tighten the stop without changing the ATR-derived target.

**Opposite flips:** OFF disables the standalone exit on an opposite flip. A fully confirmed opposite entry still reverses, matching v3's Pine order logic. No same-direction pyramiding.

**VP window:** The latest matching directional push must be at most 10 bars old and more recent than the opposing push. This does not enter late by waiting 10 future bars. v3 uses the chart timeframe for VP; this port therefore uses 3-minute VP, not v2's separate one-minute VP behavior.

Entries use completed bar end timestamps within 09:30 <= time < 15:00. The first normal 3-minute bar closes at 09:33. The 15:00 bar cannot open a trade. Warmup updates indicators without trading. Half-days flatten one minute before the exchange closes and block further entries that day. SPY uses raw regular-session prices in both modes.

## Project parameters

The requested values are already configured. Add parameters only to override them:

| QuantConnect parameter | Default | Meaning |
|---|---|---|
| `execution_mode` | `shares` | `shares` or `options` |
| `one_year_backtest` | `true` | Test the 365 calendar dates ending on `end_date`; OFF uses the full-history start |
| `end_date` | `2026-10-06` | Inclusive test end, YYYY-MM-DD |
| `full_history_start_date` | `2024-01-01` | Used only with one-year toggle OFF |
| `dollars_per_trade` | `2500` | Share allocation, or option premium budget in options mode |
| `exit_on_opposite_kernel_flip` | `false` | Standalone opposite-flip exit |
| `use_kernel_smoothing` | `true` | Enhanced smoothing |
| `kernel_lag` | `6` | Smoothing lag |
| `use_slope_filter` | `false` | ATR-normalized kernel slope filter |
| `vp_confirmation_window` | `10` | Matching push age in signal bars |
| `stop_atr_multiple` | `1.5` | Fixed entry ATR stop multiple |
| `profit_target_r` | `0.45` | Target / original ATR stop distance |
| `enable_cash_loss_cap` | `false` | Independent cash-loss stop |
| `maximum_cash_loss` | `500` | Inactive default cash cap, excludes fees |

Other preserved settings: kernel source close, lookback 8, relative weight 8, regression level 25; VP fast/slow ATR 5/20, volume SMA 20, minimum score 2/3, minimum ATR ratio 1.10, range/ATR 1.25, volume ratio 1.50, body/ATR 0.80, body/range 0.65, bullish/bearish close location 0.70/0.30. No additional EMA/SMA/ML entry filters.

## Optional historical options mode

To backtest actual options instead of the selected shares default, set **`execution_mode = options`** in the QC project parameters. Signals still use SPY's 3-minute bars:

- Bullish signal buys an ATM call; bearish signal buys an ATM put. Puts provide bearish exposure; options are never sold short.
- Select the nearest expiration within 0–2 calendar days, then closest strike, from a universe within five strikes either side including weekly contracts. This expiry/strike rule is an explicit added default because Pine does not select options.
- Buy `floor(2500 / (fresh ask × contract multiplier))` contracts. For a standard 100 multiplier and $2 ask, that is 12 contracts. Quotes must be current, two-sided, non-fill-forward, positive, and non-crossed. Missing data or a premium exceeding the budget skips the signal, without a delayed retry or stock fallback.
- The ATR stop and target remain **SPY price levels**. Exits are triggered by observable minute SPY closing values, then execute on the held option at LEAN's simulated market fill. Intraminute SPY touches are not used to invent option prices. Thus this mode's risk timing differs from the native stock OCO bracket.
- Reported profit, loss and drawdown come from actual historical option premiums, not synthetic SPY returns. **0.45R is an underlying-price target, not a guaranteed option P&L multiple.** Theta, volatility, spreads and discrete contract quantities affect the result.
- The cash-cap toggle, if enabled, monitors option liquidation P&L using available fresh bid closes. It is OFF by default.
- Runtime statistics report execution mode, skipped option signals, and rejected orders.

QuantConnect supports options backtesting; the older DELPHI file's stock-only behavior is an implementation choice, not a prohibition on free-tier options. Free cloud historical data availability is documented by QuantConnect. Cloud runtime, engine version, account limits and available data still determine whether a particular run completes.

## Validation and execution limits

Python syntax compilation and local tests with a LEAN API double passed. Tests cover requested defaults/dates, whole-share sizing, fill anchors, long/short levels, cancellation before reversal, rejected reversal recovery, cash-cap tightening, cutoff, warmup, Wilder ATR, kernel formulas, VP direction/age, signal session boundaries, actual option-symbol selection, premium sizing, stale/missing quotes, signal expiry, and failed-liquidation retries. These tests do **not** run the LEAN engine or historical market data.

No QuantConnect cloud backtest was run as part of this conversion, and no historical performance is asserted. Keep LEAN's default brokerage fee/fill models: stock slippage is zero by default; option quote data lets simulated market fills account for bid/ask spreads. These are modeling assumptions, not live fills. Native stock OCO prioritizes the stop when both exits could fill on the same minute. Partial stock exits are followed by liquidation of residual exposure on the next callback. Gaps/slippage can exceed stop or cash-cap levels. Data normalization, different data feeds, and fill timing can produce differences from TradingView.

Run local logic tests from the repository root:

```bash
python -m unittest discover -s quantconnect/tests -v
```

## Official references

- [Equity option universes and subscriptions](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity-options)
- [Equity option chains and quotes](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/equity-options/handling-data)
- [Native OCO orders, stop-first backtest behavior and brokerage support](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/one-cancels-other-orders)
- [US Equity Options historical dataset](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-equity-options)

Kernel attribution: jdehorty / KernelFunctions. Adaptation: JXS_918. Source code is distributed under MPL 2.0, as in the parent repository.
