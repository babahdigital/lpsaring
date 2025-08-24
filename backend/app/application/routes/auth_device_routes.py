from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_current_user
from app.infrastructure.db.models import User, UserDevice
from app.extensions import db
import logging
from app.utils.request_utils import get_client_ip, get_client_mac

# Set up logger for this module
logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/authorize-device', methods=['POST'])
@jwt_required()
def authorize_device():
    """
    Explicitly authorize a device for the current user
    """
    try:
        # Get current user
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                "status": "ERROR",
                "message": "User not found"
            }), 404
        
        # Get request data
        data = request.get_json(silent=True) or {}
        client_ip = data.get('ip')
        client_mac = data.get('mac')
        device_name = data.get('device_name', f"Device-{client_mac[-4:]}" if client_mac else None)
        
        # If IP/MAC not provided, try to get from request
        if not client_ip:
            client_ip = get_client_ip()
        if not client_mac:
            client_mac = get_client_mac()
            
        if not client_ip or not client_mac:
            return jsonify({
                "status": "ERROR",
                "message": "IP and MAC are required"
            }), 400
            
        # Create or update device record
        device = UserDevice.query.filter_by(mac_address=client_mac).first()
        if not device:
            # Create a new UserDevice object - adapting to the actual model attributes
            device = UserDevice()
            device.user_id = current_user.id
            device.mac_address = client_mac
            device.device_name = device_name
            device.ip_address = client_ip  # Use the correct column name
            db.session.add(device)
        else:
            device.user_id = current_user.id
            device.ip_address = client_ip  # Use the correct column name
            if device_name:
                device.device_name = device_name
                
        db.session.commit()
        
        # Update bypass address list and DHCP lease
        from app.infrastructure.gateways import mikrotik_client
        
        list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
        comment = f"{current_user.phone_number.lstrip('+')}"
        
        # Update address list entry
        bypass_ok = dhcp_ok = False
        if list_name:
            bypass_ok, bypass_msg = mikrotik_client.find_and_update_address_list_entry(list_name, client_ip, comment)
        
        # Create static DHCP lease
        dhcp_ok, dhcp_msg = mikrotik_client.create_static_lease(client_ip, client_mac, comment)
        
        # Log the authorization
        logger.info(f"[DEVICE-AUTH] User {current_user.phone_number} authorized device MAC:{client_mac} IP:{client_ip}")
        
        return jsonify({
            "status": "SUCCESS",
            "message": "Device authorized successfully",
            "device_id": str(device.id),
            "bypass_updated": bypass_ok,
            "dhcp_updated": dhcp_ok
        }), 200
        
    except Exception as e:
        logger.error(f"[AUTHORIZE-DEVICE] Error: {e}")
        db.session.rollback()
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500

@auth_bp.route('/devices', methods=['GET'])
@jwt_required()
def get_user_devices():
    """
    Get list of user's authorized devices
    """
    try:
        # Get current user
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                "status": "ERROR",
                "message": "User not found"
            }), 404
        
        # Get user devices
        devices = UserDevice.query.filter_by(user_id=current_user.id).all()
        
        devices_list = []
        for device in devices:
            devices_list.append({
                "id": str(device.id),
                "device_name": device.device_name,
                "mac_address": device.mac_address,
                "last_ip": device.ip_address,  # Use the correct column name
                "created_at": device.created_at.isoformat() if device.created_at else None,
                "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None
            })
        
        return jsonify({
            "status": "SUCCESS",
            "devices": devices_list
        }), 200
        
    except Exception as e:
        logger.error(f"[GET-USER-DEVICES] Error: {e}")
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500

@auth_bp.route('/devices/<device_id>', methods=['DELETE'])
@jwt_required()
def remove_device(device_id):
    """
    Remove device authorization
    """
    try:
        # Get current user
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                "status": "ERROR",
                "message": "User not found"
            }), 404
        
        # Find the device
        device = UserDevice.query.filter_by(
            id=device_id,
            user_id=current_user.id
        ).first()
        
        if not device:
            return jsonify({
                "status": "ERROR",
                "message": "Device not found"
            }), 404
        
        # Remove bypass address list entry if possible
        try:
            from app.infrastructure.gateways import mikrotik_client
            
            if device.ip_address:  # Use the correct column name
                list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
                if list_name:
                    mikrotik_client.remove_ip_from_address_list(list_name, device.ip_address)
            
            if device.mac_address:
                mikrotik_client.find_and_remove_static_lease_by_mac(device.mac_address)
        except Exception as e:
            logger.warning(f"[REMOVE-DEVICE] Error removing from Mikrotik: {e}")
        
        # Delete the device
        db.session.delete(device)
        db.session.commit()
        
        # Log the removal
        logger.info(f"[DEVICE-REMOVE] User {current_user.phone_number} removed device MAC:{device.mac_address}")
        
        return jsonify({
            "status": "SUCCESS",
            "message": "Device authorization removed successfully"
        }), 200
        
    except Exception as e:
        logger.error(f"[REMOVE-DEVICE] Error: {e}")
        db.session.rollback()
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500
