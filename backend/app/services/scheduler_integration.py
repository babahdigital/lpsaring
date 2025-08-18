# backend/app/services/scheduler_integration.py
"""
Integration dengan Celery Scheduler untuk Auth Optimization
Harmonis dengan struktur extensions.py yang sudah ada
"""

import logging
from typing import Dict, Any, Optional
from celery.schedules import crontab
from flask import current_app

logger = logging.getLogger(__name__)

class AuthOptimizationScheduler:
    """
    Scheduler untuk auth optimization tasks
    Terintegrasi dengan Celery factory pattern yang sudah ada
    """
    
    @staticmethod
    def register_auth_tasks(celery_app):
        """
        Register periodic tasks untuk auth optimization
        Dipanggil dari extensions.py atau app factory
        """
        try:
            # Konfigurasi beat schedule
            auth_beat_schedule = {
                # Cleanup expired sessions setiap 30 menit
                'auth-cleanup-sessions': {
                    'task': 'auth.cleanup_expired_sessions',
                    'schedule': crontab(minute='*/30'),
                    'options': {'queue': 'maintenance'}
                },
                
                # Monitor auth performance setiap 5 menit
                'auth-monitor-performance': {
                    'task': 'auth.monitor_auth_performance', 
                    'schedule': crontab(minute='*/5'),
                    'options': {'queue': 'monitoring'}
                },
                
                # Daily auth system health check
                'auth-daily-health-check': {
                    'task': 'auth.daily_health_check',
                    'schedule': crontab(hour=2, minute=0),  # 2 AM setiap hari
                    'options': {'queue': 'maintenance'}
                }
            }
            
            # Merge dengan beat schedule yang sudah ada
            existing_schedule = getattr(celery_app.conf, 'beat_schedule', {})
            existing_schedule.update(auth_beat_schedule)
            celery_app.conf.beat_schedule = existing_schedule
            
            logger.info("[SCHEDULER] Auth optimization tasks registered")
            return True
            
        except Exception as e:
            logger.error(f"[SCHEDULER] Failed to register auth tasks: {e}")
            return False
    
    @staticmethod
    def configure_auth_queues(celery_app):
        """
        Konfigurasi queue routing untuk auth tasks
        """
        try:
            auth_routes = {
                'auth.cleanup_expired_sessions': {'queue': 'maintenance'},
                'auth.monitor_auth_performance': {'queue': 'monitoring'},
                'auth.refresh_client_detection': {'queue': 'auth_processing'},
                'auth.sync_device_background': {'queue': 'auth_processing'},
                'auth.daily_health_check': {'queue': 'maintenance'}
            }
            
            # Merge dengan routes yang sudah ada
            existing_routes = getattr(celery_app.conf, 'task_routes', {})
            existing_routes.update(auth_routes)
            celery_app.conf.task_routes = existing_routes
            
            logger.info("[SCHEDULER] Auth queue routing configured")
            return True
            
        except Exception as e:
            logger.error(f"[SCHEDULER] Failed to configure auth queues: {e}")
            return False

def integrate_with_extensions(celery_app):
    """
    Function untuk dipanggil dari extensions.py
    Mengintegrasikan auth optimization dengan Celery factory
    """
    try:
        # Register tasks
        scheduler = AuthOptimizationScheduler()
        scheduler.register_auth_tasks(celery_app)
        scheduler.configure_auth_queues(celery_app)
        
        # Set additional configuration
        celery_app.conf.update(
            # Task serialization
            task_serializer='json',
            result_serializer='json',
            accept_content=['json'],
            
            # Auth-specific settings
            task_soft_time_limit=300,  # 5 minutes
            task_time_limit=600,       # 10 minutes
            worker_prefetch_multiplier=1,
            
            # Enable task tracking
            task_track_started=True,
            task_send_events=True,
            
            # Result backend settings untuk monitoring
            result_expires=3600,  # 1 hour
        )
        
        logger.info("[INTEGRATION] Auth optimization integrated with Celery factory")
        return True
        
    except Exception as e:
        logger.error(f"[INTEGRATION] Failed to integrate with extensions: {e}")
        return False

# Convenience functions untuk dipanggil dari aplikasi
def setup_auth_scheduler(app, celery_app):
    """
    Setup auth scheduler dalam Flask app context
    """
    with app.app_context():
        return integrate_with_extensions(celery_app)

def trigger_immediate_cleanup():
    """
    Trigger immediate cleanup (untuk testing atau emergency)
    """
    try:
        try:
            from app.tasks.auth_optimization_tasks import cleanup_expired_sessions
            task = cleanup_expired_sessions.apply_async(queue='maintenance')
            logger.info(f"[TRIGGER] Immediate cleanup triggered: {task.id}")
            return task.id
        except ImportError:
            logger.warning("[TRIGGER] Auth optimization tasks not available")
            return "stub_task"
    except Exception as e:
        logger.error(f"[TRIGGER] Failed to trigger immediate cleanup: {e}")
        return None

def get_auth_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Get status of auth optimization task
    """
    try:
        try:
            from app.extensions import celery_app as celery
        except ImportError:
            logger.warning("Celery not available from extensions")
            return None
            
        result = celery.AsyncResult(task_id)
        
        return {
            "task_id": task_id,
            "state": result.state,
            "result": result.result if result.ready() else None,
            "info": result.info,
            "successful": result.successful() if result.ready() else None,
            "failed": result.failed() if result.ready() else None
        }
        
    except Exception as e:
        logger.error(f"[STATUS] Failed to get task status: {e}")
        return None
