// ==UserScript==
// @name         ZenithCam Web PTZ & Privacy Shield
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Injects PTZ controls and stream hijacking for ZenithCam
// @author       Elite Architect
// @match        *://*/PTZ_Tampermonkey/mock-studio.html*
// @match        *://*.stripchat.com/*
// @match        *://*.chaturbate.com/*
// @match        *://*.xhamsterlive.com/*
// @grant        GM_addStyle
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-start
// ==/UserScript==

(function () {
    'use strict';

    console.log("[ZenithCam] Injecting UserScript at document-start");

    let ws = null;
    let isBRBActive = false;
    let originalVideoTrack = null;
    let canvasStreamTrack = null;
    let isAimMode = false;

    // --- 1. WEBSOCKET BRIDGE ---
    function connectWebSocket() {
        ws = new WebSocket('ws://localhost:8765');
        ws.onopen = () => console.log("[ZenithCam] Connected to local ZenithCam engine");
        ws.onerror = (e) => console.log("[ZenithCam] WebSocket Error. Is ZenithCam running?", e);
        ws.onclose = () => setTimeout(connectWebSocket, 5000); // Auto-reconnect
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'telemetry') {
                    updateMiniMap(data.pan, data.tilt);
                } else if (data.type === 'brb_trigger') {
                    toggleBRB(data.active);
                }
            } catch (e) {
                console.warn("[ZenithCam] Failed to parse WS message", e);
            }
        };
    }
    connectWebSocket();

    function sendPTZCommand(action) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ command: 'ptz', action: action }));
        } else {
            console.warn("[ZenithCam] Cannot send command, WS offline");
        }
    }

    // --- 2. GETUSERMEDIA HIJACK (PRIVACY SHIELD) ---
    const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);

    navigator.mediaDevices.getUserMedia = async function (constraints) {
        console.log("[ZenithCam] Intercepted getUserMedia", constraints);

        // Enforce Resolution Override (720p 16:9 for ZenithCam ML Pipeline strictness)
        if (constraints.video) {
            constraints.video.width = { ideal: 1280 };
            constraints.video.height = { ideal: 720 };
        }

        const stream = await originalGetUserMedia(constraints);

        if (constraints.video) {
            originalVideoTrack = stream.getVideoTracks()[0];

            // Create an invisible canvas to act as our fake video source
            const canvas = document.createElement('canvas');
            canvas.width = 1280;
            canvas.height = 720;
            const ctx = canvas.getContext('2d');

            // Background video element to feed the canvas
            const hiddenVideo = document.createElement('video');
            hiddenVideo.srcObject = new MediaStream([originalVideoTrack]);
            hiddenVideo.play();

            // Loop to draw real video OR the BRB screen to the canvas
            function renderFrame() {
                if (isBRBActive) {
                    ctx.fillStyle = '#1e1e2e';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                    ctx.fillStyle = '#89b4fa';
                    ctx.font = 'bold 80px Arial';
                    ctx.textAlign = 'center';
                    ctx.fillText('BRB - PRIVACY SHIELD ON', canvas.width / 2, canvas.height / 2);
                } else {
                    ctx.drawImage(hiddenVideo, 0, 0, canvas.width, canvas.height);
                }
                requestAnimationFrame(renderFrame);
            }
            renderFrame();

            // Replace the real video track with the canvas track
            canvasStreamTrack = canvas.captureStream(30).getVideoTracks()[0];
            stream.removeTrack(originalVideoTrack);
            stream.addTrack(canvasStreamTrack);
        }
        return stream;
    };

    // --- Telemetry & BRB Handlers ---
    let miniMapDot = null;
    function updateMiniMap(pan, tilt) {
        if (!miniMapDot) return;
        // Map pan (-468000 to 468000) and tilt (-324000 to 324000) to 0-100%
        const x = ((pan + 468000) / 936000) * 100;
        const y = (1.0 - ((tilt + 324000) / 648000)) * 100; // Invert Y so up is up
        miniMapDot.style.left = `${Math.max(0, Math.min(100, x))}%`;
        miniMapDot.style.top = `${Math.max(0, Math.min(100, y))}%`;
    }

    function toggleBRB(forceState) {
        const brbBtn = document.getElementById('zc-brb');
        if (brbBtn) {
            isBRBActive = (forceState !== undefined) ? forceState : !isBRBActive;
            brbBtn.innerText = isBRBActive ? "Disable BRB Shield" : "Enable BRB Shield";
            brbBtn.classList.toggle('active', isBRBActive);
        }
    }

    // --- Visual Crosshair for Click-to-Aim ---
    function drawCrosshair(x, y) {
        const ch = document.createElement('div');
        ch.style.position = 'fixed';
        ch.style.left = (x - 15) + 'px';
        ch.style.top = (y - 15) + 'px';
        ch.style.width = '30px';
        ch.style.height = '30px';
        ch.style.border = '2px solid #f38ba8';
        ch.style.borderRadius = '50%';
        ch.style.pointerEvents = 'none';
        ch.style.zIndex = '9999999';
        ch.style.transition = 'transform 0.2s, opacity 0.5s';
        ch.style.transform = 'scale(0.5)';
        document.body.appendChild(ch);
        requestAnimationFrame(() => { ch.style.transform = 'scale(1)'; });
        setTimeout(() => { ch.style.opacity = '0'; setTimeout(() => ch.remove(), 500); }, 800);
    }

    // --- 3. UI OVERLAY INJECTION ---
    let styleInjected = false;
    let globalsAttached = false;
    let chatObserved = false;

    function initZenithCamUI() {
        if (!document.body) return;

        if (!styleInjected) {
            GM_addStyle(`
            #zc-overlay { position: fixed; top: 20px; right: 20px; width: 200px; background: rgba(30, 30, 46, 0.85); backdrop-filter: blur(10px); border: 1px solid #89b4fa; border-radius: 12px; z-index: 999999; color: white; font-family: sans-serif; box-shadow: 0 4px 15px rgba(0,0,0,0.5); cursor: move; }
            .zc-header { padding: 10px; background: rgba(137, 180, 250, 0.2); border-bottom: 1px solid #89b4fa; border-radius: 12px 12px 0 0; text-align: center; font-weight: bold; }
            .zc-body { padding: 15px; text-align: center; }
            .zc-ptz-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5px; margin-bottom: 15px; }
            .zc-btn { background: #313244; color: white; border: 1px solid #45475a; padding: 10px; border-radius: 6px; cursor: pointer; transition: 0.2s; }
            .zc-btn:hover { background: #45475a; }
            .zc-btn-brb { width: 100%; background: #f38ba8; color: #11111b; font-weight: bold; padding: 10px; border: none; border-radius: 6px; cursor: pointer; }
            .zc-btn-brb.active { background: #a6e3a1; }
            .zc-btn-aim { width: 100%; background: #89b4fa; color: #11111b; font-weight: bold; padding: 10px; border: none; border-radius: 6px; cursor: pointer; margin-top: 10px; }
            .zc-btn-aim.active { background: #f9e2af; }
            .zc-minimap { width: 100px; height: 70px; background: rgba(0,0,0,0.5); border: 1px solid #45475a; border-radius: 6px; margin: 10px auto 0 auto; position: relative; overflow: hidden; }
            .zc-minimap-dot { width: 8px; height: 8px; background: #f38ba8; border-radius: 50%; position: absolute; transform: translate(-50%, -50%); top: 50%; left: 50%; transition: top 0.2s, left 0.2s; box-shadow: 0 0 5px #f38ba8; }
            .zc-minimap-cross { position: absolute; top: 50%; left: 50%; width: 100%; height: 1px; background: rgba(255,255,255,0.1); transform: translate(-50%, -50%); }
            .zc-minimap-cross-v { position: absolute; top: 50%; left: 50%; width: 1px; height: 100%; background: rgba(255,255,255,0.1); transform: translate(-50%, -50%); }
            `);
            styleInjected = true;
        }

        if (!document.getElementById('zc-overlay')) {
            const overlay = document.createElement('div');
            overlay.id = 'zc-overlay';
            overlay.innerHTML = `
            <div class="zc-header">ZenithCam PTZ</div>
            <div class="zc-body">
                <div class="zc-ptz-grid">
                    <div></div><button class="zc-btn" id="zc-up">▲</button><div></div>
                    <button class="zc-btn" id="zc-left">◀</button>
                    <button class="zc-btn" id="zc-rst">▣</button>
                    <button class="zc-btn" id="zc-right">▶</button>
                    <div></div><button class="zc-btn" id="zc-down">▼</button><div></div>
                </div>
                <button class="zc-btn-brb ${isBRBActive ? 'active' : ''}" id="zc-brb">${isBRBActive ? 'Disable BRB Shield' : 'Enable BRB Shield'}</button>
                <button class="zc-btn-aim ${isAimMode ? 'active' : ''}" id="zc-aim">Click-to-Aim: ${isAimMode ? 'ON' : 'OFF'}</button>
                <div class="zc-minimap">
                    <div class="zc-minimap-cross"></div>
                    <div class="zc-minimap-cross-v"></div>
                    <div class="zc-minimap-dot" id="zc-minimap-dot"></div>
                </div>
            </div>
            `;
            document.body.appendChild(overlay);

            miniMapDot = document.getElementById('zc-minimap-dot');

            // Event Listeners
            const ptzButtons = ['up', 'down', 'left', 'right'];
            ptzButtons.forEach(dir => {
                const btn = document.getElementById(`zc-${dir}`);
                // Start moving on press
                btn.addEventListener('mousedown', () => sendPTZCommand(dir));
                btn.addEventListener('touchstart', (e) => { e.preventDefault(); sendPTZCommand(dir); });
                // Stop moving on release or drag off
                btn.addEventListener('mouseup', () => sendPTZCommand('stop'));
                btn.addEventListener('mouseleave', () => sendPTZCommand('stop'));
                btn.addEventListener('touchend', () => sendPTZCommand('stop'));
            });
            document.getElementById('zc-rst').onclick = () => sendPTZCommand('reset');

            const brbBtn = document.getElementById('zc-brb');
            brbBtn.onclick = () => {
                isBRBActive = !isBRBActive;
                brbBtn.innerText = isBRBActive ? "Disable BRB Shield" : "Enable BRB Shield";
                brbBtn.classList.toggle('active', isBRBActive);
            };

            // Click-to-Aim Logic
            const aimBtn = document.getElementById('zc-aim');
            aimBtn.onclick = () => {
                isAimMode = !isAimMode;
                aimBtn.innerText = isAimMode ? "Click-to-Aim: ON" : "Click-to-Aim: OFF";
                aimBtn.classList.toggle('active', isAimMode);
                document.body.style.cursor = isAimMode ? 'crosshair' : 'default';
            };

            // Simple drag logic
            let isDragging = false, startX, startY, startLeft, startTop;
            overlay.querySelector('.zc-header').addEventListener('mousedown', (e) => {
                isDragging = true;
                startX = e.clientX; startY = e.clientY;
                const rect = overlay.getBoundingClientRect();
                startLeft = rect.left; startTop = rect.top;
            });
            document.addEventListener('mousemove', (e) => {
                if (!isDragging) return;
                overlay.style.left = startLeft + (e.clientX - startX) + 'px';
                overlay.style.top = startTop + (e.clientY - startY) + 'px';
                overlay.style.right = 'auto'; // Disable right-anchor so left/top works
            });
            document.addEventListener('mouseup', () => isDragging = false);
        }

        if (!globalsAttached) {
            globalsAttached = true;
            document.addEventListener('click', (e) => {
                if (!isAimMode) return;
                // Allow clicks on video or generic broadcast wrappers (XHamster WebRTC player)
                if (e.target.tagName.toLowerCase() === 'video' || e.target.tagName.toLowerCase() === 'canvas' || e.target.closest('.web-rtc-player-wrapper')) {
                    const rect = e.target.getBoundingClientRect();
                    // Normalize coordinates to -1.0 to 1.0 (Center is 0,0)
                    const normX = ((e.clientX - rect.left) / rect.width) * 2 - 1;
                    const normY = ((e.clientY - rect.top) / rect.height) * 2 - 1;

                    console.log(`[ZenithCam] Firing PTZ Aim -> X:${normX.toFixed(2)}, Y:${normY.toFixed(2)}`);
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ command: 'ptz_aim', x: normX, y: normY }));
                    }
                    drawCrosshair(e.clientX, e.clientY);
                }
            });

            // --- Keyboard Controls (WASD / Arrows) ---
            let keyActive = null;
            document.addEventListener('keydown', (e) => {
                // Ignore if typing in input
                if (['input', 'textarea'].includes(e.target.tagName.toLowerCase()) || e.target.isContentEditable) return;
                const keyMap = { 'w': 'up', 'ArrowUp': 'up', 's': 'down', 'ArrowDown': 'down', 'a': 'left', 'ArrowLeft': 'left', 'd': 'right', 'ArrowRight': 'right' };
                const action = keyMap[e.key.toLowerCase()] || keyMap[e.key];
                if (action && keyActive !== action) {
                    keyActive = action;
                    sendPTZCommand(action);
                }
            });
            document.addEventListener('keyup', (e) => {
                if (['input', 'textarea'].includes(e.target.tagName.toLowerCase()) || e.target.isContentEditable) return;
                const keyMap = { 'w': 'up', 'ArrowUp': 'up', 's': 'down', 'ArrowDown': 'down', 'a': 'left', 'ArrowLeft': 'left', 'd': 'right', 'ArrowRight': 'right' };
                const action = keyMap[e.key.toLowerCase()] || keyMap[e.key];
                if (action === keyActive) {
                    keyActive = null;
                    sendPTZCommand('stop');
                }
            });
        }
    }

    // Run continuously to defeat SPA frameworks that wipe the DOM
    setInterval(initZenithCamUI, 1000);

    // --- FPS-Style Analog Mouse Look (Hold Alt) ---
    let isAltPressed = false;
    let mouseLookActive = false;

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Alt') {
            e.preventDefault(); // Prevent browser menu from focusing
            isAltPressed = true;
            document.body.style.cursor = 'all-scroll';
        }
    });

    document.addEventListener('keyup', (e) => {
        if (e.key === 'Alt') {
            isAltPressed = false;
            if (mouseLookActive) {
                mouseLookActive = false;
                sendPTZCommand('stop'); // Halt motors instantly on release
            }
            document.body.style.cursor = isAimMode ? 'crosshair' : 'default';
        }
    });

    document.addEventListener('mousemove', (e) => {
        if (isAltPressed) {
            mouseLookActive = true;
            // Convert raw mouse movement deltas into gimbal speed (-60.0 to 60.0 limits)
            const sensitivity = 1.5;
            let pSpeed = Math.max(-60, Math.min(60, e.movementX * sensitivity));
            let tSpeed = Math.max(-60, Math.min(60, e.movementY * sensitivity));

            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ command: 'ptz_analog', pan_speed: -pSpeed, tilt_speed: tSpeed }));
            }
        }
    });

    // --- Chat-Driven Reactions (Tip Integration) ---
    // Basic observer looking for tip keywords in the DOM (mock support for generic chat boxes)
    const observer = new MutationObserver((mutations) => {
        for (let mut of mutations) {
            if (mut.addedNodes.length) {
                mut.addedNodes.forEach(node => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        // Skip massive structural nodes or raw scripts to save performance
                        if (['script', 'style', 'svg', 'img', 'video', 'canvas'].includes(node.tagName.toLowerCase())) return;

                        const text = node.innerText || '';
                        if (!text || text.length > 500) return; // Ignore full page layout injections

                        // 1. Unified Chat Extraction
                        let username = "System";
                        let message = text.trim();

                        // Attempt to extract specific username/message elements across different platforms
                        const userNode = node.querySelector('.username, .name, .nickname, [class*="username"], [class*="name"]');
                        const msgNode = node.querySelector('.message-body, .text, .content, [class*="message-body"], [class*="text"]');

                        if (userNode && msgNode) {
                            username = userNode.innerText.trim();
                            message = msgNode.innerText.trim();
                        } else if (message.includes(':')) {
                            const parts = message.split(':');
                            if (parts[0].length < 25) { // Ensure it looks like a username
                                username = parts[0].trim();
                                message = parts.slice(1).join(':').trim();
                            }
                        }

                        const platform = window.location.hostname.replace('www.', '').split('.')[0];

                        if (ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({ command: 'chat', platform: platform, username: username, message: message }));
                        }

                        // 2. Tip Detection -> Reaction
                        if (text.match(/(tipped|tokens|sent tip|\$)/i)) {
                            console.log("[ZenithCam] Tip detected, sending reaction!");
                            if (ws && ws.readyState === WebSocket.OPEN) {
                                ws.send(JSON.stringify({ command: 'reaction', action: 'zoom_action' }));
                            }
                        }
                    }
                });
            }
        }
    });
    setInterval(() => {
        if (chatObserved) return;
        const chatContainer = document.querySelector('.messages, .chat-list, .chat-box, #chat, [class*="chat"]') || document.body;
        if (chatContainer) {
            observer.observe(chatContainer, { childList: true, subtree: true });
            chatObserved = true;
            console.log("[ZenithCam] Chat observer attached to:", chatContainer);
        }
    }, 2000);
})();