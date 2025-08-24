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

from flask import Blueprint, Response, stream_with_context, current_app, request
from flask_sock import Sock  # type: ignore
import simple_websocket
from flask_jwt_extended import decode_token

from app.utils.request_utils import get_client_ip, get_client_mac
from app.services.client_detection_service import ClientDetectionService

logger = logging.getLogger(__name__)

# Active WebSocket client registry keyed by IP
ws_clients: Dict[str, List[Any]] = {}
ws_clients_lock = threading.RLock()

# User connections registry 
client_connections = None

websocket_bp = Blueprint('websocket', __name__)
sock = Sock()

# SSE fallback client structures
_sse_clients: Set[Queue] = set()
_sse_lock = threading.RLock()

def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

def _ws_handler(ws):
    socket_ip = get_client_ip()
    client_mac = get_client_mac()  # Get MAC from headers if available
    user_id = None
    registered_ip = socket_ip  # Start with the socket IP as default
    registered_mac = client_mac
    ip_changed = False
    previous_ip = None

    start_ts = time.time()
    # Register connection with the actual connection IP
    with ws_clients_lock:
        if socket_ip:
            ws_clients.setdefault(socket_ip, []).append(ws)

    try:
        logger.info(f"[WEBSOCKET] New connection from ip={socket_ip} mac={client_mac}")
        
        # Pemeriksaan keamanan - pastikan objek ws valid
        if not hasattr(ws, 'send') or not callable(getattr(ws, 'send', None)):
            logger.error(f"[WEBSOCKET] Invalid WebSocket object received - lacks 'send' method")
            return
            
        # Send more helpful welcome message with debugging info
        ws.send(json.dumps({
            "type": "welcome",
            "message": "Connected to real-time updates",
            "debug": {
                "client_ip": socket_ip,
                "client_mac": client_mac,
                "server_time": time.time(),
                "connection_id": f"{id(ws)}"
            }
        }))

        # Loop for receiving messages from clients - PERBAIKAN KETANGGUHAN
        while True:
            # Pengecekan eksplisit jika objek ws mendukung 'closed'
            if hasattr(ws, 'closed') and ws.closed:
                logger.debug(f"[WEBSOCKET] Connection marked as closed, exiting loop")
                break
                
            # Receive and parse message
            try:
                message = ws.receive(timeout=60)  # 60-second timeout
                if message is None:  # Timeout or connection closed
                    continue

                data = json.loads(message)
                msg_type = data.get("type")
                payload = data.get("payload", {})
            except simple_websocket.ConnectionClosed:
                logger.info(f"[WEBSOCKET] Connection gracefully closed by client.")
                break
            except Exception as e:
                # Periksa apakah error karena koneksi sudah ditutup
                if isinstance(e, (simple_websocket.ConnectionClosed, BrokenPipeError)):
                    logger.warning(f"[WEBSOCKET] Connection closed unexpectedly.")
                    break
                logger.warning(f"[WEBSOCKET] Error receiving or parsing message: {e}")
                continue
            
            # Process the message based on type
            if msg_type == 'auth':
                token = data.get('token') or payload.get('token')
                if token:
                    try:
                        decoded = decode_token(token)
                        user_id = decoded.get('sub')
                        ws.send(json.dumps({"type": "auth_success", "user_id": user_id}))
                        logger.info(f"[WEBSOCKET] Authenticated user={user_id} ip={registered_ip}")
                        
                        # Check for IP change after authentication
                        try:
                            # Load user directly from database
                            from app.infrastructure.db.models import User
                            from app.extensions import db
                            
                            user = db.session.get(User, user_id) if user_id else None
                            
                            if user and hasattr(user, 'last_login_ip'):
                                previous_ip = user.last_login_ip
                                if previous_ip and previous_ip != registered_ip:
                                    ip_changed = True
                                    logger.info(f"[WEBSOCKET] Detected IP change for user {user_id}: {previous_ip} -> {registered_ip}")
                                    
                                    # Try to update user's last login IP
                                    try:
                                        user.last_login_ip = registered_ip
                                        db.session.commit()
                                    except Exception as e:
                                        logger.warning(f"[WEBSOCKET] Failed to update last login IP: {e}")
                                        db.session.rollback()
                        except Exception as e:
                            logger.warning(f"[WEBSOCKET] Failed to check for IP change: {e}")
                    except Exception as e:
                        logger.warning(f"[WEBSOCKET] Auth failed: {e}")
                        ws.send(json.dumps({"type": "auth_failed", "error": str(e)}))
                
                # --- HANDLER BARU UNTUK REGISTRASI KLIEN ---
            elif msg_type == "register_client":
                client_ip = payload.get("ip")
                client_mac = payload.get("mac")
                
                if client_ip:
                    registered_ip = client_ip
                    if client_mac:
                        registered_mac = client_mac
                    
                    logger.info(
                        f"[WEBSOCKET] Client registered ip={registered_ip} mac={registered_mac} (socket_ip={socket_ip})"
                    )
                    
                    # Update user connection if authenticated
                    if user_id and client_connections:
                        client_connections.register(user_id, ws, registered_ip, registered_mac)
                    
                    # Acknowledge the registration
                    ws.send(json.dumps({
                        "type": "register_client_ack",
                        "payload": {
                            "ip": registered_ip,
                            "mac": registered_mac,
                            "user_id": user_id
                        }
                    }))
                    
                    # If the IP has changed, we should update the user's record
                    if user_id:
                        try:
                            from app.services.client_detection_service import ClientDetectionService
                            # Force a fresh detection to ensure we have the latest MAC
                            detection_result = ClientDetectionService.force_refresh_detection(
                                client_ip=client_ip, 
                                client_mac=client_mac,
                                is_browser=True
                            )
                            detected_mac = detection_result.get('detected_mac')
                            
                            if detected_mac and client_ip:
                                # Update the user's last login IP in the database
                                from app.extensions import db
                                from app.infrastructure.db.models import User
                                
                                user = db.session.get(User, user_id) if user_id else None
                                if user:
                                    user.last_login_ip = client_ip
                                    user.last_login_mac = detected_mac
                                    db.session.commit()
                                
                                    # Also update MikroTik with the new IP/MAC
                                    from app.infrastructure.gateways.mikrotik_client import (
                                        find_and_update_address_list_entry,
                                        add_ip_to_address_list,
                                        create_static_lease,
                                        find_and_remove_static_lease_by_mac,
                                    )
                                    
                                    # Get bypass list name
                                    from flask import current_app
                                    list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
                                    
                                    # Format phone number for comment
                                    from app.utils.formatters import format_to_local_phone
                                    comment = format_to_local_phone(user.phone_number)
                                    
                                    # Only proceed if we have all required values
                                    if list_name and comment and client_ip:
                                        # Update address list
                                        ok_upd, msg_upd = find_and_update_address_list_entry(list_name, client_ip, comment)
                                        if not ok_upd:
                                            ok_add, msg_add = add_ip_to_address_list(list_name, client_ip, comment)
                                            if ok_add:
                                                logger.info(f"[WEBSOCKET] Bypass added for {client_ip} comment {comment}")
                                        
                                        # Update DHCP lease
                                        _ok_rm, _ = find_and_remove_static_lease_by_mac(detected_mac)
                                        ok_lease, msg_lease = create_static_lease(client_ip, detected_mac, comment)
                                        if ok_lease:
                                            logger.info(f"[WEBSOCKET] DHCP lease updated for {client_ip}/{detected_mac}")
                        except Exception as e:
                            logger.error(f"[WEBSOCKET] Failed to update user IP/MAC: {e}")
                            
            elif msg_type == 'register':
                registered_ip = data.get('ip')
                registered_mac = data.get('mac')
                if registered_ip:
                    # CRITICAL FIX: Always prioritize the actual connection IP over registered IP
                    # The client may be sending stale IP information
                    actual_ip = socket_ip
                    actual_mac = client_mac or registered_mac
                    
                    # Log discrepancy if the registered IP doesn't match the actual connection IP
                    if registered_ip != actual_ip:
                        logger.warning(f"[WEBSOCKET] IP mismatch: registered={registered_ip}, actual={actual_ip}. Using actual IP.")
                        registered_ip = actual_ip
                    
                    logger.info(f"[WEBSOCKET] Client registered ip={registered_ip} mac={registered_mac} (socket_ip={socket_ip})")
                    
                    # Register with the actual connection IP to prevent disconnect loops
                    if registered_ip and registered_ip != socket_ip:
                        with ws_clients_lock:
                            ws_clients.setdefault(str(registered_ip), []).append(ws)
                    
                    # Send confirmation with the ACTUAL IP that we're using, not what the client sent
                    ws.send(json.dumps({
                        "type": "registered", 
                        "ip": actual_ip, 
                        "mac": actual_mac,
                        "ip_changed": ip_changed,
                        "previous_ip": previous_ip
                    }))

            elif msg_type == 'pong':
                # Keep-alive response
                pass

    except Exception as e:  # noqa: BLE001
        error_msg = str(e)
        if 'WebSocket' not in error_msg and 'Connection closed' not in error_msg:
            # Only log unusual errors, not normal disconnects
            logger.warning(f"[WEBSOCKET] Error in connection: {error_msg}")
        elif 'code=1005' in error_msg:
            # This is a normal closure, just debug log it
            logger.debug(f"[WEBSOCKET] Normal client disconnect: {error_msg}")
        else:
            # Other WebSocket errors
            logger.debug(f"[WEBSOCKET] Connection closed: {error_msg}")
    finally:
        with ws_clients_lock:
            if socket_ip and socket_ip in ws_clients:
                try:
                    ws_clients[socket_ip].remove(ws)
                    if not ws_clients[socket_ip]:
                        del ws_clients[socket_ip]
                except ValueError:
                    pass
            if registered_ip and registered_ip != socket_ip and registered_ip in ws_clients:
                try:
                    ws_clients[registered_ip].remove(ws)
                    if not ws_clients[registered_ip]:
                        del ws_clients[registered_ip]
                except ValueError:
                    pass
        duration = time.time() - start_ts
        logger.info(f"[WEBSOCKET] Connection closed ip={socket_ip} reg_ip={registered_ip} user={user_id} duration={duration:.1f}s")

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
