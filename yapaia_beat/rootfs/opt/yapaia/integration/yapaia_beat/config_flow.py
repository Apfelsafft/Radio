"""Config flow: Supervisor discovery (one click) or manual host/port."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

try:
    from homeassistant.helpers.service_info.hassio import HassioServiceInfo
except ImportError:  # HA < 2025.1
    from homeassistant.components.hassio import HassioServiceInfo  # type: ignore[no-redef]

from .const import DEFAULT_HOST, DEFAULT_PORT, DOMAIN


class YapaiaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    async def _test(self, host: str, port: int) -> bool:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(f"http://{host}:{port}/api/info", timeout=aiohttp.ClientTimeout(total=5)) as r:
                return r.status == 200 and (await r.json()).get("name") == "Yapaia Beat"
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return False

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if await self._test(user_input[CONF_HOST], user_input[CONF_PORT]):
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(title="Yapaia Beat", data=user_input)
            errors["base"] = "cannot_connect"
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, DEFAULT_HOST)): str,
                vol.Required(CONF_PORT, default=(user_input or {}).get(CONF_PORT, DEFAULT_PORT)): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        data = {CONF_HOST: discovery_info.config["host"], CONF_PORT: int(discovery_info.config["port"])}
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured(updates=data)
        self._discovered = data
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            if not await self._test(self._discovered[CONF_HOST], self._discovered[CONF_PORT]):
                return self.async_abort(reason="cannot_connect")
            return self.async_create_entry(title="Yapaia Beat", data=self._discovered)
        return self.async_show_form(step_id="hassio_confirm")
