"""WebSocket routes for real-time client updates.

Fix applied: Frontend connects to /api/ws/client-updates (through nginx). Originally the
backend only exposed /client-updates so the handshake returned 404. We now expose BOTH
the canonical absolute path '/api/ws/client-updates' and the legacy '/client-updates'.
Remove the legacy route once all clients are updated.
"""

import logging
import json
import time
from typing import Dict, List, Any, Set
import threading
from queue import Queue, Empty

from flask import Blueprint, Response, stream_with_context
from flask_sock import Sock  # type: ignore
from flask_jwt_extended import decode_token

from app.utils.request_utils import get_client_ip, get_client_mac

logger = logging.getLogger(__name__)

# Active WebSocket client registry keyed by IP
ws_clients: Dict[str, List[Any]] = {}
ws_clients_lock = threading.RLock()

websocket_bp = Blueprint('websocket', __name__)
sock = Sock()

# SSE fallback client structures
_sse_clients: Set[Queue] = set()
_sse_lock = threading.RLock()

def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

def _ws_handler(ws):
    client_ip = get_client_ip()
    client_mac = get_client_mac()  # noqa: F841 (reserved for future auth / filtering)
    user_id = None
    registered_ip = None
    registered_mac = None

    start_ts = time.time()
    # Register connection
    with ws_clients_lock:
        if client_ip:
            ws_clients.setdefault(client_ip, []).append(ws)

    try:
        logger.info(f"[WEBSOCKET] New connection from ip={client_ip} mac={client_mac}")
        ws.send(json.dumps({"type": "welcome", "message": "Connected to real-time updates"}))

        while True:
            message = ws.receive()
            if not message:
                continue
            try:
                data = json.loads(message)
            except Exception:
                continue
            mtype = data.get('type')

            if mtype == 'auth':
                token = data.get('token')
                if token:
                    try:
                        decoded = decode_token(token)
                        user_id = decoded.get('sub')
                        ws.send(json.dumps({"type": "auth_success", "user_id": user_id}))
                        logger.info(f"[WEBSOCKET] Authenticated user={user_id} ip={client_ip}")
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"[WEBSOCKET] Auth failed: {e}")
                        ws.send(json.dumps({"type": "auth_error", "error": "Invalid token"}))

            elif mtype == 'register':
                registered_ip = data.get('ip')
                registered_mac = data.get('mac')
                if registered_ip:
                    logger.info(f"[WEBSOCKET] Client registered ip={registered_ip} mac={registered_mac} (socket_ip={client_ip})")
                    if registered_ip != client_ip:
                        with ws_clients_lock:
                            ws_clients.setdefault(registered_ip, []).append(ws)
                    ws.send(json.dumps({"type": "registered", "ip": registered_ip, "mac": registered_mac}))

            elif mtype == 'pong':
                # Keep-alive response
                pass

    except Exception as e:  # noqa: BLE001
        if 'WebSocket' not in str(e):
            logger.warning(f"[WEBSOCKET] Connection error: {e}")
    finally:
        with ws_clients_lock:
            if client_ip and client_ip in ws_clients:
                try:
                    ws_clients[client_ip].remove(ws)
                    if not ws_clients[client_ip]:
                        del ws_clients[client_ip]
                except ValueError:
                    pass
            if registered_ip and registered_ip != client_ip and registered_ip in ws_clients:
                try:
                    ws_clients[registered_ip].remove(ws)
                    if not ws_clients[registered_ip]:
                        del ws_clients[registered_ip]
                except ValueError:
                    pass
    duration = time.time() - start_ts
    logger.info(f"[WEBSOCKET] Connection closed ip={client_ip} reg_ip={registered_ip} user={user_id} duration={duration:.1f}s")

# Register both canonical and legacy paths
@sock.route('/api/ws/client-updates')  # absolute path used via nginx
def client_updates_canonical(ws):  # type: ignore
    _ws_handler(ws)

@sock.route('/client-updates')  # legacy (pre-fix) path
def client_updates_legacy(ws):  # type: ignore
    logger.debug('[WEBSOCKET] Legacy /client-updates path used; please update frontend to /api/ws/client-updates')
    _ws_handler(ws)

def broadcast_mac_detected(ip: str, mac: str, notify: bool = True) -> int:
    if not ip or not mac:
        return 0
    payload = json.dumps({
        'type': 'mac_detected',
        'ip': ip,
        'mac': mac,
        'notify': notify,
        'timestamp': time.time(),
    })
    sent = 0
    with ws_clients_lock:
        if ip in ws_clients:
            for client in list(ws_clients[ip]):
                try:
                    client.send(payload)
                    sent += 1
                except Exception:
                    pass
    # SSE broadcast
    with _sse_lock:
        dead: list[Queue] = []
        for q in list(_sse_clients):
            try:
                q.put_nowait({
                    'type': 'mac_detected', 'ip': ip, 'mac': mac, 'notify': notify, 'timestamp': time.time(),
                })
            except Exception:
                dead.append(q)
        for dq in dead:
            _sse_clients.discard(dq)
    return sent

def broadcast_cache_cleared() -> int:
    msg = json.dumps({'type': 'cache_cleared', 'timestamp': time.time()})
    sent = 0
    with ws_clients_lock:
        all_clients = {c for lst in ws_clients.values() for c in lst}
        for c in list(all_clients):
            try:
                c.send(msg)
                sent += 1
            except Exception:
                pass
    with _sse_lock:
        dead: list[Queue] = []
        for q in list(_sse_clients):
            try:
                q.put_nowait({'type': 'cache_cleared', 'timestamp': time.time()})
            except Exception:
                dead.append(q)
        for dq in dead:
            _sse_clients.discard(dq)
    return sent

def ping_clients():
    logger.info('[WEBSOCKET] Starting ping thread')
    ping_msg = json.dumps({'type': 'ping'})
    while True:
        time.sleep(30)
        try:
            with ws_clients_lock:
                all_clients = {c for lst in ws_clients.values() for c in lst}
                for c in list(all_clients):
                    try:
                        c.send(ping_msg)
                    except Exception:
                        pass
            logger.debug(f"[WEBSOCKET] Ping sent to {sum(len(v) for v in ws_clients.values())} clients")
        except Exception as e:  # noqa: BLE001
            logger.error(f"[WEBSOCKET] Ping thread error: {e}")

ping_thread = threading.Thread(target=ping_clients, daemon=True)
ping_thread.start()

@websocket_bp.route('/sse/client-updates')
def sse_client_updates():  # final URL: /api/ws/sse/client-updates
    q: Queue = Queue(maxsize=100)
    with _sse_lock:
        _sse_clients.add(q)
    try:
        q.put_nowait({'type': 'welcome', 'message': 'Connected (SSE)'})
    except Exception:
        pass

    @stream_with_context
    def _event_stream():
        try:
            while True:
                try:
                    item = q.get(timeout=30)
                    yield _sse_event(item)
                except Empty:
                    yield _sse_event({'type': 'ping', 'ts': time.time()})
        finally:
            with _sse_lock:
                _sse_clients.discard(q)

    headers = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive',
    }
    return Response(_event_stream(), headers=headers)  # type: ignore
