"""Pipeline orchestration tests that do not require FastAPI or model weights."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.pipeline import AssessmentPipeline, DEFAULT_PRICING_PATH  # noqa: E402
from ml.src.repair_cost_estimator import load_pricing_config  # noqa: E402


class TestAssessmentPipeline(unittest.TestCase):
    def make_pipeline(self, model_loader=None, pricing_loader=None):
        return AssessmentPipeline(
            model_loader=model_loader or (lambda _path: object()),
            pricing_loader=pricing_loader or (
                lambda path: load_pricing_config(DEFAULT_PRICING_PATH)
            ),
        )

    def test_health_reports_both_dependencies_and_loads_once(self):
        calls = {"model": 0, "pricing": 0}

        def model_loader(_path):
            calls["model"] += 1
            return object()

        def pricing_loader(_path):
            calls["pricing"] += 1
            return load_pricing_config(DEFAULT_PRICING_PATH)

        pipeline = self.make_pipeline(model_loader, pricing_loader)
        self.assertTrue(pipeline.health()["ready"])
        self.assertTrue(pipeline.health()["model"]["available"])
        self.assertTrue(pipeline.health()["pricing_configuration"]["available"])
        self.assertEqual(calls, {"model": 1, "pricing": 1})

    def test_model_load_failure_keeps_pipeline_not_ready(self):
        def fail(_path):
            raise FileNotFoundError("private/path/model.pt")

        pipeline = self.make_pipeline(model_loader=fail)
        status = pipeline.health()
        self.assertFalse(status["ready"])
        self.assertFalse(status["model"]["available"])
        self.assertEqual(status["model"]["error"], "model_file_missing")
        self.assertNotIn("private/path", str(status))

    def test_existing_functions_are_composed_and_local_paths_are_removed(self):
        pipeline = self.make_pipeline()
        pipeline.initialize()
        detection = {
            "image_path": "temporary/path/upload",
            "image_width": 10,
            "image_height": 10,
            "model_name": "mock.pt",
            "model_path": "private/model/path.pt",
            "inference_device": "cpu",
            "image_size": 640,
            "confidence_threshold": 0.25,
            "coordinate_system": "pixels",
            "detection_count": 0,
            "detections": [],
            "masks_available": False,
            "overlap_diagnostics": {"overlapping_pairs": []},
            "timestamp_utc": "2026-01-01T00:00:00+00:00",
        }
        with patch(
            "backend.app.pipeline.damage_detection.analyze_image",
            return_value=detection,
        ) as analyze:
            stages = pipeline.assess("temporary/path/upload", "car.png")
        analyze.assert_called_once()
        self.assertEqual(stages["detection_report"]["image_path"], "car.png")
        self.assertNotIn("model_path", stages["detection_report"])
        self.assertEqual(stages["severity_assessment"]["source_image"], "car.png")
        self.assertIn("summary", stages["repair_cost_estimate"])


if __name__ == "__main__":
    unittest.main()
