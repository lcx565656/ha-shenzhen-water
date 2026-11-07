from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ShenzhenWaterApi
from .const import (
    CONF_CUSTOMER_CODE,
    CONF_OPENID,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ShenzhenWaterCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Shenzhen Water from a config entry."""
    session = async_get_clientsession(hass)

    api = ShenzhenWaterApi(
        session,
        customer_code=entry.data[CONF_CUSTOMER_CODE],
        openid=entry.data[CONF_OPENID],
    )

    coordinator = ShenzhenWaterCoordinator(hass, api, entry.options)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when data or options change (OpenId / 轮询间隔)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Shenzhen Water config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
