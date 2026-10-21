# server.py
import asyncio
import websockets
import threading
import queue
import json

_clients = set()
_loop    = None
_muted   = False

# Shared inbox for commands from ANY input source (mic thread, typed UI input,
# and eventually the phone app). main.py's loop just pulls from this.
COMMAND_QUEUE = queue.Queue()


def is_muted() -> bool:
    """Read-only check used by main.py's loop (safe from any thread)."""
    return _muted


async def _handler(websocket):
    global _muted
    _clients.add(websocket)
    try:
        # Bring newly-connected UIs (laptop, phone, extra tabs) up to date
        await websocket.send(json.dumps({"state": "MUTE_STATUS", "muted": _muted}))

        async for message in websocket:
            try:
                data = json.loads(message)
            except (json.JSONDecodeError, TypeError):
                continue

            msg_type = data.get("type")

            if msg_type == "set_mute":
                _muted = bool(data.get("value"))
                # Keep every connected client (incl. sender) in sync
                await _send_all(json.dumps({"state": "MUTE_STATUS", "muted": _muted}))

            elif msg_type == "text_command":
                text = (data.get("text") or "").strip()
                if text:
                    COMMAND_QUEUE.put(text.lower())
    finally:
        _clients.discard(websocket)

async def _run():
    global _loop
    _loop = asyncio.get_running_loop()
    async with websockets.serve(_handler, "localhost", 8765):
        await asyncio.Future()   # run forever

def start():
    """Start WebSocket server in a background thread."""
    t = threading.Thread(target=lambda: asyncio.run(_run()), daemon=True)
    t.start()
    import time; time.sleep(0.5)  # give server time to bind

async def _send_all(msg):
    if _clients:
        await asyncio.gather(
            *[c.send(msg) for c in _clients.copy()],
            return_exceptions=True
        )

def broadcast(state, text=""):
    """Push a state update to every connected UI client."""
    if not _loop:
        return
    msg = json.dumps({"state": state, "text": text})
    asyncio.run_coroutine_threadsafe(_send_all(msg), _loop)