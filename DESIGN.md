# DESIGN.md — Digital Back Office AI Data Analyst

## 1. Purpose and authority

Design a usable AI-powered CSV analyst for the internship assignment: upload business data, ask questions, inspect computed answers, understand anomalies, build dashboards, find previous analyses, and export reports.

This is a product and interface specification, not a claim of implemented functionality. Read `prd.md` for scope, `trd.md` for contracts and security, and `AGENTS.md` for development rules. Those documents govern computation and permissions; this document governs presentation and interaction. Resolve material conflicts before implementation.

The supplied Velara reference is visual inspiration only. Borrow its near-black palette, purple accents, Inter typography, soft depth, and restrained glass surfaces. All navigation, content, data, actions, layouts, and workflows must serve this project's analyst experience. Reference copy, sample figures, external assets, component structure, and integration instructions are not project requirements.

## 2. Product principles

- **Reach a useful answer quickly.** Upload and suggested questions lead directly into analysis.
- **Make evidence inspectable.** Every successful answer offers sources, method, SQL, and a supporting table.
- **Keep business language primary.** Technical evidence lives in labeled disclosures; resource errors explain the user's next step.
- **Use consistent artifacts.** Chat, dashboards, search, and exports reference the same saved analysis results.
- **Represent uncertainty honestly.** Clarifications, insufficient evidence, partial dashboards, and stale sources are first-class states.
- **Keep the workspace calm.** Dense analytical content needs readable surfaces and predictable controls.

## 3. Visual system

### Color tokens

| Token | Value | Use |
| --- | --- | --- |
| canvas | #08080B | Page background |
| surface | #111116 | Sidebar and cards |
| surface-raised | #191920 | Menus, dialogs, focused panels |
| border | #34343F | Essential control and panel boundaries |
| text-primary | #F5F5F8 | Body, titles, results |
| text-secondary | #B5B5C3 | Metadata and supporting copy |
| text-muted | #9090A3 | Secondary annotations; verify contrast at actual size |
| accent | #A854F7 | Highlights, active navigation, focus accents |
| action | #782CC2 | Primary button fill with white text |
| action-hover | #6823AA | Primary hover fill |
| success | #34D399 | Successful operations |
| warning | #FBBF24 | Data-quality caveats |
| danger | #FB7185 | Failed operations and destructive actions |
| info | #60A5FA | Informational states |

Verify WCAG AA contrast in the implementation, including translucent surfaces, disabled states, chart labels, and buttons. The reference purple can highlight the interface; use the darker action fill for small white button text.

### Typography, spacing, and surfaces

Use locally bundled Inter with a system sans-serif fallback. Use a monospace font for SQL only. Body text is 14–16 px; metadata is 12–13 px; section titles are 20–24 px; primary screen headings are 28–32 px. Use tabular numerals for metrics and tables. Avoid reference-sized hero typography in the working app.

Use a 4 px spacing base: 8 px inside compact controls, 12–16 px between related items, 20–24 px card padding, and 24–32 px between sections. Controls are at least 40 px high; touch targets should reach 44 px. Use 10–12 px control radii, 16 px cards, and 20 px dialogs.

Keep analytical cards opaque enough for stable contrast. Apply subtle glass effects to the top bar or welcome panel only. Use small purple glows around a primary action or welcome illustration; charts and tables need flat backgrounds. Use Lucide icons with text labels or accessible names. Navigation always includes readable labels.

Animate menu/dialog transitions for 120–200 ms. Progress reflects actual operation states. Respect reduced motion. Chart animation must not delay inspection or imply an analytical result before computation finishes.

## 4. Information architecture

| Destination | User purpose | Main actions |
| --- | --- | --- |
| Analyze | Ask questions and inspect results | Select data, ask, follow up, inspect evidence |
| Datasets | Upload and understand available files | Upload, preview, profile, select, delete |
| Dashboards | View and save a compact analytical overview | Generate, inspect cards, reopen, export |
| Search | Find previous successful analyses by meaning | Search, inspect sources, open conversation |
| Account | Manage the current local session | View identity, sign out |

