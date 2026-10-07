# KAIROS V3 — QuantConnect options backtest

Copy all of `kairos_v3_spy_3min_backtest.py` into `main.py` in a new **Python** QuantConnect cloud project, save, set the project parameter **`execution_mode = options`** (replace any saved `shares` value), and run a backtest. Use the current cloud LEAN engine: shares mode uses native one-cancels-other (OCO) orders. The file is under the 32,000-character editor limit.

This port uses `KAIROS_LC_Swing_Engine_V3_JXS_918.pine` at commit `079ca3fc4e30eaa4eebb6cbc9dbfa628b52150b2`. It preserves v3's Rational Quadratic/Gaussian kernel flip, slope, directional Volatility Push, fixed entry ATR risk, and qualified reversal rules. Pine's chart appearance and alerts are omitted. The existing Pine files and repository README are unchanged.

## Requested defaults

| Parameter | Setting |
|---|---|
| Symbol | SPY |
| Default execution | Buy SPY calls for bullish signals; buy SPY puts for bearish signals |
| Expiration | 0DTE only: expires on the New York trading date |
| Strike | Closest available ATM strike |
| Signal timeframe | 3 minutes |
| Data / exit fill resolution | 1 minute |
| Premium budget per new bullish/bearish trade | USD 2,500; `floor(2500 / (fresh option ask × contract multiplier))` contracts |
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

**Sizing clarification:** The corrected default spends up to **$2,500 in SPY option premium per trade**, rounded down to whole contracts. For a standard 100 multiplier and $2 ask premium, it buys 12 contracts (quoted premium cost $2,400). Actual fills and fees can differ from the quoted budget. Both calls and puts are purchased; the bearish trade is a long put, not short SPY stock or short options. No SPY share orders are submitted in options mode. The previous shares-mode result concerned about three shares per position, not 2,000–2,500 shares, and does not measure this options version.

**R clarification:** Preserve v3's SPY signal-price exits: stop distance is `entry SPY ATR(14) × 1.5`; 1R is that underlying distance, and target distance is `0.45 × stop distance = 0.675 × ATR`. With SPY at $600 and ATR $2, a bullish/call position has SPY exit thresholds $597 and $601.35; a bearish/put position has $603 and $598.65. Options mode observes minute SPY closes and liquidates the held option when a threshold is reached. **These are SPY price thresholds, not option premium prices or guaranteed option return multiples.** P&L uses historical option fills. Shares mode instead anchors native stop/target orders to stock fills, with tick rounding.

**Opposite flips:** OFF disables the standalone exit on an opposite flip. A fully confirmed opposite entry still reverses, matching v3's Pine order logic. No same-direction pyramiding.

**VP window:** The latest matching directional push must be at most 10 bars old and more recent than the opposing push. This does not enter late by waiting 10 future bars. v3 uses the chart timeframe for VP; this port therefore uses 3-minute VP, not v2's separate one-minute VP behavior.

Entries use completed bar end timestamps within 09:30 <= time < 15:00. The first normal 3-minute bar closes at 09:33. The 15:00 bar cannot open a trade. Warmup updates indicators without trading. Half-days flatten one minute before the exchange closes and block further entries that day. SPY uses raw regular-session prices in both modes.

## Project parameters

The requested values are already configured. Add parameters only to override them:

| QuantConnect parameter | Default | Meaning |
|---|---|---|
| `execution_mode` | `options` | Actual SPY calls/puts; `shares` is a legacy comparison mode |
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

## Default historical options mode

The file now defaults to options. In an existing QC project, also set **`execution_mode = options`** so a saved shares-mode parameter cannot override the new default. Signals use SPY's 3-minute bars:

- Bullish signal buys an ATM call; bearish signal buys an ATM put. Puts provide bearish exposure; options are never sold short.
- Select **0DTE only**, then the closest strike, from a universe within five strikes either side including weekly contracts. Both the universe filter and the entry selector require same-day expiry in New York. Missing eligible 0DTE contracts skips the signal; later expirations are never substituted.
- Buy `floor(2500 / (fresh ask × contract multiplier))` contracts. For a standard 100 multiplier and $2 ask, that is 12 contracts. Quotes must be current, two-sided, non-fill-forward, positive, and non-crossed. Missing data or a premium exceeding the budget skips the signal, without a delayed retry or stock fallback.
- The ATR stop and target remain **SPY price levels**. Exits are triggered by observable minute SPY closing values, then execute on the held option at LEAN's simulated market fill. Intraminute SPY touches are not used to invent option prices. Thus this mode's risk timing differs from the native stock OCO bracket.
- Reported profit, loss and drawdown come from actual historical option premiums, not synthetic SPY returns. **0.45R is an underlying-price target, not a guaranteed option P&L multiple.** Theta, volatility, spreads and discrete contract quantities affect the result.
- The cash-cap toggle, if enabled, monitors option liquidation P&L using available fresh bid closes. It is OFF by default.
- Runtime statistics report execution mode, skipped option signals, and rejected orders.

QuantConnect supports options backtesting; the older DELPHI file's stock-only behavior is an implementation choice, not a prohibition on free-tier options. Free cloud historical data availability is documented by QuantConnect. Cloud runtime, engine version, account limits and available data still determine whether a particular run completes.

## Validation and execution limits

Python syntax compilation and local tests with a LEAN API double passed. Tests cover requested defaults/dates, whole-share sizing, fill anchors, long/short levels, cancellation before reversal, rejected reversal recovery, cash-cap tightening, cutoff, warmup, Wilder ATR, kernel formulas, VP direction/age, signal session boundaries, actual option-symbol selection, premium sizing, stale/missing quotes, signal expiry, and failed-liquidation retries. These tests do **not** run the LEAN engine or historical market data.

The user reported a completed **shares-mode** cloud backtest (`dd352261b3817907e167e31236bb5c20`) with no runtime errors or rejected orders. That result concerns stock shares. **The corrected options-mode default has not yet been run on QuantConnect cloud; no options historical performance is asserted.** Keep LEAN's default brokerage fee/fill models: stock slippage is zero by default; option quote data lets simulated market fills account for bid/ask spreads. These are modeling assumptions, not live fills. Native stock OCO prioritizes the stop when both exits could fill on the same minute. Partial stock exits are followed by liquidation of residual exposure on the next callback. Gaps/slippage can exceed stop or cash-cap levels. Data normalization, different data feeds, and fill timing can produce differences from TradingView.

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
