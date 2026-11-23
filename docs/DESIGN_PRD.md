# MyoControl — Product and Design Requirements

**Product:** Intelligent Control System for a Simulated Myoelectric Prosthesis under Limited Calibration Data<br>
**Document:** Design PRD for the complete diploma application<br>
**Version:** 1.1 · 23 November 2026<br>
**Language:** English product UI and design specifications<br>
**Design system:** IBM Carbon, using the existing MyoControl Carbon UI Kit

## Accepted delivery and execution decision

[ADR-001](ARCHITECTURE_DECISIONS.md) and the [deployment architecture](DEPLOYMENT_ARCHITECTURE.md) supersede earlier browser-only and single-host assumptions.

| Surface/executor | Accepted responsibility |
| --- | --- |
| Cloud platform and adaptive web portal | Operator accounts/authorization, research data/protocol management, model registry, experiment-job coordination, results/comparison/export and central artifact storage. |
| Powerful local workstation | General LDA/SVM/MLP training and batch experiments/evaluation. Cloud job submission does not imply cloud fitting. |
| Installed Electron client | Bundled local React UI, Python and PLUX SDK; recording, labelled calibration, local adaptation, live recognition, virtual hand, replay and local persistence/synchronization. |

Electron manages local process lifecycle automatically. A user does not install Python/Docker or manually start a worker. Separate tested native installers support the declared OS/CPU matrix. The responsive desktop/tablet/mobile requirement applies only to the cloud web portal. Electron supports laptop/desktop windows.

Prepared authorized desktop sessions operate during cloud loss using cached model/adaptation packages and persist pending work. First login, missing package downloads and cloud operations require connectivity. Exact offline-access/session policy is specified before release.

## 1. Purpose and product outcome

MyoControl is a research workbench for recognising hand gestures from surface electromyography (sEMG), personalising a model with limited calibration data, and controlling a simulated hand. Its interface must connect data collection, experimental preparation, model training, evaluation and demonstration into a coherent workflow.

The central research question is how calibration effort changes recognition quality, and whether personalisation improves on a source-only model under comparable test conditions. The design must make this relationship understandable without requiring users to read database tables, paste UUIDs or inspect raw JSON.

This PRD describes the complete intended application. Existing API coverage determines implementation dependencies, not which product workflows receive a design. A stored database entity does not automatically need a separate screen.

### Required user outcomes

- Prepare traceable recordings from a supported dataset or a local acquisition session.
- Establish a versioned experimental protocol and freeze a valid data split.
- Build nested calibration budgets and understand the effort available for each gesture.
- Train and compare source-only, personalised and target-only models across LDA, SVM and MLP.
- Inspect results, failures and provenance, including missing or negative outcomes.
- Select a compatible model and demonstrate live recognition or recorded replay with a simulated hand.
- Return to saved work after interruption and export a reproducible research result.

### Product boundaries

The product is a research prototype for a simulated hand. Physical prosthesis control, clinical assessment, diagnosis, continuous finger-force estimation and automatic fatigue detection remain outside the project requirements. The UI must not imply these capabilities.

The design does not introduce billing, organisation management, social features, a participant portal, a general-purpose annotation platform or a full infrastructure administration console. These do not support the documented diploma workflows.

## 2. Source of truth and implementation context

| Reference | How it informs this PRD |
| --- | --- |
| [Project requirements](PROJECT_REQUIREMENTS.md) | Product goals, US01–US19, research invariants and NFR01–NFR09. |
| [Database requirements](DATABASE_REQUIREMENTS.md) | Data ownership, provenance, freeze/publication, recovery and export rules. |
| [Database logical model](../database/LOGICAL_MODEL.md) and [data dictionary](../database/DATA_DICTIONARY.md) | Existing entities and relationships; current service schemas versus the original backend schema. |
| [Database implementation](../database/IMPLEMENTATION.md) | Implemented integrity rules and remaining limitations. |
| [Frontend guide](../frontend/README.md) | Current operator UI, demo behaviour and API limitations. |
| [Hand visualisation](../frontend/HAND_VISUALIZATION.md) | Supported poses, animation behaviour, accessibility and WebGL fallback. |
| [Data & Protocol](../services/data_protocol/README.md), [ML Experiments](../services/ml_experiments/README.md), [Recognition](../services/recognition/README.md) | Implemented service workflows and feature gaps. |
| [Service architecture](../architecture/README.md) and [experiment guidance](../experiments/README.md) | Ownership boundaries, reproducibility and protocol decisions. |
| [DB2 ingestion pilot](../scripts/NINAPRO_PILOT.md) | Import/provenance limitations and distinction between an ingestion check and research-ready data. |

