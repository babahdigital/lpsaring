# Type stubs for Flask app extensions
# pyright: reportInvalidTypeArguments=false
from typing import TYPE_CHECKING
import redis

if TYPE_CHECKING:
    from flask import Flask
    
    class FlaskWithRedis(Flask):
        redis_client_otp: redis.Redis[str]
