# Card-Acquisition Cockpit — Blueprint

> Flagship #2. A **proactive, self-directing multi-agent funnel-analytics system with a
> built-in data-honesty gate** — built on a credit-card acquisition→adoption→retention
> funnel (BigQuery + dbt governed semantic layer + Gemini copilot + Streamlit + Cloud Run
> scale-to-zero + Terraform). The funnel/vintage analytics are the substrate; the
> proactive multi-agent layer with its deterministic critic is the star.
>
> Status: **spec approved, review fixes + strategic repositioning applied** (six
> specialists + chief-evaluator + three review agents). Nothing is built yet — this is the
> pre-Phase-0 spec.

## Why this project (and why a SEPARATE repo)
- Sits on Matias's defensible domain: **credit-card acquisition** + **cohort/vintage
  analytics** (both named in the Golden Rules). Complements flagship #1
  (`credit-risk-cockpit`) by covering the *other half* of the card lifecycle: acquisition
  & adoption, not risk & losses. Together they read as "I own the full card lifecycle."
- **Separate public repo**, reusing the *architecture DNA* of the cockpit (BigQuery + dbt
  dimensional model + governed semantic layer + Gemini copilot + Streamlit + Cloud Run
  scale-to-zero + Terraform) — the **pattern**, not the code.
- **Continuity via a shared landing/hub** (`credit-risk.<domain>` + `card.<domain>`), NOT
  a repo merge — so the portfolio gains a second independent artifact (diversification)
  while still reading as one platform.

### What is technically distinct from flagship #1 (must be visible in the README)
Sharing the stack is deliberate — the story is "I can apply the same governed-metric
pattern to a different domain and defend both." But this project's analytical and agentic
layers are genuinely different, and that difference must be explicit:

1. **A proactive, multi-agent insight layer** — #1 is purely reactive Q&A; #2 pushes the
   month's insights and early-warnings without being asked, via an ADK multi-agent pipeline
   with a **critic agent that enforces the data-honesty contract via deterministic Python
   guards, not LLM judgment**. This is the primary differentiator.
2. **Multi-stage funnel with stage-to-stage conversion** (acquired → adopted → retained),
   not a single terminal outcome like #1's default flag → a **waterfall** view #1 lacks.
3. **Behavioral adoption over time** — a real *vintage curve of credit-card adoption* by
   months-since-acquisition, the cohort machinery of #1 applied to onboarding instead of
   defaults.

### Why multi-agent (and not a single agent + a validation step)?
Two honest reasons — not decoration:

**1. Parallel decomposition of an open-ended task.** "Analyze the whole funnel and tell me
what matters" is genuinely open-ended: which cohorts? which segments? which metrics and
windows? which deltas are material? Decomposing this across parallel Analyst agents (one
per slice: cohort-over-cohort, by-segment, retention, time-to-adoption) is not gratuitous
— it mirrors how a human analyst team would divide the work, and it runs the slices in
parallel rather than serially.

**2. Auditable separation of responsibilities.** Planner (scoping) / Analyst agents
(retrieval via governed tools) / Critic (deterministic honesty gate) / Narrator (grounded
prose). This separation is what makes the honesty gate **architecturally enforceable**
rather than a behavioral hope. The Narrator never sees raw analyst outputs — it sees only
what the Critic approved. That structural constraint cannot be achieved with a single agent
plus a validation prompt.

**The honest counter-case:** the REACTIVE path deliberately stays single-agent because the
task is not open-ended — one question, one retrieval, one answer. Multi-agent there would
be gratuitous. Knowing *when not to use* multi-agent is part of the skill shown here.

## The pitch (one line)
"A growth/acquisition analyst opens the cockpit and the copilot has **already** written the
latest cohort's insight — *'the Feb-acquired cohort's 6-month card-adoption rate is 6 pp
below Jan; the drop concentrates in the mid-income segment'* — flagged as an early warning,
narrated from the same governed metrics the BI charts use. No question needed."

## The funnel (domain model)

```
customer ACQUIRED (join date)  →  credit-card ADOPTED (first month holding the card)
                               →  RETAINED (still holding at +1 / +2 / +3 months)
```

