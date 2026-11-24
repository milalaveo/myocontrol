# MyoControl Desktop

Electron, React and Carbon White for acquisition, local recordings and replay. Electron starts a Python child process over private JSON-lines stdio; it opens no localhost HTTP server. Cloud access runs outside the renderer. General model training belongs to the separate local workstation, not this runtime or the cloud.

## Develop

Requirements: Node.js 22.12+ and Python 3.12. From `desktop/`:

```sh
npm ci
npm run setup:runtime
npm run dev
```

`npm run dev` runs Vite HMR for React/CSS and watches Electron main/preload and Python source. Successful main/preload builds and Python changes restart Electron only after capture/replay is idle; paused work also defers restart. TypeScript errors keep the last working process alive. Close the application to stop the dev server and compiler. Development uses a separate `MyoControl Development` profile unless `MYOCONTROL_PROFILE` is explicitly supplied. No installer is needed for this development loop.

Or build with `npm run build`, then `npm start`. Development Python is in `local-runtime/.venv`. `MYOCONTROL_BOOTSTRAP_PYTHON` selects the interpreter used to create it; `MYOCONTROL_PYTHON` overrides the development runtime executable. Packaged builds always use the bundled executable.

## User flow

1. Turn on BITalino and select **Scan sensors**. Windows discovers Classic Bluetooth sensor candidates and serial endpoints; **Bluetooth settings** opens system pairing, then **Rescan sensors** refreshes the list. Choose the outgoing serial port (Windows `COM…`, macOS `/dev/…`). The explicit selection is remembered in this OS user profile. Incoming ports are not selectable; manual entry remains available. The default is **four analog channels A1–A4 at 1000 Hz**, ten seconds. More/fewer channels can be explicitly selected. The bundled Windows path requires paired Bluetooth serial/SPP; unsupported direct MAC input gives an actionable error. BLE-only sensors are not supported. Discovery does not open the port or prove the sensor responds; capture validates the actual connection. Other operating systems enumerate serial ports after OS pairing.
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

This build captures labelled calibration repetitions and trains a target-only personal LDA from selected recordings. It does not adapt imported source-model parameters. LDA adaptation packages, SVM/MLP inference, model catalog download, terminal recognition-session report synchronization and the general workstation training worker remain separate work. The current sync API publishes recording parts; it does not publish models or experiment outcomes.

The SDK adapter has simulated-device tests, and Classic Bluetooth acquisition was checked on Windows with a physical BITalino. M1 Pro compatibility has not been verified with hardware. Electron portability alone does not establish SDK/OS compatibility. The SDK is pinned to `bitalino==1.2.6` and installed without its optional PyBluez dependency for the paired-serial path; retain upstream license information when distributing its bundled code.

## GitHub Actions builds and release notes

`Desktop builds` runs on pushes to `main`, pull requests and manual dispatch. Its native matrix targets Windows x64, macOS Apple Silicon arm64 and macOS Intel x64, including the matching Python runtime. Each platform runs runtime tests, formatting, the Electron e2e test and the same test against the packaged application. macOS builds must pass their native CI jobs before those packages are considered verified.

Builds are identified by the first 12 characters of the commit SHA; no manual version bump or version tag is required. The internal `package.json` version remains a technical Electron requirement. Successful push/manual build packages are downloadable from the run's **Artifacts** section for 14 days:

- Windows: `MyoControl-<SHA>-windows-x64-setup.exe` and an install-free ZIP. Extract the entire ZIP and run `MyoControl.exe`; user data belongs to the Windows user profile.
- macOS: `MyoControl-<SHA>-macos-<arm64|x64>.dmg` and `.zip`.

After all desktop matrix jobs succeed, a push to `main` automatically publishes a **GitHub Release** named `build-<SHA>` with the packages and GitHub-generated release notes. No manual publication is required. If a rerun finds a draft for that commit, it refreshes the assets and publishes it; already-published releases and their assets are preserved. PRs validate packages without uploading installers or creating releases. The workflow does not deploy the server.

Generated notes list merged pull requests, contributors and a comparison link, grouped using `.github/release.yml`. Use descriptive PR titles and labels (`enhancement`, `bug`, `dependencies`, etc.). Only the release job receives `contents: write`; other jobs use read access. No additional API secret or AI service is required.

Windows packages are unsigned; macOS packages are unsigned and not notarized, with Hardened Runtime disabled for these test distributions. Signing/notarization and real BITalino hardware testing remain separate work. Intel packages require a macOS version supported by the bundled Electron release; they do not target the original OS of a 2010 Mac mini.

Cloud URL is the API base, which may include `/api`, rather than the static website root. No deployment domain is built into the application. The update subsystem writes a bounded diagnostic log; general runtime/cloud file logging remains unimplemented.

Imported models are copied into the runtime profile and validated again on each launch. The original filename and model checksum are retained; moving or deleting the source file does not affect the saved model. **Clear model** removes the persistent selection. A failed import keeps the previous model, and an unreadable saved copy leaves acquisition available with an explanatory recognition status.

Local LDA inference supports two-channel (`time-domain-2ch-v1`) and four-channel (`time-domain-4ch-v1`) models. The loaded model shows its channel count and sample rate. Use a separately trained two-channel model for A1/A2; a four-channel model remains incompatible with two-channel recordings. This runtime does not train models or verify their recognition accuracy.

## Train a personal model

Use Acquisition > Calibration repetition to collect separately labelled `rest`, `fist` and `finger_spread` recordings. Keep one participant pseudonym and electrode placement; use A1/A2 (or four channels), 1000 Hz, 6 seconds, comfortable steady effort and rest between recordings. Record 10 repetitions per class if possible. Hold the labelled pose before starting and throughout each recording; relax after it finishes. The first and last second are excluded during fitting.

In Recordings > Train a personal model, choose the matching data group and explicitly select the recordings, or use Select latest 10 per gesture. Train and use personal model fits only the training repetitions, archives the model/report and selects the persistent model. The latest 20% whole repetitions per class remain held out. The minimum is five and maximum twenty per gesture. Current training is a local target-only LDA, not adaptation of imported DB2 weights. Completed recordings remain unchanged; old research recordings without labels are not silently included.

Read the held-out confusion matrix and rest false-activation rate, then test fresh live gestures. Even a perfect small same-collection score does not establish robustness after changing placement, effort or session. Clear model removes the persistent selection, while archived trained model/report files remain in the profile.
