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

## D14 — Lead narrative = acquisition-mix decomposition, not "low adoption"
Post-Phase-1 data reconnaissance (queries on `fct_customer`) reframed the story. The
blended card-adoption rate falls ~7x across 2015 (Q1 2.61% → Q3 0.38%), but this is
**mostly a composition illusion**: acquisition mix flips from ~85% PARTICULARES in H1-2015
to ~76% UNIVERSITARIO in H2-2015, and UNIVERSITARIO customers adopt the card at ~0.18%
(students essentially never take it, regardless of income). Holding segment constant
(PARTICULARES only), adoption still declines but far less — 2.65% → 1.47% (~1.8x), a
smaller *genuine* within-segment softening. So the top-line is a textbook mix effect
(Simpson's-paradox flavor) layered over a modest real decline. Heterogeneity is large:
~16x by segment×income (TOP/high 3.08% vs UNIVERSITARIO 0.19%), ~4x by channel (6.6% vs
1.7%). **Decision:** the lead analytical narrative is *"the blended funnel rate is a vanity
metric — what moved is acquisition mix and channel quality, not the card offer,"* which is
(a) more interview-defensible (standard portfolio-analyst mix decomposition), (b) actionable
(re-target PARTICULARES / high-income / best channels), (c) native fuel for the Phase 3
proactive digest + deterministic critic (guard against naive top-line reads; surface the
mix-drift). Stays 100% inside the credit-card domain — no product switch. **Consequence for
Phase 2:** the semantic layer gains a mix-adjusted adoption metric (segment held constant)
plus a first-class `segment_mix` / acquisition-composition metric, so BI and the agents can
separate mix effect from genuine change. Caveat to honor: the within-segment decline rests
on smaller n — narrate as directional, and the min-n guard (D10) still applies.

## D15 — Semantic layer is a framework-neutral Python package (not FastAPI-owned, not MCP-owned)
The open Phase-2 question was whether the governed metrics live inside the FastAPI copilot
module (as they effectively do in flagship #1, under `copilot/tools.py`) or in an MCP-native
definition file. **Decision:** neither — the metric definitions live in a standalone,
framework-neutral `semantic/` package (`windows.py`, `errors.py`, `metrics.py`, `layer.py`)
that has zero web/LLM/MCP dependencies. Streamlit imports it directly today; in Phase 3 the
reactive FastAPI copilot, the proactive ADK digest, and the thin MCP wrapper each *wrap* the
same four functions (`list_metrics`, `query_metric`, `compare_cohorts`, `explain_metric`) —
adding error-as-data + `TOOL_DECLARATIONS` at the edge — rather than owning the definitions.
Rationale: (a) no single consumer owns the source of truth, so BI and every agent path speak
one vocabulary; (b) the layer is unit-testable offline with no HTTP/LLM/BigQuery mocking;
(c) it improves on #1, where the tool contract and the metric registry are slightly coupled
in `copilot/`. **Consequence:** Phase 2 ships `semantic/` + a supporting dbt mart
(`mart_adoption_curves_by_segment`, the acq_month×segmento×msa grain the segment-adjusted
metric needs); the FastAPI/ADK/MCP wrappers are deferred to Phase 3 as planned.

## D16 — adoption_rate_segment_adjusted via direct standardization to a pooled reference mix
`adoption_rate_segment_adjusted` (the D14 mix-decomposition metric) is computed by direct
standardization: each cohort's per-segment adoption rate is reweighted to a FIXED reference
segment mix — the pooled segment shares across all within-panel cohorts — so a mix shift
cannot masquerade as a change in the card offer. The denominator renormalizes on the sum of
present weights, so a cohort missing a segment cell (e.g. right-censored) is not penalized.
Verified live (msa_6): the blended rate falls 1.54% (2015-01) → 0.24% (2015-09), a ~6.4x
drop, while the segment-adjusted rate falls only 0.84% → 0.52% (~1.6x). `compare_cohorts`
attributes ~1.30 pp of the ~1.30 pp blended gap to mix and ~0.32 pp to genuine within-segment
change — i.e. roughly three-quarters of the top-line move is composition, confirming D14.

## D17 — Per-segment metric access via an optional `dimension` param on `query_metric` (not a 5th tool)
The Phase-3 "by-segment" analyst slice and the critic's min-n guard both need adoption
**broken down by segment cell** (adoption rate AND n per cohort×segmento), but Phase-2's
`query_metric('adoption_rate')` returns only the segment-blended value with no n. **Decision:**
extend the existing `query_metric` with an optional `dimension="segmento"` argument that reads
`mart_adoption_curves_by_segment` and returns one row per segment carrying both `value` and
`n` — rather than adding a 5th governed tool. Rationale: keeps the governed surface at four
tools (the number the README sells), reuses a mart that already exists, and the min-n guard
gets its `n` from the same governed call instead of reaching around the semantic layer.
Rejected alternative: a separate `query_metric_by_segment` tool (more surface, same result).

## D18 — `mart_digest_cache` is written by the digest job, NOT a dbt model
The digest cache is accumulated state (one persisted digest per cohort-month), not a
transformation. If it were a dbt model, every `dbt build` would drop and rebuild it, wiping
stored digests. **Decision:** the digest job creates it with `CREATE TABLE IF NOT EXISTS`
and upserts into it; dbt never owns it. Invalidation stays keyed on `(cohort_month,
dbt_run_id)` so a dbt re-run forces regeneration without dbt destroying the table. This is
consistent with the "data layer stays bootstrapped so IaC can't destroy loaded data" lesson.

## D19 — Provider: AI Studio free tier is the demo default; Vertex is a documented prod path via one env var
The BLUEPRINT was always internally consistent on **AI Studio free tier** ($0, 1,500 req/day
hard ceiling) as the provider the demo actually runs on, with **Vertex named only as the
documented production path** (BLUEPRINT lines 328, 415, 426; D6; the D14-inherited row). The
Phase-3 kickoff message and the root `CLAUDE.md` line ("Vertex AI Gemini for now") introduced
apparent ambiguity, but there is no real conflict: **Decision:** the demo runs on AI Studio
free tier (needs a Gemini API key in `.env`, never committed) to honour the "$0 / free tier
in everything we build" rule, and Vertex remains a one-line-in-the-README prod path toggled
by `GOOGLE_GENAI_USE_VERTEXAI=true` (ADK / `google-genai` support both backends with the same
code — no architecture change). We never run Vertex in the demo; we only document that it
scales there. README "$0" wording is kept literal (AI Studio), with Vertex framed as
"production would route to Vertex AI for governance/data-residency".

## D20 — ADK powers the reactive copilot's tool-calling loop; the deterministic digest uses google-genai directly
BLUEPRINT line 417 reads "ADK for the proactive multi-agent digest", which taken literally
would put Google ADK inside the digest pipeline. **Decision:** ADK earns its place in the
*reactive copilot* — `build_governed_agent` / `adk_generator` in `agents/copilot.py` run a
genuine multi-turn `LlmAgent` + `InMemoryRunner` tool-calling loop where the model decides
which of the four governed tools to call. The *proactive digest*, by contrast, is
deterministic by design (D5): planner → parallel analysts → **deterministic** critic gate →
narrator, where orchestration is plain Python and only the single narrator step calls an LLM.
Wrapping that lone, structured narrator call in an ADK agent would be gratuitous (Golden Rule
#3) — it has no tools to call and no turns to take — so the narrator uses `google-genai`
directly (`agents/narrator.py`, `genai_generator`). Consequences: (a) ADK is genuinely
exercised (D6 honoured) but only where a real agentic loop exists; (b) the Airflow digest
container runs a **light** `agents_venv` with `google-genai` only (no `google-adk`), keeping
the pipeline image small and dependency-clean; (c) the two LLM entrypoints stay separate —
`adk_generator` (copilot, tool-calling) vs `genai_generator` (narrator, single structured
call) — both injected as `Callable[[str], str]` so all orchestration is offline-testable.
Rejected alternative: force ADK into the digest narrator for literal BLUEPRINT fidelity —
more deps, heavier Airflow image, zero added capability.
