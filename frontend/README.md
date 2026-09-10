# A+B Bundling Platform — Frontend

Next.js 15 App Router frontend for the A+B bundling operations workbench.

## Quick Start

```powershell
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

Before submitting a task, open [http://localhost:3000/settings/api](http://localhost:3000/settings/api) and enable at least one primary API provider. Settings are global and take effect for all subsequent hypothesis, judgment, and batch tasks. Saved keys remain masked in the UI.

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Start development server |
| `npm run build` | Production build |
| `npm run start` | Start production server |
| `npm run typecheck` | TypeScript type checking |
| `npm run test` | Run Vitest tests |
| `npm exec playwright test` | Run E2E tests |

## Project Structure

```
frontend/
  app/              Next.js App Router pages
    page.tsx        Workbench home
    layout.tsx      Root layout with providers
    jobs/[jobId]/   Job detail page
    history/        Job history page
    settings/api/   Global API provider settings
  components/
    layout/         App shell, sidebar, mobile nav
    workbench/      Hypothesis, judgment, batch forms
    jobs/           Job progress, error, result, artifacts
    history/        Job table and filters
  lib/
    api/            Typed API client (client.ts, jobs.ts, types.ts)
    schemas/        Zod validation schemas
  tests/            Vitest unit tests
  e2e/              Playwright E2E tests
```

## Environment

Copy `.env.example` to `.env.local`:

```powershell
Copy-Item .env.example .env.local
```

Required variables:

- `NEXT_PUBLIC_API_BASE` — Backend API URL (default: `http://localhost:8000`)

The API settings screen depends on the backend's localhost-only settings endpoints. Run the frontend and backend on the same computer; the backend intentionally rejects remote settings requests.