Functional and research requirements take precedence over older architecture proposals. Implementation documents establish current availability; they do not prove that a planned research capability is working.

### Current state versus design target

The current frontend supports an illustrative demo, recording browsing, initial source-only LDA submission and recorded prediction playback. Service schemas already represent participants, recordings, labelled segments, protocols, manifests, calibration selections, experiment jobs and replay sessions. The original schema describes additional source metadata, model lineage, evaluations and artifact verification. These are separate implementations; the UI must not assume that one API can access both schemas.

Full dataset import, guided acquisition, complete protocol editing, personalisation, target-only training and comprehensive comparison remain design requirements even where implementation is incomplete. Capability availability must come from actual application support. The released UI must not offer a seemingly working action that only produces fabricated results.

The currently documented ML contract expects four channels. A local hardware pilot also establishes a two-channel acquisition use case. Treat acquisition configuration and model input contracts separately: two-channel recordings may be stored and inspected, but cannot run through a four-channel model without a separately implemented and validated contract. Never silently duplicate, pad or relabel channels.

## 3. Users and access

| User | Needs | Interface implications |
| --- | --- | --- |
| Operator / researcher | Prepare data, run calibration and experiments, inspect results, demonstrate recognition. | Full workbench with guided setup, saved configuration and clear recovery actions. |
| Reviewer / supervisor | Understand a comparison and verify the origin of its data and models. | Readable results with linked provenance and export; a separate account or portal is not required. |
| Recording participant | Understand the next gesture, rest interval and recording progress; pause or stop. | A focused acquisition/calibration presentation within the operator workflow. |

Participant identity is distinct from an application login. Use participant codes in everyday UI. Do not put names, contact information, consent documents or identifying acquisition details into shared results by default.

Operator accounts and authorization are cloud-managed and required. The desktop authenticates for permitted downloads/publication and has explicit cached/offline access states. Show sign-in, sign-out, account context, expired access and access-denied states without inventing an enterprise identity-management console. Accounts remain distinct from research participants. The current shared Basic-auth gateway does not implement these account requirements.

## 4. Information architecture

Use two task-oriented surfaces with reusable React/Carbon components. The cloud portal covers research management and centrally published records. Electron covers local device control and local computation. The six groups below are logical product areas, not six mandatory identical navigation items in both applications. Related entities open as details/tabs; Settings and Help are secondary utilities.

| Product area | Cloud adaptive portal | Electron desktop |
| --- | --- | --- |
| Workspace | Published session summaries and model selection/preparation metadata | Live/replay setup, signal, hand and session controls |
| Data | Permitted recording/dataset/participant management and published provenance | SDK acquisition, local signal/label review and pending uploads |
| Protocols | Author, validate, freeze and browse research versions | Inspect/use prepared compatible protocol packages |
| Calibration | Published subsets, budgets and adaptation provenance | Guided collection, local subset validation, local adaptation and pending publication |
| Experiments | Configure/submit research jobs; inspect local-worker availability, runs and model versions | Interactive adaptation progress and locally produced personal model |
| Results | Central evaluations, comparisons and export | Immediate local session/adaptation results and synchronization state |

The following functional descriptions are assigned by this table. Cloud pages do not request direct browser Bluetooth access or run live/calibration remotely.

| Destination | Main content | Main actions |
| --- | --- | --- |
| **Workspace** | Live/replay setup, signal, current gesture, simulated hand and session status. | Select input/model, start, pause, stop, inspect session. |
| **Data** | Recordings and participants; dataset/source details. | Import data, record a session, inspect signal and labels, review validation. |
| **Protocols** | Protocol versions, split membership and validation. | Create draft, allocate data, validate, freeze, create a new version. |
| **Calibration** | Target participant, calibration plan, budget coverage and selected repeats. | Collect or select calibration data, validate and freeze a subset. |
| **Experiments** | Run history, experiment setup and model versions. | Train, personalise, train target-only, evaluate, inspect model lineage. |
| **Results** | Evaluations and saved comparison context. | Compare conditions, inspect per-participant results, export a research bundle. |

**Secondary utilities:** Connection & Settings, contextual help, job activity and notifications. Show infrastructure availability only when it affects a user action. Detailed logs and service dashboards may be linked from troubleshooting rather than copied into the workbench.

Provide contextual cross-links: recording → containing split; calibration → its manifest; run → produced model; model → evaluation; result → source inputs; model/recording → Workspace. Preserve the relevant selection when navigating.

## 5. Core end-to-end journeys

