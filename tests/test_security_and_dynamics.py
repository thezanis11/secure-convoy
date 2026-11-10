from dataclasses import replace
import os
import unittest

import numpy as np

from secure_convoy.simulation import Config, authenticate, integrate, safety_bound, sign, simulate
from secure_convoy.experiments import wilson


class MessageSecurityTests(unittest.TestCase):
    def packet(self):
        return sign(dict(sender=0, sequence=8, sent_at=1.0, position=20., speed=25., acceleration=0.))

    def test_authentic_fresh_packet_is_accepted(self):
        self.assertIsNone(authenticate(self.packet(), 0, 1.1, 7, .4))

    def test_modification_without_key_is_rejected(self):
        packet = self.packet()
        packet['speed'] = 80.
        self.assertEqual(authenticate(packet, 0, 1.1, 7, .4), 'signature')

    def test_valid_signature_does_not_prove_truth(self):
        packet = self.packet()
        packet['speed'] = 80.
        self.assertIsNone(authenticate(sign(packet), 0, 1.1, 7, .4))

    def test_replay_expiry_future_and_sender(self):
        p = self.packet()
        self.assertEqual(authenticate(p, 0, 1.1, 8, .4), 'replay')
        self.assertEqual(authenticate(p, 0, 2., 7, .4), 'freshness')
        self.assertEqual(authenticate(p, 0, .1, 7, .4), 'freshness')
        self.assertEqual(authenticate(p, 1, 1.1, 7, .4), 'sender')

    def test_nonfinite_and_malformed_are_rejected(self):
        p = self.packet()
        p['speed'] = float('nan')
        self.assertEqual(authenticate(p, 0, 1.1, 7, .4), 'nonfinite')
        self.assertEqual(authenticate({}, 0, 1.1, 7, .4), 'malformed')


class DynamicsTests(unittest.TestCase):
    def test_constant_acceleration_kinematics(self):
        x, v, a = integrate(np.array([0.]), np.array([10.]), np.array([2.]), np.array([2.]), np.array([.2]), np.array([8.]), .1, 25)
        np.testing.assert_allclose(x, [1.01])
        np.testing.assert_allclose(v, [10.2])

    def test_stopping_does_not_reverse_or_overshoot(self):
        x, v, a = integrate(np.array([0.]), np.array([.1]), np.array([-8.]), np.array([-8.]), np.array([.2]), np.array([8.]), .1, 25)
        self.assertEqual(v[0], 0)
        self.assertAlmostEqual(x[0], .1*.1/(2*8))

    def test_saturation_and_jerk_are_physical(self):
        _, _, a = integrate(np.array([0.]), np.array([10.]), np.array([0.]), np.array([100.]), np.array([.2]), np.array([8.]), .05, 10)
        self.assertAlmostEqual(a[0], .5)

    def test_headway_barrier_demands_braking_at_short_gap(self):
        self.assertLess(safety_bound(5, 25, 25), 0)

    def test_seed_is_reproducible(self):
        cfg = Config(duration=2)
        a, ta = simulate(123, 'clean', 'defended_cacc', cfg, trace=True)
        b, tb = simulate(123, 'clean', 'defended_cacc', cfg, trace=True)
        self.assertEqual(a, b)
        self.assertEqual(ta, tb)

    def test_invalid_setup_is_rejected(self):
        with self.assertRaises(ValueError):
            simulate(config=Config(dt=.2))
        with self.assertRaises(ValueError):
            simulate(scenario='invented')

    def test_collision_stops_trace_at_contact(self):
        result, frames = simulate(0, 'insider_spoof', 'trusting_cacc', trace=True)
        self.assertTrue(result['collision'])
        self.assertLess(result['simulated_seconds'], 42)
        self.assertAlmostEqual(max(r['time'] for r in frames), result['first_collision_seconds'])

    def test_confidence_interval_does_not_claim_zero_risk(self):
        low, high = wilson(0, 32)
        self.assertLess(low, 1e-10)
        self.assertGreater(high, .10)


@unittest.skipUnless(os.environ.get('RUN_SUMO_TESTS') == '1', 'SUMO integration is opt-in')
class SumoIntegration(unittest.TestCase):
    def test_closed_loop_two_second_consistency(self):
        from secure_convoy.sumo_validation import SumoPlant
        cfg = Config(duration=2)
        reference, _ = simulate(1000, 'clean', 'defended_cacc', cfg)
        plant = SumoPlant(cfg)
        try:
            actual, _ = simulate(1000, 'clean', 'defended_cacc', cfg, plant_step=plant.step)
        finally:
            plant.close()
        self.assertAlmostEqual(reference['min_gap_m'], actual['min_gap_m'], places=7)


if __name__ == '__main__':
    unittest.main()
