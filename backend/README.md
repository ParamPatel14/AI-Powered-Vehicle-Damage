# FastAPI backend

The backend validates image uploads, runs the existing YOLO detector and
provisional severity pipeline, stores bounded assessment artifacts, generates
PDF reports, and provides explicit Gemini summary and repair-cost endpoints.
The API key is read from the backend environment only.

## Local setup

Follow the root [README](../README.md) to install Python dependencies, download
the primary checkpoint, and run the frontend. Copy `backend/.env.example` to
`backend/.env` for local settings. Gemini is optional; detection stays
available when it is disabled or its key is absent.

Start the service from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Open the API schema at <http://127.0.0.1:8000/docs>.

## Routes

- `GET /health`
- `POST /api/v1/assessments`
- `GET /api/v1/assessments/{assessment_id}`
- `POST /api/v1/assessments/{assessment_id}/ai-summary`
- `POST /api/v1/assessments/{assessment_id}/ai-assessment` (compatibility alias)
- `POST /api/v1/assessments/{assessment_id}/repair-cost`
- `POST /api/v1/gemini/diagnostic` (explicit live check)
- `GET /api/v1/assessments/{assessment_id}/{source-image|annotated-preview|pdf}`

Image analysis does not request Gemini. Summary and cost actions reuse the
stored assessment and image. PDF generation reads the latest saved structured
results and reports incomplete sections as incomplete.

Run backend and ML tests from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
.\.venv\Scripts\python.exe -m unittest discover -s ml\tests -v
```
