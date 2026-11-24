# MyoControl Desktop

Electron, React and Carbon White for acquisition, local recordings and replay. Electron starts a Python child process over private JSON-lines stdio; it opens no localhost HTTP server. Cloud access runs outside the renderer. General model training belongs to the separate local workstation, not this runtime or the cloud.

## Develop

Requirements: Node.js 22.12+ and Python 3.12. From `desktop/`:

```sh
npm ci
npm run setup:runtime
npm run dev
```

Or build with `npm run build`, then `npm start`. Development Python is in `local-runtime/.venv`. `MYOCONTROL_BOOTSTRAP_PYTHON` selects the interpreter used to create it; `MYOCONTROL_PYTHON` overrides the development runtime executable. Packaged builds always use the bundled executable.

## User flow

1. Pair BITalino using the operating system. Enter the paired serial port (Windows `COM…`, macOS `/dev/…`). The default is **four analog channels A1–A4 at 1000 Hz**, ten seconds. More/fewer channels can be explicitly selected. Direct MAC connections require an additional Bluetooth backend; the bundled path uses Bluetooth serial.
2. Enter a participant pseudonym and choose research capture or a labelled calibration repetition. Start capture; samples are written to local SQLite chunks while the chart displays a bounded projection. A connection or sequence error stops the session and returns the hand to neutral. Reconnect explicitly.
3. Open Recordings to replay, export JSON, or queue a completed/stopped recording for synchronization. Imported signals retain their actual channel mapping; two channels are never padded to four.
4. For a device-free check, import the bundled **synthetic** demo and replay it from Recordings. It is not measured EMG and includes no trained model.
5. Import an exported `time-domain-4ch-v1` LDA JSON for compatible replay/live inference. Device inference additionally requires an explicitly matching ordered `channel_map` and `units` in the model contract. Legacy models without these declarations are limited to engineering replay. Models are parsed as JSON, never unpickled.
6. Sign in under Cloud sync with an operator account and the API base URL supplied by your administrator. The Cloud URL field starts empty; enter it manually (for example, `https://your-server.example/api`, or `http://localhost:8000` for local Compose). Include `/api` if your deployment uses that prefix. Select Sync on a recording. Upload parts contain at most 10,000 samples and retain original coordinates. Retries reuse the same operator-owned identity, including after signing in again. Conflicts remain visible and are not overwritten.

Credentials stay in Electron main/Python memory, encrypted with Electron safeStorage where a secure OS backend is available. There is no plaintext fallback. On systems without a secure backend, sign-in lasts for the session. A local application profile is a workspace shared by its OS user; use separate OS profiles when local recordings must be isolated.

## Build and verify

```sh
npm run build
npm run test:e2e
npm run build:runtime
npm exec electron-builder -- --win nsis --publish never
```

`npm run dist` rebuilds everything and produces the current platform's installer in `release/`. It bundles Python, NumPy, pyserial and BITalino SDK; end users do not install Python, Node or Docker. Native builds are required per OS/CPU. Windows installers are unsigned unless a signing certificate is configured. For macOS build on Apple Silicon using `npm exec electron-builder -- --mac --arm64 --publish never`; distribution signing/notarization requires the corresponding Apple credentials.

The Electron e2e check uses the real Python runtime and verifies four-channel defaults, offline import/replay/pause/stop, restart persistence and renderer isolation. Set `MYOCONTROL_TEST_EXECUTABLE` to a packaged executable to run the same check against bundled Python. Test profiles are created in the OS temporary directory.

From the repository root, run runtime tests with Python 3.12:

```sh
# Windows: set PYTHONPATH=local-runtime, then use local-runtime/.venv/Scripts/python.exe
PYTHONPATH=local-runtime local-runtime/.venv/bin/python -m unittest discover -s local-runtime/tests -v
```

## Implementation boundaries

This build captures labelled calibration repetitions and reports collected data; it does **not** adapt classifier parameters. LDA adaptation packages, SVM/MLP inference, model catalog download, terminal recognition-session report synchronization and the general workstation training worker remain separate work. The current sync API publishes recording parts; it does not publish models or experiment outcomes.

The SDK adapter has simulated-device tests. Actual BITalino Bluetooth acquisition and M1 Pro compatibility have not been verified with hardware. Electron portability alone does not establish SDK/OS compatibility. The SDK is pinned to `bitalino==1.2.6` and installed without its optional PyBluez dependency for the paired-serial path; retain upstream license information when distributing its bundled code.

## GitHub Actions builds and release notes

`Desktop builds` runs on pushes to `main`, pull requests and manual dispatch. Its native matrix targets Windows x64, macOS Apple Silicon arm64 and macOS Intel x64, including the matching Python runtime. Each platform runs runtime tests, formatting, the Electron e2e test and the same test against the packaged application. macOS builds must pass their native CI jobs before those packages are considered verified.

Builds are identified by the first 12 characters of the commit SHA; no manual version bump or version tag is required. The internal `package.json` version remains a technical Electron requirement. Successful push/manual build packages are downloadable from the run's **Artifacts** section for 14 days:

- Windows: `MyoControl-<SHA>-windows-x64-setup.exe` and an install-free ZIP. Extract the entire ZIP and run `MyoControl.exe`; user data belongs to the Windows user profile.
- macOS: `MyoControl-<SHA>-macos-<arm64|x64>.dmg` and `.zip`.

After all desktop matrix jobs succeed, a push to `main` automatically publishes a **GitHub Release** named `build-<SHA>` with the packages and GitHub-generated release notes. No manual publication is required. If a rerun finds a draft for that commit, it refreshes the assets and publishes it; already-published releases and their assets are preserved. PRs validate packages without uploading installers or creating releases. The workflow does not deploy the server.

Generated notes list merged pull requests, contributors and a comparison link, grouped using `.github/release.yml`. Use descriptive PR titles and labels (`enhancement`, `bug`, `dependencies`, etc.). Only the release job receives `contents: write`; other jobs use read access. No additional API secret or AI service is required.

Windows packages are unsigned; macOS packages are unsigned and not notarized, with Hardened Runtime disabled for these test distributions. Signing/notarization and real BITalino hardware testing remain separate work. Intel packages require a macOS version supported by the bundled Electron release; they do not target the original OS of a 2010 Mac mini.

Cloud URL is the API base, which may include `/api`, rather than the static website root. No deployment domain is built into the application. Persistent desktop file logging is not implemented.
