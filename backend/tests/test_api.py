"""API tests with mock inference; no model execution is performed."""

import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
except ModuleNotFoundError as import_error:
    TestClient = None
    FASTAPI_IMPORT_ERROR = str(import_error)
else:
    FASTAPI_IMPORT_ERROR = ""


@unittest.skipUnless(TestClient, f"FastAPI test dependencies unavailable: {FASTAPI_IMPORT_ERROR}")
class TestVehicleAssessmentAPI(unittest.TestCase):
    def make_app(self, max_upload_bytes=1024 * 1024, model_error=None, pricing_error=None):
        from backend.app.pipeline import AssessmentPipeline, DEFAULT_PRICING_PATH
        from backend.app.gemini import GeminiService
        from backend.app.settings import Settings
        from ml.src.repair_cost_estimator import load_pricing_config

        def load_model(_path):
            if model_error:
                raise model_error
            return object()

        def load_pricing(_path):
            if pricing_error:
                raise pricing_error
            return load_pricing_config(DEFAULT_PRICING_PATH)

        pipeline = AssessmentPipeline(
            model_loader=load_model,
            pricing_loader=load_pricing,
        )
        # Keep API unit tests deterministic and free of paid provider calls even
        # when a developer has enabled Gemini in their local backend/.env.
        return create_app(
            pipeline=pipeline,
            max_upload_bytes=max_upload_bytes,
            gemini_service=GeminiService(Settings(gemini_enabled=False)),
        )

    @staticmethod
    def png_bytes():
        import cv2
        import numpy as np

        ok, encoded = cv2.imencode(".png", np.zeros((12, 12, 3), dtype=np.uint8))
        if not ok:
            raise AssertionError("Could not encode test PNG")
        return encoded.tobytes()

    @staticmethod
    def detection_result(image_path, **kwargs):
        result = {
            "image_path": str(image_path),
            "image_width": 12,
            "image_height": 12,
            "model_name": "mock-model.pt",
            "model_path": "private/local/path/mock-model.pt",
            "inference_device": "cpu",
            "image_size": 640,
            "confidence_threshold": 0.25,
            "coordinate_system": "original-image pixels",
            "detection_count": 0,
            "detections": [],
            "masks_available": False,
            "overlap_diagnostics": {"overlapping_pairs": []},
            "timestamp_utc": "2026-01-01T00:00:00+00:00",
        }
        result.update(kwargs)
        return result

    def test_health_reports_ready_model_and_pricing(self):
        app = self.make_app()
        with patch.object(app.state.gemini_service, "diagnostic") as diagnostic, TestClient(app) as client:
            response = client.get("/health")
        diagnostic.assert_not_called()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["api"], "running")
        self.assertTrue(payload["ready"])
        self.assertTrue(payload["model"]["available"])
        self.assertTrue(payload["pricing_configuration"]["available"])
        self.assertNotIn("path", str(payload).lower())

    def test_health_is_not_ready_if_required_component_fails(self):
        app = self.make_app(model_error=FileNotFoundError("private model path"))
        with TestClient(app) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertFalse(payload["ready"])
        self.assertFalse(payload["model"]["available"])
        self.assertEqual(payload["model"]["error"], "model_file_missing")
        self.assertNotIn("private model path", str(payload))

    def test_valid_image_upload_returns_all_stage_schemas(self):
        app = self.make_app()
        with patch(
            "backend.app.pipeline.damage_detection.analyze_image",
            side_effect=lambda path, **kwargs: self.detection_result(path),
        ) as analyze:
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/assessments",
                    files={"file": ("../car.png", self.png_bytes(), "image/png")},
                )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["source_image"], "car.png")
        self.assertIn("assessment_id", payload)
        self.assertIn("detection_report", payload)
        self.assertIn("severity_assessment", payload)
        self.assertIn("repair_cost_estimate", payload)
        self.assertTrue(payload["preliminary"])
        self.assertNotIn("gemini_assessment", payload)
        self.assertEqual(payload["detection_report"]["detections"], [])
        self.assertEqual(payload["severity_assessment"]["summary"]["detection_count"], 0)
        self.assertIsNone(payload["repair_cost_estimate"]["summary"]["vehicle_total"]["low"])
        self.assertNotIn("model_path", payload["detection_report"])
        self.assertEqual(analyze.call_args.args[0].suffix, ".png")
        self.assertEqual(analyze.call_count, 1)

    def test_upload_does_not_call_gemini_and_explicit_action_reuses_existing_assessment(self):
        app = self.make_app()
        image_bytes = self.png_bytes()
        with patch.object(app.state.gemini_service, "generate_summary", return_value={
            "status": "completed", "model": "mock-model", "summary": {"summary": "Mock only"},
            "message": "Mock structured response.", "generated_at": "now",
        }) as summary, patch.object(app.state.gemini_service, "estimate_repair_cost", return_value={
            "status": "completed", "model": "mock-model", "pricing_status": "estimate_unavailable",
            "verified_market_price": False, "illustrative_example_only": False, "currency": "INR",
            "findings": [], "total_status": "estimate_unavailable", "vehicle_total": None,
            "partial_subtotal": None, "total_reason": "No findings.", "assumptions": [],
            "message": "No prices returned.", "generated_at": "now",
        }) as costs, patch(
            "backend.app.pipeline.damage_detection.analyze_image",
            side_effect=lambda path, **kwargs: self.detection_result(path),
        ) as analyze:
            with TestClient(app) as client:
                created = client.post("/api/v1/assessments", files={"file": ("car.png", image_bytes, "image/png")})
                self.assertEqual(created.status_code, 200, created.text)
                record = created.json()
                self.assertEqual(summary.call_count, 0)
                self.assertEqual(costs.call_count, 0)
                assessment_id = record["assessment_id"]
                first = client.post(f"/api/v1/assessments/{assessment_id}/ai-summary")
                second = client.post(f"/api/v1/assessments/{assessment_id}/repair-cost")
                retry = client.post(f"/api/v1/assessments/{assessment_id}/repair-cost")
                fetched = client.get(f"/api/v1/assessments/{assessment_id}")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(summary.call_count, 1)
        self.assertEqual(costs.call_count, 2)
        self.assertEqual(costs.call_args.args[2], image_bytes)
        self.assertEqual(analyze.call_count, 1)
        self.assertEqual(fetched.json()["ai_summary"]["status"], "completed")
        self.assertEqual(fetched.json()["ai_cost_estimate"]["status"], "completed")
        self.assertEqual(fetched.json()["detection_report"], record["detection_report"])

    def test_concurrent_gemini_actions_do_not_start_duplicate_generation(self):
        app = self.make_app()
        with patch(
            "backend.app.pipeline.damage_detection.analyze_image",
            side_effect=lambda path, **kwargs: self.detection_result(path),
        ), TestClient(app) as client:
            created = client.post("/api/v1/assessments", files={"file": ("car.png", self.png_bytes(), "image/png")})
            self.assertEqual(created.status_code, 200, created.text)
            assessment_id = created.json()["assessment_id"]
            started = threading.Event()
            release = threading.Event()

            def slow_assessment(*_args):
                started.set()
                release.wait(timeout=5)
                return {"status": "unavailable", "model": None, "assessment": None,
                        "message": "Original findings remain available.", "generated_at": None,
                        "fallback_insurance_guidance": {}}

            with patch.object(app.state.gemini_service, "generate_summary", side_effect=slow_assessment) as assess:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    first_request = executor.submit(client.post, f"/api/v1/assessments/{assessment_id}/ai-summary")
                    self.assertTrue(started.wait(timeout=5), "First Gemini request did not start")
                    duplicate = client.post(f"/api/v1/assessments/{assessment_id}/ai-summary")
                    release.set()
                    first = first_request.result(timeout=5)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(duplicate.status_code, 409)
            self.assertEqual(assess.call_count, 1)

    def test_failed_cost_request_is_persisted_without_example_price_or_detector_rerun(self):
        app = self.make_app()
        with patch("backend.app.pipeline.damage_detection.analyze_image", side_effect=lambda path, **kwargs: self.detection_result(path)) as detector:
            with TestClient(app) as client:
                created = client.post("/api/v1/assessments", files={"file": ("car.png", self.png_bytes(), "image/png")})
                self.assertEqual(created.status_code, 200, created.text)
                assessment_id = created.json()["assessment_id"]
                with patch.object(app.state.gemini_service, "estimate_repair_cost", return_value={
                    "status": "unavailable", "model": None, "message": "Gemini timed out.",
                    "generated_at": None, "pricing_status": "estimate_unavailable",
                    "verified_market_price": False, "illustrative_example_only": False,
                    "currency": "INR", "findings": [], "total_status": "estimate_unavailable",
                    "vehicle_total": None, "partial_subtotal": None,
                    "total_reason": "Gemini timed out.", "assumptions": [],
                }) as estimate:
                    failed = client.post(f"/api/v1/assessments/{assessment_id}/repair-cost")
                loaded = client.get(f"/api/v1/assessments/{assessment_id}").json()
        self.assertEqual(failed.status_code, 200, failed.text)
        estimate.assert_called_once()
        self.assertEqual(detector.call_count, 1)
        self.assertEqual(loaded["ai_cost_estimate"]["status"], "unavailable")
        self.assertIsNone(loaded["ai_cost_estimate"]["vehicle_total"])
        self.assertNotIn("illustrative_example_only", loaded["repair_cost_estimate"])
        self.assertEqual(loaded["detection_report"], created.json()["detection_report"])

    def test_invalid_file_type_is_rejected(self):
        with TestClient(self.make_app()) as client:
            response = client.post(
                "/api/v1/assessments",
                files={"file": ("note.txt", b"hello", "text/plain")},
            )
        self.assertEqual(response.status_code, 415)

    def test_oversized_upload_is_rejected(self):
        with TestClient(self.make_app(max_upload_bytes=16)) as client:
            response = client.post(
                "/api/v1/assessments",
                files={"file": ("large.png", self.png_bytes(), "image/png")},
            )
        self.assertEqual(response.status_code, 413)

    def test_malformed_image_is_rejected_before_pipeline(self):
        app = self.make_app()
        with patch("backend.app.pipeline.damage_detection.analyze_image") as analyze:
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/assessments",
                    files={"file": ("broken.png", b"\x89PNG\r\n\x1a\nnot-an-image", "image/png")},
                )
        self.assertEqual(response.status_code, 422)
        analyze.assert_not_called()

    def test_pipeline_error_returns_sanitized_server_error(self):
        app = self.make_app()
        with patch(
            "backend.app.pipeline.damage_detection.analyze_image",
            side_effect=RuntimeError("failure at C:\\private\\weights.pt"),
        ):
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/assessments",
                    files={"file": ("car.png", self.png_bytes(), "image/png")},
                )
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private", response.text)
        self.assertIn("Assessment pipeline failed", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
