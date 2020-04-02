"""Support for Kamereon-supporting cars."""
from datetime import timedelta
import logging

import voluptuous as vol
from kamereon import NCISession

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.helpers import discovery
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util.dt import utcnow

DOMAIN = "kamereon"

DATA_KEY = DOMAIN

_LOGGER = logging.getLogger(__name__)

MIN_UPDATE_INTERVAL = timedelta(minutes=1)
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=5)

CONF_MANUFACTURER = 'manufacturer'
CONF_REGION = "region"

SIGNAL_STATE_UPDATED = f"{DOMAIN}.updated"

MANUFACTURERS = {
    'nissan': NCISession,
}

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_MANUFACTURER): vol.All(cv.string, [vol.In(MANUFACTURERS)]),
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): vol.All(cv.time_period, vol.Clamp(min=MIN_UPDATE_INTERVAL)),
                vol.Optional(CONF_REGION): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Set up the Kamereon component."""
    session = async_get_clientsession(hass)

    mfr_session_class = MANUFACTURERS[config[DOMAIN].get(CONF_MANUFACTURER)]
    kamereon_session = mfr_session_class(
        region=config[DOMAIN].get(CONF_REGION),
        session=session,
    )

    interval = config[DOMAIN][CONF_SCAN_INTERVAL]

    hass.data[DATA_KEY] = kamereon_session

    def discover_vehicle(vehicle):
        """Load relevant platforms."""

        for component in ('binary_sensor', 'climate', 'device_tracker', 'lock', 'sensor', 'switch'):
            hass.async_create_task(
                discovery.async_load_platform(
                    hass,
                    component,
                    DOMAIN,
                    vehicle,
                    config,
                )
            )

    async def update(now):
        """Update status from the online service."""
        try:

            for vehicle in kamereon_session.fetch_vehicles():
                vehicle.refresh()
                if vehicle.vin not in data.vehicles:
                    discover_vehicle(vehicle)

            async_dispatcher_send(hass, SIGNAL_STATE_UPDATED)

            return True
        finally:
            async_track_point_in_utc_time(hass, update, utcnow() + interval)

    _LOGGER.info("Logging in to service")
    kamereon_session.login(
        username=config[DOMAIN].get(CONF_USERNAME),
        password=config[DOMAIN].get(CONF_PASSWORD)
        )
    return await update(utcnow())


class KamereonEntity(Entity):
    """Base class for all Kamereon car entities."""

    def __init__(self, vehicle):
        """Initialize the entity."""
        self.vehicle = vehicle

    async def async_added_to_hass(self):
        """Register update dispatcher."""
        async_dispatcher_connect(
            self.hass, SIGNAL_STATE_UPDATED, self.async_schedule_update_ha_state
        )

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:car'

    @property
    def _entity_name(self):
        return NotImplemented

    @property
    def _vehicle_name(self):
        return self.vehicle.nickname

    @property
    def name(self):
        """Return full name of the entity."""
        return f"{self._vehicle_name} {self._entity_name}"

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def assumed_state(self):
        """Return true if unable to access real state of entity."""
        return True

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        return dict(
            'manufacturer': self.vehicle.session.tenant,
            'vin': self.vehicle.vin,
            'name': self.vehicle.nickname,
            'model': self.vehicle.model_name,
            'color': self.vehicle.color,
            'registration_number': self.vehicle.registration_number,
            'device_picture': self.vehicle.picture_url,
            'first_registration_date': self.vehicle.first_registration_date,
        )

    @property
    def device_info(self):
        return {
            'identifiers': (DOMAIN, self.vehicle.session.tenant, self.vehicle.vin),
            'manufacturer': self.vehicle.session.tenant,
            'vin': self.vehicle.vin,
        }