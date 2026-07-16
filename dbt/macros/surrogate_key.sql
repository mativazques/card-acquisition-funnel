{#- Deterministic surrogate key: MD5 over pipe-joined, null-safe fields.
    Kept local so the project has no external package dependency. -#}
{% macro surrogate_key(fields) %}
to_hex(md5(concat(
    {%- for f in fields %}
    coalesce(cast({{ f }} as string), '_null_'){% if not loop.last %}, '|',{% endif %}
    {%- endfor %}
)))
{%- endmacro %}
