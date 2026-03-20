#!/usr/bin/env python3
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("Error: 'websockets' library is required. Run: pip install websockets")
    sys.exit(1)

async def trigger_panic():
    uri = "ws://localhost:8765"
    try:
        async with websockets.connect(uri) as ws:
            payload = {"command": "system", "action": "panic"}
            await ws.send(json.dumps(payload))
            print("🚨 Panic command sent successfully to ZenithCam Studio.")
    except ConnectionRefusedError:
        print("❌ Error: Could not connect to ZenithCam. Is the engine running?")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(trigger_panic())