Use a shared application shell. Primary navigation sits above recent conversations in the left sidebar; the account control sits at the bottom. Show selected datasets in the Analyze header and a contextual dataset panel. Search is its own destination; do not confuse searching past analyses with querying CSV rows.

Suggested routes: `/login`, `/register`, `/analyze`, `/analyze/[conversationId]`, `/datasets`, `/datasets/[datasetId]`, `/dashboards`, `/dashboards/[dashboardId]`, and `/search`. Adapt names to the existing repo. Export is a dialog and download, not a separate editor.

## 5. Entry and authentication

Prioritize a working application over a marketing page. The signed-out entry can combine a concise product introduction with a login form: “Turn CSV data into answers you can verify.” Supporting copy: “Ask questions, explore charts, and inspect the calculations behind each result.”

Primary action: “Sign in.” Secondary: “Create account.” Show documented demo-account details only if that account actually exists. Do not imply automatic guest access.

Forms use persistent labels, visible validation, password visibility controls, and clear submission states. Login failures use a generic message. Successful authentication opens Analyze or restores an authorized destination. Session expiry preserves unsent question text where safe, prompts login, and clears private rendered data. Logout clears private client state.

## 6. Analyze workspace

### Desktop layout

Use a 240 px navigation sidebar, a flexible conversation column, and an optional 300–340 px dataset-details panel. Keep the conversation readable at approximately 760–900 px wide. The top bar shows conversation title, selected-data summary, and “Generate dashboard.” A sticky composer sits below the conversation without obscuring messages.

The dataset panel displays selected filenames, versions, row/column counts, quality warnings, and “Manage selection.” Collapsing it preserves a visible selection summary.

### Empty state and upload

Before data is available, show “Start with your data,” a CSV drop zone, “Upload CSV,” and “Use sample data.” Display supported encoding and the current upload limits beside the drop zone. The file picker supports multiple files; use the same validations for drag-and-drop.

Each upload has independent progress and a final accepted or failed state. A successful upload shows inferred schema and quality warnings; a failed file explains the cause without erasing accepted files. Suggested questions appear after profiling and derive from actual columns.

Examples for the checked-in sales fixture: “Which region has the highest revenue?”, “Show revenue by month,” and “Find unusual order values.” Only display these when the fixture supports them.

### Composer and context

The composer has a labeled multiline input, dataset-selection summary, and a send button. Enter sends and Shift+Enter inserts a newline; preserve accessible alternatives. Disable sending when no eligible dataset is selected and explain why. During a request, preserve its question and prevent accidental duplicate submission.

Show actual phases such as “Preparing analysis” and “Calculating results” only when supported by real backend status. Otherwise use a single truthful busy indicator. Add cancellation only if the API implements it.

Follow-ups use the conversation's valid dataset versions and analytical context. Changing datasets shows the change clearly and revalidates prior context. Do not present previous results as if calculated on the new selection.

### Answer card

Each successful answer contains, in order:

1. A short answer using computed figures and explicit units where known.
2. A chart or compact result table when appropriate.
3. Relevant caveats, quality warnings, or anomaly explanations.
4. Source chips with dataset name/version and an analysis timestamp.
5. “Method” and “SQL” disclosures.
6. Actions: copy SQL, open supporting table, include in report.

Use Chart/Table tabs when both representations exist. Method details include filters, grouping, formulas, assumptions, and limitations. SQL is selectable and copyable; it is an inspection surface rather than an arbitrary execution console.

A small “Reused calculation” badge indicates an execution cache hit. It does not imply the whole response or provider call was cached. Timing details can sit in a compact optional details section.

### Clarification, failures, and anomalies

Clarification appears as an assistant question with selectable options only when those options are supported by schema. Retain the original intent. Ambiguous joins show candidate keys, uniqueness, join type, and unmatched counts for confirmation.

Anomaly results show the rule, baseline, threshold, sample size, flagged count, and caveats, followed by affected records/groups. “No values flagged by this rule” differs from “Insufficient evidence to evaluate this rule.” Do not label anomalies as errors or proven fraud.

