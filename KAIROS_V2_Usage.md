# KAIROS LC Swing Engine V2

V2 keeps the original kernel flip, trading-session, entry slope and directional Volatility Push filters. It adds staged exits while retaining the navy/gold theme, naming explanation, statistics, watermark controls and native order-fill alerts. V1 remains a separate file.

## Default behavior

| Control | Default |
| --- | --- |
| Chart | Intraday, 1 minute or higher; 3-minute and 5-minute charts supported |
| Continuation VP timeframe | Always 1 minute, independent of the chart interval |
| Trading hours | 09:30 to before 15:00 America/New_York; editable |
| Position quantity | 100 underlying shares/contracts; editable and rounded to the symbol minimum |
| Initial capital / account currency | 100,000 USD / USD; adjustable in strategy Properties |
| Definition of 1R | ATR(14) times 1.0, frozen at the entry signal and rounded to ticks |
| First partial | 25% of original quantity at a close of at least 0.4R |
| Second partial | 25% of original quantity at a close of at least 0.7R |
| Later partials | 10% of original quantity at 0.8R, 0.9R, 1.0R, etc. |
| Continuation | Latest directional 1-minute VP within 2 one-minute bars, at or after entry, no newer opposing VP, correct chart kernel color; optional chart slope check enabled |
| Adverse-candle exit | One opposite-color candle closes the remainder; count and switch editable |
| Maximum cash loss | Enabled, 500 USD; amount editable |
| Cash loss display | Enabled, bottom left; separate visibility and protection switches |

A long's adverse candle has close below open; a short's has close above open. Dojis reset the consecutive-adverse count. If an opposite entry qualifies on that same candle, a reversal can close the old remainder and open the new direction. Session and cash-loss exits take priority over reversals.

## One-minute volume checks on higher charts

On a 3-minute chart, the continuation checker uses completed 1-minute candles inside each chart candle. The existing directional Volatility Push formula, including ATR lengths, volume average, candle shape, score and push ages, is evaluated entirely in the 1-minute context. The original entry VP filter and its chart markers continue to use the chart timeframe. Both contexts share the editable Volatility Push thresholds.

Freshness is counted in actual 1-minute bars, not chart bars: a setting of 2 permits a push on the latest completed minute or either of the previous two. The checker retains the ordering of pushes inside a larger candle. A newer opposing push defeats continuation even if an earlier minute in that same chart candle had a qualifying push. Pushes from before entry do not qualify the new position.

Entries, kernel color, slope, adverse-candle exits and profit orders are evaluated at confirmed chart closes. A 3-minute chart therefore uses 1-minute volume information but makes its next adaptive profit decision at the 3-minute close; it does not submit a profit order every minute. The statistics row **Continuation VP · 1m** shows the latest fresh direction and age, or missing/stale data. That row describes the volume signal; continuation also requires the position-entry timestamp, kernel and enabled slope checks to pass.

TradingView limits historical lower-timeframe coverage and some feeds omit inactive minutes. If no completed 1-minute intrabars are available on a higher chart, continuation fails rather than substituting the chart's volume signal. At a reached adaptive target, the remainder then closes. On a 1-minute chart the checker uses the same confirmed chart candles directly. Seconds charts and daily-or-higher charts are unsupported.

## Profit-taking semantics

These are close-confirmed market exits, not resting limit orders at the target prices. A wick alone reaching a target does not trigger profit-taking. A qualifying close triggers at most one stage per bar. Execution is simulated on that closing tick, subject to TradingView's configured execution/slippage behavior.

At a reached target, directional 1-minute VP, chart kernel color and the optional chart continuation slope must pass to take a partial and advance to the next target. Otherwise the entire remaining position closes. If price has not reached the next target, the position continues subject to stops, adverse candles, kernel exits and session cutoff.

Each slice is a percentage of ORIGINAL quantity, rounded down to a tradable unit, with a one-unit minimum. The last slice is capped at the remaining quantity. A one-share position therefore exits completely at the first stage. With the default 100 units, slices are 25, 25, then five slices of 10; the position is fully closed at the 1.2R stage if all continuation checks keep passing. Change the partial percentages to retain a runner for longer.

Disabling adaptive profits enables the editable fixed 2R close-confirmed full exit instead. Disabling ATR stops does not disable adaptive profit targets or the independent cash-loss cap.

## Maximum loss

The cap applies to the remaining OPEN position, not a daily account loss or cumulative trade P/L including realized partial profits. It is expressed in USD account currency. Symbol currency conversion, point value, position quantity and tick size determine a protective stop distance. If the ATR stop is enabled, the tighter stop is used.

Protection attaches to the entry using a fill-relative stop, and its initial distance stays fixed after partial exits. Smaller remaining quantity consequently has smaller protected monetary exposure. An entry is skipped if even a one-tick cash stop would exceed the selected cap. A close-time emergency exit also checks open P/L against the cap.

A stop is not a guaranteed maximum realized loss: gaps, slippage, commissions, liquidity and execution settings can cause a larger loss. Fees are not included in the protective stop-distance calculation. R remains based on the original ATR distance even if the cash cap tightens the stop.

Hide **Show Maximum Loss Box** to remove the display. Uncheck **Enable Maximum Cash Loss** to remove that protection.

## Alerts and statistics

Create a TradingView strategy alert using **Order fills only**. The default message contains the order message, ticker and actual fill price. Separate entry and exit alert switches control entry fills, partial profits, protective stops and remainder exits. Recreate alerts after changing script inputs.

TradingView counts partial exits as closed trade portions; the table labels this as Closed Portions and Portion Win Rate. These figures are not completed-position win rates.

## Validation status

Source checks confirmed the inherited entry calculations and filters were preserved. Numerical checks covered staged-quantity conservation, target progression, minimum tradable quantities, USD/symbol cash-stop sizing, quantity reductions, long/short symmetry and hard-exit priority. The 1-minute update also checks intrabar event ordering, age in minute bars, long/short symmetry, pre-entry exclusion, completed-candle selection and missing-data handling. TradingView compilation, broker-emulator backtesting and live performance have not been verified here. Set realistic fees and slippage in strategy Properties before evaluating results.
