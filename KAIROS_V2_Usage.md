# KAIROS LC Swing Engine V2

V2 keeps the original kernel flip, trading-session, entry slope and directional Volatility Push filters. It adds staged exits while retaining the navy/gold theme, naming explanation, statistics, watermark controls and native order-fill alerts. V1 remains a separate file.

## Default behavior

| Control | Default |
| --- | --- |
| Chart | 1 minute; other chart intervals blocked unless the requirement is disabled |
| Trading hours | 09:30 to before 15:00 America/New_York; editable |
| Position quantity | 100 underlying shares/contracts; editable and rounded to the symbol minimum |
| Initial capital / account currency | 100,000 USD / USD; adjustable in strategy Properties |
| Definition of 1R | ATR(14) times 1.0, frozen at the entry signal and rounded to ticks |
| First partial | 25% of original quantity at a close of at least 0.4R |
| Second partial | 25% of original quantity at a close of at least 0.7R |
| Later partials | 10% of original quantity at 0.8R, 0.9R, 1.0R, etc. |
| Continuation | Latest directional VP within 2 bars, no newer opposing VP, correct kernel color; optional slope check enabled |
| Adverse-candle exit | One opposite-color candle closes the remainder; count and switch editable |
| Maximum cash loss | Enabled, 500 USD; amount editable |
| Cash loss display | Enabled, bottom left; separate visibility and protection switches |

A long's adverse candle has close below open; a short's has close above open. Dojis reset the consecutive-adverse count. If an opposite entry qualifies on that same candle, a reversal can close the old remainder and open the new direction. Session and cash-loss exits take priority over reversals.

## Profit-taking semantics

These are close-confirmed market exits, not resting limit orders at the target prices. A wick alone reaching a target does not trigger profit-taking. A qualifying close triggers at most one stage per bar. Execution is simulated on that closing tick, subject to TradingView's configured execution/slippage behavior.

At a reached target, directional VP, kernel color and the optional continuation slope must pass to take a partial and advance to the next target. Otherwise the entire remaining position closes. If price has not reached the next target, the position continues subject to stops, adverse candles, kernel exits and session cutoff.

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

Source checks confirmed the inherited entry calculations and filters were preserved. Numerical checks covered staged-quantity conservation, target progression, minimum tradable quantities, USD/symbol cash-stop sizing, quantity reductions, long/short symmetry and hard-exit priority. TradingView compilation, broker-emulator backtesting and live performance have not been verified here. Set realistic fees and slippage in strategy Properties before evaluating results.