Failed analyses show a safe explanation, retry where meaningful, and request ID in expandable details. Preserve prior successful messages. Never display an empty chart as a completed calculation.

## 7. Datasets

The list shows filename, version, status, rows, columns, upload time, and quality summary. Actions are “Inspect,” “Use in analysis,” and “Delete.” Show uploading/profiling entries separately from ready entries.

Dataset detail has Preview and Profile tabs. Preview contains bounded rows with horizontal scrolling and a visible truncation label. Profile shows column names, inferred types, missing counts/rates, duplicate-row count, and parsing warnings. Preserve original values; no implied cleaning or imputation.

Deletion requires a concrete confirmation explaining dependent analyses/dashboard cards will become unavailable. After success, remove the dataset from selection and show unavailable-source states for affected artifacts. UI labels must match the implemented cascade behavior.

## 8. Charts and tables

Use validated chart artifacts and computed data only. Render supported bar, line, pie, and scatter charts with titles, units, axis/legend labels, and an accessible supporting table.

| Chart | Appropriate use | Presentation rule |
| --- | --- | --- |
| Bar | Category comparisons | Prefer horizontal bars for long names |
| Line | Ordered/time trends | Sort by actual order; do not bridge missing periods misleadingly |
| Pie | Valid nonnegative part-to-whole results | Label values/shares; use another chart when categories become hard to read |
| Scatter | Two numeric variables | Label both axes and show useful tooltips |

Chart palette: purple #A854F7, blue #60A5FA, teal #2DD4BF, amber #FBBF24, rose #FB7185, and lavender #C4B5FD. Maintain consistent category colors within a view. Do not rely on color alone; use labels, legends, markers, or patterns. Positive changes are not automatically green unless their business meaning is known.

Tables use sticky headers, right-aligned numbers, explicit null representation, and clear units. Differentiate returned-row count from source-row count. If a capped result may exclude categories, label that limitation rather than implying a complete chart.

## 9. Dashboards

Generate from selected datasets through a compact dialog showing scope and up to six cards. The result uses a fixed grid, not a drag-and-drop builder: two or three columns on wide screens and one on mobile.

Each card has a descriptive title, computed metric/chart, source references, and access to its method/table. Successful cards remain visible when another card fails. Failed cards show the reason and an available retry action; dashboard completeness is explicit.

Users can name, save, and reopen dashboards. Saved dashboards show source versions and generation time. Opening one must not imply fresh computation. Do not expose unsupported edit, refresh, share, or scheduling controls.

## 10. Semantic search

Heading: “Find previous analyses.” Placeholder: “Search by meaning, such as regional performance.” Index and retrieve only eligible successful analyses owned by the current user.

Results show the original question/title, grounded excerpt, dataset references, and date. “Open analysis” navigates to the saved artifact/conversation. Search results are historical references; they do not answer a new numeric question.

Distinguish searching, no matches, no saved analyses, unavailable embedding runtime, and deleted source. Do not show an arbitrary relevance percentage or silently substitute keyword search.

## 11. Report export

“Export report” opens a selection dialog for successful analyses or dashboard cards. Show title, selected count, sources, and the committed format: “Offline HTML report.” Disable unavailable artifacts with a reason.

The exported document includes title, generation time, dataset versions, answers, charts, tables, SQL, methods, assumptions, and limitations. It uses a light background, dark text, restrained purple headings, and readable print styles. Embed required chart assets so it opens offline. Report content comes from the saved evidence, not a separate calculation pipeline.

After download begins, say “Download started.” Do not claim the user saved or opened the report. Keep selection intact if generation fails.

## 12. Observability and user-facing status

Expose useful status at the point of failure: analysis failed, search unavailable, upload rejected, or session expired. Include a safe request ID for troubleshooting. Provider configuration and infrastructure details belong in setup documentation and logs.

Use health/readiness checks for actual availability; avoid fabricated uptime, token-cost, latency, or accuracy widgets. Detailed operation timings may be shown in an analysis details disclosure when real.

