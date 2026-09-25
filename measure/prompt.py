import asyncio
import time


async def wait_for_enter(message):
    print(f"\n>>> {message}")
    await asyncio.get_running_loop().run_in_executor(None, input)
    return time.perf_counter()
