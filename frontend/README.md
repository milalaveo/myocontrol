# Cloud research frontend

React + TypeScript + Vite portal for operator-owned experiment history, published models and evaluation results. The interface adapts to desktop, tablet and mobile widths. All UI text is English.

The cloud UI uses official `@carbon/react` components and `@carbon/icons-react`, with Carbon's White theme throughout. `src/styles.scss` uses Carbon spacing/type tokens for layout; forms, shell/navigation, buttons, tables, pagination, notifications and structured details use Carbon components. IBM Plex fonts are bundled locally by Vite. `src/local-preview/styles.css` is retained with the earlier local preview styling and is not loaded by the cloud entry point.

## Start

Configure `IDENTITY_DB_PASSWORD` and `CLOUD_INTERNAL_KEY` in addition to the existing Compose variables. Create an operator as described in [gateway setup](../gateway/README.md), then run:

```powershell
docker compose --profile ui up -d --build
```

Open http://127.0.0.1:3000 and sign in with the operator email/password. This account is separate from the development gateway Basic credentials. The browser receives an HttpOnly SameSite=Strict cookie valid for eight hours; JavaScript keeps only the operator summary. Refresh restores the account through `GET /auth/v1/me` before protected routes render. A temporary server outage offers retry without discarding the cookie. Sign out revokes the server session and clears the cookie. Neither passwords nor tokens are written to localStorage/sessionStorage. Set `WEB_SESSION_SECURE=true` for HTTPS deployments; HTTP localhost development uses a non-Secure cookie.

For local development, run `npm ci` and `npm run dev` in this directory. Vite forwards `/api` to http://127.0.0.1:8000. The production nginx container provides the same proxy. `npm run preview` has no API proxy.

## Implemented

- Recordings: owned desktop uploads, real channel mapping/sample rate/length, source labels, pagination and JSON signal download. Long recordings appear as uploaded parts; an upload is not an experiment/model/evaluation.

- Experiments: owner-filtered run history, execution location, status and reproducibility details.
- Models: published versions, family/condition and package metadata.
- Results: accuracy, macro F1, rest false activation (N/A remains N/A), raw evaluation detail including confusion counts.
- Protected routes and direct record links, browser history, URL-based pagination, manual refresh, loading/error/empty states, centralized expired-session handling and cancellation of outdated requests.
- Field-level sign-in validation, disabled duplicate submissions, cleared rejected passwords and global render recovery through ErrorBoundary.

These screens read the new generic registry. Old synthetic `source_lda_runs` are not automatically migrated into it. An empty account has empty lists; the portal does not invent models or scientific results. General training remains on the local workstation. Submission/remote worker execution/publication and package downloads are still to be implemented, so no new training button is shown.

## Local desktop scope

Live recognition, acquisition, calibration/adaptation, hand control and replay belong to Electron. `src/local-preview/SignalChart.tsx`, `src/local-preview/HandScene.tsx`, their dependencies and shared types remain in source for reuse. The cloud entry point does not import them, generate demo signals or execute recognition. The packaged Electron application is documented in [desktop](../desktop/README.md).

## Frontend assessment requirements

| Requirement                                        | Evidence                                                                                              |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Modern SPA and bundler                             | React + TypeScript + Vite; `npm run build`.                                                           |
| Architecture, user flows and stack justification   | [Frontend architecture](ARCHITECTURE.md), including diagrams, route mapping and technology decisions. |
| Components, pages and API services                 | `src/components/`, `src/pages/`, `src/services/`; orchestration in hooks/context.                     |
| Form validation, global error handling and loading | `LoginForm`, `services/http`, `ErrorBoundary`, `AuthContext` and `useRegistry`.                       |
| Unit tests for at least three key components       | `LoginForm`, `RegistryTable`, `RegistryDetails` and `ErrorBoundary`; additional HTTP-client tests.    |
| One or two e2e scenarios                           | Two Playwright scenarios, each run on desktop, tablet and mobile.                                     |

## Verification

`npm run build` checks TypeScript and produces assets; CI builds and audits the frontend. Gateway integration tests exercise actual PostgreSQL registry queries and account isolation. IBM Plex is served from the same application, with system fallbacks. Data/protocol management, experiment submission and further metric visualizations remain separate work.

Run from `frontend/` using Node.js 24:

```powershell
npm ci
npm run format:check
npm run test:unit
npm run build
npx playwright install chromium
npm run test:e2e
```

There are 17 unit tests across components, browser session restoration and the HTTP client. The two e2e scenarios each run at 1440 px, 768 px and 390 px (six executions):

1. Invalid/valid login, paginated experiments, details and browser Back, page-reload session restoration, model/results navigation, synced recordings and JSON download, N/A metrics and logout.
2. Protected deep-link restoration, API-error retry, empty registry, expired session and reauthentication.

Playwright starts the production preview server on port 4173 and intercepts `/api` with isolated synthetic fixtures; it does not require Docker or real credentials and does not write to the database. These are frontend browser tests with a controlled API boundary. Backend/database integration is verified separately by gateway tests. The normal Docker app uses the actual API; no fixture data are bundled into production.

`npm run format` applies the shared formatting rules. CI checks formatting, runs unit tests, builds, installs Chromium, runs all e2e viewport projects and audits dependencies. Failure reports/traces are uploaded as an Actions artifact. Local generated reports are ignored by Git.
