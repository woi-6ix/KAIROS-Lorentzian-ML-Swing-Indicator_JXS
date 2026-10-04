# This Source Code Form is subject to the Mozilla Public License, v. 2.0.
# See https://mozilla.org/MPL/2.0/
# Kernel regression adapted from jdehorty's KernelFunctions/2.
# DELPHI 3 strategy adaptation: JXS_918.

from AlgorithmImports import *
from collections import deque
from datetime import date, datetime, time, timedelta
import math


class Delphi3QuantConnectBacktest(QCAlgorithm):
    """Copy this entire file into QuantConnect main.py.

    Signals: regular-session SPY 3-minute TradeBars, using close as source.
    Entries: kernel flip + most recent directional Volatility Push within
    10 bars. The window looks backward; it does not delay entries after flips.
    Risk: fixed entry ATR stop and 0.5R target, anchored to actual fill price.
    Fully qualified opposite entries can reverse the position, as in Pine.

    One-year toggle:
      Set ONE_YEAR_BACKTEST below, or add a QuantConnect project parameter
      named one_year_backtest with value true/false (or 1/0).
      ON: END_DATE minus 365 days through END_DATE.
      OFF: FULL_HISTORY_START_DATE through END_DATE.
      Optional project parameters: end_date and full_history_start_date,
      both formatted YYYY-MM-DD. Dates never depend on the machine clock.

    Uses current LEAN native OCO orders, so the stop and target cannot both
    exit the same position. LEAN prioritizes the stop if both are reachable
    in the same minute. Signals use 3-minute bars; exit fills use minute data.
    Data/fill models and whole-share sizing can differ from TradingView.
    """

    # Requested test configuration.
    TICKER = "SPY"
    BAR_MINUTES = 3
    DOLLARS_PER_TRADE = 1000.0  # USD position notional, before transaction fees.
    ONE_YEAR_BACKTEST = True
    FULL_HISTORY_START_DATE = (2024, 1, 1)
    END_DATE = (2026, 10, 2)
    STARTING_CASH = 100000

    SESSION_START = time(9, 30)
    SESSION_END = time(15, 0)
    CLOSE_AT_SESSION_END = True
    ENABLE_LONGS = True
    ENABLE_SHORTS = True
    EXIT_ON_OPPOSITE_KERNEL_FLIP = False

    KERNEL_LOOKBACK = 8
    KERNEL_RELATIVE_WEIGHT = 8.0
    KERNEL_REGRESSION_LEVEL = 25
    USE_KERNEL_SMOOTHING = True
    KERNEL_LAG = 6

    USE_SLOPE_FILTER = False
    SLOPE_LOOKBACK_BARS = 2
    SLOPE_ATR_LENGTH = 14
    MIN_SLOPE_ATR = 0.05

    REQUIRE_VOLATILITY_PUSH = True
    VP_CONFIRMATION_WINDOW = 10
    VP_FAST_ATR_LENGTH = 5
    VP_SLOW_ATR_LENGTH = 20
    VP_MIN_ATR_RATIO = 1.10
    VP_MIN_RANGE_ATR = 1.25
    VP_VOLUME_LENGTH = 20
    VP_MIN_VOLUME_RATIO = 1.50
    VP_MIN_SCORE = 2
    VP_MIN_BODY_ATR = 0.80
    VP_MIN_BODY_RANGE = 0.65
    VP_BULL_CLOSE_LOCATION = 0.70
    VP_BEAR_CLOSE_LOCATION = 0.30

    USE_RISK_MANAGEMENT = True
    RISK_ATR_LENGTH = 14
    STOP_ATR_MULTIPLE = 1.0
    PROFIT_TARGET_R = 0.5

    def initialize(self):
        self.one_year_backtest = self._bool_parameter(
            "one_year_backtest", self.ONE_YEAR_BACKTEST
        )
        self.backtest_end = self._date_parameter("end_date", self.END_DATE)
        self.backtest_start = (
            self.backtest_end - timedelta(days=365)
            if self.one_year_backtest else self._date_parameter(
                "full_history_start_date", self.FULL_HISTORY_START_DATE
            )
        )
        if self.backtest_start > self.backtest_end:
            raise ValueError("Backtest start date must be on/before end_date")
        self.set_start_date(
            self.backtest_start.year, self.backtest_start.month,
            self.backtest_start.day
        )
        self.set_end_date(
            self.backtest_end.year, self.backtest_end.month, self.backtest_end.day
        )
        self.set_cash(self.STARTING_CASH)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.set_brokerage_model(
            BrokerageName.QUANTCONNECT_BROKERAGE, AccountType.MARGIN
        )
        security = self.add_equity(
            self.TICKER, Resolution.MINUTE, extended_market_hours=False,
            data_normalization_mode=DataNormalizationMode.ADJUSTED
        )
        self.symbol = security.symbol
        self.set_benchmark(self.symbol)
        self.tick_size = float(security.symbol_properties.minimum_price_variation)

        # KernelFunctions/2 loops over offsets 0..(1 + startAtBar), inclusive.
        self.kernel_terms = self.KERNEL_REGRESSION_LEVEL + 2
        self.closes = deque(maxlen=self.kernel_terms)
        self.volumes = deque(maxlen=self.VP_VOLUME_LENGTH)
        self.kernel_history = deque(maxlen=self.SLOPE_LOOKBACK_BARS + 1)
        rq_h = float(self.KERNEL_LOOKBACK)
        rq_r = float(self.KERNEL_RELATIVE_WEIGHT)
        gaussian_h = float(max(1, self.KERNEL_LOOKBACK - self.KERNEL_LAG))
        self.rq_weights = [
            (1.0 + i * i / (2.0 * rq_h * rq_h * rq_r)) ** (-rq_r)
            for i in range(self.kernel_terms)
        ]
        self.gaussian_weights = [
            math.exp(-i * i / (2.0 * gaussian_h * gaussian_h))
            for i in range(self.kernel_terms)
        ]
        lengths = {
            self.VP_FAST_ATR_LENGTH, self.VP_SLOW_ATR_LENGTH,
            self.RISK_ATR_LENGTH, self.SLOPE_ATR_LENGTH
        }
        self.atr_state = {
            length: {"value": None, "seed": []} for length in lengths
        }
        self.prev_close = None
        self.prev_kernel_bullish = None
        self.prev_kernel_bearish = None
        self.prev_yhat1 = None
        self.bar_index = -1
        self.last_bull_push_bar = None
        self.last_bear_push_bar = None
        self.risk_tickets = []
        self.stop_price = None
        self.target_price = None

        # Initialize state before registering/warming the consolidator.
        self.consolidator = self.consolidate(
            self.symbol, timedelta(minutes=self.BAR_MINUTES), self.on_signal_bar
        )
        self.set_warm_up(timedelta(days=10))
        self.debug(
            f"DELPHI 3 | {self.TICKER} {self.BAR_MINUTES}m | "
            f"{self.backtest_start} to {self.backtest_end} | "
            f"one_year_backtest={self.one_year_backtest} | "
            f"${self.DOLLARS_PER_TRADE:.0f} position | "
            f"target={self.PROFIT_TARGET_R}R"
        )

    def _bool_parameter(self, name, default):
        value = self.get_parameter(name)
        if value is None or not str(value).strip():
            return default
        value = str(value).strip().lower()
        if value in ("true", "1", "yes", "on"):
            return True
        if value in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"{name} must be true/false or 1/0")

    def _date_parameter(self, name, default):
        value = self.get_parameter(name)
        if value is None or not str(value).strip():
            return date(*default)
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()

    def _update_atr(self, length, true_range):
        # Pine ta.atr = Wilder RMA, seeded by a length-bar SMA of true range.
        state = self.atr_state[length]
        if state["value"] is None:
            state["seed"].append(true_range)
            if len(state["seed"]) == length:
                state["value"] = sum(state["seed"]) / length
                state["seed"].clear()
        else:
            state["value"] = (
                state["value"] * (length - 1) + true_range
            ) / length
        return state["value"]

    def _kernel(self, weights):
        if len(self.closes) < self.kernel_terms:
            return None
        return sum(
            price * weight for price, weight in zip(reversed(self.closes), weights)
        ) / sum(weights)

    def _volatility_push(self, o, h, low, c, volume, fast_atr, slow_atr):
        if (fast_atr is None or slow_atr is None or slow_atr <= 0
                or len(self.volumes) < self.VP_VOLUME_LENGTH):
            return False, False
        candle_range = max(h - low, self.tick_size)
        body = abs(c - o)
        close_location = (c - low) / candle_range
        average_volume = sum(self.volumes) / self.VP_VOLUME_LENGTH
        volume_ratio = volume / average_volume if average_volume > 0 else 0.0
        score = (
            int(fast_atr / slow_atr >= self.VP_MIN_ATR_RATIO)
            + int(candle_range / slow_atr >= self.VP_MIN_RANGE_ATR)
            + int(volume_ratio >= self.VP_MIN_VOLUME_RATIO)
        )
        qualified = (
            score >= self.VP_MIN_SCORE
            and body / slow_atr >= self.VP_MIN_BODY_ATR
            and body / candle_range >= self.VP_MIN_BODY_RANGE
        )
        return (
            qualified and c > o and close_location >= self.VP_BULL_CLOSE_LOCATION,
            qualified and c < o and close_location <= self.VP_BEAR_CLOSE_LOCATION
        )

    def _push_confirmations(self):
        bull_age = (
            self.bar_index - self.last_bull_push_bar
            if self.last_bull_push_bar is not None else 100000
        )
        bear_age = (
            self.bar_index - self.last_bear_push_bar
            if self.last_bear_push_bar is not None else 100000
        )
        return (
            not self.REQUIRE_VOLATILITY_PUSH or (
                bull_age <= self.VP_CONFIRMATION_WINDOW and bull_age < bear_age
            ),
            not self.REQUIRE_VOLATILITY_PUSH or (
                bear_age <= self.VP_CONFIRMATION_WINDOW and bear_age < bull_age
            )
        )

    def on_signal_bar(self, bar: TradeBar):
        self.bar_index += 1
        o, h, low, c, volume = map(
            float, (bar.open, bar.high, bar.low, bar.close, bar.volume)
        )
        true_range = h - low if self.prev_close is None else max(
            h - low, abs(h - self.prev_close), abs(low - self.prev_close)
        )
        self.prev_close = c
        for length in self.atr_state:
            self._update_atr(length, true_range)
        fast_atr = self.atr_state[self.VP_FAST_ATR_LENGTH]["value"]
        slow_atr = self.atr_state[self.VP_SLOW_ATR_LENGTH]["value"]
        risk_atr = self.atr_state[self.RISK_ATR_LENGTH]["value"]
        self.closes.append(c)
        self.volumes.append(volume)
        bull_push, bear_push = self._volatility_push(
            o, h, low, c, volume, fast_atr, slow_atr
        )
        if bull_push:
            self.last_bull_push_bar = self.bar_index
        if bear_push:
            self.last_bear_push_bar = self.bar_index

        rq = self._kernel(self.rq_weights)
        gaussian = self._kernel(self.gaussian_weights)
        if rq is None or gaussian is None or risk_atr is None:
            return
        self.kernel_history.append(rq)
        if self.USE_KERNEL_SMOOTHING:
            bullish, bearish = gaussian >= rq, gaussian <= rq
        else:
            bullish = self.prev_yhat1 is not None and rq > self.prev_yhat1
            bearish = self.prev_yhat1 is not None and rq < self.prev_yhat1
        bullish_flip = (
            self.bar_index > 2 and bullish and self.prev_kernel_bullish is False
        )
        bearish_flip = (
            self.bar_index > 2 and bearish and self.prev_kernel_bearish is False
        )
        self.prev_kernel_bullish = bullish
        self.prev_kernel_bearish = bearish
        self.prev_yhat1 = rq
        # Warmup updates indicator state but must never submit orders.
        if self.is_warming_up:
            return

        # SPY data and the algorithm both use New York time, including DST.
        # Match Pine's time_close by using the consolidated bar's end_time.
        bar_time = bar.end_time.time()
        if self.CLOSE_AT_SESSION_END and bar_time >= self.SESSION_END:
            self._close_position("DELPHI 3 SESSION CUTOFF")
            return
        in_session = self.SESSION_START <= bar_time < self.SESSION_END
        bull_confirmed, bear_confirmed = self._push_confirmations()
        long_slope_pass = short_slope_pass = True
        if self.USE_SLOPE_FILTER:
            slope_atr = self.atr_state[self.SLOPE_ATR_LENGTH]["value"]
            ready = (
                len(self.kernel_history) > self.SLOPE_LOOKBACK_BARS
                and slope_atr is not None and slope_atr > 0
            )
            slope = (
                (rq - self.kernel_history[0]) / slope_atr if ready else None
            )
            long_slope_pass = ready and slope >= self.MIN_SLOPE_ATR
            short_slope_pass = ready and slope <= -self.MIN_SLOPE_ATR
        long_signal = (
            self.ENABLE_LONGS and in_session and bullish_flip
            and bull_confirmed and long_slope_pass
        )
        short_signal = (
            self.ENABLE_SHORTS and in_session and bearish_flip
            and bear_confirmed and short_slope_pass
        )
        quantity = int(self.portfolio[self.symbol].quantity)
        if long_signal and quantity <= 0:
            self._enter_position(1, c, risk_atr)
        elif short_signal and quantity >= 0:
            self._enter_position(-1, c, risk_atr)
        elif self.EXIT_ON_OPPOSITE_KERNEL_FLIP and (
            (quantity > 0 and bearish_flip) or (quantity < 0 and bullish_flip)
        ):
            self._close_position("DELPHI 3 OPPOSITE KERNEL EXIT")

        self.plot("DELPHI 3", "RQ Kernel", rq)
        self.plot("DELPHI 3", "Gaussian", gaussian)

    def _enter_position(self, direction, reference_price, risk_atr):
        if self.is_warming_up or reference_price <= 0:
            return
        risk_distance = float(risk_atr) * self.STOP_ATR_MULTIPLE
        if self.USE_RISK_MANAGEMENT and risk_distance <= 0:
            return
        # Largest whole-share position at/below $1,000 at the signal price.
        # Example: SPY at $600 -> 1 share ($600), with $400 unused.
        shares = math.floor(self.DOLLARS_PER_TRADE / reference_price)
        if shares < 1:
            return
        current_qty = int(self.portfolio[self.symbol].quantity)
        order_qty = direction * shares - current_qty
        if order_qty == 0:
            return
        old_stop, old_target = self.stop_price, self.target_price
        self._cancel_risk_orders()
        ticket = self.market_order(
            self.symbol, order_qty,
            tag="DELPHI 3 LONG" if direction > 0 else "DELPHI 3 SHORT"
        )
        # Market orders are synchronous in LEAN backtests. Check for rejection
        # before attaching an exit sized to the resulting holdings.
        if ticket.status != OrderStatus.FILLED:
            self.error("DELPHI 3 market entry did not fill synchronously")
            remaining = int(self.portfolio[self.symbol].quantity)
            if remaining and old_stop is not None and old_target is not None:
                self._place_risk_orders(remaining, old_stop, old_target)
            return
        filled_qty = int(self.portfolio[self.symbol].quantity)
        if filled_qty == 0 or not self.USE_RISK_MANAGEMENT:
            return
        fill_price = float(ticket.average_fill_price)
        stop = fill_price - direction * risk_distance
        target = fill_price + direction * risk_distance * self.PROFIT_TARGET_R
        # Exchange tick rounding can make realized R differ slightly from 0.5.
        stop = round(round(stop / self.tick_size) * self.tick_size, 8)
        target = round(round(target / self.tick_size) * self.tick_size, 8)
        self._place_risk_orders(filled_qty, stop, target)

    def _place_risk_orders(self, quantity, stop, target):
        self.stop_price, self.target_price = stop, target
        self.risk_tickets = list(self.one_cancels_other_order([
            self.order_factory.stop_market_order(
                self.symbol, -quantity, stop, tag="DELPHI 3 STOP"
            ),
            self.order_factory.limit_order(
                self.symbol, -quantity, target,
                tag=f"DELPHI 3 {self.PROFIT_TARGET_R:.2f}R TARGET"
            )
        ]))
        if any(t.status == OrderStatus.INVALID for t in self.risk_tickets):
            self.error("DELPHI 3 exit bracket rejected; closing position")
            self._close_position("DELPHI 3 BRACKET REJECTED")

    def _cancel_risk_orders(self):
        tickets = self.risk_tickets
        self.risk_tickets = []
        self.stop_price = self.target_price = None
        for ticket in tickets:
            if ticket.status not in (
                OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.INVALID
            ):
                # Native OCO cancellation also cancels the sibling order.
                ticket.cancel("Cancel DELPHI 3 bracket before reversal/cutoff")

    def _close_position(self, tag):
        self._cancel_risk_orders()
        if self.portfolio[self.symbol].invested:
            self.liquidate(self.symbol, tag=tag)

    def on_order_event(self, order_event: OrderEvent):
        if order_event.status == OrderStatus.INVALID:
            self.error(f"DELPHI 3 rejected order: {order_event}")
        # Native OCO manages sibling cancellation inside LEAN, including
        # partial fills. Retain tickets until flat so cutoff can cancel them.
        if (order_event.status == OrderStatus.FILLED
                and any(t.order_id == order_event.order_id for t in self.risk_tickets)
                and not self.portfolio[self.symbol].invested):
            self.risk_tickets = []
            self.stop_price = self.target_price = None
