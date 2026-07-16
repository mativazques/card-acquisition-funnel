"""Cached read access to the analytics marts.

Every query is wrapped in @st.cache_data(ttl=3600): the dataset is static, so a
1-hour cache eliminates repeated BigQuery scans while a user explores the dashboard.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config import GCP_PROJECT, MARTS_DATASET, get_client, marts_table

_TTL = 3600


@st.cache_data(ttl=_TTL)
def load_adoption_curves() -> pd.DataFrame:
    """Vintage triangle — one row per (acq_month x msa).

    Powers visual 1: adoption curves with right-censoring awareness.
    """
    sql = f"""
        select
            acq_month,
            msa,
            as_of_month,
            n_observed,
            n_adopted_clean,
            adoption_rate,
            is_cell_right_censored,
            fully_observed_n
        from {marts_table('mart_adoption_curves')}
        order by acq_month, msa
    """
    df = get_client().query(sql).to_dataframe()
    # acq_month arrives as datetime.date objects (dbdate); convert to string label
    df["acq_month_label"] = df["acq_month"].astype(str).str[:7]
    return df


@st.cache_data(ttl=_TTL)
def load_funnel_counts() -> pd.DataFrame:
    """Funnel waterfall counts from fct_customer.

    Grain: one aggregate row with three stage counts:
      acquired  = is_within_panel_cohort = true
      adopted   = is_adopted_clean = true (within panel cohort)
      retained  = retained_3m = true (within adopted)
    """
    sql = f"""
        select
            countif(is_within_panel_cohort) as acquired,
            countif(is_within_panel_cohort and is_adopted_clean) as adopted,
            countif(is_within_panel_cohort and is_adopted_clean and retained_3m) as retained_3m
        from `{GCP_PROJECT}.{MARTS_DATASET}.fct_customer`
    """
    return get_client().query(sql).to_dataframe()


@st.cache_data(ttl=_TTL)
def load_cohort_heatmap() -> pd.DataFrame:
    """Cohort x segment adoption rates for the heatmap visual.

    Filtered to fully_observed_6 = true so partially-observed cohorts
    are not shown as final rates.
    """
    sql = f"""
        select
            acq_month,
            segmento,
            cohort_size,
            n_adopted,
            adoption_rate,
            fully_observed_6,
            fully_observed_12,
            n_right_censored
        from {marts_table('mart_cohort_adoption')}
        where fully_observed_6 = true
        order by acq_month, segmento
    """
    df = get_client().query(sql).to_dataframe()
    df["acq_month_label"] = df["acq_month"].astype(str).str[:7]
    return df
