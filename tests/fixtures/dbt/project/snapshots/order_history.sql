{% snapshot order_history %}
{{ config(target_schema='history', unique_key='order_id', strategy='timestamp', updated_at='updated_at') }}
select * from {{ source('shop', 'orders') }}
{% endsnapshot %}
