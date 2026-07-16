-- Acquisition channel dimension. NOTE: Santander obfuscates all channel codes
-- (`canal_entrada` is a 3-letter code like 'KAT', 'KHE', etc.). The underlying
-- channel names (branch / web / telesales / etc.) are NOT disclosed in this
-- public dataset. Values are presented here as "channel segments", never
-- relabeled with inferred channel names — doing so would be fabricating labels.
-- See BLUEPRINT.md §Scope Boundary for the honesty rationale.

with base as (

    select distinct
        canal_entrada
    from {{ ref('stg_customer_month') }}

)

select
    {{ surrogate_key(['canal_entrada']) }}          as channel_key,
    coalesce(canal_entrada, 'unknown')              as channel_code,
    -- Label honest to the data: code only, not an inferred name
    coalesce(
        concat('channel_', lower(canal_entrada)),
        'channel_unknown'
    )                                               as channel_label
from base
