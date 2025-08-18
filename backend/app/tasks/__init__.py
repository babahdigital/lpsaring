# backend/app/tasks/__init__.py
"""
Celery tasks package untuk hotspot portal
"""

# Import dari auth optimization tasks (baru)
from .auth_optimization_tasks import (
    cleanup_expired_sessions,
    refresh_client_detection,
    monitor_auth_performance,
    sync_device_background,
    schedule_auth_maintenance,
    trigger_background_sync
)

def init_celery(app, celery):
    """Initialize Celery with Flask app context"""
    class ContextTask(celery.Task):
        """Make celery tasks work with Flask app context."""
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery

# Define a class to create stub tasks that mimic Celery tasks
class CeleryTaskStub:
    """Task stub class that mimics a Celery task"""
    def __init__(self, task_name):
        self.task_name = task_name
        
    def __call__(self, *args, **kwargs):
        """Direct call implementation"""
        try:
            # Direct import of specific task instead of whole module to avoid circular imports
            import importlib
            module = importlib.import_module('app.tasks')
            task_func = getattr(module, self.task_name)
            return task_func(*args, **kwargs)
        except (ImportError, AttributeError) as e:
            return {"status": "stub", "message": f"Legacy task not available: {str(e)}"}
    
    def delay(self, *args, **kwargs):
        """Implements .delay() method for async execution"""
        try:
            # We should directly call the function instead of trying to call delay recursively
            # This avoids the infinite recursion issue
            return self.__call__(*args, **kwargs)
        except Exception as e:
            return {"status": "stub", "message": f"Legacy task delay not available: {str(e)}"}

# Create task stub instances for legacy tasks
send_whatsapp_invoice_task = CeleryTaskStub("send_whatsapp_invoice_task")
check_low_quota_task = CeleryTaskStub("check_low_quota_task")
sync_single_user_status = CeleryTaskStub("sync_single_user_status")
dispatch_all_users_sync = CeleryTaskStub("dispatch_all_users_sync")

# Create more task stubs for other legacy tasks
record_daily_usage = CeleryTaskStub("record_daily_usage")
sync_device_ip_bindings = CeleryTaskStub("sync_device_ip_bindings")
cleanup_stale_devices = CeleryTaskStub("cleanup_stale_devices")
validate_device_consistency = CeleryTaskStub("validate_device_consistency")

__all__ = [
    # Core functions
    'init_celery',
    
    # Auth optimization tasks (baru)
    'cleanup_expired_sessions',
    'refresh_client_detection',
    'monitor_auth_performance', 
    'sync_device_background',
    'schedule_auth_maintenance',
    'trigger_background_sync',
    
    # Legacy tasks (untuk compatibility)
    'send_whatsapp_invoice_task',
    'check_low_quota_task',
    'sync_single_user_status',
    'dispatch_all_users_sync',
    'record_daily_usage',
    'sync_device_ip_bindings',
    'cleanup_stale_devices',
    'validate_device_consistency'
]
