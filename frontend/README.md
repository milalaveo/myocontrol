# Myocontrol operator interface

React + TypeScript + Vite workspace for inspecting four-channel EMG, viewing a procedural hand, and using the existing local service APIs. All UI text is English.

## Run with Docker

Prepare the environment using the root README, then run from the repository root:

```powershell
docker compose --profile ui up -d --build
```

Open http://127.0.0.1:3000. The interactive demo works without signing in. Choose **Connect API** to use `GATEWAY_USERNAME` and `GATEWAY_PASSWORD` from your local `.env`. Passwords stay in React memory; they are not written to localStorage, sessionStorage, URLs or application logs. Reload/disconnect clears them. The UI and API proxy are loopback-only by default.

## Develop locally

Install Node.js 24 and start the backend Compose services. Then:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` to the gateway at http://127.0.0.1:8000. The production nginx container provides the same route. `npm run preview` only previews static assets and does not provide the development API proxy; use the Docker image to verify the complete production setup.

## Available flows

- Demo: illustrative four-channel signal, channel visibility, zoom, five manual hand poses, a scripted rest/fist sequence, playback pause/stop and signal JSON export. Demo waveforms are vertically offset and are explicitly labelled synthetic.
- Recordings: connect, browse database records with participant filtering and pagination, and load a recording's actual four-channel signal. The API does not currently expose electrode/channel provenance or source units; the interface leaves them unspecified rather than inferring DB2 channel positions.
- Experiments: submit a source-only LDA job with an existing frozen manifest and target participant UUID, inspect its status/results, or look up an existing run UUID. Polling is bounded to two minutes, with manual refresh afterwards.
- Replay: use a successful model run and selected recording to compute real predictions through Recognition. Play back the saved window labels on the hand. Unknown poses render neutral. Pause/stop and failed operations return the hand to neutral. This is recorded playback, not live inference.

The signal chart shows the full loaded excerpt; the timeline controls hand prediction playback. Chart points are bounded to about 3000 through display-only sampling for larger inputs; source samples and JSON export remain unchanged. The hand is a conceptual illustration, not an anatomical or clinical model. Reported processing p95 excludes buffering and rendering.

## Open-source libraries

| Library | Purpose | License |
| --- | --- | --- |
| [React](https://github.com/facebook/react) | Interface | MIT |
| [Vite](https://github.com/vitejs/vite) | Development and build | MIT |
| [uPlot](https://github.com/leeoniya/uPlot) | Canvas time-series charts, approximately 50 KB minified library | MIT |
| [Three.js](https://github.com/mrdoob/three.js) | WebGL hand geometry/rendering | MIT |
| [React Three Fiber](https://github.com/pmndrs/react-three-fiber) | React integration for Three.js | MIT |
| [Lucide](https://github.com/lucide-icons/lucide) | Icons | ISC |

The 3D renderer is loaded as a separate chunk. There are no external hand assets, textures, physics or animation engines. See [hand visualization](HAND_VISUALIZATION.md). Fonts currently load from Google Fonts with system fallbacks; the interface remains usable when that request is unavailable.

## Verification and remaining scope

`npm run build` checks TypeScript and creates production assets. `npm audit` checks package advisories; `package-lock.json` records the resolved versions. CI builds and audits the UI. The Data service has a paginated `GET /v1/recordings` endpoint; it reads its own schema via SQLAlchemy.

**TBD:** in-app dataset import, split/protocol editing, calibration workflows, live device acquisition, confusion-matrix visualization, durable run history browsing, production identities and end-to-end latency measurement. Actual DB2 channel selection is not determined by this interface. Real data require a compatible model; the five-excerpt ingestion pilot alone does not supply a trained model or frozen research split.
