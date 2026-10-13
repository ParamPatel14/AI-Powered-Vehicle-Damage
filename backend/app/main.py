"""FastAPI entry point for Veyra vehicle damage assessments."""

import json
import logging
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import ValidationError

from backend.app.artifacts import AssessmentArtifactStore, ArtifactNotFoundError
from backend.app.gemini import GeminiService
from backend.app.pdf_report import generate_pdf
from backend.app.pipeline import AssessmentPipeline, PipelineNotReadyError
from backend.app.schemas import AssessmentContext
from backend.app.settings import Settings

LOGGER = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
UPLOAD_CHUNK_BYTES = 1024 * 1024
MAX_CONTEXT_BYTES = 16 * 1024
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = PROJECT_ROOT / "backend" / ".uploads" / "assessments"


def _sniff_mime_type(header: bytes):
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


def _safe_display_filename(filename: str | None):
    # The supplied name is display metadata only. It is never used as a path.
    normalized = (filename or "uploaded-image").replace("\\", "/")
    basename = Path(normalized).name
    if basename in {"", ".", ".."}:
        return "uploaded-image"
    return basename[:255]


def _parse_context(raw: str | None) -> AssessmentContext:
    raw = raw or "{}"
    if len(raw.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise HTTPException(status_code=413, detail="Assessment context is too large.")
    try:
        value = json.loads(raw)
        return AssessmentContext.model_validate(value)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Assessment context is invalid.") from exc


def create_app(
    pipeline: AssessmentPipeline | None = None,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
    gemini_service: GeminiService | None = None,
    artifact_store: AssessmentArtifactStore | None = None,
):
    assessment_pipeline = pipeline or AssessmentPipeline()
    settings = Settings.from_env()
    ai_service = gemini_service or GeminiService(settings)
    store = artifact_store or AssessmentArtifactStore(
        ARTIFACT_ROOT,
        ttl_seconds=settings.artifact_ttl_seconds,
        max_records=settings.artifact_max_records,
        max_bytes=settings.artifact_max_bytes,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        assessment_pipeline.initialize()
        store.cleanup()
        yield
        ai_service.close()

    app = FastAPI(
        title="Veyra Vehicle Damage Assessment API",
        description=(
            "Image-based damage detection and provisional severity, with separate explicit "
            "Gemini summary and image-specific cost actions. Outputs require review."
        ),
        version="2.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )
    app.state.assessment_pipeline = assessment_pipeline
    app.state.max_upload_bytes = max_upload_bytes
    app.state.gemini_service = ai_service
    app.state.assessment_artifact_store = store
    active_assessments: set[str] = set()
    active_assessments_lock = threading.Lock()

    @app.get("/health", tags=["health"])
    def health():
        status = assessment_pipeline.health()
        status["gemini"] = ai_service.health()
        status_code = 200 if status["ready"] else 503
        return JSONResponse(status_code=status_code, content=status)

    @app.post("/api/v1/assessments", tags=["assessments"])
    def create_assessment(
        file: UploadFile = File(...),
        assessment_context: str = Form("{}"),
    ):
        if not assessment_pipeline.health()["ready"]:
            raise HTTPException(
                status_code=503,
                detail="Assessment service is unavailable because a required component did not load.",
            )
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported image type. Upload a JPEG or PNG image.")
        context = _parse_context(assessment_context)
        source_name = _safe_display_filename(file.filename)
        assessment_id = str(uuid.uuid4())
        try:
            with tempfile.TemporaryDirectory(prefix="vehicle_assessment_") as temporary_dir:
                # Ultralytics uses the source suffix to identify image inputs.
                temporary_suffix = ".jpg" if file.content_type == "image/jpeg" else ".png"
                temporary_path = Path(temporary_dir) / f"upload{temporary_suffix}"
                total_bytes = 0
                first_bytes = b""
                with temporary_path.open("wb") as temporary_file:
                    while True:
                        chunk = file.file.read(UPLOAD_CHUNK_BYTES)
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if total_bytes > app.state.max_upload_bytes:
                            raise HTTPException(status_code=413, detail="Uploaded image exceeds the configured size limit.")
                        if not first_bytes:
                            first_bytes = chunk[:16]
                        temporary_file.write(chunk)

                sniffed_type = _sniff_mime_type(first_bytes)
                if sniffed_type is None or sniffed_type != file.content_type:
                    raise HTTPException(status_code=415, detail="File content does not match a supported JPEG or PNG image.")
                if total_bytes == 0:
                    raise HTTPException(status_code=422, detail="Uploaded image is empty.")

                try:
                    image = cv2.imread(str(temporary_path), cv2.IMREAD_COLOR)
                except cv2.error as exc:
                    raise HTTPException(status_code=422, detail="Image data is malformed or unreadable.") from exc
                if image is None:
                    raise HTTPException(status_code=422, detail="Image data is malformed or unreadable.")
                height, width = image.shape[:2]
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise HTTPException(status_code=413, detail="Image dimensions exceed the supported limit.")
                del image

                try:
                    stages = assessment_pipeline.assess(temporary_path, source_name)
                except PipelineNotReadyError as exc:
                    raise HTTPException(status_code=503, detail="Assessment service is unavailable.") from exc
                except Exception as exc:
                    LOGGER.error("Assessment pipeline failed")
                    raise HTTPException(status_code=500, detail="Assessment pipeline failed. Check service logs and component health.") from exc

                severity_summary = stages["severity_assessment"].get("summary", {})
                repair_summary = stages["repair_cost_estimate"].get("summary", {})
                has_review = bool(severity_summary.get("human_review_count", 0)) or bool(
                    repair_summary.get("vehicle_total", {}).get("human_review_required", True)
                )
                payload = {
                    "assessment_id": assessment_id,
                    "status": "completed_with_human_review" if has_review else "completed",
                    "source_image": source_name,
                    "assessment_context": context.model_dump(mode="json"),
                    "preliminary": True,
                    "gemini_status": ai_service.health(),
                    **stages,
                }
                try:
                    return store.save(
                        assessment_id,
                        payload,
                        temporary_path,
                        file.content_type,
                        stages["detection_report"],
                    )
                except Exception as exc:
                    LOGGER.error("Assessment artifact creation failed")
                    raise HTTPException(status_code=500, detail="Assessment completed but its report artifacts could not be created.") from exc
        finally:
            file.file.close()

    @app.get("/api/v1/assessments/{assessment_id}", tags=["assessments"])
    def get_assessment(assessment_id: str):
        try:
            return store.load(assessment_id)
        except ArtifactNotFoundError:
            artifact_error()

    def generate_gemini_for_assessment(assessment_id: str, action: str):
        try:
            record = store.load(assessment_id)
            result_key = "ai_summary" if action == "summary" else "ai_cost_estimate"
            current = record.get(result_key)
            if isinstance(current, dict) and current.get("status") == "completed" and (
                action == "summary"
                or (current.get("result_schema_version") == 2 and current.get("pricing_status") == "ai_estimate")
            ):
                return record
            lock_key = f"{assessment_id}:{action}"
            with active_assessments_lock:
                if lock_key in active_assessments:
                    raise HTTPException(status_code=409, detail=f"Gemini {action} is already running for this assessment.")
                active_assessments.add(lock_key)
            try:
                stages = {key: record[key] for key in ("detection_report", "severity_assessment", "repair_cost_estimate")}
                context = AssessmentContext.model_validate(record.get("assessment_context", {}))
                if action == "summary":
                    result = ai_service.generate_summary(stages, context)
                else:
                    source_path, mime_type = store.path_for_source(assessment_id)
                    result = ai_service.estimate_repair_cost(stages, context, source_path.read_bytes(), mime_type)
                # Save failures too, so the UI/PDF can show the latest status and retry.
                result = {**result, "request_action": action}
                return store.update(assessment_id, {result_key: result})
            finally:
                with active_assessments_lock:
                    active_assessments.discard(lock_key)
        except ArtifactNotFoundError:
            artifact_error()

    @app.post("/api/v1/assessments/{assessment_id}/ai-summary", tags=["assessments"])
    def ai_summary(assessment_id: str):
        return generate_gemini_for_assessment(assessment_id, "summary")

    @app.post("/api/v1/assessments/{assessment_id}/ai-assessment", tags=["assessments"])
    def ai_assessment(assessment_id: str):
        # Compatibility route retained; it now generates narrative only.
        return generate_gemini_for_assessment(assessment_id, "summary")

    @app.post("/api/v1/assessments/{assessment_id}/repair-cost", tags=["assessments"])
    def repair_cost(assessment_id: str):
        return generate_gemini_for_assessment(assessment_id, "cost")

    @app.post("/api/v1/gemini/diagnostic", tags=["health"])
    def gemini_diagnostic():
        # Explicit live check only. /health never sends provider traffic.
        return ai_service.diagnostic()

    def artifact_error():
        raise HTTPException(status_code=404, detail="Assessment artifact not found or has expired.")

    @app.get("/api/v1/assessments/{assessment_id}/source-image", tags=["artifacts"])
    def source_image(assessment_id: str):
        try:
            store.load(assessment_id)
            path, media_type = store.path_for_source(assessment_id)
            return FileResponse(path, media_type=media_type, filename="vehicle-source.jpg" if media_type == "image/jpeg" else "vehicle-source.png")
        except ArtifactNotFoundError:
            artifact_error()

    @app.get("/api/v1/assessments/{assessment_id}/annotated-preview", tags=["artifacts"])
    def annotated_preview(assessment_id: str):
        try:
            store.load(assessment_id)
            path = store.path_for_annotated(assessment_id)
            return FileResponse(path, media_type="image/jpeg", filename="veyra-annotated-preview.jpg")
        except ArtifactNotFoundError:
            artifact_error()

    @app.get("/api/v1/assessments/{assessment_id}/pdf", tags=["artifacts"])
    def assessment_pdf(assessment_id: str):
        try:
            record = store.load(assessment_id)
            source_path, _ = store.path_for_source(assessment_id)
            annotated_path = store.path_for_annotated(assessment_id)
            content = generate_pdf(record, source_path, annotated_path)
            return Response(
                content=content,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="veyra-assessment-{assessment_id}.pdf"'},
            )
        except ArtifactNotFoundError:
            artifact_error()
        except Exception as exc:
            LOGGER.error("PDF generation failed")
            raise HTTPException(status_code=500, detail="The assessment PDF could not be generated.") from exc

    return app


app = create_app()
