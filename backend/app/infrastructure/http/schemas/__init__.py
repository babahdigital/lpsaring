# backend/app/infrastructure/http/schemas/__init__.py

from .auth_schemas import (
    RequestOtpRequestSchema,
    VerifyOtpRequestSchema,
    UserRegisterRequestSchema,
    UserSchema,
    RequestOtpResponseSchema,
    VerifyOtpResponseSchema,
    AuthErrorResponseSchema,
    UserRegisterResponseSchema,
    ChangePasswordRequestSchema
)

from .device_schemas import (
    DeviceInfoSchema,
    AuthorizeDeviceRequestSchema,
    AuthorizeDeviceResponseSchema,
    RejectDeviceRequestSchema,
    SyncDeviceRequestSchema,
    SyncDeviceResponseSchema
)
