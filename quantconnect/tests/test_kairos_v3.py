"""Local logic tests with a small LEAN API double; no historical data claims."""
import importlib.util
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from datetime import datetime, timedelta, date

api = ModuleType('AlgorithmImports')
api.QCAlgorithm = object
api.TradeBar = api.OrderEvent = api.Slice = object
for name, values in {
    'OrderStatus': ['FILLED','CANCELED','INVALID','SUBMITTED','PARTIALLY_FILLED'],
    'TimeZones': ['NEW_YORK'], 'BrokerageName': ['QUANTCONNECT_BROKERAGE'],
    'AccountType': ['MARGIN'], 'Resolution': ['MINUTE'],
    'DataNormalizationMode': ['RAW'], 'OptionRight': ['CALL','PUT']
}.items():
    setattr(api, name, NS(**{value:value for value in values}))
sys.modules['AlgorithmImports'] = api
path = Path(__file__).parents[1] / 'kairos_v3_spy_3min_backtest.py'
spec = importlib.util.spec_from_file_location('kairos', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Holding:
    quantity = 0
    average_price = 0
    @property
    def invested(self): return self.quantity != 0

class Filter:
    def include_weeklys(self): return self
    def strikes(self, low, high): return self
    def expiration(self, low, high): return self

class Ticket:
    def __init__(self, bot, status='SUBMITTED', price=0):
        self.bot, self.status, self.average_fill_price = bot, status, price
        self.order_id = len(bot.calls)
    def cancel(self, tag):
        self.status = 'CANCELED'
        self.bot.calls.append(('cancel', tag))
        return NS(is_success=True)

class Bot(module.KairosV3QuantConnectBacktest):
    def __init__(self, params=None):
        self.params = params or {}
        self.calls = []
        self.is_warming_up = False
        self.time = datetime(2026,10,6,10)
        self.portfolio = {'SPY':Holding()}
        self.securities = {'SPY': NS(symbol='SPY', symbol_properties=NS(
            minimum_price_variation=.01, contract_multiplier=1))}
        self.schedule = NS(on=lambda *args: self.calls.append(('schedule',args)))
        self.date_rules = NS(every_day=lambda *args: args)
        self.time_rules = NS(at=lambda *args: args, before_market_close=lambda *args:args)
        self.order_factory = NS(stop_market_order=lambda *args,**kw:('stop',args,kw),
                                limit_order=lambda *args,**kw:('target',args,kw))
        self.market_price = 600.0
        self.reject_entry = False
        self.fail_liquidation = False
        self.initialize()
    def get_parameter(self, name): return self.params.get(name)
    def set_start_date(self,*args): self.start=args
    def set_end_date(self,*args): self.end=args
    def set_cash(self,amount): self.cash=amount
    def set_time_zone(self,*args): pass
    def set_brokerage_model(self,*args): pass
    def set_benchmark(self,*args): pass
    def set_warm_up(self,*args): pass
    def debug(self,*args): pass
    def error(self,*args): self.calls.append(('error',args))
    def plot(self,*args): pass
    def add_equity(self,*args,**kw): return self.securities['SPY']
    def add_option(self,*args):
        return NS(symbol='CHAIN',set_filter=lambda f:f(Filter()))
    def consolidate(self,symbol,period,callback): self.period=period; return NS()
    def market_order(self,symbol,quantity,**kw):
        # Existing stock exit tickets must be canceled before entry/reversal.
        if symbol == 'SPY':
            assert not any(t.status == 'SUBMITTED' for t in self.risk_tickets)
        self.calls.append(('market',symbol,quantity))
        if self.reject_entry:
            return Ticket(self,'INVALID')
        self.portfolio[symbol].quantity += quantity
        self.portfolio[symbol].average_price = self.market_price
        return Ticket(self,'FILLED',self.market_price)
    def one_cancels_other_order(self, requests):
        self.bracket_requests = requests
        self.calls.append(('bracket',requests))
        return [Ticket(self) for _ in requests]
    def liquidate(self,symbol,**kw):
        self.calls.append(('liquidate',symbol))
        if not self.fail_liquidation:
            self.portfolio[symbol].quantity=0
    def set_runtime_statistic(self,*args): pass


def bar(stamp, o, h, low, c, volume=1000):
    return NS(open=o,high=h,low=low,close=c,volume=volume,end_time=stamp,is_fill_forward=False)

def option_data(bot, records, price=600):
    contracts=[]; quotes={}
    for symbol,right,strike,dte,bid,ask,fresh in records:
        contracts.append(NS(symbol=symbol,right=right,strike=strike,
                            expiry=bot.time+timedelta(days=dte),volume=100))
        quotes[symbol]=NS(bid=NS(close=bid),ask=NS(close=ask),
                          end_time=bot.time,is_fill_forward=not fresh)
        bot.securities[symbol]=NS(symbol_properties=NS(contract_multiplier=100))
        if symbol not in bot.portfolio: bot.portfolio[symbol]=Holding()
    return NS(option_chains={'CHAIN':contracts},quote_bars=quotes,
              bars={'SPY':bar(bot.time,price,price,price,price)})

class TestKairos(unittest.TestCase):
    def test_requested_defaults_and_dates(self):
        b=Bot()
        self.assertEqual(b.execution_mode,'options')
        self.assertEqual(b.period,timedelta(minutes=3))
        self.assertEqual(b.start,(2025,10,7))
        self.assertEqual(b.end,(2026,10,6))
        self.assertEqual((date(*b.end)-date(*b.start)).days+1,365)
        self.assertEqual(b.DOLLARS_PER_TRADE,2500)
        self.assertEqual((b.STOP_ATR_MULTIPLE,b.PROFIT_TARGET_R),(1.5,.45))
        self.assertFalse(b.EXIT_ON_OPPOSITE_KERNEL_FLIP)
        self.assertFalse(b.ENABLE_CASH_LOSS_CAP)
        self.assertFalse(b.USE_SLOPE_FILTER)
        self.assertTrue(b.USE_KERNEL_SMOOTHING)
        self.assertEqual((b.KERNEL_LAG,b.VP_CONFIRMATION_WINDOW),(6,10))
    def test_full_history_toggle(self):
        self.assertEqual(Bot({'one_year_backtest':'false'}).start,(2024,1,1))
    def test_parameter_validation(self):
        for params in ({'execution_mode':'bad'},{'profit_target_r':'-1'},
                       {'kernel_lag':'0'},{'one_year_backtest':'bad'}):
            with self.assertRaises(ValueError): Bot(params)
    def test_whole_share_budget_and_actual_fill_anchor(self):
        b=Bot({'execution_mode':'shares'}); b.market_price=600.03; b._enter_position(1,600,2)
        self.assertEqual(b.portfolio['SPY'].quantity,4)
        self.assertAlmostEqual(b.stop_price,597.03)
        self.assertAlmostEqual(b.target_price,601.38)
        self.assertEqual([r[1][1] for r in b.bracket_requests],[-4,-4])
    def test_short_levels_and_reversal_cancels_old_bracket(self):
        b=Bot({'execution_mode':'shares'}); b._enter_position(1,600,2); old=list(b.risk_tickets)
        b._enter_position(-1,600,2)
        self.assertEqual(b.portfolio['SPY'].quantity,-4)
        self.assertTrue(all(t.status=='CANCELED' for t in old))
        self.assertEqual([c[2] for c in b.calls if c[0]=='market'],[4,-8])
        self.assertEqual((b.stop_price,b.target_price),(603,598.65))
    def test_unaffordable_share_skips(self):
        b=Bot({'execution_mode':'shares'}); b._enter_position(1,3000,2)
        self.assertFalse(any(c[0]=='market' for c in b.calls))
    def test_rejected_reversal_restores_previous_protection(self):
        b=Bot({'execution_mode':'shares'}); b._enter_position(1,600,2); b.reject_entry=True
        b._enter_position(-1,600,2)
        self.assertEqual(b.portfolio['SPY'].quantity,4)
        self.assertEqual((b.stop_price,b.target_price),(597,601.35))
        self.assertTrue(all(t.status=='SUBMITTED' for t in b.risk_tickets))
    def test_cash_cap_can_be_enabled_without_changing_target_R(self):
        b=Bot({'execution_mode':'shares','enable_cash_loss_cap':'true','maximum_cash_loss':'4'})
        b._enter_position(1,600,2)
        self.assertEqual((b.stop_price,b.target_price),(599,601.35))
    def test_cutoff_cancels_and_flattens(self):
        b=Bot({'execution_mode':'shares'}); b._enter_position(1,600,2); old=list(b.risk_tickets)
        b._session_cutoff()
        self.assertFalse(b.portfolio['SPY'].invested)
        self.assertTrue(all(t.status=='CANCELED' for t in old))
        self.assertEqual(b.blocked_date,b.time.date())
    def test_warmup_never_orders(self):
        b=Bot({'execution_mode':'shares'}); b.is_warming_up=True; b.REQUIRE_VOLATILITY_PUSH=False
        for i in range(100):
            c=600+math.sin(i/4)
            b.on_signal_bar(bar(b.time+timedelta(minutes=3*i),c-.1,c+.2,c-.2,c))
        b._session_cutoff(); b._enter_position(1,600,2)
        self.assertFalse(any(c[0] in ('market','liquidate') for c in b.calls))
    def test_wilder_atr_seed_and_update(self):
        b=Bot()
        for _ in range(14): result=b._update_atr(14,2)
        self.assertEqual(result,2)
        self.assertAlmostEqual(b._update_atr(14,4),30/14)
    def test_kernel_independent_formula(self):
        b=Bot(); prices=[600+math.sin(i/3) for i in range(27)]
        b.closes.extend(prices)
        for weights, gaussian in ((b.rq_weights,False),(b.gaussian_weights,True)):
            pairs=[]
            for offset in range(27):
                weight=(math.exp(-offset**2/8) if gaussian else
                        (1+offset**2/(2*8**2*8))**-8)
                pairs.append((prices[-offset-1],weight))
            expected=sum(p*w for p,w in pairs)/sum(w for _,w in pairs)
            self.assertAlmostEqual(b._kernel(weights),expected,12)
    def test_VP_recent_direction_and_inclusive_window(self):
        b=Bot(); b.bar_index=40; b.last_bull_push_bar=30; b.last_bear_push_bar=25
        self.assertEqual(b._push_confirmations(),(True,False))
        b.bar_index=41
        self.assertEqual(b._push_confirmations(),(False,False))
        b.last_bear_push_bar=41
        self.assertEqual(b._push_confirmations(),(False,True))
    def test_VP_score_direction(self):
        b=Bot(); b.volumes.extend([100]*19+[500])
        self.assertEqual(b._volatility_push(10,12,10,11.9,500,1.2,1),(True,False))
        self.assertEqual(b._volatility_push(12,12,10,10.1,500,1.2,1),(False,True))
    def test_signal_window_and_confirmed_reversals(self):
        b=Bot({'execution_mode':'shares'}); b.REQUIRE_VOLATILITY_PUSH=False
        calls=[]; b._enter_position=lambda direction,*rest:calls.append((b.time,direction))
        for i in range(100):
            b.time=datetime(2026,10,6,9,30)+timedelta(minutes=3*i)
            c=600+math.sin(i/3)
            b.on_signal_bar(bar(b.time,c-.1,c+.3,c-.3,c))
        self.assertGreater(len(calls),2)
        self.assertTrue(all(datetime(2026,10,6,9,30)<=t<datetime(2026,10,6,15) for t,d in calls))
        self.assertEqual(set(d for t,d in calls),{-1,1})
    def test_option_contract_selection_and_premium_sizing(self):
        b=Bot({'execution_mode':'options'})
        data=option_data(b,[('C','CALL',600,0,1.9,2,True),
                            ('P','PUT',600,0,1.9,2,True)])
        b.market_price=2; b._enter_option(data,1,600,2)
        self.assertEqual((b.active_option,b.option_direction),('C',1))
        self.assertEqual(b.portfolio['C'].quantity,12)
        self.assertEqual(b.portfolio['SPY'].quantity,0)
        self.assertEqual((b.stop_price,b.target_price),(597,601.35))
        b._enter_option(data,-1,600,2)
        self.assertEqual(b.portfolio['C'].quantity,0)
        self.assertEqual(b.portfolio['P'].quantity,12)
    def test_stale_quote_missing_chain_unaffordable_no_entry(self):
        b=Bot({'execution_mode':'options'})
        data=option_data(b,[('C','CALL',600,0,1.9,2,False)])
        b._enter_option(data,1,600,2)
        data=option_data(b,[('C','CALL',600,0,26,27,True)])
        b._enter_option(data,1,600,2)
        self.assertEqual(b.skipped_option_signals,2)
        self.assertFalse(any(c[0]=='market' for c in b.calls))
    def test_option_one_minute_stop_and_retry_failed_liquidation(self):
        b=Bot({'execution_mode':'options'})
        data=option_data(b,[('C','CALL',600,0,1.9,2,True)])
        b.market_price=2; b._enter_option(data,1,600,2)
        b.fail_liquidation=True
        b.on_data(option_data(b,[('C','CALL',600,0,1.9,2,True)],596))
        self.assertEqual(b.active_option,'C'); self.assertTrue(b.option_cash_exit_pending)
        b.fail_liquidation=False
        b.on_data(option_data(b,[('C','CALL',600,0,1.9,2,True)],600))
        self.assertIsNone(b.active_option)
    def test_option_signal_not_delayed_and_fresh_chain(self):
        b=Bot()
        data=option_data(b,[('P','PUT',600,0,1.9,2,True)])
        b.pending_signal=(b.time-timedelta(minutes=1),-1,600,2)
        b.on_data(data)
        self.assertIsNone(b.active_option)
        b.pending_signal=(b.time,-1,600,2); b.market_price=2
        b.on_data(data)
        self.assertEqual(b.active_option,'P')
    def test_algorithm_character_limit(self):
        self.assertLess(len(path.read_text()),32000)

if __name__=='__main__': unittest.main()
