# Project status & next steps

Living tracker for the card-acquisition-funnel build. Read this first when resuming.
Full spec is in [BLUEPRINT.md](BLUEPRINT.md); decision log in [DECISIONS.md](DECISIONS.md).

_Last updated: 2026-07-21 — Phases 0, 1, 2 and 3 complete and pushed to `origin/main`. **Phase 3 fully verified end-to-end, including the live LLM path.** 84 offline agent tests + 18 semantic contract tests pass; deterministic spine + digest cache live-verified against BigQuery. The live Gemini smoke test (AI Studio free tier) now passes on all three paths: digest narrator (faithful, cached), copilot ADK tool-calling loop, and the FastAPI `/ask` + `/health` contract. Two real bugs the smoke test surfaced are fixed (see below). Nothing outstanding on Phase 3; Phase 4 (deploy) is next._

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

### Phase 2 — Semantic layer (governed metrics, defined once; BI + agents share)
- **Framework-neutral `semantic/` package** (D15): `windows.py` (MSA enum — `msa_3/6/12`, `ret_1m/2m/3m`, `acquired_to_adopted`/`adopted_to_retained`, `lifetime`), `errors.py` (`SemanticError`), `metrics.py` (registry), `layer.py` (the 4 governed tools). Zero web/LLM/MCP deps; Streamlit imports it directly; Phase-3 FastAPI/ADK/MCP will each wrap the same functions.
- **7 governed metrics**, defined once: `cohort_size`, `adoption_rate` (`msa_3/6/12`, `is_adopted_clean` numerator, fully-observed cells only), `adoption_rate_segment_adjusted` (D14 mix-hold via direct standardization — D16), `time_to_adoption`, `retention_rate` (`ret_1m/2m/3m`), `funnel_conversion` (`acquired_to_adopted`/`adopted_to_retained`), `segment_mix` (compositional). **Text-to-metric, never text-to-SQL.**
- **4 governed tools:** `list_metrics`, `query_metric`, `compare_cohorts` (rejects compositional metrics), `explain_metric` (definition + windows + honesty caveats, $0 lookup).
- **Supporting dbt mart** `mart_adoption_curves_by_segment` (acq_month×segmento×msa) — the grain `adoption_rate_segment_adjusted` needs. `dbt build` = 12/12 tests PASS on it; 11 offline semantic contract tests in `tests/test_semantic.py` PASS.
- Streamlit shows a "Governed metric definitions (semantic layer)" expander from `list_metrics()`.
- **Verified live (msa_6):** blended adoption falls 1.54%→0.24% (2015-01→2015-09, ~6.4x) but segment-adjusted only 0.84%→0.52% (~1.6x) — ~¾ of the top-line move is mix, confirming D14.

### Phase 3 — Proactive multi-agent layer + reactive copilot (complete, committed & pushed)
Runtime isolation: agent code runs in **`.venv-agents`** (Python 3.12, `google-adk` 1.18.0 + `google-genai` 1.46.0, protobuf 6.x), separate from **`.venv`** (Python 3.9, dbt/Streamlit/semantic, protobuf <6). Splitting them was forced — `google-adk` pulls protobuf 6.x and breaks Streamlit's pin. `agents/requirements.txt` lets `google-adk` resolve its own fastapi/uvicorn/genai stack.

