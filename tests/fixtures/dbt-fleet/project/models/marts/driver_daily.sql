{{ config(materialized='incremental', unique_key=['driver_id', 'trip_date']) }}
select driver_id, trip_date, sum(distance_km) as total_km, count(*) as trip_count
from {{ ref('fct_trips') }}
{% if is_incremental() %}
where trip_date >= (select max(trip_date) from {{ this }})
{% endif %}
group by driver_id, trip_date
