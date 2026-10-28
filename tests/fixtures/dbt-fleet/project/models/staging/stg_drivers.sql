{{ config(materialized='ephemeral') }}
select driver_id, full_name as driver_name, hired_on
from {{ source('raw', 'drivers') }}
