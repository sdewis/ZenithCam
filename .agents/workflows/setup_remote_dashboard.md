---
description: Build a Node.js companion Web Dashboard for ZenithCam and index global skills in the background.
---

# ZenithCam Mobile Companion Workflow

This workflow spins up a real-time HTTP web dashboard for remote ZenithCam operations via ZeroMQ, while concurrently delegating hard-drive wide skill searches to a background process.

1. Spawn the asynchronous background agent to search `/media/sean/` for deep-nested skills without blocking.
// turbo
2. Create the Node.js project directory `web-remote` inside the ZenithCam project.
// turbo
3. Initialize `package.json` for the new backend.
// turbo
4. Install necessary libraries: `express`, `socket.io`, `zeromq`, and `cors`.
5. Create `server.js` establishing the Express HTTP server, Socket.io event loop, and ZeroMQ subscriber/publisher pipelines.
6. Create the polished Glassmorphism `index.html` UI for mobile interactions.
7. Inject the Python ZeroMQ bridge code into ZenithCam's `main.py` to transmit frame telemetrics and accept API inputs.
8. Verify the complete ecosystem bridge by testing remote commands.
