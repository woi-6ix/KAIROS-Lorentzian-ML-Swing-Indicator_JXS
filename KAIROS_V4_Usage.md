# KAIROS LC Swing Engine V4

V4 is a **Pine v6 strategy**, built from V3. It preserves V3's kernel trigger, session, slope/VP controls, editable entry quantity, fixed ATR target/stop, independent $500 cash cap, reversals, session close, alerts, navy/gold tables and editable watermark. New checks confirm entries; they do not introduce ML exits, adaptive profits or a separate one-minute VP checker.

## Independent switches

| Section | Default | Effect |
| --- | --- | --- |
| Enable LC Direction Filter | ON | Master LC switch; require a ready matching classification |
| Enable ML Prediction Filter | ON | Require net votes ≥1 for long or ≤−1 for short; subordinate to LC master |
| Enable EMA Entry Filter | ON, length 200 | Long close above EMA; short close below EMA |
| Enable SMA Entry Filter | ON, length 200 | Long close above SMA; short close below SMA |
| Enable Feature 1–5 | All ON | Remove individual feature contributions inside the considered slot count |
| Show New Filter Statistics | ON | Show LC, votes, neighbors/features and EMA/SMA state |
| Show ML Score in Data Window | ON | Display net votes and vote strength without price-scale plots |
| Show EMA / SMA Line | ON | Each line is independently hideable and hidden when its filter is disabled |

**Restore V3 entries:** turn off LC Direction, ML Prediction, EMA Entry and SMA Entry. LC master OFF already bypasses prediction confirmation, even if its child checkbox stays checked. V3's existing slope and VP switches remain separate.

With LC ON and ML Prediction OFF, classification persists through a zero-vote score, matching JDE's direction-state behavior. With prediction confirmation ON, zero/insufficient votes block entry. Missing ML or moving-average warmup data blocks only the enabled filter. Equal close/EMA or close/SMA passes neither direction.

## Classifier settings and features

Defaults: **8 neighbors**, **2,000 past bars**, **5 considered slots**, close as training-label source, **1 minimum net vote**. History is editable from 100 to 5,000 bars; neighbor count from 1 to 100. The vote threshold cannot exceed neighbor count. At least one considered feature must be enabled when LC is ON. Disabled LC bypasses these ML-only validation requirements.

| Slot | Feature | Parameter A | Parameter B |
| --- | --- | --- | --- |
| 1 | RSI | 14 | 1 |
| 2 | WaveTrend (WT) | 10 | 11 |
| 3 | CCI | 20 | 1 |
| 4 | ADX | 20 | 2; ignored by ADX |
| 5 | RSI | 9 | 1 |

Every slot has an Enable checkbox, feature selector and editable parameters. **Feature Slots to Consider** selects the first N slots; a checked slot beyond N is not used. Feature normalization calls JDE's `MLExtensions/2`.

Distance is `sum(log(1 + abs(current feature − historical feature)))` over enabled features. The JDE-style chronological ANN loop accepts distances against a moving threshold, skips bar indices divisible by four and keeps a persistent bounded vote queue. Its threshold uses the three-quarter queue index. This is an approximate persistent search, not a sorted exact nearest-neighbor search; retained samples can be revisited.

The published JDE four-bar labeling convention is retained: `source[4] < source` labels **−1**, `source[4] > source` labels **+1**, equality labels **0**. These known historical labels are attached to their sample's features; this is not a new forward-return labeling scheme. Positive net votes classify long, negative classify short; zero retains direction. Vote strength is `abs(net votes) / votes used × 100`, **not a probability of profit**.

Candidates precede the current query and fall within the rolling past-bar window. Buffers are bounded; expired votes are removed. Model updates/sample insertion occur at most once per confirmed chart bar, with fill-callback and rollback guards. V3's `calc_on_order_fills=true` remains enabled for risk management. TradingView's inherited fill/ATR simulation assumptions still apply; this guard does not validate V3's complete broker-emulator behavior.

## Entries, exits and testing

A long requires V3's bullish kernel flip, session, enabled slope/VP and each enabled V4 long gate. Shorts are symmetric. A rejected flip does not create a pending setup that can enter later merely because ML or an average changes. A new LC classification alone is not an entry trigger. EMA/SMA or ML changes alone do not close an existing trade; V3's stop/target, opposite-flip/reversal and session rules manage exits.

Entry size defaults to **1 share**, fixed target to **2R**, ATR multiple to **1.0**, and cash cap to **$500 enabled**, exactly as committed V3. The recent QuantConnect V3 options preset is a separate file with different settings; it has **not** been upgraded to V4.

Use **Order fills** alerts; include **alert() function calls** only if you also want the inherited optional filled-entry notification. All strategy/order naming is V4. Recreate alerts after loading V4 or changing settings.

Run source and logic checks from the repository root:

```bash
python -m unittest discover -s tests -v
```

Checks cover all filter switch combinations, V3 fallback, threshold/direction/neutral behavior, missing average data, feature masks, distance compression, known ANN votes, all neighbor counts, bounded history, excluded current samples and duplicate/fill callbacks. They do **not** compile Pine, execute TradingView or establish profitability. Compare V3 and V4 on the same symbol, dates, position size, fees and slippage, then evaluate separate unseen periods before choosing settings.

Source: [KAIROS V4 Pine](KAIROS_LC_Swing_Engine_V4_JXS_918.pine). Adaptation: JXS_918. JDE feature/distance/ANN and kernel work used under MPL 2.0.