| Journey | Sequence | Completion |
| --- | --- | --- |
| Dataset to research result | Import → validation report → signal/label inspection → protocol/split → freeze → experiment → evaluation → comparison. | A result has readable conditions and traceable inputs. |
| Local participant recording | Select participant → configure acquisition → check input → guided gestures/rest → stop/save → review. | Valid data and labels are saved; interruption is represented honestly. |
| Limited calibration | Select target and frozen protocol → choose budget → collect/select repeats → check coverage and nesting → freeze → personalise and target-only training. | Both conditions reference the same eligible calibration selection. |
| Controlled comparison | Select compatible evaluations → compare source-only/personalised/target-only across budgets → inspect participants → export. | Fixed test membership and comparable conditions are visible. |
| Demonstration | Choose live or replay → select compatible input/model/gesture mapping → start → inspect signal/hand → pause/stop. | Session status and neutral transitions are clear and measurable. |
| Recovery and review | Reopen application → find saved/interrupted work → inspect failure → retry as a new attempt or continue a supported draft. | Completed results remain available; partial output is not presented as published. |

The interface should suggest a relevant next step when prerequisites are missing. It must also support experienced users moving directly to an existing recording, run, model or result.

## 6. Screen requirements

### 6.1 Workspace — recognition and demonstration

**Execution/UI:** Electron, using the bundled local runtime. Cloud session pages are retrospective summaries, not the live control path.

**Purpose:** Operate one live or replay session with an understandable relationship between input, prediction and simulated movement.

**Setup:**

- Explicit mode selector: `Live`, `Recorded replay`, `Demo`.
- Input/device or recording, participant code where applicable, model version and gesture mapping version.
- Compatibility summary: channel count/order, sample rate, feature/preprocessing contract and class mapping.
- Model picker shows name, family, condition and version; UUID is available in details or via copy.
- Start remains unavailable until prerequisites pass, with a specific reason and a link to resolve it.

**Active view:**

- Signal plot with channel legend, show/hide controls, time scale and declared units. Unknown units remain `Unspecified`; ADC is not automatically displayed as mV.
- Readable input state: connected, receiving, waiting, disconnected or invalid. Device pairing is distinct from receiving valid samples.
- Simulated hand, predicted gesture and effective command. Hand movement is illustrative, not a measurement of the participant's hand.
- Distinguish raw prediction from a smoothed command when smoothing is enabled; show its configuration in details.
- Show confidence only if the model provides a defined, comparable quantity. Do not substitute an invented percentage.
- Replay includes timeline, current position, duration and playback controls. Seeking/speed controls are included only where supported and must not misrepresent recorded timing.
- Live uses elapsed session time and input continuity, not a fake replay timeline.
- Show latency with its measurement boundary and sample count: processing, buffering and rendering/end-to-end measurements are distinct. Unmeasured values show `Not measured`.

**Pause, stop and failure:**

Pause/stop, lost input, invalid signal or processing failure must put the recognition-controlled hand into neutral, show the reason and leave the current state readable. Recovery after a failure requires an explicit restart. Pause confirmation and neutral transition must meet the project’s ≤250 ms acceptance target; mockups alone do not prove this.

Manual pose exploration is a separate, clearly labelled preview state. Its five current canonical poses are `Rest`, `Fist`, `Finger spread`, `Wrist flexion` and `Wrist extension`. Do not relabel finger spreading as generic hand opening. Additional class sets come from a versioned protocol, not assumptions built into a visual asset. Unknown or unsupported predicted commands resolve to neutral with an explanation.

If WebGL fails, retain the session controls, signal, gesture text and a readable hand-preview fallback. Reduced-motion preferences must be respected.

### 6.2 Data — recordings, participants and import

**Recording library:** Search and filter by participant, source/version, session, gesture coverage and validation status. Columns include a readable recording label, participant code, source, channels, sample rate, duration and status. Support pagination and explicit selection. Avoid making every provenance field a permanent column.

**Recording detail:**

- Signal viewer with channel visibility and zoom; sample count, duration, frequency and units.
- Labelled timeline with canonical gesture, original label and repeat where available.
- Metadata: source/version, acquisition session, channel order/positions, known electrode metadata, original coordinates and validation findings.
- Basic label review/correction where permitted, including boundaries and a reason for change. Preserve original labels and create a new derived/versioned result once data is frozen or referenced; do not build a general annotation suite.
- Actions: `Use in protocol`, `Use for calibration` and `Open in Workspace`, subject to eligibility.
- Technical provenance in an expandable section: stable IDs, checksums, artifact verification and usage links. Missing metadata is visible rather than guessed.

