from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ShenzhenWaterApi, ShenzhenWaterApiError
from .const import (
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ShenzhenWaterCoordinator(DataUpdateCoordinator):
    """Shenzhen Water data coordinator."""

    def __init__(
        self, hass, api: ShenzhenWaterApi, options: dict | None = None
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=_update_interval(options)),
        )
        self.api = api

    async def _async_update_data(self):
        try:
            return await self.api.async_get_all()
        except ShenzhenWaterApiError as err:
            raise UpdateFailed(str(err)) from err

    @property
    def bill(self) -> dict:
        data = self.data or {}
        current = data.get("current") or {}
        rows = current.get("data") or []
        if not rows:
            return {}
        return rows[0]

    @property
    def meter(self) -> dict:
        meters = self.bill.get("meterWaterUses") or []
        if not meters:
            return {}
        return meters[0]

    @property
    def previous_bill(self) -> dict:
        data = self.data or {}
        previous = data.get("previous") or {}
        rows = previous.get("data") or []
        if not rows:
            return {}
        return rows[0]

    @property
    def previous_meter(self) -> dict:
        meters = self.previous_bill.get("meterWaterUses") or []
        if not meters:
            return {}
        return meters[0]


def _update_interval(options: dict | None) -> int:
    """Return the polling interval in minutes.

    轮询间隔是唯一因人而异的设置，存在配置项 options 里（网页可改）；
    未设置时用内置默认值（6 小时，水务账单更新很慢）。
    """
    if not options:
        return DEFAULT_UPDATE_INTERVAL_MINUTES

    try:
        minutes = int(options.get(CONF_UPDATE_INTERVAL_MINUTES))
    except (TypeError, ValueError):
        return DEFAULT_UPDATE_INTERVAL_MINUTES

    return minutes if minutes > 0 else DEFAULT_UPDATE_INTERVAL_MINUTES
