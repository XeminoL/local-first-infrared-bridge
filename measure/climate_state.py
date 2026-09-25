import asyncio

from bridge import REMOTE_CLIMATE, VIRTUAL_CLIMATE

FIELDS = ("hvac_mode", "temperature", "fan_mode", "swing_mode")
SERVICES = {
    "hvac_mode": "set_hvac_mode",
    "temperature": "set_temperature",
    "fan_mode": "set_fan_mode",
    "swing_mode": "set_swing_mode",
}
TEMPERATURE_MODES = {"cool", "heat", "heat_cool"}
TEMPERATURE_TOLERANCE = 0.01
SETTLE_S = 1.5


def observed(state):
    attributes = state.get("attributes", {})
    return {
        "hvac_mode": state.get("state"),
        "temperature": attributes.get("temperature"),
        "fan_mode": attributes.get("fan_mode"),
        "swing_mode": attributes.get("swing_mode"),
    }


def compared_fields(state):
    fields = ["hvac_mode"]
    if state["hvac_mode"] != "off":
        fields += ["fan_mode", "swing_mode"]
    if state["hvac_mode"] in TEMPERATURE_MODES:
        fields.append("temperature")
    return fields


def matches(expected, seen, fields=None):
    for field in fields or expected.keys():
        want, got = expected[field], seen.get(field)
        if field == "temperature":
            if got is None or abs(float(got) - float(want)) > TEMPERATURE_TOLERANCE:
                return False
        elif got != want:
            return False
    return True


async def command(ha, field, value):
    await ha.call("climate", SERVICES[field], REMOTE_CLIMATE, **{field: value})


async def apply_state(ha, state):
    for field in FIELDS:
        await command(ha, field, state[field])
        await asyncio.sleep(SETTLE_S)
    return await virtual_state(ha)


async def virtual_state(ha):
    return observed((await ha.states())[VIRTUAL_CLIMATE])


async def wait_for_virtual(ha, expected, deadline, fields=None):
    last_seen = None
    while True:
        reply = await ha.next_state(VIRTUAL_CLIMATE, deadline)
        if reply is None:
            return ("wrong" if last_seen else "missed"), None, last_seen
        received_at, new_state = reply
        last_seen = observed(new_state)
        if matches(expected, last_seen, fields):
            return "match", received_at, last_seen
