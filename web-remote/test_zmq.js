const zmq = require("zeromq");
async function run() {
    const pub = new zmq.Publisher();
    await pub.connect('tcp://127.0.0.1:5555');
    await pub.send(['command', JSON.stringify({action: 'get_state'})]);
    console.log("Sent command via ZeroMQ");
    pub.close();
}
run();