- **Acquisition cohort** = customers grouped by acquisition month (`fecha_alta`) and segment.
- **Vintage lens** = track each acquisition cohort forward: how many adopt the card, how
  fast (time-to-adoption), and whether they retain — a real months-since-acquisition
  adoption curve, honest and observed, not derived.
- **Fully-observed window = 6 months (primary default).** A cohort is fully observed at
  window `msa_N` when `acq_month + N months <= May 2016` (snapshot end). For msa_6: cohorts
  acquired through Nov 2015 are fully observed (~11 cohorts). For msa_12: only cohorts
  through May 2015 are fully observed (~5 early-2015 cohorts — too thin for robust
  vintage analysis). **6-month is the primary window** for vintage curves and the proactive
  digest's default cohort; 12-month is available but clearly labeled "limited cohort pool."

> ### SCOPE BOUNDARY (honesty — stated in the README from day one)
> **Real, observed data covers:** customer acquired (`fecha_alta`, a real calendar date) →
> credit-card adopted (`ind_tjcr_fin_ult1` flips 0→1, a real observed event) → retained
> (flag persists in later monthly snapshots).
> **NOT in this data (and NOT claimed):** there is **no application or approval/rejection
> stage** — every customer in the Santander dataset is already an account holder, so this is
> an **adoption/cross-sell funnel, not an approval funnel**. There is **no marketing
> top-of-funnel** (impression/click/spend). The acquisition **channel** (`canal_entrada`)
> is a real CRM field but its values are **obfuscated 3-letter codes** — presented as
> "acquisition-channel segments", never relabeled "web/branch/telesales" (that would be
> inventing labels). No synthetic data is used; the honesty comes from reframing to what the
> data actually observes.

## Business case (the *why* — illustrative, stated assumptions, public data)

> Framing: **cross-sell contribution as insurance**, not a promised adoption lift. The
> cockpit shortens the gap between a cohort's card-adoption softening and the team noticing
> and acting. Cross-selling the card to an **already-acquired** customer carries near-zero
> marginal acquisition cost, so each additional adopted card is high-margin contribution.
> Every number below is an illustrative, conservative model with stated assumptions (public
> dataset — no real book). Benefits split **hard** (incremental adopted cards × contribution)
> vs **soft** (analyst time) so the ROI survives if soft is zeroed.

### Cost of inaction (baseline)
- Consumer/fintech card CAC: **USD 80–150 fully-loaded** per acquired customer (Cornerstone
  Research / Forbes 2025; EU mid-market ≈ **USD 50–90**). That cost is already sunk at
  acquisition; a customer who never adopts a product returns little on it.
- Card-adoption/activation among acquired customers benchmarks around **~50–55%** becoming
  active card holders within the first months (FICO US Bankcards 2024, used as a range
  anchor). Adoption varies by cohort, segment, and onboarding quality — the cockpit's value
  is detecting cohort-level drops faster.
- **Clean unit: 1 pp of adoption-rate lift on 10,000 acquired customers = 100 additional
  active cards** (10,000 × 0.01). Each additional active card adds its annual contribution
  and requires near-zero incremental CAC (customer already on the books). *[Illustrative.]*
- Year-1 net contribution per active card: **EUR ~150** (conservative — interchange ~1.5–2%
  of annual spend + partial net interest on revolvers − funding cost; used as a floor, not
  a promise). CFPB 2025 (USD 160B US card interest income, 2024) is ceiling context only.
  *[Illustrative.]*

### Hard benefit — incremental adopted cards via faster cohort detection
Benefit = additional active cards recovered × contribution/yr. Mechanism: a cohort's
adoption softening detected in month M+1 instead of M+4 lets the team intervene (onboarding
nudge, UX fix, targeted outreach) while the cohort is still young enough to convert.

**Rollout ladder × adoption-lift sensitivity (contribution-only, conservative — all
numbers illustrative with stated assumptions):**

