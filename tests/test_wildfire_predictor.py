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

    def test_geojson_heatmap_structure(self):
        """Heatmap GeoJSON should conform to standard FeatureCollection format."""
        geojson = self.predictor.get_risk_heatmap_geojson(limit=10)
        self.assertEqual(geojson.get("type"), "FeatureCollection")
        self.assertIn("features", geojson)
        self.assertIn("total", geojson)
        if geojson["features"]:
            feat = geojson["features"][0]
            self.assertEqual(feat.get("type"), "Feature")
            self.assertEqual(feat["geometry"]["type"], "Point")
            self.assertEqual(len(feat["geometry"]["coordinates"]), 2)
            props = feat["properties"]
            self.assertIn("grid_id", props)
            self.assertIn("calibrated_risk", props)
            self.assertIn("risk_tier", props)
            self.assertIn("estimated_eta", props)

    def test_duckdb_error_resilience_and_caching(self):
        """Predictor should return cached cells on DuckDB error without raising."""
        # Ensure cache has cells
        initial = self.predictor.get_top_at_risk_cells(limit=3)
        self.assertGreater(len(initial), 0)
        self.assertGreater(len(self.predictor._cached_cells), 0)

        # Mock duckdb.connect to raise an error
        from unittest.mock import patch
        import duckdb
        with patch("duckdb.connect", side_effect=duckdb.Error("Database locked / config error")):
            fallback_cells = self.predictor.get_top_at_risk_cells(limit=3)
            self.assertIsInstance(fallback_cells, list)
            self.assertEqual(len(fallback_cells), len(initial))

    def test_predict_features_dataframe(self):
        """predict_features should append probability, risk tier, and predicted FRP."""
        import pandas as pd
        from src.ml.diurnal import FEATURE_COLS

        dummy_data = {col: [0.5] for col in FEATURE_COLS}
        dummy_df = pd.DataFrame(dummy_data)
        scored = self.predictor.predict_features(dummy_df)
        self.assertIn("raw_risk_prob", scored.columns)
        self.assertIn("calibrated_risk_prob", scored.columns)
        self.assertIn("risk_tier", scored.columns)
        self.assertIn("predicted_intensity_frp_mw", scored.columns)


if __name__ == "__main__":
    unittest.main()
