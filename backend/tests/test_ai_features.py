"""Offline tests for AI validation, insurance guidance, artifacts and PDF export."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import httpx
from google.genai import errors
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.app.artifacts import AssessmentArtifactStore, ArtifactNotFoundError
from backend.app.gemini import GeminiService, _gemini_response_json_schema
from backend.app.insurance import educational_guidance
from backend.app.main import create_app
from backend.app.pipeline import AssessmentPipeline, DEFAULT_PRICING_PATH
from backend.app.schemas import (
    AssessmentContext,
    CostComponent,
    GeminiAssessmentResponse,
    GeminiFindingExplanation,
    GeminiRepairEstimate,
    GeminiVehicleEstimateSummary,
    InsuranceFindingGuidance,
    InsuranceGuidance,
)
from backend.app.settings import Settings
from ml.src.repair_cost_estimator import load_pricing_config


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.models = FakeModels(response, error)
        self.closed = False

    def close(self):
        self.closed = True


def sample_stages():
    evidence = {
        "detection_id": 0,
        "class_id": 0,
        "class_name": "dent",
        "confidence": 0.92,
        "bbox_xyxy": [1.0, 1.0, 5.0, 5.0],
        "masks_available": True,
        "mask_area_pixels": 8,
        "mask_area_percent": 0.8,
        "polygons_xy": [[[1.0, 1.0], [5.0, 1.0], [5.0, 5.0]]],
    }
    severity = {
        "original_evidence": evidence,
        "preliminary_severity": "minor",
        "severity_reasons": ["Provisional class rule."],
        "image_level_mask_area_percent": 0.8,
        "mask_area_scope": "whole_image; not relative to a vehicle component",
        "component_relative_damage_percent": None,
        "inspection_flags": [],
        "human_review_required": True,
        "human_review_reasons": ["Human review is required."],
    }
    return {
        "detection_report": {
            "image_width": 12,
            "image_height": 12,
            "detections": [evidence],
            "detection_count": 1,
        },
        "severity_assessment": {
            "detections": [severity],
            "overlap_pairs": [],
        },
        "repair_cost_estimate": {"summary": {"vehicle_total": {"human_review_required": True}}},
    }


def valid_gemini_response(context: AssessmentContext) -> GeminiAssessmentResponse:
    zero = CostComponent(status="not_applicable", amount=__import__("backend.app.schemas", fromlist=["MoneyRange"]).MoneyRange(low=0, high=0), basis="No replacement part is assumed.")
    unknown_tax = CostComponent(status="unknown", amount=None, basis="Tax treatment is not verified.")
    return GeminiAssessmentResponse(
        summary="The image shows a possible localized dent; the component and repairability require inspection.",
        overall_assessment_status="requires_human_review",
        findings_explanations=[GeminiFindingExplanation(
            finding_id=0, plain_language="A localized surface irregularity is visible.", technical_context="The detector classified a dent with a high confidence score.", confidence_context="Confidence describes detection certainty, not damage severity.", severity_context="The existing severity label remains provisional.", human_review_required=True, review_reasons=["Confirm the finding in person."],
        )],
        technical_glossary=[],
        repair_estimates=[GeminiRepairEstimate(
            finding_id=0, damage_category="dent", possible_repair_approach="A localized repair and refinish scenario is possible; this is a hypothesis.", approach_is_hypothesis=True,
            estimate_range={"low": 100, "high": 200}, currency="INR",
            labor={"status": "provided", "amount": {"low": 100, "high": 200}, "basis": "Indicative labor scenario."},
            parts=zero, paint_materials=zero, other_charges=zero, tax=unknown_tax,
            pricing_basis="AI-generated indicative scenario; no live pricing provider is connected.", assumptions=["Component is not confirmed."], missing_information=["Workshop inspection"], uncertainty="Repair method is unconfirmed.", human_review_required=True, human_review_reasons=["Human review required."],
        )],
        vehicle_estimate_summary={"currency": "INR", "status": "requires_human_review", "low": None, "high": None, "reason": "Vehicle total is withheld pending review."},
        insurance_guidance=InsuranceGuidance(
            policy_category=context.policy_category, summary="Own-damage relevance depends on the active policy.", general_coverage_context="Check actual policy wording.",
            finding_guidance=[InsuranceFindingGuidance(finding_id=0, status="potentially_relevant", potential_coverage_category="Own-damage cover if applicable", conditions=["Cause and exclusions require review."], policy_questions=["Was own-damage cover active?"], missing_information=["Policy wording"])],
            add_on_notes=["Add-ons depend on the purchased endorsement."], policy_questions=["What deductible applies?"], source_references=[], disclaimer="Educational guidance only.",
        ),
        recommended_next_steps=["Have a qualified assessor inspect the panel."], missing_information=[], human_review_required=True,
        limitations=["The image cannot reveal hidden damage."], final_report_narrative="Use this report to prepare questions for a qualified assessor.",
    )


class TestGeminiValidation(unittest.TestCase):
    def test_provider_schema_removes_unsupported_json_schema_keywords(self):
        schema_text = json.dumps(_gemini_response_json_schema())
        self.assertNotIn("additionalProperties", schema_text)
        self.assertNotIn('"const"', schema_text)
        self.assertNotIn('"$ref"', schema_text)

    def test_valid_one_call_response_is_accepted_and_original_evidence_is_preserved(self):
        stages = sample_stages()
        context = AssessmentContext(policy_category="comprehensive_package", incident_cause="Parking impact")
        model = valid_gemini_response(context)
        fake = FakeClient(FakeResponse(model.model_dump_json()))
        service = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=fake)

        result = service.assess(stages, context)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(fake.models.calls), 1)
        self.assertEqual(result["assessment"]["repair_estimates"][0]["pricing_source"], "AI-generated indicative estimates")
        self.assertEqual(stages["severity_assessment"]["detections"][0]["preliminary_severity"], "minor")
        self.assertNotIn("secret", json.dumps(result))

    def test_invalid_negative_or_contradictory_output_is_rejected_without_retry(self):
        stages = sample_stages()
        context = AssessmentContext(policy_category="unknown")
        invalid = valid_gemini_response(context).model_dump(mode="json")
        invalid["repair_estimates"][0]["estimate_range"] = {"low": -1, "high": 2}
        fake = FakeClient(FakeResponse(json.dumps(invalid)))
        service = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=fake)

        result = service.assess(stages, context)

        self.assertEqual(result["status"], "invalid_response")
        self.assertEqual(len(fake.models.calls), 1)

        freeform = valid_gemini_response(context).model_copy(update={"summary": "A repair may cost ₹100."})
        freeform_client = FakeClient(FakeResponse(freeform.model_dump_json()))
        freeform_result = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=freeform_client).assess(stages, context)
        self.assertEqual(freeform_result["status"], "invalid_response")

    def test_disabled_and_timeout_paths_keep_original_results_available(self):
        stages = sample_stages()
        context = AssessmentContext()
        disabled = GeminiService(Settings(gemini_enabled=False), client=None).assess(stages, context)
        self.assertEqual(disabled["status"], "disabled")
        self.assertIn("fallback_insurance_guidance", disabled)

        missing_key = GeminiService(Settings(gemini_enabled=True, gemini_api_key=""), client=None).assess(stages, context)
        self.assertEqual(missing_key["status"], "unavailable")
        self.assertNotIn("api key", missing_key["message"].lower())

        timeout_client = FakeClient(error=httpx.ReadTimeout("timeout"))
        timed_out = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=timeout_client).assess(stages, context)
        self.assertEqual(timed_out["status"], "unavailable")
        self.assertIn("Original findings", timed_out["message"])

        rate_limited = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=FakeClient(error=errors.APIError(429, {}))).assess(stages, context)
        self.assertEqual(rate_limited["status"], "unavailable")
        self.assertIn("rate-limited", rate_limited["message"])

        auth_failure = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=FakeClient(error=errors.APIError(401, {}))).assess(stages, context)
        self.assertIn("authentication failed", auth_failure["message"])
        self.assertNotIn("secret", auth_failure["message"])

        provider_timeout = GeminiService(
            Settings(gemini_enabled=True, gemini_api_key="secret"),
            client=FakeClient(error=errors.APIError(504, {"error": {"message": "Deadline expired before operation could complete."}})),
        ).assess(stages, context)
        self.assertEqual(provider_timeout["status"], "unavailable")
        self.assertIn("timed out", provider_timeout["message"])
        self.assertIn("Original findings remain available", provider_timeout["message"])

    def test_policy_categories_have_explicit_educational_status(self):
        findings = [0]
        self.assertEqual(educational_guidance(AssessmentContext(policy_category="third_party_liability"), findings).finding_guidance[0].status, "not_covered_under_this_policy_type_in_the_usual_case")
        self.assertEqual(educational_guidance(AssessmentContext(policy_category="unknown"), findings).finding_guidance[0].status, "policy_review_required")


class TestExplicitGeminiCost(unittest.TestCase):
    @staticmethod
    def cost_response(ids=(0,)):
        return {
            "repair_groups": [{
                "group_id": f"scope-{min(ids)}", "finding_ids": list(ids),
                "scope_summary": "Visible damage repair scope",
                "observed_support": "The image shows a localized damaged area in the detector region.",
                "possible_repair_approach": "A provisional local repair scenario could be considered after inspection.",
                "approach_is_hypothesis": True,
                "parts": {"status": "not_applicable", "amount": None, "basis": "No part replacement is assumed."},
                "labor": {"status": "provided", "amount": {"low": 100, "high": 200}, "basis": "Indicative labor scenario."},
                "paint_materials": {"status": "not_applicable", "amount": None, "basis": "No paint operation is assumed."},
                "other_charges": {"status": "not_applicable", "amount": None, "basis": "None supported."},
                "tax": {"status": "unknown", "amount": None, "basis": "Tax is excluded."},
                "estimate_range": {"low": 100, "high": 200}, "unavailable_reason": None,
                "assumptions": ["Panel material is unknown."], "missing_information": ["Vehicle model."],
                "pricing_basis": "AI-generated indicative pre-tax scenario, not a verified price.",
                "professional_inspection_required": True,
            }],
            "assumptions": ["Pre-tax only; tax is excluded."],
        }

    def test_explicit_cost_uses_source_image_and_provisional_severity_does_not_hide_range(self):
        stages = sample_stages()
        fake = FakeClient(FakeResponse(json.dumps(self.cost_response())))
        service = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret", gemini_model="gemini-3.5-flash-lite"), client=fake)
        result = service.estimate_repair_cost(stages, AssessmentContext(vehicle_make="Tata", vehicle_model="Nexon"), b"current-image", "image/png")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["pricing_status"], "ai_estimate")
        self.assertFalse(result["verified_market_price"])
        self.assertEqual(result["vehicle_total"], {"low": 100.0, "high": 200.0})
        self.assertEqual(fake.models.calls[0]["model"], "gemini-3.5-flash-lite")
        self.assertEqual(fake.models.calls[0]["contents"][0].inline_data.data, b"current-image")
        self.assertEqual(fake.models.calls[0]["config"].thinking_config.thinking_level.value, "LOW")
        self.assertIsNone(fake.models.calls[0]["config"].temperature)
        self.assertIsNone(fake.models.calls[0]["config"].candidate_count)

    def test_overlapping_findings_receive_one_consolidated_estimate(self):
        stages = sample_stages()
        duplicate = json.loads(json.dumps(stages["severity_assessment"]["detections"][0]))
        duplicate["original_evidence"]["detection_id"] = 1
        stages["severity_assessment"]["detections"].append(duplicate)
        stages["severity_assessment"]["overlap_pairs"] = [{"detection_ids": [0, 1], "possible_duplicate_for_review": True, "human_review_required": True}]
        fake = FakeClient(FakeResponse(json.dumps(self.cost_response((0, 1)))))
        result = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=fake).estimate_repair_cost(stages, AssessmentContext(), b"image", "image/png")
        self.assertEqual(result["total_status"], "available")
        self.assertEqual(result["vehicle_total"], {"low": 100.0, "high": 200.0})
        self.assertIsNone(result["partial_subtotal"])
        self.assertEqual(result["pricing_status"], "ai_estimate")
        self.assertEqual(len(result["repair_groups"]), 1)
        self.assertEqual(result["repair_groups"][0]["finding_ids"], [0, 1])
        self.assertEqual(len(result["findings"]), 0)

    def test_holistic_ai_range_survives_unknown_itemized_components(self):
        payload = self.cost_response()
        line = payload["repair_groups"][0]
        line["parts"] = {"status": "unknown", "amount": None, "basis": "Image does not support a part price."}
        line["estimate_range"] = {"low": 1800, "high": 3600}
        line["assumptions"] = ["Broad cosmetic repair scenario; exact vehicle and workshop scope are unknown."]
        fake = FakeClient(FakeResponse(json.dumps(payload)))
        result = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=fake).estimate_repair_cost(sample_stages(), AssessmentContext(), b"image", "image/png")
        self.assertEqual(result["pricing_status"], "ai_estimate")
        self.assertEqual(result["repair_groups"][0]["estimate_range"], {"low": 1800.0, "high": 3600.0})
        self.assertIsNone(result["repair_groups"][0]["parts"]["amount"])
        self.assertEqual(result["vehicle_total"], {"low": 1800.0, "high": 3600.0})

    def test_missing_range_stays_null_without_example_fallback(self):
        stages = sample_stages()
        payload = self.cost_response()
        line = payload["repair_groups"][0]
        line["labor"] = {"status": "unknown", "amount": None, "basis": "Labor scope cannot be inferred."}
        line["estimate_range"] = None
        line["unavailable_reason"] = "Repair operation and labor time are not clear from the image."
        fake = FakeClient(FakeResponse(json.dumps(payload)))
        result = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=fake).estimate_repair_cost(stages, AssessmentContext(), b"image", "image/png")
        self.assertIsNone(result["repair_groups"][0]["estimate_range"])
        self.assertEqual(result["pricing_status"], "estimate_unavailable")
        self.assertIsNone(result["vehicle_total"])

    def test_negative_component_amount_is_rejected_as_invalid_response(self):
        payload = self.cost_response()
        payload["repair_groups"][0]["labor"]["amount"]["low"] = -5
        fake = FakeClient(FakeResponse(json.dumps(payload)))
        result = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=fake).estimate_repair_cost(sample_stages(), AssessmentContext(), b"image", "image/png")
        self.assertEqual(result["status"], "invalid_response")
        self.assertEqual(result["pricing_status"], "estimate_unavailable")
        self.assertEqual(result["repair_groups"], [])


class TestExplicitGeminiSummary(unittest.TestCase):
    def test_summary_is_structured_and_only_generated_when_called(self):
        context = AssessmentContext(policy_category="unknown")
        combined = valid_gemini_response(context)
        response = {
            "summary": combined.summary,
            "findings_explanations": [item.model_dump(mode="json") for item in combined.findings_explanations],
            "technical_glossary": [],
            "insurance_guidance": combined.insurance_guidance.model_dump(mode="json"),
            "recommended_next_steps": combined.recommended_next_steps,
            "limitations": combined.limitations,
            "human_review_required": True,
        }
        fake = FakeClient(FakeResponse(json.dumps(response)))
        service = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=fake)
        self.assertEqual(len(fake.models.calls), 0)
        result = service.generate_summary(sample_stages(), context)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"]["findings_explanations"][0]["finding_id"], 0)
        self.assertEqual(len(fake.models.calls), 1)

    def test_explicit_diagnostic_classifies_provider_failures_without_details(self):
        service = GeminiService(Settings(gemini_enabled=True, gemini_api_key="secret"), client=FakeClient(error=errors.APIError(504, {"error": {"message": "private provider detail"}})))
        result = service.diagnostic()
        self.assertEqual(result["category"], "timeout")
        self.assertNotIn("private provider detail", result["message"])
        self.assertNotIn("secret", json.dumps(result))


class TestArtifactsAndPdf(unittest.TestCase):
    def test_artifact_urls_are_fixed_and_pdf_is_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.png"
            ok, encoded = cv2.imencode(".png", __import__("numpy").zeros((12, 12, 3), dtype="uint8"))
            self.assertTrue(ok)
            source.write_bytes(encoded.tobytes())
            store = AssessmentArtifactStore(root / "artifacts", ttl_seconds=3600)
            assessment_id = "12345678-1234-5678-1234-567812345678"
            payload = {"assessment_id": assessment_id, "source_image": "source.png", **sample_stages()}
            record = store.save(assessment_id, payload, source, "image/png", sample_stages()["detection_report"])
            self.assertTrue(store.path_for_annotated(assessment_id).is_file())
            self.assertEqual(record["artifacts"]["annotated_preview_url"], f"/api/v1/assessments/{assessment_id}/annotated-preview")
            with self.assertRaises(ArtifactNotFoundError):
                store.load("../etc")

            from backend.app.pdf_report import generate_pdf
            pdf = generate_pdf(record, *store.path_for_source(assessment_id)[:1], annotated_path=store.path_for_annotated(assessment_id))
            self.assertTrue(pdf.startswith(b"%PDF"))
            self.assertGreaterEqual(len(PdfReader(__import__("io").BytesIO(pdf)).pages), 1)
            empty_text = "\n".join(page.extract_text() or "" for page in PdfReader(__import__("io").BytesIO(pdf)).pages)
            self.assertIn("AI-generated summary: not completed", empty_text)
            updated = store.update(assessment_id, {
                "ai_summary": {"status": "completed", "summary": {
                    "summary": "Latest AI summary content.", "technical_glossary": [],
                    "recommended_next_steps": ["Inspect the affected area."], "limitations": ["Image only."],
                }},
                "ai_cost_estimate": {"status": "completed", "pricing_status": "ai_estimate",
                    "total_status": "available", "vehicle_total": {"low": 1200, "high": 2400},
                    "partial_subtotal": None, "total_reason": "Conditional line total.", "findings": [], "assumptions": [],
                    "result_schema_version": 2,
                    "repair_groups": [{"group_id": "scope-0", "finding_ids": [0, 1], "scope_summary": "Shared exterior repair", "estimate_range": {"low": 1200, "high": 2400}, "parts": {"status": "provided", "amount": {"low": 500, "high": 900}, "basis": "Indicative."}, "labor": {"status": "provided", "amount": {"low": 700, "high": 1500}, "basis": "Indicative."}, "paint_materials": {"status": "unknown", "amount": None, "basis": "Not itemized."}, "other_charges": {"status": "not_applicable", "amount": None, "basis": "Excluded."}, "tax": {"status": "unknown", "amount": None, "basis": "Excluded."}, "observed_support": "A shared visible damage area.", "possible_repair_approach": "Provisional repair scope.", "pricing_basis": "AI generated indicative estimate."}],
                    "cost_breakdown": {"parts": {"status": "provided", "amount": {"low": 500, "high": 900}, "basis": "Combined scope."}, "labor": {"status": "provided", "amount": {"low": 700, "high": 1500}, "basis": "Combined scope."}},
                },
            })
            latest_pdf = generate_pdf(updated, store.path_for_source(assessment_id)[0], store.path_for_annotated(assessment_id))
            latest_text = "\n".join(page.extract_text() or "" for page in PdfReader(__import__("io").BytesIO(latest_pdf)).pages)
            self.assertIn("Latest AI summary content.", latest_text)
            self.assertIn("AI-generated indicative INR estimates", latest_text)
            self.assertIn("1,200", latest_text)
            self.assertIn("Shared exterior repair", latest_text)
            self.assertIn("Itemized assessment", latest_text)
            malformed_pdf = generate_pdf({"assessment_id": "malformed"})
            self.assertTrue(malformed_pdf.startswith(b"%PDF"))

    def test_artifact_routes_serve_only_generated_assessment_files(self):
        def load_model(_path):
            return object()

        def load_pricing(_path):
            return load_pricing_config(DEFAULT_PRICING_PATH)

        pipeline = AssessmentPipeline(model_loader=load_model, pricing_loader=load_pricing)
        with tempfile.TemporaryDirectory() as temp:
            store = AssessmentArtifactStore(Path(temp) / "artifacts")
            app = create_app(
                pipeline=pipeline,
                artifact_store=store,
                gemini_service=GeminiService(Settings(gemini_enabled=False)),
            )
            detection = {
                "image_path": "upload.png", "image_width": 12, "image_height": 12,
                "model_name": "mock-model.pt", "model_path": "private/model.pt", "inference_device": "cpu",
                "image_size": 640, "confidence_threshold": 0.25, "coordinate_system": "pixels",
                "detection_count": 0, "detections": [], "masks_available": False,
                "overlap_diagnostics": {"overlapping_pairs": []}, "timestamp_utc": "2026-01-01T00:00:00+00:00",
            }
            with patch("backend.app.pipeline.damage_detection.analyze_image", return_value=detection):
                with TestClient(app) as client:
                    response = client.post("/api/v1/assessments", files={"file": ("car.png", b"\x89PNG\r\n\x1a\n", "image/png")})
                    # Use a real image because OpenCV validation precedes storage.
                    if response.status_code == 422:
                        import numpy as np
                        ok, encoded = cv2.imencode(".png", np.zeros((12, 12, 3), dtype="uint8"))
                        self.assertTrue(ok)
                        response = client.post("/api/v1/assessments", files={"file": ("car.png", encoded.tobytes(), "image/png")})
                    self.assertEqual(response.status_code, 200, response.text)
                    payload = response.json()
                    assessment_id = payload["assessment_id"]
                    annotated = client.get(f"/api/v1/assessments/{assessment_id}/annotated-preview")
                    pdf = client.get(f"/api/v1/assessments/{assessment_id}/pdf")
                    traversal = client.get("/api/v1/assessments/not-a-uuid/annotated-preview")
            self.assertEqual(annotated.status_code, 200)
            self.assertEqual(annotated.headers["content-type"], "image/jpeg")
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.content.startswith(b"%PDF"))
            self.assertEqual(traversal.status_code, 404)