**Participants:** A compact list and detail view using codes, with associated sessions, source mappings and recordings. Creation and selection are part of acquisition/import. Application account identity is never substituted for participant identity.

**Import flow:**

1. Select the supported source/format and files; see applicable source/usage information.
2. Review detected metadata, map participant/source identity, select or confirm channels, units and label mapping.
3. Run validation and preview the detected signal/labels before committing.
4. Confirm import and receive a persistent report of accepted, rejected and duplicate/conflicting items, with reasons and recovery actions.

Retain original files and provenance. Re-import must not silently create a new participant or conceal duplicate content. An unresolved identity/conflict is explicit and may block research use. Show actual progress or a stage with indeterminate progress; do not fabricate percentages.

An import pilot is not automatically research-ready. Missing original coordinates, source identities, licensing metadata or verified channel mappings must remain visible in eligibility checks.

### 6.3 Guided acquisition — within Data

**Execution/UI:** Electron with direct SDK access. OpenSignals is optional diagnostic software and is not required to operate the client.

Use a focused flow, not a permanent additional navigation section:

`Participant & session → Device & channels → Input check → Guided recording → Review & save`.

- Configure the supported acquisition adapter, sample rate, measured channels/order and available electrode-placement metadata. Distinguish a shared reference connection from a measured channel.
- Display the expected contract and what the current model can consume. The two-channel pilot and four-channel ML path must never look interchangeable.
- Input check shows received channels and the quality checks actually performed, including missing data or clipping if implemented. Unknown checks remain unknown; no unsupported global `Signal healthy` diagnosis.
- Guided recording shows the current gesture, rest interval, countdown, repetition and progress through the protocol. Do not encode unconfirmed timing values in the design.
- Pause/stop is always reachable. A participant can stop without completing every repetition.
- On disconnect, preserve received samples, mark the session interrupted and show which repeats/labels are complete, partial or unusable. Resuming acquisition must not imply continuous timing across a gap.
- Review supports acceptance, rejection with reason and recollection of affected repetitions. Uncertain timing labels are not silently treated as ground truth.

Consent/usage eligibility follows the approved data-handling process. Show only the minimum operator-facing status needed to record or use data; do not create a legal consent-management system or copy private documents into the design.

### 6.4 Protocols — experimental setup and frozen splits

**Protocol list:** Name, version, class set, status and associated manifests. Detail includes research/exploratory designation, allowed data sources, gesture/channel mapping, preprocessing/feature version, budget plan, seeds and evaluation/comparison rules.

**Split editor:**

- Work with readable participant and recording/segment selections.
- Display participant categories `Source`, `Development`, `Target` separately from data roles `Source train`, `Development validation`, `Target calibration`, `Target test`.
- Assign roles before windowing. Show eligible membership and interval boundaries; detailed sample coordinates are inspectable.
- Summarise participants, recordings, repeats/classes and duration by role. Permit inspection of the actual selected membership.
- Validate participant leakage, overlapping signal/segments, missing classes, invalid mappings and other protocol requirements before freeze or training.
- A validation problem identifies the affected participant/recording/segment and an actionable remedy. A generic red banner is insufficient.

**Freeze:** Present an understandable membership summary and the consequences of making the version immutable. A frozen manifest exposes version, checksum, creation time and usage links. Editing creates a new draft/version. Training always names the frozen version used.

Target test membership stays fixed across comparable methods and calibration budgets. Changes after final-test inspection require an exploratory designation or an independent test plan; the UI must not present them as the same untouched final experiment. Advanced research settings may be collapsed, but the conditions of a completed result must remain inspectable.

### 6.5 Calibration — effort, coverage and selection

**Execution/UI:** collection and personalisation execute in Electron. Cloud stores published subsets/models and displays their provenance. Pending local records are distinguished from cloud-validated/frozen/published records; offline work uses prepared eligible protocols and is validated on synchronization.

**Purpose:** Prepare the limited labelled data used for personalisation and target-only controls.

- Select target participant, frozen manifest, class set and supported input contract.
- Choose eligible existing repeats or enter guided acquisition using the same gesture/rest presentation as Data.
- Budget panel shows required and selected repeats plus unique labelled seconds **per class**, including rest. Overlapping intervals must not be counted repeatedly.
- Where measured, display procedure/operator time separately from signal duration.
- Show budget series and parent selection: a larger budget contains the smaller selection. A comparison of budgets shows additions, not an unrelated reselection.
- Missing mandatory classes, ineligible data, overlap and broken nesting identify the exact issue and block freezing/training.
- Zero calibration is represented as the source-only condition. A zero-data personalised or target-only result is not offered as a valid control.
- Freezing creates an immutable selection with a version/checksum and readable membership.
- Final summary links to `Personalise model` and `Train target-only`, both using the same frozen subset and compatible test conditions.

