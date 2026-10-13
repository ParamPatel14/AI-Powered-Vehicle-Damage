# Veyra vehicle damage assessment

Veyra combines a YOLO vehicle-damage detector and segmentation model with
provisional severity review, an optional two-step Gemini assessment, and a
React report interface. Detection works without Gemini. AI repair prices are
indicative only and are never presented as verified workshop pricing.

## Project layout

```text
backend/     FastAPI routes, schemas, assessment artifacts, Gemini and PDF
frontend/    React, TypeScript, Tailwind and Vite client
ml/src/      Detection, severity, legacy illustrative estimator and CLI tools
ml/tests/    Model-independent ML unit tests
ml/weights/  Locally downloaded checkpoints (not committed)
pricing/     Legacy illustrative rate-card configuration
```

Generated reports, uploaded images, local credentials, dependencies, and model
checkpoints are excluded from Git. The checked-in tests use generated image
fixtures and do not need the optional sample photos.

## Requirements

- Windows PowerShell (commands below), Python 3.11, and Node.js 18 or newer.
- Internet access for package and checkpoint installation.
- A Gemini API key only if you want to use the optional AI summary and cost
  actions. Detection does not require a Gemini key.

## Install

From the project root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m ml.src.download_models primary
Copy-Item backend\.env.example backend\.env
Set-Location frontend
npm ci
```

The first checkpoint download comes from Hugging Face. See
[ml/weights/README.md](ml/weights/README.md) for upstream sources and model
terms. Keep the downloaded `.pt` files local; they are not part of this source
repository.

## Configure Gemini (optional)

Edit `backend/.env` and set `GEMINI_API_KEY` and
`GEMINI_ASSESSMENT_ENABLED=true`. The default model is `gemini-2.5-flash`.
Credentials stay on the backend; never put them in `frontend/.env` or a
`VITE_*` variable. Gemini calls happen only after the user requests an AI
summary or repair-cost assessment.

## Run

Start the backend in one terminal from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1
```

Open <http://127.0.0.1:5173>. Upload an image and run **Analyze Vehicle**;
then request **Generate AI Summary** or **Calculate Repair Cost**. The PDF
uses the latest saved sections. The backend API is documented at
<http://127.0.0.1:8000/docs>.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s ml\tests -v
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
Set-Location frontend
npm run typecheck
npm run lint
npm test -- --run
npm run build
```

The backend test suite mocks Gemini. To verify real provider access, use the
explicit `POST /api/v1/gemini/diagnostic` endpoint after configuring the
backend key; normal health checks and image uploads do not call Gemini.

## Assessment API

- `POST /api/v1/assessments` — create a detection-only assessment.
- `GET /api/v1/assessments/{assessment_id}` — retrieve its latest saved result.
- `POST /api/v1/assessments/{assessment_id}/ai-summary` — explicitly request
  the AI narrative and insurance guidance.
- `POST /api/v1/assessments/{assessment_id}/repair-cost` — explicitly request a
  structured INR estimate for the existing evidence.
- `GET /api/v1/assessments/{assessment_id}/pdf` — generate the latest PDF.

Generated artifacts use UUID-based retrieval and bounded retention. See
[backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md)
for component notes.
