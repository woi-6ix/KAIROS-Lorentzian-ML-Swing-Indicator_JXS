# KAIROS LC Swing Engine V4

![Pine Script](https://img.shields.io/badge/Pine%20Script-v6-blue)
![Python](https://img.shields.io/badge/Python-QuantConnect-3776AB)
![Platform](https://img.shields.io/badge/Platform-TradingView-black)
![License](https://img.shields.io/badge/License-MPL--2.0-purple)

**KAIROS V4 is a TradingView strategy** combining Nadaraya–Watson kernel swing triggers with optional Lorentzian Classification (LC), ML vote confirmation and EMA/SMA entry filters. It retains V3's slope/Volatility Push (VP), fixed ATR exits, editable shares, cash loss control, session, alerts and navy/gold theme.

**Inspiration:** KAIROS was inspired by **jdehorty's open-source Lorentzian Classification and kernel regression code**. JXS_918 adapted that foundation into this strategy's entry confirmations, position protection, session controls and presentation. Original work and supporting sources are linked under References.

**Why Kairos?** Kairos personifies the opportune moment in Greek mythology. The name reflects waiting until the kernel's direction, enabled confirmations and trading hours align.

## Overview: how the machine learning works

**Machine learning (ML)** here means classifying today's market state using stored historical examples. Each bar becomes a **feature vector**: a list of normalized indicator readings describing momentum, price deviation and trend strength. A **label** is the directional value attached to a historical example.

**Nearest-neighbor classification** compares a new feature vector with historical vectors, finds similar examples and combines their labels. In conventional **k-nearest neighbors (kNN)**, `k` is the number of closest examples used for voting. “Near” refers to similarity in indicator readings, not simply nearby dates. Feature normalization helps prevent an indicator's larger numerical scale from dominating the comparison. [1]

### Euclidean distance versus LC distance

**Euclidean distance** measures straight-line separation between feature vectors. It squares each feature difference, adds those squares and takes the square root. Large differences can dominate the resulting distance. [2]

KAIROS's **Lorentzian Classification (LC)** uses a logarithmic distance instead. For each enabled normalized feature, let `difference = current value − historical value`:

```text
Euclidean: sqrt(sum(difference²))
LC:        sum(log(1 + abs(difference)))
```

The logarithm compresses large differences, changing which historical states look similar. The motivation is to limit the influence of unusual readings during noisy markets or major events. The original LC overview's “price-time” analogy describes this motivation; KAIROS itself uses indicator values rather than news or event schedules. This metric choice does not establish superior trading performance. [3]

### Approximate neighbors in KAIROS

KAIROS uses **approximate nearest neighbors (ANN)**: a chronological candidate scan with a moving acceptance threshold and persistent vote queue. Its Neighbor Count controls retained votes. It does not sort the history to select the exact `k` smallest distances. The implementation and labels are explained below. Historical feature comparisons produce the ML score, which confirms a kernel trigger.

### Nadaraya–Watson kernel regression

The kernel estimates price through a weighted average: `sum(weight × price) / sum(weight)`. Rational Quadratic weights smooth price across past observations; a rising estimate is bullish and a falling estimate bearish. Optional Enhanced Smoothing compares Gaussian and Rational Quadratic estimates to determine direction. **The kernel flip triggers a trade; LC confirms it.** This price estimator and the feature-based classifier perform separate jobs. [4]

## ML features and prediction

Features are normalized through the imported `MLExtensions/2` library. Each slot has an independent Enable checkbox, feature selector and editable parameters.

| Slot | Default feature | A / B | Information represented |
| --- | --- | --- | --- |
| 1 | Relative Strength Index (RSI) | 14 / 1 | Momentum |
| 2 | WaveTrend (WT) | 10 / 11 | Smoothed momentum |
| 3 | Commodity Channel Index (CCI) | 20 / 1 | Price deviation / momentum |
| 4 | Average Directional Index (ADX) | 20 / 2 | Trend strength; B ignored |
| 5 | RSI | 9 / 1 | Faster momentum |

**Feature Slots to Consider** uses the first N slots and their Enable switches. Different RSI settings create distinct features. LC requires at least one active feature.

V4 searches prior samples within a bounded rolling history. Its chronological ANN loop accepts distances against a moving threshold, skips historical bar indices divisible by four and retains a bounded vote queue. This is an approximate persistent search, rather than a sorted exact k-nearest-neighbor search; samples can be revisited.

The original LC label convention is retained: `source[4] < source` gives **−1**, `source[4] > source` gives **+1**, equality gives **0**. These labels use a known historical four-bar comparison, not a newly constructed future-return target. The current sample is added **after** prediction, so it cannot vote on itself.

Votes sum to the ML score: positive classifies long, negative short, zero retains direction. For example, six +1 votes and two −1 votes produce a score of +4. ML Prediction confirmation blocks zero/insufficient votes. LC requires completed warmup and a full vote queue. **Vote strength** is `abs(net votes) / votes used × 100`, not a probability of profit.

## Switches and ML defaults

**EMA** is an exponential moving average, weighting recent prices more heavily; **SMA** is a simple moving average of the selected number of closes. Both filters compare price with an average; they are separate from the ML vote threshold.

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

### VP: Volatility Push

**VP means Volatility Push**: the strategy's confirmation of a strong directional candle during expanding market activity. **ATR (Average True Range)** measures recent price movement and provides the scale for its range/body tests.

VP awards one point each for fast/slow ATR expansion, candle range relative to slow ATR, and volume relative to its moving average. A bullish push also requires an up candle, sufficient body size and a close near its high; a bearish push requires the opposite. The matching push must fall within the backward-looking confirmation window and be newer than the opposing push. At the default score of 2, ATR and range alone can qualify: **volume expansion is not independently mandatory**.

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

The supplied wording for **the original LC indicator** states [3]:

> To be clear, once a bar has closed, this indicator will NOT repaint. This is true for both the ML predictions and the Kernel estimate.

**For KAIROS V4:** the LC update path requires confirmed chart bars, excludes the current sample and has once-per-bar/fill-callback guards. The kernel uses current/past price inputs. However, KAIROS is a strategy with `process_orders_on_close=true` and `calc_on_order_fills=true`. [TradingView documents](https://www.tradingview.com/pine-script-docs/concepts/strategies/#calc_on_order_fills) that fill recalculations can produce historical/realtime differences and repainting after reload. The original indicator statement is therefore **not an unconditional guarantee for KAIROS trades or backtest results**.

## Use and validation

Copy [V4 Pine](KAIROS_LC_Swing_Engine_V4_JXS_918.pine) into TradingView's Pine Editor and add it to a standard intraday chart. Check Strategy Tester with realistic quantity, fees and slippage. Compare enabled/disabled filters on the same data, then evaluate unseen periods.

[V4 usage](KAIROS_V4_Usage.md) documents the model and source/logic tests (`python -m unittest discover -s tests -v`). These checks do not compile Pine, validate live non-repainting behavior or establish improved profitability.

## Separate QuantConnect V3 options port

The [Python options port](quantconnect/kairos_v3_spy_3min_backtest.py) remains **V3**, without V4 ML filters. It buys closest-ATM same-day SPY calls/puts with a $2,500 premium budget, using 3-minute signals and one-minute SPY exit checks.

Its preset differs from Pine: smoothing ON/lag 6, slope OFF, VP window 10, opposite-flip exit OFF, stop 1.5× ATR, target 0.45R, cash cap OFF. Corrected options-mode performance remains unverified. See [backtest settings and results](quantconnect/KAIROS_V3_BACKTEST.md).

## Author and license

**Author:** JXS_918 · [@woi-6ix](https://github.com/woi-6ix). Adapted code is covered by [MPL 2.0](LICENSE); see [third-party notices](THIRD_PARTY_NOTICES.md). [V3 source](KAIROS_LC_Swing_Engine_V3_JXS_918.pine) and earlier KAIROS/DELPHI versions remain available.

## References

1. **scikit-learn:** [Nearest Neighbors](https://scikit-learn.org/stable/modules/neighbors.html) — feature-space similarity, kNN and classification by neighbor votes.
2. **SciPy:** [Euclidean distance](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.euclidean.html) — mathematical definition of the comparison metric.
3. **jdehorty:** [Machine Learning: Lorentzian Classification](https://www.tradingview.com/script/WhBzgfDu-Machine-Learning-Lorentzian-Classification/) — original inspiration, logarithmic feature distance, feature engineering and ANN logic.
4. **jdehorty:** [Nadaraya–Watson Rational Quadratic Kernel](https://www.tradingview.com/script/AWNvbPRM-Nadaraya-Watson-Rational-Quadratic-Kernel-Non-Repainting/) and [KernelFunctions](https://www.tradingview.com/script/e0Ek9x99-KernelFunctions/) — kernel estimator and imported functions.
5. **Kerimbekov, Bilge & Uğurlu (2016):** [The use of Lorentzian distance metric in classification problems](https://doi.org/10.1016/j.patrec.2016.09.006).
6. **Kerimbekov & Bilge (2017):** [Lorentzian Distance Classifier for Multiple Features](https://www.scitepress.org/Papers/2017/61970/) — DOI: 10.5220/0006197004930501.
7. **TradingView:** [Pine strategies and order-fill recalculation](https://www.tradingview.com/pine-script-docs/concepts/strategies/#calc_on_order_fills) — execution and backtest behavior.

The research papers provide broader classification background; their methods and datasets are not a validation of KAIROS's logarithmic distance, trading rules or profitability.