| Deployment stage | Acquired/qtr (influenced) | +0.5 pp | +1 pp (base) | +2 pp (best) |
| :--- | :--- | :--- | :--- | :--- |
| Pilot (1 segment/channel) | 10,000 | 50 cards · ~EUR 8k/yr | 100 · ~EUR 15k/yr | 200 · ~EUR 30k/yr |
| Partial (3 segments) | 30,000 | 150 · ~EUR 23k/yr | 300 · ~EUR 45k/yr | 600 · ~EUR 90k/yr |
| Full acquired book | 60,000 | 300 · ~EUR 45k/yr | 600 · ~EUR 90k/yr | 1,200 · ~EUR 180k/yr |

*(Unit: EUR 150 yr-1 contribution/card — illustrative. Contribution grows with tenure —
only yr-1 credited, to stay conservative. Numbers scale linearly with volume.)*

### Soft benefit — analyst time (does NOT carry the ROI)
- ~45% of analyst time goes to data prep/ad-hoc (Anaconda survey; reused from #1).
  Self-service NL Q&A + the proactive digest redeploy a slice. Illustrative: 2 growth
  analysts × EUR 75k × ~15–20% ≈ **EUR 22–30k/yr**. Not in the ROI figure.

### Costs / TCO (year 1)
- **Build:** one mid-senior engineer ~3 months (reuses #1's DNA) → **EUR 60–90k**.
- **Run** (production estimate): BigQuery ~EUR 1–3k · Cloud Run ~EUR 1–2k · Vertex/Gemini
  (multi-agent digest is batch + cached; reactive Q&A on narrow payloads) ~EUR 4–10k →
  **~EUR 6–15k/yr**. Change mgmt ~EUR 5–10k. **Year-1 TCO ~EUR 70–115k.**
- *(The PORTFOLIO DEMO runs at ~$0/mo on GCP free tier — see Cost controls.)*

### ROI & payback (honest)
- **Pilot (1 pp, 10k):** ~EUR 15k hard + ~EUR 25k soft vs ~EUR 90k TCO → pilot does **not**
  pay back on hard benefit in year 1. This is stated honestly: the pilot is a
  proof-of-detection, not the ROI case.
- **Partial rollout (1 pp, 30k):** ~EUR 45k hard vs ~EUR 90k TCO → payback ~2 years on hard
  alone; **positive from year 1 with soft included**, and from year 2 on run cost alone.
- **Full book (1 pp, 60k) or partial at 2 pp:** ~EUR 90k hard/yr → **payback ~1 year**.
- The defensible interview answer: *"at pilot scale it's a detection proof, not a slam-dunk
  ROI; the value shows up at partial/full rollout, and the demo itself costs $0."*

### Key assumptions & risks (own them)
- Assumptions: 10k acquired/qtr pilot, 52% baseline adoption, +0.5–2 pp lift, EUR 150
  contribution/card (illustrative), 3-month detection-lag cut. **The lift and detection-lag
  are the sensitive levers.**
- Risks: *attribution* (did the cockpit cause the faster action?) → pilot with before/after
  detection-lag measurement; *adoption of the tool* → the proactive digest lowers the floor
  (insight arrives without anyone querying); *lever ownership* — the cockpit surfaces the
  signal; the adoption action (onboarding/outreach) sits elsewhere, so only the detection
  speed-up is credited, not the full adoption gain.
- Public dataset — all numbers illustrative with stated assumptions.

## What BI does vs what the agents do
- **BI (standing views):** adoption vintage curves (months-since-acquisition vs cumulative
  adoption rate), cohort×segment heatmaps, time-to-adoption curves, the funnel waterfall,
  retention 30/60/90.
- **Reactive copilot (single agent — secondary feature):** ad-hoc NL "why did cohort X
  differ from Y?" — text-to-metric over the governed layer, one agent, cheap and fast.
  Multi-agent here would be gratuitous; this is deliberately minimal. The differentiating
  effort in Phase 3 concentrates on the proactive multi-agent layer, not re-polishing
  reactive Q&A. Text-to-metric parity with #1's copilot is sufficient.
- **Proactive layer (multi-agent) — the primary differentiator:** see below.
- **Non-gratuitous rule (inherited):** every agent path does **text-to-metric** over the
  semantic layer, **never raw text-to-SQL**. Same metric definitions power BI and agents.

## Proactive insight layer (the differentiating product idea)
The cockpit is not only reactive. A **period selector** (cohort-month dropdown) drives a
**"Insight of the month" panel**; with nothing selected it defaults to the **latest
fully-observed cohort at the msa_6 window** (never a right-censored one — showing an
unobserved cohort would be dishonest). The panel shows a narrated digest + **early-warning
flags** (e.g. "adoption −6 pp vs prior cohort, concentrated in mid-income").

**Generated in Airflow, served from cache ($0 at serve-time).** After `dbt run`, an Airflow
task runs the multi-agent digest for the latest fully-observed cohort (6-month window) and
stores the result (keyed by cohort-month + dbt run id). Streamlit reads the stored digest —
zero LLM tokens on page load, and the orchestration demonstrably does useful work. The
threshold breach detection (early-warning) is **deterministic** in the semantic layer; the
agents only narrate *what the data shows*.

### Multi-agent pipeline (Google ADK — self-hosted, non-gratuitous)
Open-ended "analyze the whole funnel and tell me what matters" genuinely benefits from
decomposition — unlike a single reactive question. Built with **Google's Agent Development
Kit (ADK)**:

```
Orchestrator (planner)   → picks which cohorts / metrics / segments to investigate
      │
      ├─ Analyst agents (parallel) → each calls the GOVERNED tools for one slice
      │                              (cohort-over-cohort, by-segment, retention, tta)
      ▼
  Critic agent            → DETERMINISTIC PRE-FILTER (Python/SQL checks, not LLM judgment)
      │                      see "Critic agent" subsection below
      ▼
  Narrator (synthesizer)  → writes the digest + early-warning flags
                            (receives ONLY the critic's output struct — never raw analyst outputs)
```

- **Why it's non-gratuitous:** the **critic agent does real work** — it enforces the
  right-censoring, statistical-materiality, and min-n guards via deterministic Python checks.
  It is the structural guardian against this project's biggest risk (over-reading noisy
  cohort cells). That justifies the multi-agent pattern honestly.
- **Still governed:** analyst agents call the same `list_metrics` / `query_metric` /
  `compare_cohorts` / `explain_metric` tools → the multi-agent layer sits **on top of** the
  semantic layer, never bypasses it. Text-to-metric end to end.
- **The honest split:** reactive Q&A = one agent; proactive digest = multi-agent. Knowing
  *when not* to use multi-agent is itself the skill on display.

### Critic agent — deterministic pre-filter (not LLM judgment)
Three guards are Python checks on the resolved metric payload BEFORE the narrator sees
anything. These are NOT LLM decisions — they are code.

**Guard 1 — Right-censoring suppression.**
Suppress any `adoption_rate` at `msa_N` for cohorts where `fully_observed_{N} = false`.
Concretely for this dataset (snapshot end May 2016):
- `msa_6`: suppress cohorts acquired after Nov 2015.
- `msa_12`: suppress cohorts acquired after May 2015.
Uses the `is_cell_right_censored` flag from `mart_adoption_curves` (set in dbt — the critic
reads a field, not re-derives it).

**Guard 2 — Minimum-n suppression.**
Suppress any cohort-segment cell with `cohort_size < 50`; replace with a structured
suppression token: `{"suppressed": true, "reason": "min_n", "n": <actual>}`.
Rationale: at n=50 a 1 pp delta has ~±4 pp 95% CI — too wide to narrate as a finding.

**Guard 3 — Materiality gate.**
Narrate a cohort-over-cohort delta as a "finding" only if BOTH conditions hold:
`abs(delta) >= 2pp AND abs(delta) > 1.5 × rolling_SD(prior 3 cohort deltas, same window/segment)`.
For the first fewer than 3 cohorts (no SD history available), fall back to the absolute
2 pp threshold only and label "insufficient history for materiality assessment."

The critic also flags cohort cells where the panel-gap fraction is material (>5%) — see
`has_panel_gaps` in `int_customer_adoption_resolved`.

### Narrator constraints (architectural, not behavioral)
- **Narrator receives ONLY the critic's output struct** — never the raw analyst outputs.
  The honesty gate is enforced by data flow, not by prompt instructions alone.
- **Causality prohibition.** The narrator system prompt forbids causal/root-cause claims.
  The Santander data has no causal fields. The narrator describes *what* the data shows and
  flags anomalies; it does NOT assert *why*. If pushed to explain why, it reframes as:
  "warrants investigation; possible factors are hypotheses, not findings."
- **Numeric-faithfulness check.** A Python post-generation step extracts every numeric token
  from the narrator's digest and verifies each appears verbatim in the critic-output payload.
  Any mismatch blocks caching and flags for human review — no rounding or inventing figures
  allowed through.

## Data (public)
- **Primary — Santander Product Recommendation** (Kaggle competition, 2016). ~13.6M monthly
  snapshots of ~950k real Santander customers (Jan 2015 – May 2016). Native fields the
  funnel needs: `fecha_alta` (**real** customer join date → acquisition cohorts),
  `ind_tjcr_fin_ult1` (**real** credit-card holding flag → adoption event + retention),
  `canal_entrada` (real, obfuscated channel code), `segmento`, `renta` (income), `age`,
  province, `ind_actividad_cliente`, plus 23 other product flags.
- **Why this over the alternatives (all vetted):** it is the only public set giving a
  **real acquisition date** and a **real adoption event** with a **monthly series** at scale
  — no derived approval label, no synthetic date (the honesty problems of the Kaggle
  "Credit Card Approval Prediction" set), and it comes from a **different institution** than
  #1's LendingClub, so the portfolio differentiates cleanly. Rejected: rikdifos approval set
  (date + approval + channel all derived/synthetic), LendingClub rejected+accepted (real
  approval funnel but loans + same source as #1), Home Credit `previous_application` (real
  approval + channel but relative dates + installment loans), UCI sets (too small / wrong
  stage / deposits).

### License — RESOLVED YELLOW (proceed with mitigations)
Santander competition data: owner Banco Santander, S.A. No open CC/ODbL license. Competition-
use data, widely reused in public notebooks (8+ years, zero enforcement). Non-commercial /
educational / portfolio use sits within Kaggle's "academic research and education" carve-out.
**Verdict: proceed with the following mitigations — this is no longer an open blocker.**

Mitigations (all must be in place before the first public commit):
1. Raw CSVs NEVER committed — `make hydrate` runs
   `kaggle competitions download -c santander-product-recommendation`.
2. Only aggregated charts/screenshots published; never raw rows.
3. Honest provenance footer in README (see below).
4. Accept Kaggle competition rules under the `matirvazques@gmail.com` account before
   downloading (Phase 0 checklist item).

Fallback (if ever needed — synthetic generator): publish a drop-in synthetic data generator
(MIT/CC0). Zero changes to dbt/semantic/agent code. This is cleaner even than the rikdifos
fallback and remains available at any time.

### README honesty footer (approved text)
- **Dataset:** Santander Product Recommendation (Kaggle competition, 2016), ~13.6M monthly
  customer snapshots (Jan 2015–May 2016), released by Banco Santander, S.A.
- **Access:** raw data NOT redistributed; reproduce via
  `kaggle competitions download -c santander-product-recommendation` after accepting the
  competition rules.
- **Licence:** competition-use data, no open CC/ODbL licence; used for
  non-commercial/educational/portfolio purposes only, consistent with Kaggle's
  academic-research-and-education carve-out; no raw data committed, only aggregated
  non-recoverable outputs.
- **Funnel scope:** acquisition → card adoption → retention; NO application/approval stage
  (every customer is already an account holder); `canal_entrada` channel codes obfuscated,
  presented as segments, never relabeled.
- All ROI/business-case numbers illustrative with stated assumptions; no proprietary systems
  or any employer represented.

## Architecture (GCP) — reuse cockpit DNA
```
                    ┌──── Airflow (LOCAL Astro/Docker — NOT Cloud Composer) ────┐
                    │  ingest → dbt run → dbt test → GENERATE MONTHLY DIGEST     │
                    │  (Cosmos: each dbt model a task) (multi-agent, cached)     │
                    └──────────────────────────┬────────────────────────────────┘
                                               ▼
Santander CSV → GCS (raw) → BigQuery (raw)
                          → dbt (staging → intermediate → marts + semantic layer)
                          → Streamlit  (cockpit: funnel + curves + heatmap + insight panel + chat)
                          → FastAPI + Gemini (AI Studio free · Vertex prod) + ADK + MCP  (copilot)
                          → Cloud Run (deploy, min-instances=0)   ·   Terraform (IaC)
```
Airflow is **local Astro/Docker** (Cloud Composer ~USD 300–400/mo would kill the $0 target).
The monthly-digest generation is an added Airflow task after `dbt test`.

### Digest cache
The digest cache is a BigQuery table `mart_digest_cache` with schema:

```
cohort_month      DATE
generated_at      TIMESTAMP
digest_json       STRING
warning_flags     JSON
critic_passed     BOOL
model_version     STRING
```

Invalidation key: `(cohort_month, dbt_run_id)` — a dbt re-run forces digest regeneration
(no stale digests served). The `cohort_month` for each Airflow run is NOT hardcoded; it is
derived by querying `mart_cohort_adoption` for the latest cohort where `fully_observed_6 = true`.

Airflow task chain: `dbt_test_pass >> generate_digest >> upsert_digest_cache`.

### Dimensional model (dbt on BigQuery)
- **Staging:** `stg_customer_month` (one row per customer×snapshot-month from the raw panel;
  cast, band income/age, keep `ind_tjcr_fin_ult1` + segment/channel).
- **Intermediate:** `int_customer_adoption_resolved` (one row per customer):
  - `acq_month` (from `fecha_alta`), `first_card_month` (min snapshot where card flag = 1),
    `months_to_adoption`, `is_right_censored`
  - `first_obs_month` (min snapshot month for this customer in the panel)
  - `is_left_censored_card` (= `first_card_month <= first_obs_month` — customer was already
    holding the card at their first observed snapshot; must NOT be counted as adopted-at-
    acquisition)
  - `is_adopted_observed` (flip 0→1 seen in the panel)
  - `is_adopted_clean` (= `is_adopted_observed AND NOT is_left_censored_card` — the metric
    consumed by the semantic layer)
  - `retained_1m/2m/3m`
  - `n_snapshots_observed` (count of months this customer appears in the panel)
  - `has_panel_gaps` (true if any expected monthly snapshot is missing — gaps can inflate
    time-to-adoption by making a flip appear one month late)
- **Facts:** `fct_customer` (grain: customer; TABLE) and `fct_customer_month` (grain:
  customer × months-since-acquisition; the card-holding panel — **materialized as a TABLE**,
  `partition by DATE_TRUNC(snapshot_month, MONTH)`, `cluster by acq_month, segmento`.
  ~13M rows; storage ~1–2 GB within BigQuery's 10 GB/mo free tier. Materialized as a TABLE
  to eliminate 3–8 s per-query scan cost on every Streamlit/semantic-layer call — the VIEW
  pattern from #1's `fct_loan_month` does NOT transfer here because #1's panel is ~2.2M rows
  while this is 13M.)
- **Dims:** `dim_customer` (junk dim — segment, income_band, age_band, province; no stable
  person key, documented like #1's `dim_borrower`), `dim_date`, `dim_channel` (obfuscated
  `canal_entrada` codes, labeled as segments).
- **Marts:**
  - `mart_adoption_curves` (cohort × months-since-acquisition cumulative adoption rate — the
    vintage triangle). Each row carries: `n_observed`, `fully_observed_n`,
    `is_cell_right_censored` (= `latest_snapshot_available < cohort_month + N months`,
    computed in dbt so the critic reads a field rather than re-deriving it).
  - `mart_cohort_adoption` (cohort × segment summary: adoption/retention/time-to-adoption +
    `n_right_censored`, `fully_observed_*` flags).
  - `mart_digest_cache` (see Digest cache above).
- dbt tests + docs on every model; every derived field documented.

### Semantic layer (governed metrics, defined once, consumed by BI + agents)
- `cohort_size` (count; lifetime) — customers acquired in the cohort.
- `adoption_rate` (rate; `msa_3/msa_6/msa_12`, lifetime) — card holders / cohort_size at N
  months-since-acquisition; filtered to `fully_observed` cohorts; **filter:
  `is_adopted_clean = TRUE`** (excludes left-censored customers from the numerator).
- `time_to_adoption` (ratio, months; lifetime) — avg months acq→first card; the delta is
  anchor-independent.
- `retention_rate` (rate; `ret_1m/2m/3m`) — still holding at +N months / adopted (monthly
  granularity — disclosed).
- `funnel_conversion` (rate; stage-pair windows `acquired_to_adopted`, `adopted_to_retained`).
- **Window enum** (funnel vocabulary, NOT #1's MOB): `msa_3, msa_6, msa_12` (months-since-
  acquisition), `ret_1m, ret_2m, ret_3m`, `acquired_to_adopted, adopted_to_retained`,
  `lifetime`. Each metric declares valid windows; invalid → structured error, not SQL.
- **Four governed tools:** `list_metrics`, `query_metric`, `compare_cohorts`,
  **`explain_metric`** (returns definition + valid windows + data caveats; lets the agents
  narrate honesty caveats without hallucinating — a dict lookup, $0).

### Copilot (reactive) + hardening
FastAPI + `gemini-flash-lite-latest` (AI Studio free tier; Vertex as documented prod path).
Single-agent function-calling for reactive Q&A (deliberately minimal — text-to-metric parity
is sufficient; Phase 3 effort concentrates on the proactive multi-agent layer); **ADK** for
the proactive multi-agent digest — both self-hosted in the same Cloud Run container (**NOT**
Vertex Agent Engine, which bills per vCPU-hour even idle and would break $0). Thin MCP
wrapper exposes the same governed tools to any MCP client. Hardening L1–L4 inherited
(on-topic router, input caps + `max_output_tokens`, per-IP + global rate limit, answer
cache) **plus context-caching** of the system prompt + metric catalog.

### Cost controls — $0/mo demo
Scale-to-zero Cloud Run (`min-instances=0`), `@st.cache_data` on BigQuery reads, **ADK
self-hosted (no Agent Engine)**, Gemini AI Studio free tier (1,500 req/day = hard $0
ceiling, no billing kill-switch), digest **pre-generated + cached** (a handful of LLM
calls once per cohort-month, trivially within free tier), GCS/Artifact Registry within free
tiers, raw CSV never committed, `make hydrate`/`trim`/`teardown`. Dataset (~13M rows but
compact monthly panel; `fct_customer_month` TABLE ~1–2 GB) fits the billing-account-wide
free tiers alongside #1. Dedicated GCP project **`card-acquisition-cockpit-2026`** on
`matirvazques@gmail.com`. **Terraform owns the serving layer only**; the data layer is left
as bootstrapped (so IaC can't destroy loaded data — #1's lesson).

## Phased plan
- **Phase 0 — Scaffold.** Repo (`card-acquisition-cockpit`), `.gitignore` committed FIRST
  (covering `.env`, `*service-account*.json`, `*credentials*.json`, `*.csv`, `*.parquet`,
  `__pycache__/`), ingestion CSV→GCS→BQ, README with the SCOPE BOUNDARY stated, dedicated
  GCP project `card-acquisition-cockpit-2026`. Git identity `matirvazques@gmail.com`.
  **Hard gate:** accept Kaggle competition rules under `matirvazques@gmail.com` before first
  public commit; inspect the actual panel for gap/left-censoring frequency before finalizing
  `is_adopted_clean` grain.
- **Phase 1 — BI core.** Airflow+Cosmos (local) from the start; dbt staging + adoption/cohort
  marts + tests + docs; Streamlit adoption vintage curves + funnel waterfall + cohort×segment
  heatmap. *Standalone analytics-eng piece.*
- **Phase 2 — Semantic layer.** The governed metrics above defined once; BI + agents share.
- **Phase 3 — Proactive multi-agent layer (primary differentiator).** The proactive ADK
  multi-agent digest (planner → analysts → deterministic critic gate → narrator) + early-
  warning + thin MCP wrapper + L1–L4 hardening. Reactive single-agent Q&A also wired in
  this phase but as a minimal secondary feature — no re-polishing beyond text-to-metric
  parity.
- **Phase 4 — Polish & deploy.** Cloud Run (`min-instances=0`), Terraform (serving layer),
  public live cockpit with the proactive insight panel leading the demo, `make
  hydrate/trim/teardown`, README with screenshots/GIF (the proactive digest + early-warning
  featured first, then adoption curves, waterfall, heatmap) + write-up. Cross-link from
  #1's README.

## Decisions (RESOLVED)
1. **Path A — Santander Product Recommendation** as the primary dataset; funnel reframed to
   **acquisition → card adoption → retention** (no approval stage; honest, real, observed).
2. **Separate public repo** `card-acquisition-cockpit`; continuity via shared landing/hub.
3. **Reuse #1's architecture DNA** (pattern, not code).
4. **Value lever = card-adoption lift** (cross-sell contribution), NOT approval rate.
5. **Proactive insight layer**: period selector + monthly digest, **pre-generated in Airflow**,
   defaulting to the latest fully-observed cohort at msa_6; served from cache ($0 serve-time).
6. **Multi-agent via Google ADK, self-hosted** in the Cloud Run container (NOT Vertex Agent
   Engine — it bills even idle). Multi-agent ONLY for the proactive digest; reactive Q&A stays
   single-agent (multi-agent there would be gratuitous). Critic agent = the honesty gate.
7. **Early-warning flags** on threshold breaches (deterministic detection + agent narration).
8. **`fct_customer_month` as a TABLE** (not a VIEW), partitioned by snapshot_month,
   clustered by acq_month and segmento. ~13M rows → 3–8 s per-query scan cost as a VIEW is
   unacceptable for a live cockpit. The VIEW pattern from #1 does NOT transfer (2.2M rows vs
   13M). Storage ~1–2 GB, within BQ free tier. `explain_metric` as the 4th governed tool.
   Channel (`canal_entrada`) as obfuscated segments. Airflow local.
