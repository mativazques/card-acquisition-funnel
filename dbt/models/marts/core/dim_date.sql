-- Month-grain calendar dimension. Range covers the Santander panel
-- (Jan 2015) plus enough runway for the msa_12 window (May 2016 + 12 months).
-- Used as the time axis for snapshot_month and acq_month lookups.

with months as (

    select date_month
    from unnest(generate_date_array('2015-01-01', '2017-12-01', interval 1 month)) as date_month

)

select
    cast(format_date('%Y%m', date_month) as int64)  as date_key,
    date_month,
    extract(year    from date_month)                as year,
    extract(quarter from date_month)                as quarter,
    extract(month   from date_month)                as month,
    concat(
        cast(extract(year from date_month) as string), '-Q',
        cast(extract(quarter from date_month) as string)
    )                                               as year_quarter,
    format_date('%b-%Y', date_month)                as month_label
from months
