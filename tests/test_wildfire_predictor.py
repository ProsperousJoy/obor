"""Unit tests for WildfirePredictor dual ML models and diurnal cycle."""

import unittest
from src.ml.predictor import WildfirePredictor


class TestWildfirePredictor(unittest.TestCase):
    """Verifies ML dual-model inference and probability scoring."""

    @classmethod
    def setUpClass(cls):
        cls.predictor = WildfirePredictor()

    def test_models_loaded(self):
        """Dual models (classifier + regressor) should be loaded successfully."""
        self.assertTrue(self.predictor.is_ready)
        self.assertIsNotNone(self.predictor.clf_artifact)
        self.assertIsNotNone(self.predictor.reg_artifact)

    def test_prediction_output_structure(self):
        """Prediction on Borneo grid should produce valid probability, intensity, and ETA."""
        predictions = self.predictor.get_top_at_risk_cells(limit=5)
        self.assertIsInstance(predictions, list)
        self.assertGreater(len(predictions), 0)

        top_pred = predictions[0]
        self.assertIn("grid_id", top_pred)
        self.assertIn("calibrated_risk", top_pred)
        self.assertIn("predicted_frp_mw", top_pred)
        self.assertIn("risk_tier", top_pred)
        self.assertIn("estimated_eta", top_pred)
        self.assertIn("eta_hours_min", top_pred)
        self.assertGreaterEqual(top_pred["calibrated_risk"], 0.0)
        self.assertLessEqual(top_pred["calibrated_risk"], 1.0)
        self.assertGreaterEqual(top_pred["eta_hours_min"], 0.0)


if __name__ == "__main__":
    unittest.main()
