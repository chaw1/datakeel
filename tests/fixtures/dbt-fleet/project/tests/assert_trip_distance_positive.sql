{{ config(severity='warn') }}
select trip_id from {{ source('raw', 'trips') }} where distance_km < 0
