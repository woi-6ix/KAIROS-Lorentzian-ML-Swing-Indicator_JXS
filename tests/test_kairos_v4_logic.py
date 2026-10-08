"""Source/logic checks only; these do not compile Pine or test market profitability."""
import itertools
import math
from pathlib import Path
import random
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / 'KAIROS_LC_Swing_Engine_V3_JXS_918.pine'
V4 = ROOT / 'KAIROS_LC_Swing_Engine_V4_JXS_918.pine'


def direction_gates(side, *, lc, prediction, ema, sma, ready, classification,
                    votes, minimum, close, ema_value, sma_value):
    class_ok = not lc or (ready and classification == side)
    prediction_ok = not lc or not prediction or (ready and side * votes >= minimum)
    ema_ok = not ema or (ema_value is not None and side * (close - ema_value) > 0)
    sma_ok = not sma or (sma_value is not None and side * (close - sma_value) > 0)
    return class_ok and prediction_ok and ema_ok and sma_ok


def distance(current, historical, mask):
    return sum(math.log1p(abs(a-b)) for a,b,active in zip(current,historical,mask) if active)


class AnnModel:
    """Model the specified persistent JDE-style queue and bounded bar window."""
    def __init__(self, neighbors, window):
        self.neighbors, self.window = neighbors, window
        self.history, self.votes = [], []
        self.last_bar, self.position, self.closed = None, 0, 0
        self.direction = 0
        self.accepted = []

    def execution(self, bar, features, label, mask, *, confirmed=True, position=0, closed=0):
        fill = position != self.position or closed != self.closed
        self.position, self.closed = position, closed
        if not confirmed or fill or bar == self.last_bar:
            return None
        self.last_bar = bar
        oldest = max(0, bar-self.window)
        self.votes = [v for v in self.votes if v[0] >= oldest]
        last_distance = -1
        self.accepted = []
        for sample_bar, sample, outcome in self.history:
            if sample_bar < oldest or sample_bar >= bar or sample_bar % 4 == 0:
                continue
            d = distance(features, sample, mask)
            if d >= last_distance:
                last_distance = d
                self.votes.append((sample_bar, d, outcome))
                self.accepted.append(sample_bar)
                if len(self.votes) > self.neighbors:
                    index = min(len(self.votes)-1, math.floor(self.neighbors*0.75+0.5))
                    last_distance = self.votes[index][1]
                    self.votes.pop(0)
        score = sum(v[2] for v in self.votes)
        if score: self.direction = 1 if score > 0 else -1
        # This bar joins the candidate pool only after the query has completed.
        self.history.append((bar, features, label))
        self.history = self.history[-self.window:]
        return score


