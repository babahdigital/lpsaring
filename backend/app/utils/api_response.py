# backend/app/utils/api_response.py
"""
Standardized API response utilities to ensure consistent response formats
between backend and frontend
"""

from typing import Any, Dict, List, Optional, Union
from flask import jsonify

# Standard error codes that can be interpreted by the frontend
class ApiErrorCode:
    """Standard API error codes for frontend interpretation"""
    AUTHENTICATION_ERROR = "AUTH_ERROR"
    AUTHORIZATION_ERROR = "ACCESS_DENIED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_NOT_FOUND = "NOT_FOUND"
    RESOURCE_ALREADY_EXISTS = "ALREADY_EXISTS"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_ERROR = "SERVER_ERROR"
    CLIENT_DETECTION_ERROR = "CLIENT_DETECTION_ERROR"
    MIKROTIK_ERROR = "MIKROTIK_ERROR"
    DEVICE_ERROR = "DEVICE_ERROR"
    OTP_ERROR = "OTP_ERROR"

def api_response(
    data: Optional[Union[Dict, List]] = None,
    message: Optional[str] = None,
    success: bool = True,
    status_code: int = 200,
    error_code: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None
) -> tuple:
    """
    Creates a standardized API response with consistent structure.
    
    Args:
        data: The main response data
        message: A human-readable message describing the response
        success: Whether the operation was successful
        status_code: The HTTP status code for the response
        error_code: A standardized error code (for failed operations)
        meta: Additional metadata about the response (pagination, etc.)
    
    Returns:
        A tuple containing the response JSON and the HTTP status code
    """
    response: Dict[str, Any] = {
        "success": success,
    }
    
    if data is not None:
        response["data"] = data
    
    if message:
        response["message"] = message
    
    if error_code and not success:
        response["errorCode"] = error_code
    
    if meta:
        response["meta"] = meta
    
    return jsonify(response), status_code

# Helper functions for common response types
def success_response(data=None, message="Operation successful", meta=None, status_code=200):
    """Helper for successful responses"""
    return api_response(data=data, message=message, meta=meta, status_code=status_code)

def error_response(message, error_code=ApiErrorCode.SERVER_ERROR, status_code=400, data=None):
    """Helper for error responses"""
    return api_response(
        data=data,
        message=message,
        success=False,
        status_code=status_code,
        error_code=error_code
    )

def validation_error(errors, message="Validation error"):
    """Helper specifically for validation errors"""
    return api_response(
        data={"errors": errors},
        message=message,
        success=False,
        status_code=422,
        error_code=ApiErrorCode.VALIDATION_ERROR
    )

def not_found_error(resource_type="Resource", resource_id=None):
    """Helper for not found errors"""
    message = f"{resource_type} not found"
    if resource_id:
        message = f"{resource_type} with ID {resource_id} not found"
    
    return api_response(
        message=message,
        success=False,
        status_code=404,
        error_code=ApiErrorCode.RESOURCE_NOT_FOUND
    )
