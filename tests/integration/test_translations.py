"""Every translation key the code uses must exist, and en.json must match.

None of this is checked at runtime: a missing key renders as a raw slug in the
UI, and strings.json and translations/en.json are two files that have to say
the same thing with nothing keeping them in step.
"""

import json
import re
from pathlib import Path

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.carlo_gavazzi_em300.entity_descriptions import (
    EM300_SENSOR_DESCRIPTIONS,
    PHASE_SEQUENCE_OPTIONS,
)

COMPONENT = Path("custom_components/carlo_gavazzi_em300")
STRINGS = json.loads((COMPONENT / "strings.json").read_text())
SENSOR_STRINGS = STRINGS["entity"]["sensor"]


def source(name: str) -> str:
    return (COMPONENT / name).read_text()


def test_en_json_matches_strings_json():
    # strings.json is the source; translations/en.json is its English copy.
    assert json.loads((COMPONENT / "translations/en.json").read_text()) == STRINGS


class TestSensorNames:
    @pytest.mark.parametrize(
        "description", EM300_SENSOR_DESCRIPTIONS, ids=lambda d: d.key
    )
    def test_every_description_has_a_name(self, description):
        assert description.translation_key, f"{description.key} has no translation key"
        assert description.translation_key in SENSOR_STRINGS
        assert SENSOR_STRINGS[description.translation_key].get("name")

    def test_there_are_no_orphaned_names(self):
        used = {d.translation_key for d in EM300_SENSOR_DESCRIPTIONS}
        assert set(SENSOR_STRINGS) == used

    def test_names_are_unique(self):
        names = [entry["name"] for entry in SENSOR_STRINGS.values()]
        assert len(names) == len(set(names))


class TestEnumStates:
    """An enum sensor's options each need a state translation."""

    @property
    def enum_descriptions(self):
        return [
            d
            for d in EM300_SENSOR_DESCRIPTIONS
            if d.device_class is SensorDeviceClass.ENUM
        ]

    def test_there_is_at_least_one_enum_sensor(self):
        assert self.enum_descriptions

    def test_every_option_has_a_state_translation(self):
        for description in self.enum_descriptions:
            states = SENSOR_STRINGS[description.translation_key].get("state", {})
            assert set(description.options or []) == set(states)

    def test_the_decoded_values_map_onto_the_declared_options(self):
        sequence = next(d for d in self.enum_descriptions if d.key == "phase_sequence")
        assert set(PHASE_SEQUENCE_OPTIONS.values()) == set(sequence.options or [])


class TestConfigFlow:
    """Steps, errors and abort reasons referenced from the flow source."""

    def test_every_step_shown_has_strings(self):
        steps = set(STRINGS["config"]["step"])
        shown = set(re.findall(r'step_id="([a-z_]+)"', source("config_flow.py")))
        # The transport steps are reached through a menu, so their ids are the
        # Transport values rather than literals in the source.
        shown |= {"serial", "tcp"}
        assert shown <= steps, f"missing strings for {shown - steps}"

    def test_every_menu_option_has_a_label(self):
        for step in ("user", "reconfigure"):
            options = STRINGS["config"]["step"][step]["menu_options"]
            assert set(options) == {"serial", "tcp"}

    def test_every_form_error_has_a_message(self):
        raised = set(re.findall(r'"base": "([a-z_]+)"', source("config_flow.py")))
        assert raised
        assert raised <= set(STRINGS["config"]["error"])

    def test_every_abort_reason_has_a_message(self):
        flow = source("config_flow.py")
        raised = set(re.findall(r'reason="([a-z_]+)"', flow))
        # _abort_if_unique_id_configured and async_update_reload_and_abort
        # use Home Assistant's default reasons without naming them.
        raised |= {"already_configured", "reconfigure_successful"}
        assert raised <= set(STRINGS["config"]["abort"])

    @pytest.mark.parametrize("step", ["serial", "tcp"])
    def test_every_field_is_labelled(self, step):
        # Fields without a label render as raw keys like "scan_interval".
        strings = STRINGS["config"]["step"][step]
        assert strings["data"]
        assert set(strings["data_description"]) <= set(strings["data"])


class TestSelectors:
    @pytest.mark.parametrize(
        ("key", "options"),
        [("parity", {"N", "E", "O"}), ("framer", {"socket", "rtu"})],
    )
    def test_every_dropdown_option_is_translated(self, key, options):
        assert set(STRINGS["selector"][key]["options"]) == options

    def test_every_translation_key_used_in_the_flow_exists(self):
        used = set(re.findall(r'translation_key="([a-z_]+)"', source("config_flow.py")))
        assert used <= set(STRINGS["selector"])


class TestExceptions:
    def test_every_raised_translation_key_has_a_message(self):
        raised = set(
            re.findall(r'translation_key="([a-z_]+)"', source("coordinator.py"))
        )
        assert raised
        assert raised <= set(STRINGS["exceptions"])

    def test_every_message_placeholder_is_supplied(self):
        # UpdateFailed(translation_placeholders={"error": ...}) in the
        # coordinator has to cover every {placeholder} in the message.
        coordinator = source("coordinator.py")
        for key, entry in STRINGS["exceptions"].items():
            placeholders = set(re.findall(r"\{([a-z_]+)\}", entry["message"]))
            for placeholder in placeholders:
                assert f'"{placeholder}"' in coordinator, (
                    f"exceptions.{key} uses {{{placeholder}}}, "
                    "which the coordinator never supplies"
                )
