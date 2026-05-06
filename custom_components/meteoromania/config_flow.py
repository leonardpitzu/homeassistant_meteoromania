import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, CONF_COUNTY, COUNTY_KEYWORDS

_COUNTY_OPTIONS = [{"value": "", "label": "— None (show all) —"}] + [
    {"value": c, "label": c} for c in sorted(COUNTY_KEYWORDS)
]


class MeteoRomaniaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="MeteoRomania",
                data={},
                options={CONF_COUNTY: user_input.get(CONF_COUNTY, "")},
            )

        schema = vol.Schema({
            vol.Optional(CONF_COUNTY, default=""): vol.In(
                {c["value"]: c["label"] for c in _COUNTY_OPTIONS}
            ),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MeteoRomaniaOptionsFlow(config_entry)


class MeteoRomaniaOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._config_entry.options.get(CONF_COUNTY, "")
        schema = vol.Schema({
            vol.Optional(CONF_COUNTY, default=current): vol.In(
                {c["value"]: c["label"] for c in _COUNTY_OPTIONS}
            ),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
