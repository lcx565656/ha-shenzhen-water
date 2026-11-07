from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ShenzhenWaterApi,
    ShenzhenWaterApiError,
    ShenzhenWaterAuthError,
    ShenzhenWaterOpenIdError,
)
from .const import (
    CONF_CUSTOMER_CODE,
    CONF_OPENID,
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
    MAX_UPDATE_INTERVAL_MINUTES,
    MIN_UPDATE_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


def _clean(value: Any) -> str:
    """Normalize a user supplied value (复制粘贴常带引号/空格)。"""
    return str(value or "").strip().strip('"').strip("'").strip()


def _parse_interval(value: Any, errors: dict) -> int:
    """Validate the polling interval from user input."""
    if value in (None, ""):
        return DEFAULT_UPDATE_INTERVAL_MINUTES

    try:
        minutes = int(value)
    except (TypeError, ValueError):
        errors["base"] = "invalid_update_interval"
        return DEFAULT_UPDATE_INTERVAL_MINUTES

    if not MIN_UPDATE_INTERVAL_MINUTES <= minutes <= MAX_UPDATE_INTERVAL_MINUTES:
        errors["base"] = "invalid_update_interval"
        return DEFAULT_UPDATE_INTERVAL_MINUTES

    return minutes


class ShenzhenWaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Shenzhen Water.

    用户只需要填 OpenId：户号、Utoken、GUID 都会自动获取。
    """

    VERSION = 1

    def __init__(self) -> None:
        self._openid: str = ""
        self._accounts: list[dict[str, Any]] = []

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            openid = _clean(user_input.get(CONF_OPENID))

            if not openid:
                errors["base"] = "invalid_openid"
            else:
                api = ShenzhenWaterApi(
                    async_get_clientsession(self.hass),
                    customer_code="",
                    openid=openid,
                )

                try:
                    users = await api.async_get_users()
                except (ShenzhenWaterOpenIdError, ShenzhenWaterAuthError) as err:
                    _LOGGER.warning("OpenId 无效: %s", err)
                    errors["base"] = "invalid_openid"
                except ShenzhenWaterApiError as err:
                    _LOGGER.exception("读取绑定户号失败: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    accounts = [
                        account
                        for account in users.get("data") or []
                        if account.get("customerCode")
                    ]
                    if not accounts:
                        errors["base"] = "no_accounts"
                    elif len(accounts) == 1:
                        return await self._async_create_account_entry(
                            openid,
                            _clean(accounts[0].get("customerCode")),
                        )
                    else:
                        self._openid = openid
                        self._accounts = accounts
                        return await self.async_step_account()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_OPENID): str}),
            errors=errors,
        )

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry=None):
        """Return the options flow used to update OpenId later.

        参数保留成可选以兼容 HA 不同版本的调用签名；OptionsFlow 自己会拿到
        config_entry（新版属性 / 旧版 handler），所以不往里传。
        """
        return ShenzhenWaterOptionsFlow()

    async def async_step_account(self, user_input=None):
        """Let the user choose one account when OpenId has multiple bindings."""
        errors = {}

        account_options = {
            _clean(account.get("customerCode")): self._format_account(account)
            for account in self._accounts
            if account.get("customerCode")
        }

        if user_input is not None:
            customer_code = _clean(user_input.get(CONF_CUSTOMER_CODE))
            if customer_code not in account_options:
                errors["base"] = "cannot_connect"
            else:
                return await self._async_create_account_entry(
                    self._openid,
                    customer_code,
                )

        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CUSTOMER_CODE): vol.In(account_options),
                }
            ),
            errors=errors,
        )

    @staticmethod
    def _format_account(account: dict[str, Any]) -> str:
        customer_code = str(account.get("customerCode") or "")
        name = str(account.get("customerName") or "")
        address = str(account.get("address") or "")
        label_parts = [part for part in (customer_code, name, address) if part]
        return " - ".join(label_parts) or customer_code

    async def _async_create_account_entry(self, openid: str, customer_code: str):
        if not customer_code:
            return self.async_abort(reason="no_account_found")

        await self.async_set_unique_id(customer_code)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"深圳水务 {customer_code}",
            data={
                CONF_CUSTOMER_CODE: customer_code,
                CONF_OPENID: openid,
            },
        )


class ShenzhenWaterOptionsFlow(config_entries.OptionsFlow):
    """更新 OpenId / 轮询间隔，不用删掉集成重加。

    OpenId 可能因为换微信号、小程序重新授权而失效。以前只能删掉集成再加，
    实体 ID 和自动化都会断；这里让用户直接在网页上改。
    """

    async def async_step_init(self, user_input=None):
        errors = {}
        entry = self._entry()

        if user_input is not None:
            openid = _clean(user_input.get(CONF_OPENID))
            interval = _parse_interval(
                user_input.get(CONF_UPDATE_INTERVAL_MINUTES), errors
            )

            if not openid:
                errors["base"] = "invalid_openid"

            if not errors:
                api = ShenzhenWaterApi(
                    async_get_clientsession(self.hass),
                    customer_code=entry.data.get(CONF_CUSTOMER_CODE, ""),
                    openid=openid,
                )

                try:
                    await api.async_get_users()
                except (ShenzhenWaterOpenIdError, ShenzhenWaterAuthError) as err:
                    _LOGGER.warning("OpenId 无效: %s", err)
                    errors["base"] = "invalid_openid"
                except ShenzhenWaterApiError as err:
                    _LOGGER.exception("校验 OpenId 失败: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    # data 或 options 任一变化，HA 都会触发 update listener
                    # （见 __init__.py 注册的 reload），不需要手动重载。
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={**entry.data, CONF_OPENID: openid},
                    )

                    return self.async_create_entry(
                        title="",
                        data={CONF_UPDATE_INTERVAL_MINUTES: interval},
                    )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_OPENID, default=entry.data.get(CONF_OPENID, "")
                    ): str,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL_MINUTES,
                        default=entry.options.get(
                            CONF_UPDATE_INTERVAL_MINUTES,
                            DEFAULT_UPDATE_INTERVAL_MINUTES,
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_UPDATE_INTERVAL_MINUTES,
                            max=MAX_UPDATE_INTERVAL_MINUTES,
                        ),
                    ),
                }
            ),
            errors=errors,
        )

    def _entry(self):
        """Return the config entry this options flow belongs to."""
        entry = getattr(self, "config_entry", None)
        if entry is not None:
            return entry

        return self.hass.config_entries.async_get_entry(self.handler)
