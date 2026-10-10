from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.test import SimpleTestCase

from tracking.progress import Sample, TrackState, evaluate, haversine_m

CFG = settings.FLUXO_TRACKING
T0 = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
STOP = (-5.6, -37.8)
NEAR = (-5.6003, -37.8)  # ~33 m
FAR = (-5.6020, -37.8)  # ~222 m


def s(xy, sec, acc=10):
    return Sample(xy[0], xy[1], T0 + timedelta(seconds=sec), acc)


class HaversineTests(SimpleTestCase):
    def test_zero(self):
        self.assertEqual(haversine_m(*STOP, *STOP), 0)

    def test_one_milli_degree_lat_is_about_111m(self):
        self.assertAlmostEqual(haversine_m(0, 0, 0.001, 0), 111.2, delta=0.5)


class ArrivalTests(SimpleTestCase):
    def run_seq(self, samples, next_stop=STOP, departing=None):
        state, out = TrackState(), []
        for smp in samples:
            r = evaluate(smp, state, next_stop, departing, CFG)
            state = r.state
            out.append(r)
        return out

    def test_arrives_only_on_third_consecutive_sample(self):
        r = self.run_seq([s(NEAR, 0), s(NEAR, 5), s(NEAR, 10)])
        self.assertEqual([x.arrived for x in r], [False, False, True])

    def test_leaving_radius_resets_streak(self):
        r = self.run_seq([s(NEAR, 0), s(NEAR, 5), s(FAR, 10), s(NEAR, 15), s(NEAR, 20)])
        self.assertFalse(any(x.arrived for x in r))

    def test_gap_over_20s_restarts_streak(self):
        r = self.run_seq([s(NEAR, 0), s(NEAR, 5), s(NEAR, 40), s(NEAR, 45)])
        self.assertFalse(any(x.arrived for x in r))

    def test_inaccurate_samples_are_ignored_and_do_not_reset(self):
        r = self.run_seq([s(NEAR, 0), s(NEAR, 5), s(FAR, 8, acc=80), s(NEAR, 10)])
        self.assertTrue(r[2].ignored)
        self.assertTrue(r[3].arrived)

    def test_no_next_stop_never_arrives(self):
        r = self.run_seq([s(NEAR, 0), s(NEAR, 5), s(NEAR, 10)], next_stop=None)
        self.assertFalse(any(x.arrived for x in r))


class DepartureTests(SimpleTestCase):
    def test_departs_after_two_samples_beyond_125m(self):
        state = TrackState()
        r1 = evaluate(s(FAR, 0), state, None, STOP, CFG)
        r2 = evaluate(s(FAR, 5), r1.state, None, STOP, CFG)
        self.assertEqual([r1.departed, r2.departed], [False, True])

    def test_between_75_and_125m_does_not_depart(self):
        mid = (-5.6009, -37.8)  # ~100 m
        state = TrackState()
        for sec in (0, 5, 10):
            r = evaluate(s(mid, sec), state, None, STOP, CFG)
            state = r.state
            self.assertFalse(r.departed)
