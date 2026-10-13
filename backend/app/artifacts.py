"""Safe, bounded storage for completed assessment artifacts.

Artifacts are addressed only by generated UUIDs and fixed filenames.  No
client-supplied path is ever resolved or returned.
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ml.src.damage_detection import create_annotated_preview


class ArtifactNotFoundError(FileNotFoundError):
    pass


class AssessmentArtifactStore:
    def __init__(self, root: str | Path, ttl_seconds: int = 3600, max_records: int = 32, max_bytes: int = 64 * 1024 * 1024):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.cleanup()

    @staticmethod
    def validate_id(assessment_id: str) -> str:
        try:
            parsed = uuid.UUID(assessment_id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ArtifactNotFoundError("Assessment artifact not found") from exc
        canonical = str(parsed)
        if canonical != assessment_id:
            raise ArtifactNotFoundError("Assessment artifact not found")
        return canonical

    def _directory(self, assessment_id: str) -> Path:
        safe_id = self.validate_id(assessment_id)
        directory = (self.root / safe_id).resolve()
        if directory.parent != self.root:
            raise ArtifactNotFoundError("Assessment artifact not found")
        return directory

    def _fixed_path(self, assessment_id: str, name: str) -> Path:
        directory = self._directory(assessment_id)
        allowed = {
            "assessment.json": directory / "assessment.json",
            "source.jpg": directory / "source.jpg",
            "source.png": directory / "source.png",
            "annotated.jpg": directory / "annotated.jpg",
        }
        if name not in allowed:
            raise ArtifactNotFoundError("Assessment artifact not found")
        path = allowed[name].resolve()
        if path.parent != directory:
            raise ArtifactNotFoundError("Assessment artifact not found")
        return path

    def cleanup(self) -> None:
        now = time.time()
        directories = [path for path in self.root.iterdir() if path.is_dir() and self._is_uuid_dir(path.name)]
        for directory in directories:
            try:
                if now - directory.stat().st_mtime > self.ttl_seconds:
                    shutil.rmtree(directory, ignore_errors=True)
            except OSError:
                continue
        directories = [path for path in self.root.iterdir() if path.is_dir() and self._is_uuid_dir(path.name)]
        directories.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for directory in directories[self.max_records:]:
            shutil.rmtree(directory, ignore_errors=True)
        total = 0
        for directory in directories[: self.max_records]:
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    try:
                        total += file_path.stat().st_size
                    except OSError:
                        pass
        for directory in reversed(directories[: self.max_records]):
            if total <= self.max_bytes:
                break
            size = sum((file_path.stat().st_size for file_path in directory.rglob("*") if file_path.is_file()), 0)
            shutil.rmtree(directory, ignore_errors=True)
            total -= size

    @staticmethod
    def _is_uuid_dir(name: str) -> bool:
        try:
            return str(uuid.UUID(name)) == name
        except (ValueError, AttributeError):
            return False

    def urls(self, assessment_id: str, expires_at: str | None = None) -> dict:
        safe_id = self.validate_id(assessment_id)
        base = f"/api/v1/assessments/{safe_id}"
        return {
            "source_image_url": f"{base}/source-image",
            "annotated_preview_url": f"{base}/annotated-preview",
            "annotated_preview_available": True,
            "pdf_url": f"{base}/pdf",
            "expires_at": expires_at or "",
        }

    def save(self, assessment_id: str, payload: dict, source_path: str | Path, media_type: str, detection_report: dict) -> dict:
        safe_id = self.validate_id(assessment_id)
        directory = self._directory(safe_id)
        directory.mkdir(parents=True, exist_ok=False)
        source_suffix = ".jpg" if media_type == "image/jpeg" else ".png"
        source_target = directory / f"source{source_suffix}"
        annotated_target = directory / "annotated.jpg"
        try:
            shutil.copyfile(source_path, source_target)
            create_annotated_preview(source_path, detection_report, annotated_target)
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)).isoformat()
            record = {
                **payload,
                "artifacts": self.urls(safe_id, expires_at),
                "artifact_created_at": datetime.now(timezone.utc).isoformat(),
                "artifact_expires_at": expires_at,
            }
            (directory / "assessment.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        self.cleanup()
        return record

    def load(self, assessment_id: str) -> dict:
        directory = self._directory(assessment_id)
        try:
            if time.time() - directory.stat().st_mtime > self.ttl_seconds:
                shutil.rmtree(directory, ignore_errors=True)
                raise ArtifactNotFoundError("Assessment artifact not found")
        except OSError as exc:
            raise ArtifactNotFoundError("Assessment artifact not found") from exc
        path = self._fixed_path(assessment_id, "assessment.json")
        if not path.is_file():
            raise ArtifactNotFoundError("Assessment artifact not found")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactNotFoundError("Assessment artifact not found") from exc
        if not isinstance(record, dict) or record.get("assessment_id") != self.validate_id(assessment_id):
            raise ArtifactNotFoundError("Assessment artifact not found")
        return record

    def update(self, assessment_id: str, updates: dict) -> dict:
        """Persist structured assessment updates while retaining fixed artifacts."""
        record = self.load(assessment_id)
        record.update(updates)
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)).isoformat()
        record["artifact_expires_at"] = expires_at
        if isinstance(record.get("artifacts"), dict):
            record["artifacts"]["expires_at"] = expires_at
        path = self._fixed_path(assessment_id, "assessment.json")
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return record

    def path_for_source(self, assessment_id: str) -> tuple[Path, str]:
        for name, media_type in (("source.jpg", "image/jpeg"), ("source.png", "image/png")):
            path = self._fixed_path(assessment_id, name)
            if path.is_file():
                return path, media_type
        raise ArtifactNotFoundError("Assessment source image not found")

    def path_for_annotated(self, assessment_id: str) -> Path:
        path = self._fixed_path(assessment_id, "annotated.jpg")
        if not path.is_file():
            raise ArtifactNotFoundError("Annotated preview not found")
        return path
