# KAIROS LC Swing Engine V4

![Pine Script](https://img.shields.io/badge/Pine%20Script-v6-blue)
![Python](https://img.shields.io/badge/Python-QuantConnect-3776AB)
![Platform](https://img.shields.io/badge/Platform-TradingView-black)
![License](https://img.shields.io/badge/License-MPL--2.0-purple)

**KAIROS V4 is a TradingView strategy** combining Nadaraya–Watson kernel swing triggers with optional Lorentzian Classification (LC), ML vote confirmation and EMA/SMA entry filters. It retains V3's slope/Volatility Push (VP), fixed ATR exits, editable shares, cash loss control, session, alerts and navy/gold theme.

**Why Kairos?** Kairos personifies the opportune moment in Greek mythology. The name reflects waiting until the kernel's direction, enabled confirmations and trading hours align.

## Background: Lorentzian Classification and kernel regression

[Jdehorty's Lorentzian Classification](https://www.tradingview.com/script/WhBzgfDu-Machine-Learning-Lorentzian-Classification/) compares historical RSI, WaveTrend, CCI and ADX features using approximate neighbor classification. Its distance is:

```text
distance = sum(log(1 + abs(current feature - historical feature)))
```

The logarithm compresses large feature differences, reducing their contribution relative to an uncompressed distance. JDE's event-driven “price-time” analogy motivates handling noise and outliers. KAIROS compares features; it does not ingest news or event schedules.

[Nadaraya–Watson regression](https://www.tradingview.com/script/AWNvbPRM-Nadaraya-Watson-Rational-Quadratic-Kernel-Non-Repainting/) estimates price as a weighted average: `sum(weight × price) / sum(weight)`. KAIROS uses JDE's Rational Quadratic kernel to identify swings. Normally, a rising estimate is bullish and a falling estimate bearish. Optional Enhanced Smoothing instead compares a Gaussian estimate with the Rational Quadratic estimate. **The kernel flip triggers a trade; LC confirms it.**

## ML features and prediction

Features are normalized through JDE's `MLExtensions/2`. Each slot has an independent Enable checkbox, feature selector and editable parameters.

| Slot | Default feature | A / B | Information represented |
| --- | --- | --- | --- |
| 1 | RSI | 14 / 1 | Momentum |
| 2 | WaveTrend (WT) | 10 / 11 | Smoothed momentum |
| 3 | CCI | 20 / 1 | Price deviation / momentum |
| 4 | ADX | 20 / 2 | Trend strength; B ignored |
| 5 | RSI | 9 / 1 | Faster momentum |

**Feature Slots to Consider** uses the first N slots and their Enable switches. Different RSI settings create distinct features. LC requires at least one active feature.

V4 searches prior samples within a bounded rolling history. Its JDE-style chronological ANN loop accepts distances against a moving threshold, skips historical bar indices divisible by four and retains a bounded vote queue. This is an approximate persistent search, rather than a sorted exact k-nearest-neighbor search; samples can be revisited.

The published JDE label convention is retained: `source[4] < source` gives **−1**, `source[4] > source` gives **+1**, equality gives **0**. These labels use a known historical four-bar comparison, not a newly constructed future-return target. The current sample is added **after** prediction, so it cannot vote on itself.

Votes sum to the ML score: positive classifies long, negative short, zero retains direction. ML Prediction confirmation blocks zero/insufficient votes. LC requires completed warmup and a full vote queue. **Vote strength** is `abs(net votes) / votes used × 100`, not a probability of profit.

## Switches and ML defaults

| Section / setting | Default | Effect |
| --- | --- | --- |
| LC Direction Filter | ON | Master switch; require a ready matching classification |
| Neighbor Count | 8; range 1–100 | Maximum retained votes |
| Maximum Training History | 2,000 bars; range 100–5,000 | Rolling candidate/history window |
| Feature Slots / Training Label Source | 5 / close | Considered features and four-bar label input |
| ML Prediction Filter / Minimum Net Votes | ON / 1 | Long score ≥ threshold; short score ≤ negative threshold |
| EMA Entry Filter | ON / 200 | Long close above EMA; short below |
| SMA Entry Filter | ON / 200 | Long close above SMA; short below |

LC master OFF bypasses both LC and its ML vote check. EMA/SMA remain independently switchable. Turn off LC, EMA and SMA to restore V3 entry conditions. A vote threshold cannot exceed neighbor count when its check is active. Equal close/average passes neither direction; missing data blocks only enabled filters.

## How KAIROS takes trades

All enabled checks must agree on the **kernel-flip bar**:

| Check | Long | Short |
| --- | --- | --- |
| Direction enabled | Enable Longs | Enable Shorts |
| Kernel trigger | Newly bullish state | Newly bearish state |
| Session | Bar close inside entry window | Same |
| Slope | Normalized kernel slope ≥ minimum | Slope ≤ negative minimum |
| VP | Qualifying bullish push | Qualifying bearish push |
| LC / ML | Long classification and sufficient positive votes | Short classification and sufficient negative votes |
| EMA / SMA | Close above each enabled average | Close below each enabled average |
| Position / size | Flat or short; feasible quantity | Flat or long; feasible quantity |

A rejected flip does not become a pending entry. ML or average changes alone do not trigger trades or exits. No same-direction pyramiding is allowed; a qualified opposite entry closes the old direction and opens the requested new quantity.

VP awards one point each for ATR expansion, candle-range expansion and volume expansion, then checks directional candle body and close location. The matching push must fall within the backward-looking confirmation window and be newer than the opposing push. At the default score of 2, ATR and range alone can qualify: **volume expansion is not independently mandatory**.

V4 uses **chart-timeframe VP and fixed targets**. [V2](KAIROS_V2_Usage.md) separately contains adaptive partial profits and one-minute continuation checks.

## Inherited strategy parameters

| Setting | Pine V4 default |
| --- | --- |
| Trading session / timezone | 09:30–before 15:00 / America/New_York; intraday charts |
| Longs / shorts / opposite-flip exit / session close | All ON |
| Kernel source / lookback / relative weighting | Close / 8 / 8.0 |
| Regression Level | 25; passed to KernelFunctions' `_startAtBar` |
| Enhanced Smoothing / lag | OFF / 5; Gaussian bandwidth `max(1, lookback − lag)` |
| Slope filter / lookback / ATR / minimum | ON / 2 bars / 14 / 0.05 ATR |
| Require VP / confirmation window | ON / 0 bars; push on flip candle |
| VP fast / slow ATR | 5 / 20 |
| Minimum ATR ratio / range-to-ATR | 1.10 / 1.25 |
| Volume SMA / minimum volume ratio | 20 / 1.50 |
| Minimum VP score | 2 of 3 |
| Minimum body-to-ATR / body-to-range | 0.80 / 0.65 |
| Bull / bear close location | ≥0.70 / ≤0.30 |
| Profit / Stop / risk ATR | ON / 14 |
| Stop ATR multiple / target | 1.0 / 2.0R |
| Entry quantity | 1 share/contract; editable |
| Maximum Cash Loss / amount / box | ON / $500 USD / visible, bottom left |

## Position protection and exits

After a fill, `1R = risk ATR × stop multiple`. The target is entry price ± `1R × target R`; the ATR stop is one R away. Cash protection converts the configured account-currency loss into a price distance using **actual filled quantity**, symbol point value and tick size. The tighter ATR/cash stop and target share one exit bracket. Tightening the cash stop leaves the ATR-based target unchanged.

Quantity overrides Properties sizing and rounds down to the symbol minimum. An infeasible one-tick cash stop blocks entry. Cash protection works with Profit / Stop disabled; hiding the loss box does not disable it. Gaps, slippage and fees can exceed the configured cap.

An opposite kernel flip reverses only when the opposite entry qualifies; otherwise the optional opposite-flip exit closes the trade. Optional session close liquidates at the first bar closing at/after cutoff. ML/EMA/SMA do not add exit rules.

## Metrics, appearance and alerts

The table uses executed TradingView `strategy.*` results:

| Metric | Meaning |
| --- | --- |
| Closed trades; wins/losses/breakevens | Executed outcomes |
| Win rate / profit factor | Wins ÷ closed trades; gross profit ÷ absolute gross loss |
| Net profit / net return | Net P/L; net P/L ÷ initial capital |
| Average trade / maximum drawdown | Net P/L ÷ closed trades; maximum equity drawdown |
| Position / target | Current direction and configured R |
| LC / votes / neighbors / averages | Current classification, raw vote score, model usage and filter states |

Kernel/VP markers, stop/target lines and the loss box are configurable. Table fonts and bottom watermark text, size, font family and color are editable.

Use **Order fills** alerts for V4 order messages. Including **alert() function calls** adds optional filled-entry notifications and can duplicate entry messages. Long/short notification switches are separate. Recreate alerts after code or settings changes.

## Note on "repainting"

The supplied background describes **JDE's original indicator** as follows:

> To be clear, once a bar has closed, this indicator will NOT repaint. This is true for both the ML predictions and the Kernel estimate.

**For KAIROS V4:** the LC update path requires confirmed chart bars, excludes the current sample and has once-per-bar/fill-callback guards. The kernel uses current/past price inputs. However, KAIROS is a strategy with `process_orders_on_close=true` and `calc_on_order_fills=true`. [TradingView documents](https://www.tradingview.com/pine-script-docs/concepts/strategies/#calc_on_order_fills) that fill recalculations can produce historical/realtime differences and repainting after reload. The original indicator statement is therefore **not an unconditional guarantee for KAIROS trades or backtest results**.

## Use and validation

Copy [V4 Pine](KAIROS_LC_Swing_Engine_V4_JXS_918.pine) into TradingView's Pine Editor and add it to a standard intraday chart. Check Strategy Tester with realistic quantity, fees and slippage. Compare enabled/disabled filters on the same data, then evaluate unseen periods.

[V4 usage](KAIROS_V4_Usage.md) documents the model and source/logic tests (`python -m unittest discover -s tests -v`). These checks do not compile Pine, validate live non-repainting behavior or establish improved profitability.

## Separate QuantConnect V3 options port

The [Python options port](quantconnect/kairos_v3_spy_3min_backtest.py) remains **V3**, without V4 ML filters. It buys closest-ATM same-day SPY calls/puts with a $2,500 premium budget, using 3-minute signals and one-minute SPY exit checks.

Its preset differs from Pine: smoothing ON/lag 6, slope OFF, VP window 10, opposite-flip exit OFF, stop 1.5× ATR, target 0.45R, cash cap OFF. Corrected options-mode performance remains unverified. See [backtest settings and results](quantconnect/KAIROS_V3_BACKTEST.md).

## Attribution

**Author:** JXS_918 · [@woi-6ix](https://github.com/woi-6ix). LC feature/distance/ANN logic and [KernelFunctions/2](https://www.tradingview.com/script/e0Ek9x99-KernelFunctions/) adapted from **jdehorty**, under [MPL 2.0](LICENSE). [Third-party notices](THIRD_PARTY_NOTICES.md). [V3 source](KAIROS_LC_Swing_Engine_V3_JXS_918.pine) and earlier KAIROS/DELPHI versions remain available.
