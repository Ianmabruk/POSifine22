"""
TIME TRACKING CONTROLLER
========================
Handles clock in/out operations with automatic duration calculation
and real-time sync across admin and cashier dashboards.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class TimeTrackingController:
    """
    Time tracking controller for cashier clock in/out operations
    """
    
    def __init__(self, datastore):
        """
        Initialize time tracking controller
        
        Args:
            datastore: DataStore instance
        """
        self.ds = datastore
    
    def clock_in(self, user_id: int, user_name: str, account_id: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Clock in a user
        
        Args:
            user_id: User ID
            user_name: User name
            account_id: Account ID
        
        Returns:
            (success, error_message, time_entry)
        """
        try:
            # Check if user is already clocked in
            active_entry = self.ds.get_active_time_entry(user_id, account_id)
            if active_entry:
                return False, f"User {user_name} is already clocked in since {active_entry.get('clock_in_time')}", None
            
            # Create new time entry
            now = datetime.now()
            time_entry = {
                'account_id': account_id,
                'user_id': user_id,
                'user_name': user_name,
                'clock_in_time': now.isoformat(),
                'clock_out_time': None,
                'duration_minutes': 0,
                'date': now.strftime('%Y-%m-%d'),
                'notes': None
            }
            
            created_entry = self.ds.create('time_entries', time_entry)
            
            logger.info(f"✅ User {user_name} (ID: {user_id}) clocked in at {now.strftime('%H:%M:%S')}")
            
            return True, None, created_entry
            
        except Exception as e:
            logger.error(f"❌ Clock in failed for user {user_id}: {e}")
            return False, f"Clock in failed: {str(e)}", None
    
    def clock_out(self, user_id: int, user_name: str, account_id: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Clock out a user
        
        Args:
            user_id: User ID
            user_name: User name
            account_id: Account ID
        
        Returns:
            (success, error_message, time_entry)
        """
        try:
            # Find active time entry
            active_entry = self.ds.get_active_time_entry(user_id, account_id)
            if not active_entry:
                return False, f"User {user_name} is not clocked in", None
            
            # Calculate duration
            now = datetime.now()
            clock_in_time = datetime.fromisoformat(active_entry['clock_in_time'])
            duration = now - clock_in_time
            duration_minutes = int(duration.total_seconds() / 60)
            
            # Update time entry
            updates = {
                'clock_out_time': now.isoformat(),
                'duration_minutes': duration_minutes
            }
            
            success = self.ds.update('time_entries', active_entry['id'], updates, account_id)
            if not success:
                return False, "Failed to update time entry", None
            
            # Get updated entry
            updated_entry = self.ds.get_by_id('time_entries', active_entry['id'], account_id)
            
            logger.info(f"✅ User {user_name} (ID: {user_id}) clocked out at {now.strftime('%H:%M:%S')} - Duration: {duration_minutes} minutes")
            
            return True, None, updated_entry
            
        except Exception as e:
            logger.error(f"❌ Clock out failed for user {user_id}: {e}")
            return False, f"Clock out failed: {str(e)}", None
    
    def get_clock_status(self, user_id: int, account_id: str) -> Dict:
        """
        Get current clock status for user
        
        Args:
            user_id: User ID
            account_id: Account ID
        
        Returns:
            Clock status information
        """
        try:
            active_entry = self.ds.get_active_time_entry(user_id, account_id)
            
            if active_entry:
                clock_in_time = datetime.fromisoformat(active_entry['clock_in_time'])
                current_duration = int((datetime.now() - clock_in_time).total_seconds() / 60)
                
                return {
                    'isClockedIn': True,
                    'clockInTime': active_entry['clock_in_time'],
                    'currentDuration': current_duration,
                    'entryId': active_entry['id']
                }
            else:
                return {
                    'isClockedIn': False,
                    'clockInTime': None,
                    'currentDuration': 0,
                    'entryId': None
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to get clock status for user {user_id}: {e}")
            return {
                'isClockedIn': False,
                'clockInTime': None,
                'currentDuration': 0,
                'entryId': None,
                'error': str(e)
            }
    
    def get_time_entries(self, account_id: str, user_id: Optional[int] = None, date: Optional[str] = None) -> list:
        """
        Get time entries with optional filters
        
        Args:
            account_id: Account ID
            user_id: Optional user ID filter
            date: Optional date filter (YYYY-MM-DD)
        
        Returns:
            List of time entries
        """
        try:
            entries = self.ds.get_all('time_entries', account_id)
            
            # Apply filters
            if user_id:
                entries = [e for e in entries if e.get('user_id') == user_id]
            
            if date:
                entries = [e for e in entries if e.get('date') == date]
            
            # Sort by clock_in_time descending
            entries.sort(key=lambda x: x.get('clock_in_time', ''), reverse=True)
            
            return entries
            
        except Exception as e:
            logger.error(f"❌ Failed to get time entries: {e}")
            return []
    
    def get_daily_summary(self, account_id: str, date: Optional[str] = None) -> Dict:
        """
        Get daily time tracking summary
        
        Args:
            account_id: Account ID
            date: Date (YYYY-MM-DD), defaults to today
        
        Returns:
            Daily summary statistics
        """
        try:
            if not date:
                date = datetime.now().strftime('%Y-%m-%d')
            
            entries = self.get_time_entries(account_id, date=date)
            
            total_hours = 0
            active_users = []
            completed_shifts = 0
            
            for entry in entries:
                if entry.get('clock_out_time'):
                    # Completed shift
                    duration_minutes = entry.get('duration_minutes', 0)
                    total_hours += duration_minutes / 60
                    completed_shifts += 1
                else:
                    # Active shift
                    active_users.append({
                        'user_id': entry.get('user_id'),
                        'user_name': entry.get('user_name'),
                        'clock_in_time': entry.get('clock_in_time')
                    })
            
            return {
                'date': date,
                'totalHours': round(total_hours, 2),
                'activeUsers': len(active_users),
                'completedShifts': completed_shifts,
                'activeUsersList': active_users
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get daily summary: {e}")
            return {
                'date': date or datetime.now().strftime('%Y-%m-%d'),
                'totalHours': 0,
                'activeUsers': 0,
                'completedShifts': 0,
                'activeUsersList': [],
                'error': str(e)
            }