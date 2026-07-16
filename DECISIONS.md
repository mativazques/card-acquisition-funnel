# Decisions Log — card-acquisition-cockpit

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

## Status
BLUEPRINT complete and Factory-reviewed (6 specialists + chief-evaluator: ~REVISE, no
BLOCK; 12 honesty actions incorporated). No code written yet — implementation begins in a
future session per the phased plan (Phases 0–4) in the BLUEPRINT.
