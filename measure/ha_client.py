import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager

import aiohttp

DEFAULT_HA_URL = "http://localhost:8123"
WEBSOCKET_PATH = "/api/websocket"
CLOSED_MESSAGE = "Home Assistant websocket closed"


def websocket_url():
    base = os.environ.get("HA_URL", DEFAULT_HA_URL).rstrip("/")
    return base.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + WEBSOCKET_PATH


class HomeAssistant:
    def __init__(self, ws):
        self.ws = ws
        self.next_id = 1
        self.pending = {}
        self.events = asyncio.Queue()
        self.closed = False

    async def request(self, payload):
        if self.closed:
            raise ConnectionError(CLOSED_MESSAGE)
        message_id = self.next_id
        self.next_id += 1
        future = asyncio.get_running_loop().create_future()
        self.pending[message_id] = future
        await self.ws.send_json({"id": message_id, **payload})
        reply = await future
        if not reply.get("success", False):
            raise RuntimeError(f"Home Assistant rejected {payload['type']}: {reply.get('error')}")
        return reply.get("result")

    async def listen(self):
        async for message in self.ws:
            if message.type != aiohttp.WSMsgType.TEXT:
                break
            data = message.json()
            if data.get("type") == "event":
                self.events.put_nowait((time.perf_counter(), data["event"]))
            elif data.get("id") in self.pending:
                self.pending.pop(data["id"]).set_result(data)
        self.closed = True
        for future in self.pending.values():
            if not future.done():
                future.set_exception(ConnectionError(CLOSED_MESSAGE))
        self.pending.clear()

    def drain_events(self):
        while not self.events.empty():
            self.events.get_nowait()

    async def states(self):
        return {state["entity_id"]: state for state in await self.request({"type": "get_states"})}

    async def call(self, domain, service, entity_id=None, **data):
        payload = {"type": "call_service", "domain": domain, "service": service, "service_data": data}
        if entity_id:
            payload["target"] = {"entity_id": entity_id}
        await self.request(payload)

    async def services(self, domain):
        return (await self.request({"type": "get_services"})).get(domain, {})

    async def next_state(self, entity_id, deadline):
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return None
            try:
                received_at, event = await asyncio.wait_for(self.events.get(), remaining)
            except asyncio.TimeoutError:
                return None
            new_state = event.get("data", {}).get("new_state") or {}
            if new_state.get("entity_id") == entity_id:
                return received_at, new_state


async def authenticate(ws, token):
    greeting = await ws.receive_json()
    if greeting.get("type") != "auth_required":
        raise RuntimeError(f"Unexpected greeting: {greeting}")
    await ws.send_json({"type": "auth", "access_token": token})
    answer = await ws.receive_json()
    if answer.get("type") != "auth_ok":
        raise RuntimeError("Authentication failed. Check HA_TOKEN.")


async def require_entities(ha, *entities):
    states = await ha.states()
    for entity in entities:
        if entity not in states:
            domain = entity.split(".")[0]
            candidates = sorted(e for e in states if e.startswith(domain + ".ir_bridge"))
            raise RuntimeError(f"{entity} not found. IR Bridge {domain} entities: {candidates or 'none'}")
        if states[entity]["state"] == "unavailable":
            raise RuntimeError(f"{entity} is unavailable. Is the ESP32 online?")
    return states


@asynccontextmanager
async def connect():
    token = os.environ.get("HA_TOKEN")
    if not token:
        sys.exit("Set HA_TOKEN to a Home Assistant long-lived access token.")
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(websocket_url()) as ws:
            await authenticate(ws, token)
            ha = HomeAssistant(ws)
            listener = asyncio.create_task(ha.listen())
            try:
                await ha.request({"type": "subscribe_events", "event_type": "state_changed"})
                yield ha
            finally:
                listener.cancel()


def run_script(main):
    try:
        asyncio.run(main())
    except aiohttp.ClientConnectorError:
        sys.exit(f"cannot reach Home Assistant at {websocket_url()}. Is it running? Set HA_URL if it is elsewhere.")
    except (ConnectionError, RuntimeError) as error:
        sys.exit(str(error))
