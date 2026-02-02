"""
Monitoring & Analytics Module
Performance monitoring, error tracking, user analytics
"""

import time
import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict

class PerformanceMonitor:
    def __init__(self):
        self.metrics = defaultdict(list)
        self.errors = []
        self.user_actions = []
    
    def track_performance(self, operation_name):
        """Performance tracking decorator"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    
                    self.metrics[operation_name].append({
                        'duration': duration,
                        'timestamp': datetime.utcnow().isoformat(),
                        'success': True
                    })
                    
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    self.track_error(operation_name, str(e))
                    self.metrics[operation_name].append({
                        'duration': duration,
                        'timestamp': datetime.utcnow().isoformat(),
                        'success': False,
                        'error': str(e)
                    })
                    raise
            return wrapper
        return decorator
    
    def track_error(self, operation, error_message):
        """Track errors"""
        self.errors.append({
            'operation': operation,
            'error': error_message,
            'timestamp': datetime.utcnow().isoformat()
        })
    
    def track_user_action(self, user_id, action, metadata=None):
        """Track user actions"""
        self.user_actions.append({
            'user_id': user_id,
            'action': action,
            'metadata': metadata or {},
            'timestamp': datetime.utcnow().isoformat()
        })
    
    def get_performance_stats(self):
        """Get performance statistics"""
        stats = {}
        for operation, metrics in self.metrics.items():
            durations = [m['duration'] for m in metrics]
            success_rate = sum(1 for m in metrics if m['success']) / len(metrics) * 100
            
            stats[operation] = {
                'avg_duration': sum(durations) / len(durations),
                'max_duration': max(durations),
                'min_duration': min(durations),
                'success_rate': success_rate,
                'total_calls': len(metrics)
            }
        return stats
    
    def get_error_summary(self):
        """Get error summary"""
        error_counts = defaultdict(int)
        for error in self.errors[-100:]:  # Last 100 errors
            error_counts[error['operation']] += 1
        return dict(error_counts)

class UserAnalytics:
    def __init__(self):
        self.sessions = {}
        self.page_views = []
        self.conversions = []
    
    def track_session_start(self, user_id, metadata=None):
        """Track session start"""
        self.sessions[user_id] = {
            'start_time': datetime.utcnow().isoformat(),
            'metadata': metadata or {},
            'page_views': 0,
            'actions': 0
        }
    
    def track_page_view(self, user_id, page):
        """Track page views"""
        self.page_views.append({
            'user_id': user_id,
            'page': page,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        if user_id in self.sessions:
            self.sessions[user_id]['page_views'] += 1
    
    def track_conversion(self, user_id, conversion_type, value=None):
        """Track conversions (sales, signups, etc.)"""
        self.conversions.append({
            'user_id': user_id,
            'type': conversion_type,
            'value': value,
            'timestamp': datetime.utcnow().isoformat()
        })
    
    def get_analytics_summary(self):
        """Get analytics summary"""
        return {
            'active_sessions': len(self.sessions),
            'total_page_views': len(self.page_views),
            'total_conversions': len(self.conversions),
            'conversion_rate': len(self.conversions) / max(len(self.sessions), 1) * 100
        }

# Error tracking middleware
class ErrorTracker:
    def __init__(self):
        self.errors = []
    
    def log_error(self, error, context=None):
        """Log error with context"""
        self.errors.append({
            'error': str(error),
            'type': type(error).__name__,
            'context': context or {},
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # Log to file/external service
        logging.error(f"Error: {error}", extra={'context': context})
    
    def get_recent_errors(self, limit=50):
        """Get recent errors"""
        return self.errors[-limit:]