9. **Fully-observed window = 6 months (primary).** msa_6 is the default for vintage curves
   and the proactive digest. msa_12 leaves only ~5 early-2015 cohorts — too thin for robust
   analysis; available but labeled. A cohort is fully observed at msa_N when
   `acq_month + N months <= May 2016`.
10. **Deterministic critic guards** (Python/SQL, not LLM): (a) right-censoring suppression
    using dbt flags; (b) min-n = 50 (suppress cells with cohort_size < 50, structured token);
    (c) materiality = `abs(delta) >= 2pp AND abs(delta) > 1.5 × rolling_SD(prior 3 cohorts)`,
    with 2pp-only fallback if fewer than 3 prior cohorts.
11. **Narrator architecture:** narrator receives ONLY the critic output struct (not raw analyst
    outputs); system prompt forbids causal claims; numeric-faithfulness Python check post-
    generation (mismatch blocks caching).
12. **License YELLOW — proceed with mitigations.** Raw CSVs not committed; `make hydrate`
    via Kaggle CLI; only aggregated outputs published; accept competition rules before
    download; honest provenance footer. Synthetic generator fallback available (MIT/CC0).
13. **Strategic identity: proactive multi-agent system, not cockpit #2.** Project lead is the
    proactive multi-agent layer + deterministic honesty gate. Reactive Q&A is secondary.
    Phase 3 effort concentrates on the proactive layer. "What is distinct from #1" section
    leads with the multi-agent differentiator.
14. Inherited from #1 unless a reason to change: Streamlit on Cloud Run, AI Studio free tier +
    `gemini-flash-lite-latest`, Terraform serving-only, MIT license, $0/mo, dedicated GCP
    project `card-acquisition-cockpit-2026`, secrets out, English everywhere, git identity
    `matirvazques@gmail.com`.

## Open items before/at Phase 0 (genuine remaining items only)
- **Accept Kaggle competition rules** under `matirvazques@gmail.com` before first public
  commit (mitigation #4 from the license resolution).
- **Inspect actual panel for gap/left-censoring frequency** at Phase 0 — before finalizing
  the `is_adopted_clean` grain in `int_customer_adoption_resolved`. If left-censoring is
  pervasive (e.g., >20% of customers already held the card at first observation) it may
  affect cohort definitions.

## Status
- Design/blueprint: **approved + review-fixed + strategically repositioned.**
  Confirmed decisions: 6-month fully-observed window, `fct_customer_month` as TABLE,
  deterministic critic guards, narrator architecture, license YELLOW with mitigations,
  proactive multi-agent as the project identity. Nothing built yet.
