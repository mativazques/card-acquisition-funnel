-- Staging: cast, clean, rename. One row per customer x snapshot month.
-- ALL 48 source columns are STRING (loaded raw-as-text on purpose).
-- All casting, null-handling, and banding happen here so downstream models
-- only see typed, clean data.
--
-- Key cleaning decisions:
--   * fecha_dato / fecha_alta: parse from 'YYYY-MM-DD' string to DATE.
--   * age: strip leading spaces; 'NA' -> NULL; cast to INT64 then band.
--   * renta (income): strip spaces; 'NA' -> NULL; cast to FLOAT64 then band.
--   * antiguedad (seniority months): strip spaces; 'NA'/negative -> NULL.
--   * ind_tjcr_fin_ult1: the credit-card holding flag (0/1 string -> INT64).

with source as (

    select * from {{ source('santander', 'santander_customer_month') }}

),

renamed as (

    select
        -- keys
        cast(ncodpers as int64)                          as customer_id,
        parse_date('%Y-%m-%d', fecha_dato)               as snapshot_month,

        -- acquisition date (the cohort anchor)
        safe.parse_date('%Y-%m-%d', fecha_alta)          as fecha_alta,
        date_trunc(safe.parse_date('%Y-%m-%d', fecha_alta), month)
                                                         as acq_month,

        -- seniority (months as customer; messy — strip spaces, coerce negatives)
        case
            when trim(antiguedad) = 'NA'     then null
            when trim(antiguedad) = ''       then null
            when safe_cast(trim(antiguedad) as int64) < 0 then null
            else safe_cast(trim(antiguedad) as int64)
        end                                              as seniority_months,

        -- is_new_customer flag (raw string '0'/'1')
        safe_cast(ind_nuevo as int64)                    as is_new_customer,

        -- demographics: age
        case
            when trim(age) = 'NA' then null
            when trim(age) = ''   then null
            else safe_cast(trim(age) as int64)
        end                                              as age,

        -- age band (for junk dim and BI slicing)
        case
            when trim(age) = 'NA' or trim(age) = '' or age is null then 'unknown'
            when safe_cast(trim(age) as int64) < 18    then 'under_18'
            when safe_cast(trim(age) as int64) < 25    then '18_24'
            when safe_cast(trim(age) as int64) < 35    then '25_34'
            when safe_cast(trim(age) as int64) < 45    then '35_44'
            when safe_cast(trim(age) as int64) < 55    then '45_54'
            when safe_cast(trim(age) as int64) < 65    then '55_64'
            else                                             '65_plus'
        end                                              as age_band,

        -- income (renta): strip spaces, 'NA'/empty -> NULL
        case
            when trim(renta) = 'NA' then null
            when trim(renta) = ''   then null
            else safe_cast(trim(renta) as float64)
        end                                              as income,

        -- income band (EUR; approximate — Santander internal scale)
        case
            when trim(renta) = 'NA' or trim(renta) = '' or renta is null then 'unknown'
            when safe_cast(trim(renta) as float64) < 30000    then 'low'
            when safe_cast(trim(renta) as float64) < 80000    then 'mid'
            when safe_cast(trim(renta) as float64) < 150000   then 'high'
            else                                                    'very_high'
        end                                              as income_band,

        -- segment: 01 - VIP, 02 - Individuals, 03 - college graduates
        trim(segmento)                                   as segmento,

        -- acquisition channel (obfuscated 3-letter codes; never relabeled)
        trim(canal_entrada)                              as canal_entrada,

        -- geography
        trim(cod_prov)                                   as cod_prov,
        trim(nomprov)                                    as nomprov,

        -- country / residency flags
        trim(pais_residencia)                            as pais_residencia,
        trim(indresi)                                    as indresi,
        trim(indext)                                     as indext,

        -- activity flag
        safe_cast(ind_actividad_cliente as int64)        as is_active,

        -- employee indicator
        trim(ind_empleado)                               as ind_empleado,

        -- relationship type
        trim(indrel)                                     as indrel,
        trim(tiprel_1mes)                                as tiprel_1mes,

        -- THE funnel outcome: credit-card holding flag
        -- 1 = holds credit card in this snapshot month, 0 = does not
        safe_cast(ind_tjcr_fin_ult1 as int64)            as card_flag,

        -- keep raw for audit; other product flags kept for completeness
        ind_tjcr_fin_ult1                                as card_flag_raw

    from source
    -- drop rows with no customer or no snapshot date (safety filter)
    where ncodpers is not null
      and fecha_dato is not null

)

select * from renamed
