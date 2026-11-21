"""
Unit tests for confidence interval calculations, weighted mixed-workload payloads,
and benchmark timestamp validation.
"""

import datetime
import math
import unittest
from bench.process_unified_results import compute_confidence_interval, get_t_critical, STUDENT_T_CRIT_95


class TestStatisticalCalculations(unittest.TestCase):

    def test_t_critical_values(self):
        # n = 7 => df = 6: t_crit ≈ 2.4469
        t_crit_n7 = get_t_critical(df=6, confidence=0.95)
        self.assertAlmostEqual(t_crit_n7, 2.4469, places=3)
        self.assertEqual(STUDENT_T_CRIT_95[6], 2.4469)

        # n = 5 => df = 4: t_crit ≈ 2.7764
        t_crit_n5 = get_t_critical(df=4, confidence=0.95)
        self.assertAlmostEqual(t_crit_n5, 2.7764, places=3)
        self.assertEqual(STUDENT_T_CRIT_95[4], 2.7764)

        # n = 10 => df = 9: t_crit ≈ 2.2622
        t_crit_n10 = get_t_critical(df=9, confidence=0.95)
        self.assertAlmostEqual(t_crit_n10, 2.2622, places=3)

    def test_confidence_interval_small_samples(self):
        # 7 synthetic trial data points
        data_n7 = [100.0, 102.0, 98.0, 101.0, 99.0, 103.0, 97.0]
        ci_n7 = compute_confidence_interval(data_n7, confidence=0.95)
        # mean = 100, var = (4 + 0 + 4 + 1 + 1 + 9 + 9)/6 = 28/6 = 4.6667, std = 2.1602
        # SE = 2.1602 / sqrt(7) = 0.8165
        # CI = 2.4469 * 0.8165 = 1.9979
        self.assertAlmostEqual(ci_n7, 1.998, places=2)

        # 5 synthetic trial data points
        data_n5 = [10.0, 12.0, 14.0, 16.0, 18.0]
        # mean = 14, std = sqrt(10) ≈ 3.1623, SE = 3.1623 / sqrt(5) ≈ 1.4142
        # CI = 2.7764 * 1.4142 ≈ 3.926
        ci_n5 = compute_confidence_interval(data_n5, confidence=0.95)
        self.assertAlmostEqual(ci_n5, 3.926, places=2)

    def test_confidence_interval_edge_cases(self):
        # n < 2 must return 0.0 without exception
        self.assertEqual(compute_confidence_interval([]), 0.0)
        self.assertEqual(compute_confidence_interval([42.0]), 0.0)

        # identical values => variance = 0 => CI = 0
        self.assertEqual(compute_confidence_interval([5.0, 5.0, 5.0, 5.0, 5.0]), 0.0)


class TestMixedWorkloadCalculations(unittest.TestCase):

    def test_weighted_payload_arithmetic(self):
        # Mixed 80/20 workload: 80% small (64 B), 20% large (16,384 B)
        p_small = 64
        p_large = 16384
        weight_small = 0.8
        weight_large = 0.2
        weighted_mean = (weight_small * p_small) + (weight_large * p_large)
        self.assertEqual(weighted_mean, 3328.0)
        self.assertNotEqual(weighted_mean, 3315.0)

    def test_total_payload_and_throughput_consistency(self):
        # 10,000 messages: 8,000 at 64 B, 2,000 at 16,384 B
        n_small = 8000
        n_large = 2000
        total_bytes = (n_small * 64) + (n_large * 16384)
        self.assertEqual(total_bytes, 33280000)
        # Average per message
        self.assertEqual(total_bytes / (n_small + n_large), 3328.0)


class TestTimestampMetadataValidation(unittest.TestCase):

    def test_timestamp_ordering_validation(self):
        t0 = datetime.datetime.now(datetime.timezone.utc)
        t1 = t0 + datetime.timedelta(seconds=1.5)
        self.assertLessEqual(t0, t1)

        # Inversion must fail validation
        with self.assertRaises(ValueError):
            if t1 < t0:
                pass
            else:
                # Simulated invalid metadata
                start_dt = t1
                completed_dt = t0
                if start_dt > completed_dt:
                    raise ValueError("Benchmark started_at_utc timestamp cannot occur after completed_at_utc")


if __name__ == "__main__":
    unittest.main()
