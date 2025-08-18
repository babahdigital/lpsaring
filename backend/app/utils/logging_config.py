# backend/app/utils/logging_config.py
import logging
from logging.config import dictConfig
import os

def setup_logging(app):
    """
    Mengkonfigurasi logging untuk Flask dan Gunicorn secara terpusat.
    """
    log_level = app.config.get('LOG_LEVEL', 'INFO').upper()
    
    dictConfig({
        'version': 1,
        'formatters': {
            'default': {
                'format': '[%(asctime)s] %(levelname)s in %(module)s.%(funcName)s: %(message)s',
            }
        },
        'handlers': {
            'wsgi': {
                'class': 'logging.StreamHandler',
                'stream': 'ext://flask.logging.wsgi_errors_stream',
                'formatter': 'default'
            }
        },
        'root': {
            'level': log_level,
            'handlers': ['wsgi']
        },
        'loggers': {
            'gunicorn.error': {
                'level': log_level,
                'handlers': ['wsgi'],
                'propagate': False,
            },
            'gunicorn.access': {
                'level': log_level,
                'handlers': ['wsgi'],
                'propagate': False,
            }
        }
    })