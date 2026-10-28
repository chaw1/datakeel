{{ config(alias='Orders Daily', tags=['finance'], meta={'owner': 'Finance'}) }}
select order_id, amount, ordered_at, updated_at
from {{ source('shop', 'orders') }}
