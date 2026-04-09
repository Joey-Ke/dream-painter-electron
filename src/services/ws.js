// src/services/ws.js
let ws = null;

function connectWs({ baseUrl, token, onEvent }) {
  // 把 http://127.0.0.1:xxxx 转成 ws://127.0.0.1:xxxx
  const wsUrl = baseUrl.replace(/^http/, "ws") + "/ws"; // /ws 路径按你后端实现调整
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    // 如果你要 token，可在连接后先发一条 auth 消息（或用 querystring），由后端决定
    // ws.send(JSON.stringify({ type: "auth", token }));
  };

  ws.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      onEvent(data);
    } catch (_) {}
  };

  ws.onerror = () => onEvent({ type: "ws_error" });
  ws.onclose = () => onEvent({ type: "ws_close" });

  return () => ws && ws.close();
}

module.exports = { connectWs };
