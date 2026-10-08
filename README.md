# KAIROS LC Swing Engine V3

![Pine Script](https://img.shields.io/badge/Pine%20Script-v6-blue)
![Python](https://img.shields.io/badge/Python-QuantConnect-3776AB)
![Platform](https://img.shields.io/badge/Platform-TradingView-black)
![License](https://img.shields.io/badge/License-MPL--2.0-purple)

**KAIROS V3** trades intraday kernel flips with slope and directional Volatility Push confirmation, fixed ATR targets/stops, editable entry shares and an independent cash-loss cap.

**Why Kairos?** Kairos personifies the opportune moment in Greek mythology: waiting until direction, confirmation and trading hours align before entering a swing.

## Background

[Jdehorty's Lorentzian Classification](https://www.tradingview.com/script/WhBzgfDu-Machine-Learning-Lorentzian-Classification/) compares historical RSI, WaveTrend, CCI and ADX features using approximate neighbor classification. Its `sum(log(1 + abs(feature difference)))` distance compresses large differences when forming directional predictions.

**V3 uses the kernel component of that work.** The full feature/neighbor classifier remains in the legacy DELPHI source; V3 has no neighbor-count, ML-prediction or EMA/SMA entry filter.

[Nadaraya–Watson regression](https://www.tradingview.com/script/AWNvbPRM-Nadaraya-Watson-Rational-Quadratic-Kernel-Non-Repainting/) estimates price through a kernel-weighted average. V3 uses jdehorty's [KernelFunctions/2](https://www.tradingview.com/script/e0Ek9x99-KernelFunctions/) Rational Quadratic estimate: rising/falling values set direction. Enhanced smoothing instead compares Gaussian and Rational Quadratic estimates, using Gaussian bandwidth `max(1, lookback − lag)`.

## Trading logic

1. **Trigger:** A new bullish kernel state triggers long; a new bearish state triggers short. No same-direction pyramiding; qualified opposite entries reverse.
2. **Confirm:** Optional ATR-normalized slope and directional VP must pass. VP scores ATR, candle-range and volume expansion, then checks candle body and close location. The matching push must be within the backward-looking window and newer than the opposing push.
3. **Session:** Signal-bar closing time must fall inside the New York entry window. Session cutoff optionally liquidates remaining positions at the first bar closing at/after cutoff.
4. **Protect/exit:** After fills, `1R = ATR × stop multiple`; target distance is `1R × target R`. The tighter ATR/cash stop shares one exit bracket. Optional opposite-flip exits close trades without a qualifying reversal.

V3 uses **chart-timeframe VP and fixed targets**. [V2](KAIROS_V2_Usage.md) separately provides adaptive partial profits and one-minute continuation checks. A VP score of 2 can pass through ATR and range alone; the volume point is not independently mandatory.

## Parameters

Pine defaults below come from committed V3 code. Your configured preset comes from the [QuantConnect port](quantconnect/kairos_v3_spy_3min_backtest.py), independently of saved TradingView inputs.

| Parameter | Pine V3 default | Configured QuantConnect preset |
| --- | --- | --- |
| Instrument / signal interval | Chart symbol / interval | SPY / 3 minutes |
| Session / timezone | 09:30–before 15:00 / America/New_York | Same; DST aware |
| Longs / shorts / session close | ON / ON / ON | Same |
| Opposite kernel-flip exit | ON | OFF; qualified reversals enabled |
| Kernel source / lookback / relative weight | Close / 8 / 8.0 | Same |
| Regression Level | 25; library `_startAtBar` | Same |
| Enhanced smoothing / lag | OFF / 5 | ON / 6 |
| Slope filter / lookback / ATR / minimum | ON / 2 / 14 / 0.05 ATR | OFF; same thresholds |
| Require VP / confirmation window | ON / 0 bars | ON / 10 signal bars |
| VP fast / slow ATR | 5 / 20 | Same |
| Minimum ATR ratio / range-to-ATR | 1.10 / 1.25 | Same |
| Volume SMA / minimum volume ratio | 20 / 1.50 | Same |
| Minimum VP score | 2 of 3 | Same |
| Minimum body-to-ATR / body-to-range | 0.80 / 0.65 | Same |
| Bull / bear close location | ≥0.70 / ≤0.30 | Same |
| Profit / Stop enabled; risk ATR | ON; 14 | Same |
| Stop ATR multiple / target R | 1.0 / 2.0R | 1.5 / 0.45R |
| Entry size | 1 share/contract; editable | $2,500 option-premium budget |
| Cash cap / amount | ON / $500 USD | OFF / $500 inactive |
| Loss box | Visible; bottom left | Chart display omitted |

A zero VP window requires the flip candle's push; 10 looks backward rather than delaying entry. Pine quantity overrides Properties sizing and rounds down to the symbol minimum. Cash protection works with Profit / Stop disabled; hiding its box leaves protection enabled. An infeasible one-tick cash stop blocks entry. Cash tightening preserves the ATR-based target; gaps/slippage/fees can exceed the cap.

## Metrics and controls

V3's table uses actual TradingView `strategy.*` results:

| Metric | Calculation / meaning |
| --- | --- |
| Closed trades; wins/losses/breakevens | Executed outcomes |
| Win rate / profit factor | Wins ÷ closed trades; gross profit ÷ absolute gross loss |
| Net profit / net return | Net P/L; net P/L ÷ initial capital |
| Average trade / maximum drawdown | Net P/L ÷ closed trades; maximum equity drawdown |
| Position / target | Current direction and configured R target |

The navy/gold theme includes kernel/VP markers, stop/target lines and a loss box displaying quantity, open P/L and effective stop exposure. Table fonts and bottom watermark text, size, family and color are editable.

Use **Order fills** alerts for order messages; include **alert() function calls** for optional filled-entry notifications, which can duplicate entry messages. Recreate alerts after changes. Pine uses `process_orders_on_close=true` and `calc_on_order_fills=true`; review simulated fills, fees and slippage in Strategy Tester.

## QuantConnect: 0DTE options

The [Python port](quantconnect/kairos_v3_spy_3min_backtest.py) buys closest-ATM **same-day-expiry SPY calls** on bullish signals and **puts** on bearish signals, within a $2,500 premium budget. Missing eligible contracts/quotes skips entry. Signals use 3-minute bars; exits observe one-minute SPY closes.

The preset's `0.45R` target equals `0.675 × SPY ATR(14)`: **an underlying-price threshold, not an option-premium return**. Test window: **2025-10-07–2026-10-06**; initial cash **$100,000**. The recorded cloud run used shares mode; corrected options-mode historical performance remains unverified. See [backtest details](quantconnect/KAIROS_V3_BACKTEST.md).

## Use and attribution

Copy [V3 Pine](KAIROS_LC_Swing_Engine_V3_JXS_918.pine) into TradingView's Pine Editor and add it to an intraday chart. Pine trades the chart symbol; the separate Python port supplies the documented options workflow.

**Author:** JXS_918 · [@woi-6ix](https://github.com/woi-6ix). Kernel logic adapted from **jdehorty**, under [MPL 2.0](LICENSE). [Third-party notices](THIRD_PARTY_NOTICES.md). Earlier KAIROS/DELPHI sources remain available.
