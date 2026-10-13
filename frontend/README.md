# Veyra frontend

The frontend is a Vite React/TypeScript application. It keeps the existing
warm off-white, charcoal and restrained-blue Veyra identity and communicates
with the FastAPI service through a typed API layer.

## Start

```powershell
Set-Location -LiteralPath 'C:\Projects\AI Powered Vehicle Damage\frontend'
npm install
npm run dev -- --host 127.0.0.1
```

During local development, Vite proxies `/health`, `/api` and artifact routes to
`http://127.0.0.1:8000`. For a deployed API origin, copy `.env.example` to a
local `.env` and set:

```dotenv
VITE_API_BASE_URL=https://your-backend.example
```

Never place `GEMINI_API_KEY` or any other provider credential in this file.
Gemini is called only by the backend.

## Checks

```powershell
npm run typecheck
npm run lint
npm test
npm run build
```

Assessment history is intentionally session-only because the backend does not
expose a history/list endpoint. Completed reports include server-controlled
source, detector-annotated preview and PDF URLs while their bounded artifacts
remain available.