An interrupted calibration procedure preserves valid completed data and offers recovery based on actual saved state. Do not automatically promise that an unsupported acquisition session can resume mid-repeat.

### 6.6 Experiments — configuration, runs and models

**Execution/UI:** the cloud portal coordinates general-training/batch research jobs; a powerful local workstation executes them. Show worker availability and queued/waiting states. Electron executes interactive model adaptation locally; large research sweeps do not become cloud computation by submitting a web form.

**Run history:** Name/ID, family, condition, target, protocol version, calibration budget, status and time. Include filters and a persistent detail route. Users should not need to retain a UUID outside the product to reopen a job.

**Experiment configuration:**

| Setting | Design requirement |
| --- | --- |
| Family | LDA, SVM or MLP, with supported options clearly available. |
| Condition | Source-only, personalised or target-only; explain the required data and parent model. |
| Inputs | Frozen protocol/split and target participant; frozen calibration subset when required. |
| Features | Versioned preprocessing, channels/order, sample rate, feature order, window and step; inspectable defaults. |
| Method | Family-specific training/adaptation parameters; advanced controls grouped separately. |
| Reproducibility | Seed, configuration/software versions and input snapshot. |
| Evaluation | Compatible locked test, class mapping and intended research/exploratory status. |

The current four-channel time-domain contract produces 20 features from five features per channel. Window length and step are versioned configuration, not universal fixed UI assumptions. Proposed adaptation methods remain configurable protocol decisions rather than validated product claims.

Before submission, show a compact summary and validation report. Unavailable capabilities have explicit implementation status; mocks for them must still describe the full target flow. The normal interface should use selectors and readable summaries rather than raw JSON forms.

**Run detail:** Persisted status, start/end time, current reported stage, elapsed time, inputs and eventual result. Support queued/running/succeeded/failed/interrupted states as provided by the service. Cancellation is offered only if the backend supports it; leaving a page or stopping polling is not cancellation. Repeated submit must not accidentally create duplicate work.

On success, link to the model and evaluation. On failure/interruption, explain what is saved, what is unavailable and how to create a retry attempt. Do not display partial models as published. A failed personalisation leaves its source model available.

**Model detail:** Family, condition, version, publication/verification state, feature and class compatibility, parent model, calibration selection, training run and associated evaluations. Actions: `Evaluate`, `Use in Workspace`, `Personalise`, where valid. Model lineage is a simple linked chain/table; a large graph editor is unnecessary.

### 6.7 Results — evaluation and comparison

**Evaluation detail:**

- Model, target participant, condition, calibration budget, locked test version and evaluation run.
- Macro-F1, accuracy, confusion matrix and rest false-activation rate.
- Display the evaluated class set, class support and test sample/window counts needed to interpret the metrics.
- Confusion matrix labels clearly separate actual and predicted classes. Offer count/normalised views with the normalisation definition.
- Rest false-activation is based on rest windows predicted as non-rest before smoothing. When no rest windows exist, show `Not applicable`, not 0%.
- Values that are unavailable are distinct from valid zeros. Do not fabricate metrics for an unfinished or failed run.
- Provenance and artifact/version details are available without overwhelming the main result.

**Comparison workspace:**

- Compare source-only, personalised and target-only under compatible protocol, target/test membership, family, features and class mapping. Parameter differences are visible and assessed against the protocol rather than automatically treated as equivalent.
- Plot recognition quality against calibration effort. Support repeats per gesture and unique labelled seconds; do not conflate either with measured operator time.
- Provide per-participant rows alongside aggregate summaries, participant count, paired changes, uncertainty and missing runs.
- Clearly show negative transfer, exclusions, unequal coverage and incomplete comparison cells. Do not silently average only successful runs without revealing the selection.
- Display uncertainty only when calculated using a defined method. The final estimator/interval rule remains a protocol decision; no invented confidence interval.
- Keep DB2 results, measured MuscleBIT evaluations, synthetic checks and live engineering measurements separate in analysis and export.
- Comparisons that fail matching rules show why; unmatched results can be inspected side by side with an explicit non-comparable designation, not included in a pooled research conclusion.

**Export:** A single flow offers a human-readable summary and a machine-readable research bundle containing available metrics, comparison conditions, manifests, configurations, versions and provenance. Show contents and omissions before export. Exclude secrets and restricted source recordings by default. Report missing artifacts explicitly instead of presenting an incomplete bundle as fully reproducible.

