"""Constants for the Event Scout integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "event_scout"
LOGGER = logging.getLogger(__package__)

PLATFORMS: Final = ["calendar", "sensor", "binary_sensor"]

CONF_RADIUS_MILES: Final = "radius_miles"
CONF_HORIZON_DAYS: Final = "horizon_days"
CONF_UPDATE_INTERVAL_HOURS: Final = "update_interval_hours"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_VENDOR_LEAD_DAYS: Final = "vendor_lead_days"
CONF_RECONNAISSANCE_DAYS: Final = "reconnaissance_days"
CONF_DIGEST_TIME: Final = "digest_time"
CONF_CATEGORIES: Final = "categories"
CONF_TARGET_CALENDAR: Final = "target_calendar"
CONF_SOURCE_KIND: Final = "source_kind"

CONF_AREA_MODE: Final = "area_mode"
CONF_CITIES: Final = "cities"
CONF_COUNTIES: Final = "counties"
CONF_DISTANCE_METRIC: Final = "distance_metric"
CONF_DISTANCE_LIMIT: Final = "distance_limit"
CONF_ROAD_FACTOR: Final = "road_factor"
CONF_AVERAGE_SPEED_MPH: Final = "average_speed_mph"
CONF_OSRM_URL: Final = "osrm_url"

AREA_MODE_ANY: Final = "any"
AREA_MODE_ALL: Final = "all"
AREA_MODES: Final = [AREA_MODE_ANY, AREA_MODE_ALL]

DISTANCE_METRIC_STRAIGHT_LINE: Final = "straight_line"
DISTANCE_METRIC_DRIVING_MILES: Final = "driving_miles"
DISTANCE_METRIC_DRIVING_MINUTES: Final = "driving_minutes"
DISTANCE_METRICS: Final = [
    DISTANCE_METRIC_STRAIGHT_LINE,
    DISTANCE_METRIC_DRIVING_MILES,
    DISTANCE_METRIC_DRIVING_MINUTES,
]

DISTANCE_ORIGIN_STRAIGHT: Final = "straight"
DISTANCE_ORIGIN_ESTIMATED: Final = "estimated"
DISTANCE_ORIGIN_ROUTED: Final = "routed"

EXCLUDED_REASON_OUTSIDE_AREA: Final = "outside_area"
EXCLUDED_REASON_NO_COORDINATES: Final = "no_coordinates"
EXCLUDED_REASON_COUNTY_UNRESOLVED: Final = "county_unresolved"

DEFAULT_AREA_MODE: Final = AREA_MODE_ANY
DEFAULT_CITIES: Final[list[str]] = []
DEFAULT_COUNTIES: Final[list[str]] = []
DEFAULT_DISTANCE_METRIC: Final = DISTANCE_METRIC_STRAIGHT_LINE
DEFAULT_DISTANCE_LIMIT: Final = 50
DEFAULT_ROAD_FACTOR: Final = 1.3
DEFAULT_AVERAGE_SPEED_MPH: Final = 45
DEFAULT_OSRM_URL: Final = ""

CENSUS_GEOCODER_URL: Final = (
    "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
    "?x={lon}&y={lat}&benchmark=Public_AR_Current&vintage=Current_Current&format=json"
)
CENSUS_REQUEST_SPACING_SECONDS: Final = 0.5

OSRM_TABLE_PATH: Final = "/table/v1/driving/{coords}?sources=0&annotations=distance,duration"
OSRM_MAX_DESTINATIONS_PER_REQUEST: Final = 50
ROUTE_CACHE_MAX_AGE_DAYS: Final = 30

DEFAULT_RADIUS_MILES: Final = 50
DEFAULT_HORIZON_DAYS: Final = 90
DEFAULT_UPDATE_INTERVAL_HOURS: Final = 6
MIN_UPDATE_INTERVAL_HOURS: Final = 1
DEFAULT_VENDOR_LEAD_DAYS: Final = [30, 14, 3]
DEFAULT_RECONNAISSANCE_DAYS: Final = 240
DEFAULT_DIGEST_TIME: Final = "07:00"

SOURCE_TYPE: Final = "source"

SOURCE_KIND_ICS: Final = "ics"
SOURCE_KIND_JSONLD: Final = "jsonld"
SOURCE_KIND_TICKETMASTER: Final = "ticketmaster"
SOURCE_KIND_SOCRATA: Final = "socrata"
SOURCE_KIND_MANUAL: Final = "manual"
SOURCE_KIND_EVENTBRITE: Final = "eventbrite"

SOURCE_KINDS: Final = [
    SOURCE_KIND_ICS,
    SOURCE_KIND_JSONLD,
    SOURCE_KIND_TICKETMASTER,
    SOURCE_KIND_SOCRATA,
    SOURCE_KIND_MANUAL,
    SOURCE_KIND_EVENTBRITE,
]

CATEGORY_FESTIVAL: Final = "festival"
CATEGORY_FAMILY: Final = "family"
CATEGORY_CITY_ANNIVERSARY: Final = "city_anniversary"
CATEGORY_COMMUNITY: Final = "community"
CATEGORY_OTHER: Final = "other"

CATEGORIES: Final = [
    CATEGORY_FESTIVAL,
    CATEGORY_FAMILY,
    CATEGORY_CITY_ANNIVERSARY,
    CATEGORY_COMMUNITY,
    CATEGORY_OTHER,
]

VENDOR_AVAILABLE_YES: Final = "yes"
VENDOR_AVAILABLE_NO: Final = "no"
VENDOR_AVAILABLE_UNKNOWN: Final = "unknown"

VENDOR_ORIGIN_EXPLICIT: Final = "explicit"
VENDOR_ORIGIN_HEURISTIC: Final = "heuristic"
VENDOR_ORIGIN_MANUAL: Final = "manual"

ALERT_KIND_RECONNAISSANCE: Final = "reconnaissance"
ALERT_KIND_DEADLINE: Final = "deadline"
ALERT_KIND_OPENS: Final = "opens"

EVENT_SCOUT_DISMISS: Final = "EVENT_SCOUT_DISMISS"
EVENT_SCOUT_ADD_CAL: Final = "EVENT_SCOUT_ADD_CAL"

SERVICE_GET_DIGEST: Final = "get_digest"
SERVICE_SEND_DIGEST: Final = "send_digest"
SERVICE_SEND_ALERTS: Final = "send_alerts"
SERVICE_SET_VENDOR_INFO: Final = "set_vendor_info"
SERVICE_REFRESH: Final = "refresh"

ATTR_UID: Final = "uid"
ATTR_PERIOD: Final = "period"
ATTR_CATEGORIES: Final = "categories"

DIGEST_PERIOD_DAILY: Final = "daily"
DIGEST_PERIOD_WEEKLY: Final = "weekly"

STORE_VERSION: Final = 1
STORE_KEY_PREFIX: Final = "event_scout."

VENDOR_PROBE_PATHS: Final = ("/vendors", "/vendor-application", "/exhibitors", "/apply")

SOURCE_FETCH_TIMEOUT: Final = 30
