{{ config(alias='fact_trips', meta={'owner': 'ops-analytics'}) }}
with t as (
    select * from {{ ref('stg_trips') }}
)
select
    t.trip_id,
    t.driver_id,
    d.driver_name,
    t.distance_km,
    v.capacity as vehicle_capacity,
    t.started_at,
    cast(t.started_at as date) as trip_date
from t
join {{ ref('stg_drivers') }} as d on d.driver_id = t.driver_id
join {{ ref('vehicle_types') }} as v on v.vehicle_type = t.vehicle_type
