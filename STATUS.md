# Project status & next steps

Living tracker for the card-acquisition-funnel build. Read this first when resuming.
Full spec is in [BLUEPRINT.md](BLUEPRINT.md); decision log in [DECISIONS.md](DECISIONS.md).

_Last updated: 2026-07-16 — Phases 0 and 1 complete and pushed to `origin/main`._

## Done

### Phase 0 — Scaffold + ingest + panel gate
- Repo scaffolded; `.gitignore` covers `.env`, `profiles.yml`, `target/`, `dbt_packages/`, venvs, CSVs.
- GCP project `card-acquisition-funnel-2026` (on `matirvazques@gmail.com`), GCS bucket `card-acquisition-funnel-raw` (US), BigQuery + Storage APIs enabled, ADC configured.
- Kaggle competition rules accepted. Ingest uses the **new KGAT bearer token** via the REST API (the pip `kaggle` lib only supports the legacy user+key). Token lives in `~/.kaggle/access_token` (never committed).
- Raw loaded: `card-acquisition-funnel-2026.raw.santander_customer_month` — **13,647,309 rows, 956,645 customers, 17 monthly snapshots** (2015-01 … 2016-05). All 48 columns loaded as **STRING** (BQ autodetect fails on the mixed-format Santander panel; casting happens in dbt staging).
- **Panel inspection gate — PASSED.** Within-panel acquirees (cohort universe) ≈ **155k (16.2%)**; left-censoring on the card = **0.06%** (well below the 20% abort threshold); monthly gaps = 0.84%. Before-panel acquirees (83%) are left-truncated and excluded from vintage curves. This validated the `is_adopted_clean` grain.

### Phase 1 — BI core (dbt + Streamlit + Airflow)
- **dbt dimensional model** (`dbt/models/`): staging (view) → `int_customer_adoption_resolved` (ephemeral) → dims + facts + analytics marts. `fct_customer_month` is a **TABLE** (13.6M rows) partitioned by `snapshot_month`, clustered by `acq_month, segmento`. Vintage triangle `mart_adoption_curves` carries `is_cell_right_censored` / `fully_observed_n` computed in dbt. **`dbt build` = 65/65 tests PASS.**
- **Streamlit BI** (`app/`): 3 tabs — adoption vintage curves (right-censored cells dashed + "fully-observed only" toggle), funnel waterfall (acquired→adopted→retained), cohort×segment heatmap. Visually QA'd in-browser, no console errors.
- **Airflow (local, Astro + Cosmos)** (`airflow/`): DAG `card_acquisition_pipeline` = `ingest >> dbt`. Cosmos renders one task per dbt model + its tests. **Verified by a real Cosmos render (`dbt ls`) → 18 tasks**, not just `py_compile`.

Commits pushed: `714b6e2` (scaffold), `f2cbcc9` (ingest/KGAT + STRING load), `48d3360` (dbt), `95d27c3` (Streamlit), `dde1eeb` (Airflow).

## Reproduce
`make hydrate` (accept Kaggle rules first) → `cd dbt && dbt deps && dbt build` → `streamlit run app/main.py`. Env from `.env` (see `.env.example`). Marts land in BigQuery dataset `analytics_marts`.

## Next steps

### Phase 2 — Semantic layer (governed metrics, defined once; BI + agents share)
- Define 5 metrics: `cohort_size`, `adoption_rate` (windows `msa_3/6/12`, filter `is_adopted_clean=TRUE`), `time_to_adoption`, `retention_rate` (`ret_1m/2m/3m`), `funnel_conversion`.
- 4 governed tools: `list_metrics`, `query_metric`, `compare_cohorts`, `explain_metric`. **Text-to-metric, never text-to-SQL.** Window enum is MSA vocabulary (`msa_3/6/12`, `ret_*`, `lifetime`), NOT #1's MOB.
- Open design question: is the semantic layer a FastAPI module (like flagship #1) or an MCP-native definition file that both FastAPI and the ADK agents consume? Decide before building.

### Phase 3 — Proactive multi-agent layer (the primary differentiator)
- Google ADK self-hosted (same Cloud Run container, NOT Vertex Agent Engine): planner → analysts → **deterministic critic gate** → narrator.
- Critic guards (Python/SQL, not LLM): (a) right-censoring suppression via dbt flags; (b) min-n = 50; (c) materiality = `abs(delta) >= 2pp AND > 1.5×rolling_SD(prior 3 cohorts)`.
- Digest pre-generated in Airflow for the latest fully-observed cohort at msa_6, served from `mart_digest_cache` ($0 serve-time). Narrator sees only the critic struct; numeric-faithfulness check blocks caching on mismatch.
- Reactive single-agent Q&A wired here too, but minimal (text-to-metric parity only).

### Phase 4 — Polish & deploy
- Cloud Run (`min-instances=0`), Terraform (serving layer only — data layer stays bootstrapped so IaC can't destroy loaded data), `make hydrate/trim/teardown`, README screenshots/GIF (proactive digest first), cross-link from #1.

## Analytical note (for the digest to narrate honestly)
Card adoption is genuinely low (~1,100 clean adopters of 155k within-panel; msa_6 rates ~0.2–1.7%) — it's cross-sell of one specific card over a short window. There's a real signal: a 4–5× step-down in adoption from early- to late-2015 cohorts. That's material for the Phase 3 digest.
