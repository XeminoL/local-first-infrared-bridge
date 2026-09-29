import asyncio
import time

from bridge import (CALIBRATE_SERVICE, DELETE_CODE_SERVICE, GET_CODE_SERVICE, LAST_CAPTURE_SERVICE, LEARN_SERVICE,
                    LEARNER_STATUS, SEND_RAW_DOMAIN, SEND_RAW_SERVICE)

LEARN_PROMPT_PREFIX = "point the remote"
LEARNED_PREFIX = "learned "
ANSWER_TIMEOUT_S = 15.0
LEARN_ATTEMPTS = 2
RETRY_PAUSE_S = 2.0


async def learn(ha, name, timings_to_send=None, attempts=LEARN_ATTEMPTS):
    for _ in range(attempts):
        learned, status = await learn_once(ha, name, timings_to_send)
        if learned or timings_to_send is None:
            return learned, status
        await asyncio.sleep(RETRY_PAUSE_S)
    return learned, status


async def learn_once(ha, name, timings_to_send):
    ha.drain_events()
    await ha.call(SEND_RAW_DOMAIN, LEARN_SERVICE, name=name)
    deadline = time.perf_counter() + ANSWER_TIMEOUT_S
    while True:
        change = await ha.next_state(LEARNER_STATUS, deadline)
        if change is None:
            return False, "no answer from the learner"
        status = change[1]["state"]
        if not status.startswith(LEARN_PROMPT_PREFIX):
            return status.startswith(LEARNED_PREFIX), status
        if timings_to_send is not None:
            await ha.call(SEND_RAW_DOMAIN, SEND_RAW_SERVICE, timings=signed(timings_to_send))


async def fetch(ha, name):
    response = await ha.call_for_response(SEND_RAW_DOMAIN, GET_CODE_SERVICE, name=name)
    return [abs(value) for value in response.get("timings", [])]


async def fetch_last_capture(ha):
    response = await ha.call_for_response(SEND_RAW_DOMAIN, LAST_CAPTURE_SERVICE)
    return [abs(value) for value in response.get("timings", [])]


async def forget(ha, name):
    await ha.call(SEND_RAW_DOMAIN, DELETE_CODE_SERVICE, name=name)


def signed(timings):
    return [value if index % 2 == 0 else -value for index, value in enumerate(timings)]


async def calibrate(ha):
    ha.drain_events()
    await ha.call(SEND_RAW_DOMAIN, CALIBRATE_SERVICE)
    change = await ha.next_state(LEARNER_STATUS, time.perf_counter() + ANSWER_TIMEOUT_S)
    return change[1]["state"] if change else "no answer from the learner"