A compact report view within Results is sufficient. Do not design an additional BI/report-builder application.

### 6.8 Connection, settings and help

Separate cloud-account/API connectivity, local-runtime health, device connectivity and training-worker availability. Cloud loss must not be shown as device loss or automatically stop a prepared live session. Show pending uploads, successful sync, transfer failures and retry without duplicate publication.

Installation/first launch must identify missing or failed bundled native components and provide useful diagnostics. Users should not be instructed to fix normal startup by manually installing Python packages or starting a terminal worker.

- Connection/sign-in state shows local/demo versus connected operation and which product capabilities are currently available.
- Session disconnect does not erase persisted research data. Credentials never appear in URLs, exports or result metadata.
- Settings cover the environment connection and relevant acquisition/visualisation preferences. Model/training parameters belong to experiments; protocol decisions belong to protocols.
- A compact dependency-status panel provides a readable affected capability, recent failure and diagnostic reference/correlation ID where available.
- Contextual help explains terms such as frozen test, calibration budget, source-only and neutral. Help links to the applicable workflow, not just a generic documentation homepage.

## 7. Shared interaction and state requirements

| State | Required presentation and behaviour |
| --- | --- |
| First use / empty | Explain what belongs here and offer a relevant next action or demo. |
| No filter matches | Preserve filters and offer clear/reset; distinguish from an empty database. |
| Loading | Keep layout stable and identify the object being loaded. |
| Long-running job | Stable ID, persisted status and reported stage; allow navigation away. |
| Validation blocked | Specific field/object, reason and remedy; preserve the draft. |
| Missing capability/dependency | Explain what is unavailable and which actions remain possible. |
| Access denied / expired session | Request reconnection without presenting the object as missing or deleting saved work. |
| Error / interrupted | Retain valid saved information; show a safe next action and diagnostics in details. |
| Frozen / published | Read-only conditions and provenance; offer a new version/attempt where appropriate. |
| Partial / unknown / not applicable | Use distinct labels; never silently substitute zero, success or a guessed value. |
| Stale data / connection lost | Identify stale content and offer refresh/reconnect; stop implying live updates. |
| Destructive or irreversible action | Explain the specific effect before confirmation; referenced research history may block the action. |

Drafts are editable; frozen/published records are not silently overwritten. UI status vocabulary must map to real backend state. Transient view states such as loading, paused playback or disconnected input are separate from persisted job states.

Use persistent inline feedback for blockers and failures. Toasts are suitable for brief confirmations, not the only evidence that recording stopped, a run failed or data were excluded. Avoid multiple competing primary actions on one screen.

Data handling actions must follow the approved retention/withdrawal policy. Do not offer unrestricted hard deletion of a participant and all dependent research records as a shortcut. Detailed policy and permissions remain open implementation decisions.

## 8. Platform layouts and responsive behaviour

### Cloud web portal

Design and review research workflows at **1440 px desktop, 768 px tablet and 390 px mobile**, including reflow toward 320 px. This scope includes operator access, data/protocol/model browsing and management, research-job configuration/status, results/comparisons and exports.

| Element | Desktop | Tablet | Mobile |
| --- | --- | --- | --- |
| Navigation | Persistent research navigation | Collapsible navigation | Compact menu and current context |
| Research forms | Restrained columns | Fewer columns | Single-column/staged configuration |
| Libraries | Tables with search/filter/detail | Secondary columns in detail | Summary cards and explicit selection |
| Comparisons/matrix | Labelled charts and tables | Focused scrolling where needed | Scrollable labelled matrix and textual metrics |
| Details/dialogs | Side panel or short modal | Wider panel | Full-screen detail/task with return action |

A mobile browser can inspect research records or submit a job to an available local training worker. It does not acquire BITalino, run calibration/adaptation or control a live desktop session.

### Electron desktop client

Design installed laptop/desktop windows with usable minimum window size, resizing, keyboard access and clear focus. Signal/hand panels may move from columns to a vertical layout as the desktop window narrows. Pause/stop, active gesture, input state and local-runtime status stay reachable. Exact supported minimum window size is validated with prototypes.

No tablet/phone Electron layouts are required. The desktop loads its bundled UI and native runtime without relying on cloud-hosted UI assets, external fonts or manual Python startup. Network-required versus prepared-offline actions are explicit.

## 9. Visual system and accessibility

