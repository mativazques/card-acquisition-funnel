# Decisions Log — card-acquisition-funnel

Chronological log of the binding decisions taken while designing this project, so any
future session (or reviewer) can see *why* the BLUEPRINT looks the way it does. Newest
decisions at the bottom. See `BLUEPRINT.md` for the full spec.

## D1 — Separate public repo, not a merge into credit-risk-cockpit
Continuity with flagship #1 is real, but merging repos hurts portfolio diversification
(two visible flagships > one big one) and couples release cadence. **Decision:** new
standalone public repo, reusing the architecture DNA. Continuity is delivered later via a
shared landing/hub page, NOT by nesting this inside the cockpit.

## D2 — Domain reframe: adoption funnel, not approval funnel
No public dataset exposes a native credit-card *approval* funnel (application → decision →
issuance) with real grains. Forcing one would require synthetic/derived stages, breaking
Golden Rule #2 (honesty). **Decision:** reframe to the *acquisition → card-adoption →
retention* funnel, which a real public dataset DOES support natively. A SCOPE BOUNDARY box
in the BLUEPRINT states plainly that there is no approval stage.

## D3 — Dataset: Santander Product Recommendation (Path A)
Chosen over the rikdifos "Credit Card Approval Prediction" set (whose funnel stages are all
derived). Santander gives **native grains**: `fecha_alta` (join date → cohort), monthly
snapshots (~13.6M rows, ~950k customers, Jan 2015–May 2016), `ind_tjcr_fin_ult1`
(credit-card holding flag → adoption event), `ind_actividad_cliente` (activity → retention),
plus `canal_entrada`, `segmento`, `renta`, `age`, province. License caveat flagged for
verification before publishing.

## D4 — Proactive insight layer (not just reactive Q&A)
Added a period selector + a monthly insight digest the bot surfaces without being asked
(defaults to the last fully-observed cohort when nothing is selected). **Decision:** the
digest is **pre-generated in Airflow** as a post-dbt task, cached by cohort-month, so
serve-time cost stays $0. Includes deterministic **early-warning** threshold-breach
detection, narrated by an agent.

## D5 — Multi-agent, but non-gratuitous
Rejected the "agents chatting to each other" decoration (violates Golden Rule #3).
**Decision:** a purposeful pipeline — Orchestrator/planner → parallel Analyst agents →
**Critic/verifier agent that enforces the data-honesty contract** (right-censoring,
materiality, min-n) → Narrator. The critic-as-honesty-gate is what makes the multi-agent
shape earn its place.

## D6 — Framework: Google ADK, self-hosted (confirmed)
ADK is free (Apache 2.0, open source). The cost trap is Vertex AI **Agent Engine**, which
bills ~$0.0864/vCPU-hour even idle (no scale-to-zero). **Decision:** self-host the ADK
runtime in the existing Cloud Run container (scale-to-zero) + Gemini AI Studio free tier =
$0/mo. Do NOT use Agent Engine.

## D7 — Text-to-metric, not text-to-SQL
Inherited differentiator from flagship #1: the copilot resolves questions against a
**governed semantic layer** (defined metrics + enumerated windows), never free-form SQL.
Keeps answers reproducible and interview-defensible.

## D8 — Fully-observed window = 6 months (primary default)
msa_6 is the primary window for vintage curves and the proactive digest's default cohort.
msa_12 leaves only ~5 early-2015 cohorts fully observed — too thin for robust vintage
analysis. Formal definition: a cohort is fully observed at msa_N when
`acq_month + N months <= May 2016`. msa_12 remains available but is clearly labeled
"limited cohort pool (n~5 cohorts)."

## D9 — fct_customer_month as a TABLE (not a VIEW)
The original spec mirrored #1's `fct_loan_month` VIEW decision. That reasoning does NOT
transfer: #1's panel is ~2.2M rows; this dataset is ~13M rows. A VIEW on 13M rows causes
3–8 s scan latency on every Streamlit page load and every semantic-layer query — not
acceptable for a live cockpit. **Decision:** `fct_customer_month` is materialized as a
TABLE, `partition by DATE_TRUNC(snapshot_month, MONTH)`, `cluster by acq_month, segmento`.
Storage ~1–2 GB, within BigQuery's 10 GB/month free tier. The BLUEPRINT note
"mirroring #1's VIEW decision to keep storage ~$0" is removed.

## D10 — Deterministic critic guards (Python/SQL, not LLM judgment)
The critic agent's honesty gate is three Python/SQL checks on the resolved metric payload
before the narrator sees anything. (a) **Right-censoring guard:** suppress `adoption_rate`
at msa_N for any cohort where `fully_observed_N = false`, using the `is_cell_right_censored`
flag computed in dbt (read from `mart_adoption_curves`, not re-derived). (b) **Min-n guard:**
suppress cohort-segment cells with `cohort_size < 50`; replace with structured suppression
token. At n=50 a 1 pp delta has ~±4 pp 95% CI — too wide to narrate. (c) **Materiality
gate:** narrate a delta as a finding only if `abs(delta) >= 2pp AND abs(delta) > 1.5 ×
rolling_SD(prior 3 cohort deltas, same window/segment)`; fall back to 2pp-only for fewer
than 3 prior cohorts, labeled "insufficient history." None of these are LLM decisions.

## D11 — Narrator receives only the critic's output struct; causality prohibition; numeric-faithfulness check
Three architectural constraints on the narrator, enforced structurally (not by prompt alone):
(1) The narrator's input is the critic output struct only — raw analyst outputs never reach
it. (2) The narrator system prompt explicitly forbids causal/root-cause claims (the dataset
has no causal fields); if pushed, it reframes as "hypothesis, not finding." (3) A Python
post-generation step extracts every numeric token from the narrator's output and verifies
each appears verbatim in the critic payload; mismatch blocks caching and flags for human
review.

## D12 — License YELLOW: proceed with mitigations; synthetic fallback available
Santander competition data (owner: Banco Santander, S.A.) has no open CC/ODbL license.
Eight years of public reuse, zero enforcement, and non-commercial/educational/portfolio use
sits within Kaggle's academic-research-and-education carve-out. Verdict: YELLOW, not a
blocker. Mitigations: (1) raw CSVs never committed — `make hydrate` via Kaggle CLI;
(2) only aggregated outputs published; (3) honest provenance footer in README; (4) accept
Kaggle competition rules under `matirvazques@gmail.com` before downloading. Fallback: a
drop-in synthetic data generator (MIT/CC0) leaves dbt/semantic/agent code unchanged.

## D13 — Strategic identity: proactive multi-agent system (not cockpit #2)
Flagship #2 shares ~80% of the stack with #1, risking the perception of a reskin.
**Decision:** reposition the project identity to "a proactive, self-directing multi-agent
funnel-analytics system with a built-in data-honesty gate." The funnel/vintage analytics
are the substrate; the proactive multi-agent layer with the deterministic critic is the
star. Consequences: (a) the "what is distinct from #1" section leads with the multi-agent
differentiator; (b) the reactive copilot is explicitly secondary — text-to-metric parity is
sufficient, no re-polishing in Phase 3; (c) Phase 3 effort concentrates on the proactive
pipeline, not reactive Q&A; (d) the README/demo lead with the proactive digest and early-
warning, not the curves; (e) a named "Why multi-agent?" defense section is added to the
BLUEPRINT with two honest reasons: parallel decomposition and auditable separation of
responsibilities.
