const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const zmq = require('zeromq');
const path = require('path');
const { exec } = require('child_process');

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: '*' } });

app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());

// Main entry point
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Setup ZeroMQ sockets
const zmqPub = new zmq.Publisher();
const zmqSub = new zmq.Subscriber();

let pythonLastSeen = 0;
let pythonActive = false;

// Check for Python heartbeat every 2 seconds
setInterval(() => {
    const now = Date.now();
    const isNowActive = (now - pythonLastSeen < 3001);
    if (isNowActive !== pythonActive) {
        pythonActive = isNowActive;
        console.log(`Python App Connection: ${pythonActive ? 'ONLINE' : 'OFFLINE'}`);
        io.emit('python_status', { active: pythonActive });
    }
}, 2000);

async function runServer() {
    try {
        await zmqPub.bind('tcp://127.0.0.1:5555');
        await zmqSub.connect('tcp://127.0.0.1:5556');
        zmqSub.subscribe('telemetry');
        
        console.log('ZeroMQ Bridge established on ports 5555 (PUB) and 5556 (SUB)');
        
        // Listen for internal Python telemetry
        (async () => {
            console.log('Subscribing to Python telemetry on port 5556...');
            for await (const [topic, msg] of zmqSub) {
                const topicStr = topic.toString();
                if (topicStr === 'telemetry') {
                    if (!pythonActive) console.log('✅ Python Telemetry Received: APP ONLINE');
                    pythonLastSeen = Date.now();
                    const data = msg.toString();
                    io.emit('telemetry', JSON.parse(data));
                }
            }
        })();
        
    } catch (e) {
        console.error("ZeroMQ Error:", e);
    }
}

io.on('connection', (socket) => {
    console.log('Mobile Dashboard Client Connected:', socket.id);
    
    // Command listener
    socket.on('command', async (cmdData) => {
        // System level commands handled by Node
        if (cmdData.action === 'start_app') {
            if (pythonActive) {
                console.log('App already running, ignoring start request.');
                return;
            }
            console.log('Remote Start Requested: Launching ZenithCam via start_cam.sh...');
            const startCmd = `bash ${path.join(__dirname, '../app/start_cam.sh')} --remote-tailscale`;
            exec(startCmd, { cwd: path.join(__dirname, '..') }, (error, stdout, stderr) => {
                if (error) console.error(`Exec error: ${error}`);
            });
            return;
        }

        // Send command to Python over ZeroMQ
        try {
            await zmqPub.send(['command', JSON.stringify(cmdData)]);
        } catch (e) {
            console.error("Failed to send command over ZMQ:", e);
        }
    });
});

const PORT = 3001;
server.listen(PORT, '0.0.0.0', () => {
    console.log(`ZenithCam Mobile Backend listening on http://0.0.0.0:${PORT}`);
    runServer();
});
