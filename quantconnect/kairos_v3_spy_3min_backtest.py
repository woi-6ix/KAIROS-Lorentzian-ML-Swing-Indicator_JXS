# This Source Code Form is subject to the Mozilla Public License, v. 2.0.
# See https://mozilla.org/MPL/2.0/
# Kernel regression adapted from jdehorty's KernelFunctions/2.
# KAIROS V3 strategy adaptation: JXS_918.

from AlgorithmImports import *
from collections import deque
from datetime import date, datetime, time, timedelta
import math


class KairosV3QuantConnectBacktest(QCAlgorithm):
    """Copy this entire file into QuantConnect main.py (under 32,000 chars).

    Port of KAIROS_LC_Swing_Engine_V3_JXS_918.pine. Kernel, VP and ATR use
    completed regular-session SPY 3-minute bars. No Lorentzian classifier is
    used by the v3 Pine entry logic. Minute data models stop/target execution.
    VP looks BACK 10 bars; it does not wait 10 bars after the kernel flip.

    Optional execution_mode=shares: floor(2500 / signal close) SPY shares.
    This is a USD allocation, NOT Pine's literal qty=2500 (2500 shares).
    Entry slippage/fees may make actual cost differ from signal notional.
    stop = entry ATR(14) * 1.5; 1R = that distance; target = 0.45R.
    Opposite flip exits OFF still permits fully confirmed opposite reversals.

    Default execution_mode=options: buy ATM calls for long signals and ATM
    puts for short signals, SAME-DAY expiration only (0DTE). Here $2500
    is the premium budget, rounded down to whole contracts using fresh ask
    quotes and the actual multiplier. No short options and no stock entries.
    Exit triggers remain SPY-price ATR levels, checked on minute SPY closes;
    realized P&L comes from option fills. 0.45R is NOT option-premium return.
    Intraminute SPY touches are not used to infer option fills; exits use
    observable minute closing values and contemporaneous option quotes;
    no synthetic intraminute option fills or guaranteed stop prices.

    Optional QC project parameters (defaults are the constants below):
      execution_mode: shares/options
      one_year_backtest: true/false
      dollars_per_trade: 2500
      exit_on_opposite_kernel_flip: false
      use_kernel_smoothing: true; kernel_lag: 6
      use_slope_filter: false; vp_confirmation_window: 10
      stop_atr_multiple: 1.5; profit_target_r: 0.45
      enable_cash_loss_cap: false; maximum_cash_loss: 500
      end_date: 2026-10-06; full_history_start_date: 2024-01-01
    One-year ON uses 365 calendar dates ending on end_date (inclusive).
    Warmup precedes the test window and cannot trade. Dates are reproducible.
    Fees use LEAN's brokerage defaults; stock slippage defaults to zero.
    Option market fills include bid/ask spread when quote data is available.
    Requires a current cloud LEAN engine with native OCO for shares mode.
    Options mode has been locally tested, not run on a QC cloud account.
    """

    # Requested test configuration.
    EXECUTION_MODE = "options"
    ENABLE_CASH_LOSS_CAP = False
    MAXIMUM_CASH_LOSS = 500.0
    OPTION_MIN_DTE = 0
    OPTION_MAX_DTE = 0
    OPTION_STRIKES_EITHER_SIDE = 5
    TICKER = "SPY"
    BAR_MINUTES = 3
    DOLLARS_PER_TRADE = 2500.0  # USD option premium budget, before transaction fees.
    ONE_YEAR_BACKTEST = True
    FULL_HISTORY_START_DATE = (2024, 1, 1)
    END_DATE = (2026, 10, 6)
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
    STOP_ATR_MULTIPLE = 1.5
    PROFIT_TARGET_R = 0.45

    def initialize(self):
        self.execution_mode = (self.get_parameter("execution_mode") or
                               self.EXECUTION_MODE).strip().lower()
        if self.execution_mode not in ("shares", "options"):
            raise ValueError("execution_mode must be shares or options")
        for name, field in (
            ("exit_on_opposite_kernel_flip", "EXIT_ON_OPPOSITE_KERNEL_FLIP"),
            ("use_kernel_smoothing", "USE_KERNEL_SMOOTHING"),
            ("use_slope_filter", "USE_SLOPE_FILTER"),
            ("enable_cash_loss_cap", "ENABLE_CASH_LOSS_CAP"),
        ):
            setattr(self, field, self._bool_parameter(name, getattr(self, field)))
        for name, field, cast in (
            ("dollars_per_trade", "DOLLARS_PER_TRADE", float),
            ("kernel_lag", "KERNEL_LAG", int),
            ("vp_confirmation_window", "VP_CONFIRMATION_WINDOW", int),
            ("stop_atr_multiple", "STOP_ATR_MULTIPLE", float),
            ("profit_target_r", "PROFIT_TARGET_R", float),
            ("maximum_cash_loss", "MAXIMUM_CASH_LOSS", float),
        ):
            value = self.get_parameter(name)
            if value is not None and str(value).strip():
                setattr(self, field, cast(value))
        if any(not math.isfinite(x) or x <= 0 for x in (
                self.DOLLARS_PER_TRADE, self.STOP_ATR_MULTIPLE,
                self.PROFIT_TARGET_R, self.MAXIMUM_CASH_LOSS)):
            raise ValueError("Allocation, stop, target and cash cap must be positive")
        if not 1 <= self.KERNEL_LAG <= 20 or not 0 <= self.VP_CONFIRMATION_WINDOW <= 10:
            raise ValueError("kernel_lag must be 1-20; VP window must be 0-10")
        self.one_year_backtest = self._bool_parameter(
            "one_year_backtest", self.ONE_YEAR_BACKTEST
        )
        self.backtest_end = self._date_parameter("end_date", self.END_DATE)
        self.backtest_start = (
            self.backtest_end - timedelta(days=364)
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
            data_normalization_mode=DataNormalizationMode.RAW
        )
        self.symbol = security.symbol
        self.set_benchmark(self.symbol)
        self.option_symbol = None
        if self.execution_mode == "options":
            option = self.add_option(self.symbol, Resolution.MINUTE)
            option.set_filter(lambda u: u.include_weeklys().strikes(
                -self.OPTION_STRIKES_EITHER_SIDE, self.OPTION_STRIKES_EITHER_SIDE
            ).expiration(0, 0))
            self.option_symbol = option.symbol
        self.active_option = None
        self.option_direction = 0
        self.pending_signal = None
        self.option_cash_exit_pending = False
        self.partial_exit_pending = False
        self.blocked_date = None
        self.skipped_option_signals = 0
        self.rejected_orders = 0
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
        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.at(self.SESSION_END.hour, self.SESSION_END.minute),
            self._session_cutoff
        )
        # On half-days, close one minute before the exchange closes.
        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.before_market_close(self.symbol, 1),
            self._session_cutoff
        )
        self.debug(
            f"KAIROS V3 | {self.TICKER} {self.BAR_MINUTES}m | "
            f"{self.backtest_start} to {self.backtest_end} | "
            f"one_year_backtest={self.one_year_backtest} | "
            f"mode={self.execution_mode} | ${self.DOLLARS_PER_TRADE:.0f} budget | "
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

        if self.partial_exit_pending:
            return

        # SPY data and the algorithm both use New York time, including DST.
        # Match Pine's time_close by using the consolidated bar's end_time.
        bar_time = bar.end_time.time()
        if self.CLOSE_AT_SESSION_END and bar_time >= self.SESSION_END:
            self._session_cutoff()
            return
        in_session = (
            self.SESSION_START <= bar_time < self.SESSION_END
            and self.blocked_date != bar.end_time.date()
        )
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
        if self.execution_mode == "options":
            direction = 1 if long_signal else -1 if short_signal else 0
            if direction and direction != self.option_direction:
                # on_data executes using the SAME timestamp's fresh option chain,
                # not a cached previous-minute chain. Never retry this signal later.
                self.pending_signal = (bar.end_time, direction, c, risk_atr)
            elif self.EXIT_ON_OPPOSITE_KERNEL_FLIP and (
                (self.option_direction > 0 and bearish_flip)
                or (self.option_direction < 0 and bullish_flip)
            ):
                self.option_cash_exit_pending = True
            return
        quantity = int(self.portfolio[self.symbol].quantity)
        if long_signal and quantity <= 0:
            self._enter_position(1, c, risk_atr)
        elif short_signal and quantity >= 0:
            self._enter_position(-1, c, risk_atr)
        elif self.EXIT_ON_OPPOSITE_KERNEL_FLIP and (
            (quantity > 0 and bearish_flip) or (quantity < 0 and bullish_flip)
        ):
            self._close_position("KAIROS V3 OPPOSITE KERNEL EXIT")

        self.plot("KAIROS V3", "RQ Kernel", rq)
        self.plot("KAIROS V3", "Gaussian", gaussian)

    def _enter_position(self, direction, reference_price, risk_atr):
        if self.is_warming_up or reference_price <= 0:
            return
        risk_distance = max(self.tick_size, float(risk_atr) * self.STOP_ATR_MULTIPLE)
        if self.USE_RISK_MANAGEMENT and risk_distance <= 0:
            return
        # Largest whole-share position at/below $2,500 at the signal price.
        # Example: SPY at $600 -> 4 shares ($2,400), with $100 unused.
        shares = math.floor(self.DOLLARS_PER_TRADE / reference_price)
        if shares < 1:
            return
        effective_distance = risk_distance if self.USE_RISK_MANAGEMENT else None
        if self.ENABLE_CASH_LOSS_CAP:
            cash_distance = math.floor(
                self.MAXIMUM_CASH_LOSS / (shares * self.tick_size)
            ) * self.tick_size
            if cash_distance < self.tick_size:
                return
            effective_distance = (cash_distance if effective_distance is None
                                  else min(effective_distance, cash_distance))
        current_qty = int(self.portfolio[self.symbol].quantity)
        order_qty = direction * shares - current_qty
        if order_qty == 0:
            return
        old_stop, old_target = self.stop_price, self.target_price
        self._cancel_risk_orders()
        ticket = self.market_order(
            self.symbol, order_qty,
            tag="KAIROS V3 LONG" if direction > 0 else "KAIROS V3 SHORT"
        )
        # Market orders are synchronous in LEAN backtests. Check for rejection
        # before attaching an exit sized to the resulting holdings.
        if ticket.status != OrderStatus.FILLED:
            self.error("KAIROS V3 market entry did not fill synchronously")
            remaining = int(self.portfolio[self.symbol].quantity)
            if remaining == current_qty and remaining and old_stop is not None:
                self._place_risk_orders(remaining, old_stop, old_target)
            elif remaining:
                self._close_position("KAIROS V3 INCOMPLETE ENTRY")
            return
        filled_qty = int(self.portfolio[self.symbol].quantity)
        if filled_qty == 0 or effective_distance is None:
            return
        fill_price = float(ticket.average_fill_price)
        stop = fill_price - direction * effective_distance
        target = (fill_price + direction * max(
            self.tick_size, risk_distance * self.PROFIT_TARGET_R
        ) if self.USE_RISK_MANAGEMENT else None)
        # Exchange tick rounding can make realized R differ slightly from 0.45.
        stop = round(round(stop / self.tick_size) * self.tick_size, 8)
        if target is not None:
            target = round(round(target / self.tick_size) * self.tick_size, 8)
        self._place_risk_orders(filled_qty, stop, target)

    def _place_risk_orders(self, quantity, stop, target):
        self.stop_price, self.target_price = stop, target
        requests = [self.order_factory.stop_market_order(
            self.symbol, -quantity, stop, tag="KAIROS V3 STOP"
        )]
        if target is not None:
            requests.append(self.order_factory.limit_order(
                self.symbol, -quantity, target,
                tag=f"KAIROS V3 {self.PROFIT_TARGET_R:.2f}R TARGET"
            ))
        self.risk_tickets = (list(self.one_cancels_other_order(requests))
                             if target is not None else [self.stop_market_order(
                                 self.symbol, -quantity, stop, tag="KAIROS V3 CASH STOP"
                             )])
        if any(t.status == OrderStatus.INVALID for t in self.risk_tickets):
            self.error("KAIROS V3 exit bracket rejected; closing position")
            self._close_position("KAIROS V3 BRACKET REJECTED")

    def _cancel_risk_orders(self):
        tickets = self.risk_tickets
        self.risk_tickets = []
        self.stop_price = self.target_price = None
        for ticket in tickets:
            if ticket.status not in (
                OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.INVALID
            ):
                # Native OCO cancellation also cancels the sibling order.
                ticket.cancel("Cancel KAIROS V3 bracket before reversal/cutoff")

    def _close_position(self, tag):
        if self.execution_mode == "options":
            self._close_option(tag)
            return
        self._cancel_risk_orders()
        if self.portfolio[self.symbol].invested:
            self.liquidate(self.symbol, tag=tag)

    def on_order_event(self, order_event: OrderEvent):
        if order_event.status == OrderStatus.INVALID:
            self.rejected_orders += 1
            self.error(f"KAIROS V3 rejected order: {order_event}")
        if (order_event.status == OrderStatus.PARTIALLY_FILLED
                and any(t.order_id == order_event.order_id for t in self.risk_tickets)):
            # OCO cancels the other exit even on partial fill. Flatten the
            # residual on the next data callback; never leave it unprotected.
            self.partial_exit_pending = True
        # Native OCO manages sibling cancellation inside LEAN, including
        # partial fills. Retain tickets until flat so cutoff can cancel them.
        if (order_event.status == OrderStatus.FILLED
                and any(t.order_id == order_event.order_id for t in self.risk_tickets)
                and not self.portfolio[self.symbol].invested):
            self.risk_tickets = []
            self.stop_price = self.target_price = None


    def _session_cutoff(self):
        if self.is_warming_up or not self.CLOSE_AT_SESSION_END:
            return
        self.blocked_date = self.time.date()
        self.pending_signal = None
        self._close_position("KAIROS V3 SESSION CUTOFF")

    def on_data(self, data: Slice):
        if self.is_warming_up:
            return
        if self.partial_exit_pending:
            self.partial_exit_pending = False
            self._close_position("KAIROS V3 PARTIAL EXIT RESIDUAL")
        if self.execution_mode != "options":
            return
        underlying = data.bars.get(self.symbol)
        if (self.CLOSE_AT_SESSION_END
                and self.time.time() >= self.SESSION_END):
            self._session_cutoff()
            return
        if self.active_option is not None and not self.portfolio[self.active_option].invested:
            self.active_option = None
            self.option_direction = 0
            self.stop_price = self.target_price = None
        if self.active_option is not None:
            hit = False
            if underlying is not None and not underlying.is_fill_forward:
                price = float(underlying.close)
                # Closing values are observed, unlike the unknown ordering of
                # intraminute extrema. Exit fills are at current option quotes.
                hit = ((self.stop_price is not None and
                        self.option_direction * (price - self.stop_price) <= 0)
                       or (self.target_price is not None and
                           self.option_direction * (price - self.target_price) >= 0))
            if self.ENABLE_CASH_LOSS_CAP:
                quote = data.quote_bars.get(self.active_option)
                if quote is not None and not quote.is_fill_forward and quote.bid is not None:
                    holding = self.portfolio[self.active_option]
                    multiplier = float(self.securities[self.active_option].symbol_properties.contract_multiplier)
                    mark_pnl = (float(quote.bid.close) - float(holding.average_price)) * float(holding.quantity) * multiplier
                    hit = hit or mark_pnl <= -self.MAXIMUM_CASH_LOSS
            if hit or self.option_cash_exit_pending:
                self.option_cash_exit_pending = False
                self._close_option("KAIROS V3 SPY RISK/KERNEL/CASH EXIT")
        pending = self.pending_signal
        self.pending_signal = None
        if pending is None:
            return
        stamp, direction, price, atr = pending
        if (stamp != self.time or self.blocked_date == self.time.date()
                or not self.SESSION_START <= self.time.time() < self.SESSION_END):
            self.skipped_option_signals += 1
            return
        self._enter_option(data, direction, price, atr)

    def _select_option(self, data, direction, reference_price):
        chain = data.option_chains.get(self.option_symbol)
        if chain is None:
            return None
        right = OptionRight.CALL if direction > 0 else OptionRight.PUT
        candidates = []
        for contract in chain:
            # Enforce 0DTE again at entry; never substitute a later expiry
            # when today's contracts are unavailable or unquoted.
            if (contract.right != right
                    or contract.expiry.date() != self.time.date()):
                continue
            quote = data.quote_bars.get(contract.symbol)
            if (quote is None or quote.is_fill_forward or quote.end_time != self.time
                    or quote.bid is None or quote.ask is None):
                continue
            bid, ask = float(quote.bid.close), float(quote.ask.close)
            if bid <= 0 or ask < bid or not math.isfinite(ask):
                continue
            candidates.append((contract, bid, ask))
        # Same-day expiry only, then nearest strike; liquidity tie-break.
        return min(candidates, key=lambda x: (
            x[0].expiry, abs(float(x[0].strike) - reference_price),
            x[2] - x[1], -float(x[0].volume), str(x[0].symbol)
        )) if candidates else None

    def _enter_option(self, data, direction, reference_price, risk_atr):
        selected = self._select_option(data, direction, reference_price)
        if selected is None:
            self.skipped_option_signals += 1
            return
        contract, bid, ask = selected
        symbol = contract.symbol
        multiplier = float(self.securities[symbol].symbol_properties.contract_multiplier)
        if multiplier <= 0:
            self.skipped_option_signals += 1
            return
        quantity = math.floor(self.DOLLARS_PER_TRADE / (ask * multiplier))
        if quantity < 1:
            self.skipped_option_signals += 1
            return
        # Do not liquidate a valid old position for an unaffordable/missing contract.
        if self.active_option is not None:
            if not self._close_option("KAIROS V3 CONFIRMED REVERSAL"):
                return
        ticket = self.market_order(symbol, quantity, tag=(
            "KAIROS V3 LONG CALL" if direction > 0 else "KAIROS V3 LONG PUT"
        ))
        if ticket.status != OrderStatus.FILLED:
            self.error("KAIROS V3 option entry did not fill synchronously")
            if self.portfolio[symbol].invested:
                self.liquidate(symbol, tag="KAIROS V3 INCOMPLETE OPTION ENTRY")
            return
        self.active_option = symbol
        self.option_direction = direction
        distance = float(risk_atr) * self.STOP_ATR_MULTIPLE
        self.stop_price = (reference_price - direction * distance
                           if self.USE_RISK_MANAGEMENT else None)
        self.target_price = (reference_price + direction * distance * self.PROFIT_TARGET_R
                             if self.USE_RISK_MANAGEMENT else None)

    def _close_option(self, tag):
        symbol = self.active_option
        if symbol is None:
            self.option_direction = 0
            return True
        # On failed liquidation, retain state and retry on later data callbacks.
        self.liquidate(symbol, tag=tag)
        if self.portfolio[symbol].invested:
            self.option_cash_exit_pending = True
            return False
        self.active_option = None
        self.option_direction = 0
        self.stop_price = self.target_price = None
        return True

    def on_end_of_algorithm(self):
        self.set_runtime_statistic("Execution mode", self.execution_mode)
        self.set_runtime_statistic("Allocation USD", str(self.DOLLARS_PER_TRADE))
        self.set_runtime_statistic("Skipped option signals", str(self.skipped_option_signals))
        self.set_runtime_statistic("Rejected orders", str(self.rejected_orders))
