"""Config flow for the Carlo Gavazzi EM/ET300 energy meter integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api.device import Em300Device, Em300DeviceInfo
from .api.exception import Em300Exception, ModbusPortException
from .connection import client_from_config
from .const import (
    BAUDRATE_OPTIONS,
    BYTESIZE_OPTIONS,
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_FIRMWARE,
    CONF_FRAMER,
    CONF_MODEL,
    CONF_PARITY,
    CONF_SERIAL_NUMBER,
    CONF_SERIAL_PORT,
    CONF_STOPBITS,
    CONF_TRANSPORT,
    DEFAULT_ADDRESS,
    DEFAULT_BAUDRATE,
    DEFAULT_BYTESIZE,
    DEFAULT_FRAMER,
    DEFAULT_PARITY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STOPBITS,
    DEFAULT_TCP_PORT,
    DOMAIN,
    MAX_ADDRESS,
    MAX_SCAN_INTERVAL,
    MIN_ADDRESS,
    MIN_SCAN_INTERVAL,
    STOPBITS_OPTIONS,
    FramerOption,
    ParityOption,
    Transport,
)
from .options_flow import Em300OptionsFlowHandler

_LOGGER = logging.getLogger(__name__)


def _int_box(minimum: int, maximum: int) -> vol.All:
    """A numeric text box validated to an ``int`` in ``[minimum, maximum]``."""
    return vol.All(
        selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=minimum,
                max=maximum,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Coerce(int),
    )


def _select(options: list[str], translation_key: str) -> selector.SelectSelector:
    """A translated dropdown over a fixed set of string options."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=translation_key,
        )
    )


def _int_select(options: list[int]) -> vol.All:
    """A dropdown over a fixed set of integers, coerced back to ``int``."""
    return vol.All(
        selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[str(option) for option in options],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Coerce(int),
    )


def _common_schema(defaults: dict[str, Any]) -> dict:
    """The address and scan-interval fields shared by both transports."""
    return {
        vol.Required(
            CONF_ADDRESS, default=defaults.get(CONF_ADDRESS, DEFAULT_ADDRESS)
        ): _int_box(MIN_ADDRESS, MAX_ADDRESS),
        vol.Required(
            CONF_SCAN_INTERVAL,
            default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ): _int_box(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL),
    }


def serial_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the RS485 connection form."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_SERIAL_PORT, default=defaults.get(CONF_SERIAL_PORT, "")
            ): selector.TextSelector(),
            vol.Required(
                CONF_BAUDRATE, default=defaults.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)
            ): _int_select(BAUDRATE_OPTIONS),
            vol.Required(
                CONF_PARITY, default=defaults.get(CONF_PARITY, DEFAULT_PARITY)
            ): _select(list(ParityOption), "parity"),
            vol.Required(
                CONF_STOPBITS, default=defaults.get(CONF_STOPBITS, DEFAULT_STOPBITS)
            ): _int_select(STOPBITS_OPTIONS),
            vol.Required(
                CONF_BYTESIZE, default=defaults.get(CONF_BYTESIZE, DEFAULT_BYTESIZE)
            ): _int_select(BYTESIZE_OPTIONS),
            **_common_schema(defaults),
        }
    )


def tcp_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the Modbus-over-TCP connection form."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_HOST, default=defaults.get(CONF_HOST, "")
            ): selector.TextSelector(),
            vol.Required(
                CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_TCP_PORT)
            ): _int_box(1, 65535),
            vol.Required(
                CONF_FRAMER, default=defaults.get(CONF_FRAMER, DEFAULT_FRAMER)
            ): _select(list(FramerOption), "framer"),
            **_common_schema(defaults),
        }
    )


class Em300ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup of an EM/ET300 meter."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise config flow state."""
        self._transport = Transport.SERIAL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> Em300OptionsFlowHandler:
        """Return the options flow for adjusting the poll interval."""
        return Em300OptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask how the meter is reached."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[Transport.SERIAL, Transport.TCP],
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect and validate RS485 connection settings."""
        return await self._async_step_transport(
            Transport.SERIAL, serial_schema, user_input
        )

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect and validate Modbus TCP connection settings."""
        return await self._async_step_transport(
            Transport.TCP, tcp_schema, user_input
        )

    async def _async_step_transport(
        self,
        transport: Transport,
        schema_builder,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Show a transport form, then try to talk to the meter behind it."""
        self._transport = transport

        if user_input is None:
            return self.async_show_form(
                step_id=transport, data_schema=schema_builder()
            )

        data = {CONF_TRANSPORT: transport, **user_input}

        try:
            info = await self._async_probe(data)
        except ModbusPortException as err:
            _LOGGER.debug("Serial port rejected: %s", err)
            errors = {"base": "invalid_port"}
        except (Em300Exception, OSError, TimeoutError) as err:
            _LOGGER.debug("Could not reach the meter: %s", err)
            errors = {"base": "cannot_connect"}
        else:
            return await self._async_create_entry(data, info)

        return self.async_show_form(
            step_id=transport,
            data_schema=schema_builder(user_input),
            errors=errors,
        )

    async def _async_probe(self, data: dict[str, Any]) -> Em300DeviceInfo:
        """Connect to the meter described by ``data`` and identify it.

        The connection is always closed again; setup opens its own.
        """
        device = Em300Device(client_from_config(data))
        try:
            await device.connect()
            return await device.identify()
        finally:
            device.close()

    async def _async_create_entry(
        self, data: dict[str, Any], info: Em300DeviceInfo
    ) -> ConfigFlowResult:
        """Record what the meter reported and create the entry."""
        unique_id = info.serial_number or self._fallback_unique_id(data)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        name = f"{info.model} {info.serial_number}".strip() if (
            info.serial_number
        ) else info.model

        data = {
            **data,
            CONF_NAME: name,
            CONF_MODEL: info.model,
            CONF_SERIAL_NUMBER: info.serial_number,
            CONF_FIRMWARE: info.firmware,
        }
        return self.async_create_entry(title=name, data=data)

    @staticmethod
    def _fallback_unique_id(data: dict[str, Any]) -> str:
        """Identify the meter by where it lives when it has no serial number.

        Older meters do not implement the serial-number block. Two meters on
        the same bus still differ by Modbus address, and two buses differ by
        port or host, so this stays unique in practice.
        """
        address = data.get(CONF_ADDRESS, DEFAULT_ADDRESS)
        if data[CONF_TRANSPORT] == Transport.TCP:
            return f"{data[CONF_HOST]}:{data[CONF_PORT]}:{address}"
        return f"{data[CONF_SERIAL_PORT]}:{address}"
