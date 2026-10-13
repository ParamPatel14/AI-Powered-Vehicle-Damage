"""Synchronous orchestration of the existing vehicle-assessment stages."""

import threading
from pathlib import Path

from ml.src import damage_detection, repair_cost_estimator, severity_assessment


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "ml" / "weights" / "cardd-yolov8s-v2.pt"
DEFAULT_PRICING_PATH = (
    PROJECT_ROOT / "pricing" / "illustrative_repair_pricing.json"
)


class PipelineNotReadyError(RuntimeError):
    """Raised if an assessment is requested before dependencies are ready."""


class AssessmentPipeline:
    """Load shared resources once and reuse existing ML/report functions."""

    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        pricing_path: str | Path = DEFAULT_PRICING_PATH,
        model_loader=None,
        pricing_loader=None,
    ):
        self.model_path = Path(model_path)
        self.pricing_path = Path(pricing_path)
        self._model_loader = model_loader or damage_detection.get_model
        self._pricing_loader = pricing_loader or repair_cost_estimator.load_pricing_config
        self.model = None
        self.pricing = None
        self.model_error_code = None
        self.pricing_error_code = None
        self._initialized = False
        self._initialization_lock = threading.Lock()
        # YOLO/CUDA inference is serialized to avoid unsafe concurrent access.
        self._inference_lock = threading.Lock()

    @property
    def ready(self):
        return self.model is not None and self.pricing is not None

    def initialize(self):
        """Attempt both loads once; retain safe status codes without paths."""
        with self._initialization_lock:
            if self._initialized:
                return
            try:
                self.model = self._model_loader(self.model_path)
            except Exception as exc:
                self.model = None
                self.model_error_code = (
                    "model_file_missing" if isinstance(exc, FileNotFoundError)
                    else "model_load_failed"
                )
            try:
                self.pricing = self._pricing_loader(self.pricing_path)
            except Exception as exc:
                self.pricing = None
                self.pricing_error_code = (
                    "pricing_file_missing" if isinstance(exc, FileNotFoundError)
                    else "pricing_configuration_invalid"
                )
            self._initialized = True

    def health(self):
        self.initialize()
        return {
            "api": "running",
            "ready": self.ready,
            "model": {
                "available": self.model is not None,
                "error": self.model_error_code,
            },
            "pricing_configuration": {
                "available": self.pricing is not None,
                "error": self.pricing_error_code,
            },
        }

    def assess(self, image_path: str | Path, source_image_name: str):
        """Run detection, severity and cost stages without CLI subprocesses."""
        self.initialize()
        if not self.ready:
            raise PipelineNotReadyError("Model or pricing configuration is unavailable.")

        with self._inference_lock:
            detection_report = damage_detection.analyze_image(
                image_path,
                model_path=self.model_path,
                model=self.model,
            )
        # Avoid leaking an ephemeral path or local model path through the API.
        detection_report["image_path"] = source_image_name
        detection_report.pop("model_path", None)

        severity_report = severity_assessment.build_assessment_report(detection_report)
        repair_report = repair_cost_estimator.estimate_severity_report(
            severity_report,
            self.pricing,
        )
        return {
            "detection_report": detection_report,
            "severity_assessment": severity_report,
            "repair_cost_estimate": repair_report,
        }
