import unittest

from services.application.app.analysis.character_threshold import calibrate_threshold


class CharacterThresholdCalibrationTest(unittest.TestCase):
    def test_selects_boundary_separating_same_and_different_people(self):
        result = calibrate_threshold(((0.95, True), (0.9, True), (0.6, False), (0.2, False)))
        self.assertEqual(result.threshold, 0.9)
        self.assertEqual(result.balanced_accuracy, 1.0)

    def test_tie_prefers_stricter_threshold_and_requires_both_labels(self):
        result = calibrate_threshold(((0.8, True), (0.8, False)))
        self.assertEqual(result.threshold, 0.8)
        with self.assertRaisesRegex(ValueError, "both identity labels"):
            calibrate_threshold(((0.8, True),))
