export function connectDashboardLive(onRefresh, onState) {
  let socket;
  let closed = false;
  let retry;
  let delay = 1000;
  let lastMessage = Date.now();
  const connect = () => {
    if (closed || !localStorage.getItem('access_token')) return;
    onState(false);
    const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(`${scheme}//${window.location.host}/api/dashboard/live`);
    socket.onopen = () => socket.send(JSON.stringify({ token: localStorage.getItem('access_token') }));
    socket.onmessage = ({ data }) => {
      try {
        const event = JSON.parse(data);
        lastMessage = Date.now();
        if (event.type === 'ready' || event.type === 'heartbeat' || event.type === 'refresh') {
          delay = 1000;
          onState(true);
        }
        if (event.type === 'ready' || event.type === 'refresh') onRefresh();
      } catch { socket.close(); }
    };
    socket.onerror = () => socket.close();
    socket.onclose = ({ code }) => {
      onState(false);
      if (!closed && code !== 1008) {
        retry = setTimeout(connect, delay + Math.random() * 500);
        delay = Math.min(30000, delay * 2);
      }
    };
  };
  const watchdog = setInterval(() => {
    if (socket?.readyState === WebSocket.OPEN && Date.now() - lastMessage > 45000) socket.close();
  }, 15000);
  connect();
  return () => {
    closed = true;
    clearTimeout(retry);
    clearInterval(watchdog);
    socket?.close();
  };
}
