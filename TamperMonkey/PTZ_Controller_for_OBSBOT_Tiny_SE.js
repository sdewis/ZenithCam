// ==UserScript==
// @name         PTZ Controller for OBSBOT Tiny SE
// @namespace    http://tampermonkey.net/
// @version      1.2
// @description  Adds PTZ controls, Presets, and YOLO ONNX Tracking for OBSBOT Tiny SE.
// @author       OutdoorFC
// @match        https://stripchat.com/*
// @match        https://www.xhamsterlive.com/*
// @match        https://chaturbate.com/*
// @match        https://webcamtests.com/*
// @match        https://thundr.com/*
// @match        http://localhost:*/*
// @require      https://cdn.jsdelivr.net/npm/onnxruntime-web/dist/ort.min.js
// @grant        GM_addStyle
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// ==/UserScript==

(function() {
    'use strict';

    GM_registerMenuCommand("Toggle PTZ Overlay", () => {
        const overlay = document.getElementById('ptz-overlay');
        if (overlay) overlay.style.display = overlay.style.display === 'none' ? 'block' : 'none';
        else createUI();
    });

    GM_addStyle(`
        #ptz-overlay {
            position: fixed; top: 20px; right: 20px; width: 220px; min-width: 180px;
            background: rgba(0, 0, 0, 0.9); color: white; padding: 15px;
            border-radius: 8px; z-index: 10000; cursor: move; user-select: none;
            font-family: sans-serif; border: 1px solid #4CAF50; box-shadow: 0 4px 20px rgba(0,0,0,0.8);
            resize: both; overflow: hidden;
        }
        .ptz-section { margin-bottom: 12px; border-top: 1px solid #333; padding-top: 8px; }
        .ptz-control-group { margin-bottom: 8px; }
        .ptz-control-group label { display: block; font-size: 10px; margin-bottom: 2px; text-transform: uppercase; color: #888; }
        .ptz-slider { width: 100%; height: 4px; background: #444; border-radius: 2px; outline: none; -webkit-appearance: none; }
        .ptz-slider::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; background: #4CAF50; border-radius: 50%; cursor: pointer; }
        #ptz-header { font-weight: bold; padding-bottom: 8px; display: flex; justify-content: space-between; align-items: center; pointer-events: none; }
        .ptz-btn { background: #4CAF50; color: white; border: none; padding: 5px 8px; cursor: pointer; border-radius: 4px; font-size: 11px; font-weight: bold; }
        .ptz-btn:hover { background: #45a049; }
        .ptz-btn-danger { background: #F44336; }
        .ptz-btn-secondary { background: #333; pointer-events: auto; }
        .ptz-btn-sm { padding: 3px 6px; font-size: 9px; }

        #ptz-crosshair {
            position: absolute; width: 44px; height: 44px;
            border: 2px solid #00ff00; border-radius: 50%;
            transform: translate(-50%, -50%); pointer-events: none;
            display: none; z-index: 9999;
            box-shadow: 0 0 15px #00ff00;
        }
    `);

    let activeVideoTrack = null;
    let isPrivacyActive = false;
    let ws = null;
    let bridgeCanvas = document.createElement('canvas');
    let bridgeCtx = bridgeCanvas.getContext('2d');
    let bridgeVideo = document.createElement('video');
    bridgeVideo.autoplay = true; bridgeVideo.muted = true;

    // AI & Tracking Variables
    let isTracking = false; // Manual
    let isYOLOTracking = false; // AI
    let targetPoint = { x: 0, y: 0 };
    let crosshair = null;
    let ortSession = null;

    // Manual Tracking
    let templateData = null;
    const T_SIZE = 32;
    const S_SIZE = 100;

    // YOLO inputs
    const INPUT_DIM = 640;
    const inputCanvas = document.createElement('canvas');
    inputCanvas.width = INPUT_DIM;
    inputCanvas.height = INPUT_DIM;
    const inputCtx = inputCanvas.getContext('2d', { willReadFrequently: true });
    let isProcessingFrame = false;

    async function initAI() {
        if (ortSession) return;
        try {
            console.log('Loading YOLO Model from local server...');
            ort.env.wasm.wasmPaths = 'https://cdn.jsdelivr.net/npm/onnxruntime-web/dist/';
            ortSession = await ort.InferenceSession.create('http://localhost:8080/model.onnx', { executionProviders: ['wasm'] });
            console.log('Model loaded successfully.');
        } catch (e) {
            console.error('Failed to load ONNX model:', e);
            alert('Failed to load model. Is the helper server running?');
        }
    }

    const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async function(constraints) {
        const resOverride = document.getElementById('ptz-res-override')?.value || localStorage.getItem('ptz-res-pref');
        if (resOverride && constraints.video) {
            const [w, h] = resOverride.split('x').map(Number);
            constraints.video = { width: { ideal: w }, height: { ideal: h } };
        }
        const realStream = await originalGetUserMedia(constraints);
        activeVideoTrack = realStream.getVideoTracks()[0];
        const settings = activeVideoTrack.getSettings();
        bridgeCanvas.width = settings.width || 1280; bridgeCanvas.height = settings.height || 720;
        bridgeVideo.srcObject = realStream;

        startBridgeLoop();
        return bridgeCanvas.captureStream(30);
    };

    function startBridgeLoop() {
        const render = async () => {
            if (!activeVideoTrack) return;
            if (isPrivacyActive) {
                bridgeCtx.fillStyle = '#050505'; bridgeCtx.fillRect(0, 0, bridgeCanvas.width, bridgeCanvas.height);
                bridgeCtx.fillStyle = '#ffffff'; bridgeCtx.font = 'bold 48px sans-serif'; bridgeCtx.textAlign = 'center';
                bridgeCtx.fillText('BRB', bridgeCanvas.width/2, bridgeCanvas.height/2);
            } else {
                bridgeCtx.drawImage(bridgeVideo, 0, 0, bridgeCanvas.width, bridgeCanvas.height);

                if (isYOLOTracking && bridgeVideo.readyState >= 2 && !isProcessingFrame) {
                    processYOLO();
                } else if (isTracking && !isYOLOTracking) {
                    performManualTracking();
                }
            }
            requestAnimationFrame(render);
        };
        render();
    }

    async function processYOLO() {
        if (!ortSession) return;
        isProcessingFrame = true;

        try {
            // 1. Prepare image
            inputCtx.drawImage(bridgeVideo, 0, 0, INPUT_DIM, INPUT_DIM);
            const imgData = inputCtx.getImageData(0, 0, INPUT_DIM, INPUT_DIM).data;

            // Convert to Float32Array [1, 3, 640, 640] normalized to 0-1
            const float32Data = new Float32Array(3 * INPUT_DIM * INPUT_DIM);
            for (let i = 0; i < INPUT_DIM * INPUT_DIM; i++) {
                float32Data[i] = imgData[i * 4] / 255.0; // R
                float32Data[INPUT_DIM * INPUT_DIM + i] = imgData[i * 4 + 1] / 255.0; // G
                float32Data[2 * INPUT_DIM * INPUT_DIM + i] = imgData[i * 4 + 2] / 255.0; // B
            }

            const tensor = new ort.Tensor('float32', float32Data, [1, 3, INPUT_DIM, INPUT_DIM]);

            // 2. Run inference
            const results = await ortSession.run({ images: tensor });
            const output = results.output0.data; // Float32Array size 9 * 8400

            // 3. Process output [1, 9, 8400]
            const targetClass = parseInt(document.getElementById('ptz-yolo-class').value, 10);
            const CONF_THRESHOLD = 0.5;

            let bestConf = 0;
            let bestBox = null;

            // output is flattened. row 0 = x, row 1 = y, row 2 = w, row 3 = h
            // rows 4 to 8 are classes
            for (let i = 0; i < 8400; i++) {
                const conf = output[(4 + targetClass) * 8400 + i];
                if (conf > bestConf && conf > CONF_THRESHOLD) {
                    bestConf = conf;
                    const xCenter = output[0 * 8400 + i];
                    const yCenter = output[1 * 8400 + i];

                    bestBox = {
                        x: (xCenter / INPUT_DIM) * bridgeCanvas.width,
                        y: (yCenter / INPUT_DIM) * bridgeCanvas.height
                    };
                }
            }

            if (bestBox) {
                targetPoint = { x: bestBox.x, y: bestBox.y };
                crosshair.style.display = 'block';
                crosshair.style.borderColor = '#ff00ff';
                updateCrosshairPosition();
                centerTarget();
            } else {
                // If lost, turn yellow
                crosshair.style.borderColor = '#ffff00';
            }

        } catch (e) {
            console.error('YOLO Processing Error:', e);
        }

        isProcessingFrame = false;
    }

    function performManualTracking() {
        const searchX = Math.max(0, Math.min(bridgeCanvas.width - S_SIZE, targetPoint.x - S_SIZE/2));
        const searchY = Math.max(0, Math.min(bridgeCanvas.height - S_SIZE, targetPoint.y - S_SIZE/2));
        const currentData = bridgeCtx.getImageData(searchX, searchY, S_SIZE, S_SIZE).data;

        let bestDist = Infinity;
        let bestX = targetPoint.x; let bestY = targetPoint.y;

        for (let y = 0; y < S_SIZE - T_SIZE; y += 5) {
            for (let x = 0; x < S_SIZE - T_SIZE; x += 5) {
                let dist = 0;
                for (let ty = 0; ty < T_SIZE; ty += 8) {
                    for (let tx = 0; tx < T_SIZE; tx += 8) {
                        const idxT = (ty * T_SIZE + tx) * 4;
                        const idxS = ((y + ty) * S_SIZE + (x + tx)) * 4;
                        dist += Math.abs(currentData[idxS] - templateData[idxT]);
                    }
                }
                if (dist < bestDist) {
                    bestDist = dist; bestX = searchX + x + T_SIZE/2; bestY = searchY + y + T_SIZE/2;
                }
            }
        }

        const confidence = 1 - (bestDist / (T_SIZE * T_SIZE * 255));
        crosshair.style.borderColor = confidence > 0.8 ? '#00ff00' : (confidence > 0.5 ? '#ffff00' : '#ff0000');

        targetPoint = { x: bestX, y: bestY };
        updateCrosshairPosition();
        centerTarget();
    }

    function centerTarget() {
        const centerX = bridgeCanvas.width / 2;
        const centerY = bridgeCanvas.height / 2;
        const errX = (targetPoint.x - centerX) / centerX;
        const errY = (targetPoint.y - centerY) / centerY;

        // Deadzone: 10% from center
        if (Math.abs(errX) > 0.1 || Math.abs(errY) > 0.1) {
            const panInp = document.getElementById('ptz-pan');
            const tiltInp = document.getElementById('ptz-tilt');

            // Speed factor
            const speed = 10;

            if (Math.abs(errX) > 0.1) panInp.value = parseFloat(panInp.value) - (errX * speed);
            if (Math.abs(errY) > 0.1) tiltInp.value = parseFloat(tiltInp.value) + (errY * speed);

            panInp.dispatchEvent(new Event('input'));
        }
    }

    function createUI() {
        if (document.getElementById('ptz-overlay')) return;
        const overlay = document.createElement('div');
        overlay.id = 'ptz-overlay';
        overlay.innerHTML = `
            <div id="ptz-header"><span>OBSBOT Tiny SE</span><span id="ptz-bridge-status" style="font-size: 9px; color: #F44336;">OFFLINE</span><button id="ptz-close" class="ptz-btn ptz-btn-secondary">×</button></div>
            <div class="ptz-control-group"><label>Pan</label><input type="range" class="ptz-slider" id="ptz-pan" min="-180" max="180" value="0"></div>
            <div class="ptz-control-group"><label>Tilt</label><input type="range" class="ptz-slider" id="ptz-tilt" min="-90" max="90" value="0"></div>
            <div class="ptz-control-group"><label>Zoom</label><input type="range" class="ptz-slider" id="ptz-zoom" min="1" max="4" step="0.1" value="1"></div>

            <div class="ptz-section">
                <label style="font-size: 9px; color: #888; margin-bottom: 5px; display: block;">AI Tracker</label>
                <div style="display: flex; gap: 5px; align-items: center; margin-bottom: 8px;">
                    <select id="ptz-yolo-class" class="ptz-slider" style="background: #222; color: #fff; border: 1px solid #444; flex: 1;">
                        <option value="0">Class 0</option>
                        <option value="1">Class 1</option>
                        <option value="2">Class 2</option>
                        <option value="3">Class 3</option>
                        <option value="4">Class 4</option>
                    </select>
                    <button class="ptz-btn" id="ptz-ai-follow" style="background: #9C27B0;">ONNX TRACK</button>
                </div>
                <div style="display: flex; gap: 5px;">
                    <button class="ptz-btn ptz-btn-secondary ptz-btn-sm" id="p-1">P1</button>
                    <button class="ptz-btn ptz-btn-secondary ptz-btn-sm" id="p-2">P2</button>
                    <button class="ptz-btn ptz-btn-secondary ptz-btn-sm" id="p-3">P3</button>
                    <button class="ptz-btn ptz-btn-sm" id="p-save" style="margin-left: auto; background: #2196F3;">SAVE</button>
                </div>
            </div>

            <div class="ptz-section">
                <label>Force Resolution</label>
                <select id="ptz-res-override" class="ptz-slider" style="background: #222; color: #fff; border: 1px solid #444;">
                    <option value="1280x720">720p</option>
                    <option value="1920x1080" selected>1080p</option>
                    <option value="3840x2160">4K</option>
                </select>
            </div>

            <div style="display: flex; gap: 8px;"><button id="ptz-reset" class="ptz-btn ptz-btn-secondary" style="flex: 1;">Reset</button><button id="ptz-privacy" class="ptz-btn" style="flex: 2;">Privacy: OFF</button></div>
        `;
        document.body.appendChild(overlay);
        crosshair = document.createElement('div'); crosshair.id = 'ptz-crosshair'; document.body.appendChild(crosshair);
        makeDraggable(overlay);
        setupEventListeners();
        connectHelper();
    }

    function setupEventListeners() {
        const update = () => applyPTZ({ pan: parseFloat(document.getElementById('ptz-pan').value), tilt: parseFloat(document.getElementById('ptz-tilt').value), zoom: parseFloat(document.getElementById('ptz-zoom').value) });
        document.getElementById('ptz-pan').oninput = update;
        document.getElementById('ptz-tilt').oninput = update;
        document.getElementById('ptz-zoom').oninput = update;
        document.getElementById('ptz-reset').onclick = () => {
            document.getElementById('ptz-pan').value = 0; document.getElementById('ptz-tilt').value = 0; document.getElementById('ptz-zoom').value = 1;
            applyPTZ({ pan: 0, tilt: 0, zoom: 1 });
        };
        document.getElementById('ptz-privacy').onclick = () => {
            isPrivacyActive = !isPrivacyActive;
            const btn = document.getElementById('ptz-privacy');
            btn.innerText = `Privacy: ${isPrivacyActive ? 'ON' : 'OFF'}`;
            btn.className = `ptz-btn ${isPrivacyActive ? 'ptz-btn-danger' : ''}`;
        };

        document.getElementById('ptz-ai-follow').onclick = async () => {
            isYOLOTracking = !isYOLOTracking;
            const btn = document.getElementById('ptz-ai-follow');
            btn.innerText = isYOLOTracking ? 'STOP TRACK' : 'ONNX TRACK';
            btn.style.background = isYOLOTracking ? '#F44336' : '#9C27B0';
            if (isYOLOTracking) {
                isTracking = false; // Disable manual if AI is on
                await initAI();
                crosshair.style.display = 'block';
            } else {
                crosshair.style.display = 'none';
            }
        };

        // Presets Logic
        document.getElementById('p-save').onclick = () => {
            const data = { pan: document.getElementById('ptz-pan').value, tilt: document.getElementById('ptz-tilt').value, zoom: document.getElementById('ptz-zoom').value };
            localStorage.setItem('ptz-preset-tmp', JSON.stringify(data));
            alert('Click a P button to save to that slot');
        };
        [1,2,3].forEach(i => {
            const btn = document.getElementById(`p-${i}`);
            btn.onclick = () => {
                const saving = localStorage.getItem('ptz-preset-tmp');
                if (saving) {
                    localStorage.setItem(`ptz-slot-${i}`, saving);
                    localStorage.removeItem('ptz-preset-tmp');
                    btn.style.borderColor = '#4CAF50';
                } else {
                    const loaded = JSON.parse(localStorage.getItem(`ptz-slot-${i}`));
                    if (loaded) {
                        document.getElementById('ptz-pan').value = loaded.pan;
                        document.getElementById('ptz-tilt').value = loaded.tilt;
                        document.getElementById('ptz-zoom').value = loaded.zoom;
                        update();
                    }
                }
            };
        });

        document.getElementById('ptz-res-override').onchange = (e) => localStorage.setItem('ptz-res-pref', e.target.value);
        document.getElementById('ptz-close').onclick = () => document.getElementById('ptz-overlay').remove();

        window.addEventListener('mousedown', (e) => {
            if (e.target.tagName !== 'VIDEO' || isYOLOTracking) return;
            const rect = e.target.getBoundingClientRect();
            const x = ((e.clientX - rect.left) / rect.width) * bridgeCanvas.width;
            const y = ((e.clientY - rect.top) / rect.height) * bridgeCanvas.height;
            targetPoint = { x, y };
            templateData = bridgeCtx.getImageData(x - T_SIZE/2, y - T_SIZE/2, T_SIZE, T_SIZE).data;
            isTracking = true; crosshair.style.display = 'block'; updateCrosshairPosition();
        });
        window.addEventListener('dblclick', () => { isTracking = false; isYOLOTracking = false; crosshair.style.display = 'none'; });
    }

    function updateCrosshairPosition() {
        const activeVideo = Array.from(document.querySelectorAll('video')).find(v => v.readyState > 0 && v.id !== 'bridge-video');
        if (!activeVideo) return;
        const rect = activeVideo.getBoundingClientRect();
        crosshair.style.left = `${rect.left + (targetPoint.x / bridgeCanvas.width) * rect.width}px`;
        crosshair.style.top = `${rect.top + (targetPoint.y / bridgeCanvas.height) * rect.height}px`;
    }

    async function applyPTZ(constraints) {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'PTZ', constraints }));
        if (activeVideoTrack) { try { await activeVideoTrack.applyConstraints({ advanced: [constraints] }); } catch (e) {} }
    }

    function connectHelper() {
        ws = new WebSocket('ws://localhost:8765');
        ws.onopen = () => {
            const s = document.getElementById('ptz-bridge-status');
            if(s){ s.innerText = 'ONLINE'; s.style.color = '#4CAF50'; }
        };
        ws.onerror = () => {
            const s = document.getElementById('ptz-bridge-status');
            if(s){ s.innerText = 'OFFLINE'; s.style.color = '#F44336'; }
        };
        ws.onclose = () => setTimeout(connectHelper, 5000);
    }

    function makeDraggable(el) {
        let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
        el.onmousedown = (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON' || e.target.tagName === 'SELECT') return;
            const isResizeHandle = (e.clientX > el.offsetLeft + el.offsetWidth - 20) && (e.clientY > el.offsetTop + el.offsetHeight - 20);
            if (isResizeHandle) return;

            e.preventDefault();
            pos3 = e.clientX; pos4 = e.clientY;
            document.onmouseup = () => { document.onmouseup = null; document.onmousemove = null; };
            document.onmousemove = (e) => {
                e.preventDefault(); pos1 = pos3 - e.clientX; pos2 = pos4 - e.clientY;
                pos3 = e.clientX; pos4 = e.clientY;
                el.style.top = (el.offsetTop - pos2) + "px"; el.style.left = (el.offsetLeft - pos1) + "px";
            };
        };
    }

    if (window.location.href.includes('broadcast') || window.location.href.includes('My Show') || window.location.hostname === 'localhost' || window.location.hostname.includes('webcamtests')) {
        setTimeout(createUI, 2000);
    }
})();

