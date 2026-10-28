{% snapshot driver_history %}
{{ config(target_schema='snapshots', unique_key='driver_id', strategy='check', check_cols=['full_name']) }}
select driver_id, full_name from {{ source('raw', 'drivers') }}
{% endsnapshot %}