- Reuse existing Carbon components, typography, spacing, colour tokens and states from the project’s UI Kit. Use real component instances and existing variants in Figma where possible.
- Prefer a consistent light research-workbench theme. A dark hand/plot surface may support visualisation, but a separate global dark theme is not required by this PRD.
- Use Carbon shell/navigation, buttons, inputs, dropdowns, tabs, data tables, pagination, progress indicators, tags, inline notifications, modals and tooltips as applicable. Custom work is concentrated in signal charts, gesture guidance, the hand and research comparisons.
- Keep the main hierarchy task-oriented: current context → important state/result → primary action → supporting detail. Avoid decorative dashboards or redundant metric cards.
- Typography and density must support extended desktop work and legible mobile use. Scientific notation, units and metric scales must be consistent.
- Provide keyboard access, a visible focus indicator, meaningful labels, predictable focus return and accessible validation. Charts and the hand need textual equivalents.
- Status must be readable without colour. Channel/class colours are consistent and paired with labels; do not rely on red/green alone.
- Follow project contrast targets: at least 4.5:1 for normal text and 3:1 for large text. Touch controls should be comfortably usable; target approximately 44 × 44 px for principal mobile actions.
- Respect reduced motion. Loading or render failure must not remove essential session controls.
- Every demo/synthetic context is persistently identified as such, including results and exported content.

## 10. Required design deliverables

The design package covers both cloud research and Electron local-control surfaces according to the ownership table in section 4. Use reusable screens/states rather than duplicating every configuration.

| Design group | Required views |
| --- | --- |
| Application entry | Cloud operator sign-in/account context; Electron installation/first launch, local-runtime health, prepared demo, disconnected/access-error and offline states. |
| Workspace | Setup, ready, running live, running replay, paused/stopped, input failure and hand fallback. |
| Data | Recording library/detail, participant selection/detail, import steps and validation report. |
| Acquisition | Setup/input check, current gesture/rest, interrupted session and review/save. |
| Protocols | Version list/detail, draft split editor, validation failure and frozen summary. |
| Calibration | Target/budget setup, class coverage, selected repeats, guided collection and frozen subset. |
| Experiments | Run list, setup/review, active job, failed/interrupted job and model detail/lineage. |
| Results | Evaluation, confusion matrix, matched comparison, incomplete/non-comparable comparison and export. |
| Utilities | Connection/settings, contextual help and compact dependency diagnostics. |

Produce high-fidelity cloud research views at all three responsive reference widths and Electron local-control views at supported desktop window sizes. Include installer/first launch, local-runtime failure, device setup, cloud sign-in, cached/prepared session, offline operation, pending upload and synchronization states, alongside shared empty/loading/error/read-only variants. Do not duplicate mobile live/calibration screens. Prototype the cross-surface journeys in §5 and annotate execution, persistence and network requirements.

Handoff must specify control behaviour, validation, navigation, data/units, persistence, job status mapping and recovery actions. Use clearly marked illustrative data and include negative/missing outcomes. No mock result should look like an established experimental finding.

## 11. Acceptance criteria

| ID | A design is acceptable when… |
| --- | --- |
| D01 | A user can trace a complete import/record → protocol → calibration → train → result → replay path without pasting UUIDs. |
| D02 | An operator can identify the active mode, participant/input, model version and connection state before starting recognition. |
| D03 | A two-channel recording and a four-channel model show an explicit compatibility blocker, with no implicit padding or remapping. |
| D04 | Import/review exposes rejected records, unknown metadata and source provenance; synthetic data remain identifiable. |
| D05 | Split conflicts name affected entities; freeze and subsequent version creation have distinct, understandable states. |
| D06 | Calibration shows per-class repeats and unique seconds, rest coverage, budget nesting and fixed test membership. |
| D07 | LDA/SVM/MLP and all three learning conditions have complete design flows, even where implementation is pending. |
| D08 | Results show the four required evaluation outputs, unavailable/N/A values, class support and actual comparison conditions. |
| D09 | Comparisons expose missing runs, negative transfer, paired participant changes and the definition/availability of uncertainty. |
| D10 | Neutral transitions and the explicit restart after input/processing failure are represented in Workspace and prototype annotations. |
| D11 | Failed/interrupted work remains discoverable; partial output is not published or depicted as complete. |
| D12 | Export contents and exclusions are visible; a result links back to model, run, configuration and frozen input membership. |
| D13 | Cloud research journeys work at desktop/tablet/mobile widths; Electron acquisition/calibration/live/replay work at supported desktop window sizes with accessible controls and keyboard navigation. |
| D14 | A reviewer can distinguish DB2 evaluation, MuscleBIT evaluation, demo values and live performance measurements. |
| D15 | Usability testing can evaluate the project target: at least 4 of 5 consenting adult users complete setup → calibration → results using instructions within 10 minutes under a defined test setup. |
| D16 | A clean supported machine installs and launches Electron with its bundled runtime/SDK and completes supplied replay without Python, Docker or manually started workers. |
| D17 | A prepared authorized desktop completes calibration/adaptation and live during cloud loss, then synchronizes pending results without duplicates. |
| D18 | Cloud job status distinguishes unavailable local workers from active computation; general training is reproducible on another provisioned workstation. |
| D19 | Downloaded packages include the source statistics/fixed pools required by their advertised adaptation method, with measured package size, adaptation duration and memory. |

