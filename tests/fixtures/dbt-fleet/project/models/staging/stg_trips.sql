select trip_id, driver_id, vehicle_type, distance_km, cast(started_at as timestamp) as started_at
from {{ source('raw', 'trips') }}
where distance_km >= 0