## 13. Shared interaction states

| State | Presentation | Recovery |
| --- | --- | --- |
| Empty | Explain what the user can do next | Upload, sample data, ask a supported question |
| Loading | Stable layout and accurate activity text | Preserve input and prior content |
| Partial | Keep successful artifacts and identify failures | Retry only supported operations |
| Invalid input | Field/file-level actionable explanation | Edit or replace input |
| Timeout/provider failure | Safe error and retained question | Retry with the same selection |
| Unavailable source | Identify affected dataset/artifact | Select available data or start a new analysis |
| Session expired | Clear private content and prompt login | Restore authorized navigation after login |
| Limit reached | State the actual enforced limit | Reduce file/selection/query scope |

Use inline messages for durable context and toasts for brief confirmations such as SQL copied. Critical errors must not disappear automatically. Dialogs trap focus and restore it to the initiating control.

## 14. Responsive and accessible behavior

At 1280 px and above, use the full shell with optional details panel. From 768–1279 px, collapse dataset details into a drawer and allow navigation to collapse. Below 768 px, use a navigation drawer, one content column, compact selected-data control, stacked dashboard cards, and full-width dialogs.

Keep charts responsive with a practical minimum height around 280 px. Tables scroll inside their own regions. The composer remains reachable when the mobile keyboard opens; avoid fixed desktop heights and clipping. Long filenames wrap or truncate with a discoverable full name.

Provide semantic landmarks, visible focus, labeled icon controls, keyboard operability, meaningful validation messages, and screen-reader status announcements. Skeletons are decorative. Charts include a textual summary and data-table alternative. Test at 200% zoom and narrow widths; essential actions must remain available.

## 15. Component and implementation guidance

Build a small reusable set: AppShell, Navigation, DatasetSelector, UploadDropzone, UploadStatusList, DatasetProfile, ConversationView, QuestionComposer, AnalysisCard, ChartView, ResultTable, SourceChips, MethodDisclosure, SqlViewer, ClarificationCard, AnomalySummary, DashboardCard, SearchResultCard, ExportDialog, EmptyState, and InlineError.

Create components when they support an actual flow. Map typed API artifacts directly to view models; do not invent missing metrics. Keep authorization on the backend and clear private client caches on logout. Treat filenames, CSV values, SQL, and summaries as text, including in exports.

Use existing Next.js/Tailwind/Plotly choices from the TRD unless the source repo requires reconciliation. Framer Motion is optional; simple CSS transitions are sufficient. Avoid bringing in the reference's background video, remote avatar, financial controls, or mock chart data. Use initials for the account avatar.

## 16. Two-day design delivery

Day 1: tokens and shell, authentication, upload/profile, selected datasets, chat composer, answer/chart/table cards, method/SQL, clarification and failures. Verify the real upload-to-answer journey before visual refinement.

Day 2: fixed dashboard grid, export selection, semantic search, cache indicator, responsive/accessibility polish, and submission screenshots. Reserve defect-fixing time; avoid building a marketing site or decorative features that compete with the agreed scope.

## 17. Design acceptance checklist

- The UI visibly belongs to a CSV analyst and every control maps to an implemented capability.
- Users can upload multiple CSVs, inspect quality, choose sources, ask a question, and inspect computed evidence.
- Follow-ups and source changes are clear; ambiguity requests clarification.
- Bar, line, pie, scatter, anomalies, and tables support honest limitations and readable labels.
- Dashboards save/reopen real artifacts and represent partial failures.
- Semantic search opens eligible historical analyses and shows unavailable states.
- Reports contain evidence and open offline; download labels match the HTML format.
- Authentication, dataset deletion, and session expiry clear or invalidate affected private UI state.
- Cache and timing indicators reflect actual metadata.
- Empty, loading, error, partial, narrow-screen, keyboard, and reduced-motion states are verified.
- Screenshots use checked-in synthetic data with computed results; any separate concept mockup is explicitly labeled.

The final experience should feel polished because its workflows are coherent and its answers are inspectable. Visual styling supports those goals throughout the project.