- **3a — tools edge** (`agents/tools.py`): wraps the 4 governed `semantic/` tools with error-as-data + Gemini `TOOL_DECLARATIONS`; D17 `dimension="segmento"` returns per-segment `value` + `n`. No LLM.
- **3b — deterministic critic** (`agents/critic.py`, `agents/faithfulness.py`): right-censoring suppression (dbt flags) + min-n=50 + materiality (`abs(delta)>=2pp AND >1.5×rolling_SD(3 prior)`, 2pp fallback); numeric-faithfulness token check. Pure Python, offline-tested, built BEFORE any LLM code.
- **3c — deterministic digest pipeline** (`agents/planner.py` → `analysts.py` parallel → `critic` gate → `narrator.py`): only the narrator calls an LLM (via `google-genai` directly — D20). Narrator sees ONLY the critic struct; causality-prohibition prompt; faithfulness mismatch blocks caching. LLM injected as `Callable[[str], str]` → whole spine offline-testable. **Live-verified against BigQuery** with a stub LLM (cohort 2015-11 @ msa_6, 5 findings, critic_passed=True).
- **3d — digest cache** (`agents/digest_cache.py`, `agents/digest_job.py`, D18): `mart_digest_cache` created via `CREATE TABLE IF NOT EXISTS` (column `metric_window`, NOT reserved `window`), MERGE upsert keyed on `(cohort_month, dbt_run_id)`. Airflow `generate_digest` task added (`ingest >> transform >> generate_digest`, light `agents_venv`). Streamlit "Insight of the month" panel reads the cache ($0 serve-time), degrades to hidden when empty. **Upsert idempotency + Streamlit readback live-verified**, then smoke-row cleaned up.
- **3e — reactive copilot** (`agents/copilot.py`, `agents/api.py`, `agents/mcp_server.py`, `agents/hardening.py`): minimal single-agent text-to-metric. **ADK earns its place here** (D20) — `adk_generator` runs a genuine `LlmAgent` + `InMemoryRunner` tool-calling loop. FastAPI `POST /ask` (200 ok / 400 rejected / 429 rate-limited) + `GET /health`; thin FastMCP wrapper exposes the same 4 tools to any MCP client. Hardening L2 input cap → L1 on-topic router → L3 rate limit → L4 answer cache, all before the LLM.
- **Tests:** 84 pass in `.venv-agents` (planner/analysts/narrator/pipeline/digest_cache/hardening/copilot/api/mcp), including regression guards for the two smoke-test bugs below.
- **Live LLM smoke test — PASSED (2026-07-21)** on the AI Studio free-tier key. All three real-Gemini paths verified: (1) digest narrator → `faithful=True`, `cacheable=True`, real digest upserted to `mart_digest_cache` (cohort 2015-11 @ msa_6); (2) copilot `adk_generator` tool-calling loop → correct registry-resolved answer; (3) FastAPI `/health` 200 + `/ask` 200 (valid) / 400 (off-topic router). **Two real bugs the smoke test surfaced, now fixed + regression-tested:** (a) the narrator prompt handed the LLM *raw floats* (and coded segment labels like `01 - TOP`) while the faithfulness gate expected 2-decimal display tokens — every real narration failed the gate. Fixed by pre-formatting figures in `build_prompt` (`_display_finding`/`_display_suppressed`, stripping segment code prefixes) so the model copies the exact allowed tokens; the window number is now an allowed token too. (b) `tool_query_metric`'s `str | None` params broke ADK automatic function calling → the copilot returned an empty answer. Fixed by using simple `str = ""` params mapped back to `None` internally.
- **NOT implemented:** context-caching of system prompt + metric catalog (blueprint L1–L4 "plus context-caching") — only the L1–L4 core shipped. ADK `ContextCacheConfig` exists but was not wired (deferred, low value at this scale).

Commits pushed (Phases 0–2): `714b6e2` (scaffold), `f2cbcc9` (ingest/KGAT + STRING load), `48d3360` (dbt), `95d27c3` (Streamlit), `dde1eeb` (Airflow), `aa4f9ef` (Phase 2 semantic layer). **Phase 3 is committed & pushed.**

## Reproduce
`make hydrate` (accept Kaggle rules first) → `cd dbt && dbt deps && dbt build` → `streamlit run app/main.py`. Semantic contract tests: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_semantic.py`. **Agent-layer tests (Phase 3):** `PYTHONPATH=. .venv-agents/bin/python -m pytest tests/` (84 pass, no LLM/network). Live digest: `.venv-agents/bin/python -m agents.digest_job --run-id <id> --window msa_6` (real Gemini + BigQuery). Copilot API locally: `.venv-agents/bin/uvicorn agents.api:app` then `POST /ask`. MCP server: `.venv-agents/bin/python -m agents.mcp_server`. All live LLM paths need a real `GEMINI_API_KEY` in `.env` (see `.env.example`). Marts land in BigQuery dataset `analytics_marts`.

## Next steps

**Phase 3 is complete, committed, pushed and fully verified end-to-end (including the live Gemini path) — see the "Phase 3" block under Done above. Nothing outstanding on Phase 3.** Phase 4 (deploy) is next.
- Decisions taken in Phase 3: **D17** (`dimension="segmento"`), **D18** (`mart_digest_cache` owned by the job), **D19** (AI Studio free tier demo / Vertex documented prod path), **D20** (ADK in the copilot tool-calling loop; digest narrator uses `google-genai` directly → light Airflow venv). See DECISIONS.md.

### Phase 4 — Polish & deploy
- Cloud Run (`min-instances=0`), Terraform (serving layer only — data layer stays bootstrapped so IaC can't destroy loaded data), `make hydrate/trim/teardown`, README screenshots/GIF (proactive digest first), cross-link from #1.

## Lead narrative (chosen — see DECISIONS.md D14)
The story is **not** "adoption is low." The blended card-adoption rate falls ~7× across 2015 (Q1 2.61% → Q3 0.38%), but that's **mostly a composition illusion**: acquisition mix flips from ~85% PARTICULARES (H1-2015) to ~76% UNIVERSITARIO (H2-2015), and students adopt the card at ~0.18% regardless of income. Holding segment constant (PARTICULARES only) adoption still declines but far less — 2.65% → 1.47% (~1.8×), a modest *genuine* softening. So: dominant mix effect (Simpson's-paradox flavor) + a smaller real decline. Heterogeneity is large — ~16× by segment×income, ~4× by channel.

Narrative line: *"the blended funnel rate is a vanity metric — what moved is acquisition mix and channel quality, not the card offer."* Interview-defensible (standard portfolio mix decomposition), actionable (re-target PARTICULARES / high-income / best channels), and native fuel for the Phase 3 digest + critic (guard against naive top-line reads; surface the mix drift). Honesty caveat: within-segment decline rests on smaller n → narrate as directional; min-n guard still applies.
