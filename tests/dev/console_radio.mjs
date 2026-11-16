// Drive a running robot-console's radio messages over its websocket.
//   node tests/dev/console_radio.mjs <deviceId> verify|free|save <channel> <group>|watch <seconds>
const [deviceId, action, a, b] = [Number(process.argv[2]), process.argv[3], process.argv[4], process.argv[5]];
const ws = new WebSocket(process.env.CONSOLE_WS ?? "ws://127.0.0.1:4795");
const wanted = /^radio-/;
const done = (code) => { ws.close(); process.exit(code); };
ws.onopen = () => {
  if (action === "verify") ws.send(JSON.stringify({ type: "radio-verify", deviceId }));
  if (action === "free") ws.send(JSON.stringify({ type: "radio-free-channels", deviceId }));
  if (action === "save") ws.send(JSON.stringify({ type: "radio-save", deviceId, channel: Number(a), group: Number(b) }));
  setTimeout(() => done(action === "watch" ? 0 : 1), (action === "watch" ? Number(a) : 60) * 1000);
};
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (!wanted.test(message.type) || message.type === "radio-survey" || message.type === "radio-map") return;
  if (message.deviceId !== undefined && message.deviceId !== deviceId) return;
  console.log(JSON.stringify(message));
  if (message.type === "radio-verify-result" || message.type === "radio-free") done(0);
  if (message.type === "radio-save-state" && message.state === "result") done(0);
};
ws.onerror = (event) => { console.error("ws error", event.message ?? ""); process.exit(2); };