Runtime acceptance additionally verifies the documented latency, neutral-response, recovery and accessibility requirements. A visual prototype demonstrates interaction intent, not measured recognition performance or timing compliance.

## 12. Requirement coverage

| Project requirement | Design coverage |
| --- | --- |
| US01–US02 | Data import, recording provenance, validation and exclusion reports. |
| US03 | Protocol versions, membership editing, leakage validation and freeze. |
| US04 | Calibration budget/coverage, unique seconds and nested selections. |
| US05 | Feature/input compatibility in protocol, experiment and recognition setup. |
| US06 | Family selection, training configuration and model provenance. |
| US07–US08 | Personalisation lineage and target-only training from matching calibration data. |
| US09 | Evaluation detail, confusion matrix and metric semantics. |
| US10 | Matched comparisons, participant-level differences, aggregates and missing results. |
| US11 | Research export with versions, provenance and data exclusions. |
| US12–US13 | Live/replay Workspace, gesture mapping, timing boundaries and neutral-state behaviour. |
| US14 | Input-quality findings, record review and recollection actions; no unsupported automatic diagnosis. |
| US15 | Persisted run/session discovery, interruption states and publication visibility. |
| US16 | User actions mapped to documented capabilities and explicit API/data dependencies. |
| US17 | Connection/authentication states and locally usable workflows. |
| US18 | Versioned alternative features and exploratory comparison designation. |
| US19 | Guided acquisition with channels, electrode metadata, timing and interruption review. |
| NFR01–NFR02 | Timing definitions, reachable stop/pause and explicit neutral transitions. |
| NFR03–NFR04 | Leakage blockers, immutable inputs and accessible reproducibility details. |
| NFR05–NFR06 | Access/export boundaries and visible recovery of persisted work. |
| NFR07–NFR08 | Usability scenario, responsive behaviour and accessibility criteria. |
| NFR09 | Actionable connection/setup help; deployment instructions remain in technical documentation. |

## 13. Open decisions and handoff dependencies

These decisions affect final controls or real-data use. They do not remove the related workflow from the design scope.

| Decision | Design treatment until resolved |
| --- | --- |
| Final gesture set and DB2 ↔ MuscleBIT mapping | Use current canonical poses as examples; class-set versions drive actual choices and unsupported poses are explicit. |
| Two-/four-channel research configuration and anatomical mapping | Show versioned contracts and known/unknown metadata; block incompatible model use. |
| Native SDK build matrix and local IPC | Electron/direct SDK execution is settled; validate native OS/CPU support and select the restricted local transport. OpenSignals is optional. |
| Preprocessing, adaptation parameters and final budget/timing plan | Use documented configuration summaries and configurable protocol fields; mark example values as illustrative. |
| Final protocol, primary comparison and uncertainty estimator | Design comparison and definition fields without claiming an agreed statistical method or successful hypothesis. |
| Participant-data policy and operator session mechanism | Cloud operator accounts are required; choose identity/session, offline expiry and retention rules, distinct from participant eligibility. |
| Artifact recovery, server-side cancellation and export formats | Display only supported runtime actions; define missing contracts before enabling them. |
| Historical-to-service schema migration and missing provenance APIs | Preserve product-level IDs and lineage in design; specify API work rather than assuming shared database access. |

Additional handoff dependencies are cloud provider/sizing, authenticated remote-worker and publication APIs, model/adaptation package formats, permitted source-pool distribution, offline authorization and idempotent synchronization. Placement is accepted, not TBD. Current migrations implement operator/session persistence and the model/package/run/evaluation/publication registry. HTTP authorization, package transfer, Electron installers and synchronization remain incomplete; UI states must distinguish schema support from functioning runtime workflows.

The final screen set should make the complete research application understandable while keeping specialist details one level below the main task. Complexity belongs in the experiment and data model when needed, not in unnecessary navigation or decorative UI.