class KairosV4Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v3, cls.v4 = V3.read_text(), V4.read_text()

    def test_strategy_and_v3_risk_execution_preserved(self):
        self.assertIn('strategy(', self.v4)
        self.assertNotRegex(self.v4, r'(?m)^indicator\(')
        for text in ('pyramiding=0', 'process_orders_on_close=true',
                     'calc_on_order_fills=true', 'qty=entryQuantity,'):
            self.assertIn(text, self.v4)
        begin, end = '// LOCK RISK LEVELS AFTER ACTUAL FILL', '// STRATEGY STATISTICS TABLE'
        self.assertEqual(self.v3[self.v3.index(begin):self.v3.index(end)],
                         self.v4[self.v4.index(begin):self.v4.index(end)].replace('V4', 'V3'))
        begin, end = 'string GROUP_GENERAL', '// ENTRY CONDITIONS'
        inherited = self.v4[self.v4.index(begin):self.v4.index(end)]
        inherited = inherited[:inherited.index('// V4 LORENTZIAN CLASSIFICATION')]
        # Compare calculations up to the new module, independent of extra dividers.
        clean = lambda x: re.sub(r'//[^\n]*|\s+', '', x.replace('V4','V3'))
        original = self.v3[self.v3.index(begin):self.v3.index(end)]
        self.assertEqual(clean(inherited), clean(original))

    def test_new_sections_have_toggles(self):
        for name in ('useLCFilter','useMLPredictionFilter','useEMAEntryFilter','useSMAEntryFilter'):
            self.assertRegex(self.v4, rf'bool {name} = input.bool\(true,')
        for n in range(1,6):
            self.assertIn(f'bool lcEnableFeature{n} = input.bool(true,', self.v4)
        self.assertIn('import jdehorty/MLExtensions/2 as ml', self.v4)
        self.assertIn('table.clear(statsTable, 0, 0, 1, 16)', self.v4)

    def test_original_input_defaults_and_entry_triggers_preserved(self):
        pattern=r'\b(?:bool|int|float|string)\s+(\w+)\s*=\s*input\.\w+\(\s*([^,\n]+)'
        original=dict(re.findall(pattern,self.v3))
        current=dict(re.findall(pattern,self.v4))
        for name,default in original.items():
            self.assertEqual(current[name],default.replace('V3','V4'))
        for direction,push in [('long','bull'),('short','bear')]:
            expr=re.search(rf'bool {direction}EntrySignal = \(.*?\n\)',self.v3,re.S).group()
            added=f'{push}PushConfirmed and\n     {direction}V4FiltersPass'
            self.assertIn(expr.replace(f'{push}PushConfirmed',added),self.v4)

    def test_published_jde_label_signs_retained(self):
        self.assertIn('lcTrainingSource[4] < lcTrainingSource ? -1 : lcTrainingSource[4] > lcTrainingSource ? 1 : 0',self.v4)
        published_label=lambda old,now: -1 if old<now else 1 if old>now else 0
        self.assertEqual(published_label(99,100),-1)
        self.assertEqual(published_label(101,100),1)
        self.assertEqual(published_label(100,100),0)

    def test_source_prevents_duplicate_and_self_samples(self):
        self.assertIn('varip array<int> lcVotes', self.v4)
        self.assertIn('not lcFillRecalculation', self.v4)
        self.assertIn('lcLastProcessedBar != bar_index', self.v4)
        self.assertIn('candidateBar < bar_index', self.v4)
        self.assertIn('candidateBar >= oldestAllowedBar', self.v4)
        self.assertLess(self.v4.index('lcPrediction := array.size'), self.v4.index('array.push(lcHistory1,'))
        self.assertNotIn('last_bar_index', self.v4)
        self.assertNotIn('request.security', self.v4)

    def test_toggle_matrix_and_baseline_fallback(self):
        for side in (-1,1):
            for lc,pred,ema,sma in itertools.product((False,True),repeat=4):
                for ready in (False,True):
                    for classification in (-1,0,1):
                        for score in (-8,0,8):
                            for close in (99,100,101):
                                got = direction_gates(side,lc=lc,prediction=pred,ema=ema,sma=sma,
                                    ready=ready,classification=classification,votes=score,minimum=1,
                                    close=close,ema_value=100,sma_value=100)
                                expected = ((not lc or (ready and classification==side)) and
                                    (not lc or not pred or (ready and side*score>=1)) and
                                    (not ema or side*(close-100)>0) and
                                    (not sma or side*(close-100)>0))
                                self.assertEqual(got,expected)
                                if not lc and not ema and not sma:
                                    self.assertTrue(got) # No added gate alters the V3 entry signal.

    def test_threshold_direction_and_neutral_state(self):
        args=dict(lc=True,ema=False,sma=False,ready=True,classification=1,
                  minimum=3,close=100,ema_value=None,sma_value=None)
        self.assertFalse(direction_gates(1,prediction=True,votes=2,**args))
        self.assertTrue(direction_gates(1,prediction=True,votes=3,**args))
        self.assertFalse(direction_gates(1,prediction=True,votes=0,**args))
        self.assertTrue(direction_gates(1,prediction=False,votes=0,**args))
        args['classification']=-1
        self.assertTrue(direction_gates(-1,prediction=True,votes=-3,**args))
        self.assertFalse(direction_gates(-1,prediction=True,votes=3,**args))

    def test_missing_average_data_and_equality_block_only_enabled_filters(self):
        args=dict(lc=False,prediction=True,ready=False,classification=0,votes=0,
                  minimum=1,close=100,ema_value=None,sma_value=None)
        self.assertTrue(direction_gates(1,ema=False,sma=False,**args))
        self.assertFalse(direction_gates(1,ema=True,sma=False,**args))
        self.assertFalse(direction_gates(-1,ema=False,sma=True,**args))
        args.update(ema_value=100,sma_value=100)
        self.assertFalse(direction_gates(1,ema=True,sma=True,**args))

    def test_log_distance_masks_and_large_difference_compression(self):
        self.assertEqual(distance([1,2],[1,999],[True,False]),0)
        self.assertAlmostEqual(distance([0,0],[1,3],[True,True]),math.log(2)+math.log(4))
        self.assertLess(math.log1p(100),100)
        self.assertEqual(distance([1],[100],[False]),0)

    def test_uniform_feature_golden_votes(self):
        for neighbors in (1,8,100):
            model=AnnModel(neighbors,200)
            for bar in range(220):
                label=(-1,0,1)[bar % 3]
                got=model.execution(bar,[0]*5,label,[True]*5)
                eligible=[i for i in range(max(0,bar-200),bar) if i%4!=0]
                # Once enough candidates exist, equal distances accept every eligible
                # candidate, so the last N chronological labels are known exactly.
                if len(eligible)>=neighbors:
                    expected=sum((-1,0,1)[i%3] for i in eligible[-neighbors:])
                    self.assertEqual(got,expected)
                self.assertTrue(all(i<bar and i%4!=0 for i in model.accepted))

    def test_once_per_bar_fill_and_unconfirmed_callbacks(self):
        model=AnnModel(1,100)
        self.assertIsNone(model.execution(10,[0],1,[True],confirmed=False))
        self.assertEqual(len(model.history),0)
        model.execution(10,[0],1,[True])
        count=len(model.history)
        self.assertIsNone(model.execution(10,[999],-1,[True],position=100))
        self.assertIsNone(model.execution(10,[999],-1,[True],position=100))
        self.assertEqual(len(model.history),count)
        self.assertIsNone(model.execution(11,[999],-1,[True],position=0,closed=1))
        self.assertEqual(len(model.history),count)
        model.execution(11,[0],1,[True],position=0,closed=1)
        self.assertEqual(len(model.history),count+1)

    def test_window_bounds_and_all_neighbor_counts(self):
        rng=random.Random(918)
        for neighbors in range(1,101):
            model=AnnModel(neighbors,100)
            for bar in range(170):
                vector=[rng.random() for _ in range(5)]
                score=model.execution(bar,vector,rng.choice([-1,0,1]),[True]*5)
                self.assertLessEqual(len(model.history),100)
                self.assertLessEqual(len(model.votes),neighbors)
                self.assertLessEqual(abs(score),len(model.votes))
                self.assertTrue(all(max(0,bar-100)<=v[0]<bar for v in model.votes))

    def test_pine_delimiters_and_versioned_labels(self):
        clean=re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*','',self.v4)
        stack=[]
        pairs={')':'(',']':'[','}':'{'}
        for char in clean:
            if char in '([{': stack.append(char)
            elif char in ')]}': self.assertTrue(stack); self.assertEqual(stack.pop(),pairs[char])
        self.assertFalse(stack)
        self.assertNotRegex(self.v4, r'"KAIROS[^"\n]*V3[^"\n]*"')


if __name__ == '__main__':
    unittest.main()
