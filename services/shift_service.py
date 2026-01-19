"""
UNIFIED SHIFT SERVICE
=====================

Replaces fragmented time_entries.json + clock_entries.json systems.

Single source of truth for cashier shifts:
- Clock-in creates shift record
- Clock-out closes shift record
- Track duration, sales count, total amount during shift
- Audit trail for all activities

Data structure:
{
    'id': 1,
    'userId': 123,
    'userName': 'John Cashier',
    'accountId': 'acme_corp',
    'clockInTime': '2024-01-19T09:30:00',
    'clockOutTime': '2024-01-19T18:00:00',
    'status': 'OPEN' | 'CLOSED',
    'durationSeconds': 30600,
    'durationDisplay': '8h 30m',
    'salesCount': 15,
    'salesTotal': 45000.50,
    'notes': '',
    'createdAt': '2024-01-19T09:30:00'
}
"""

from datetime import datetime
from typing import Dict, List, Tuple, Optional
from decimal import Decimal, ROUND_HALF_UP


def safe_round(value: float, decimal_places: int = 2) -> float:
    """Safely round to prevent floating-point errors"""
    try:
        if value is None or (isinstance(value, float) and (value != value)):
            return 0.0
        d = Decimal(str(value))
        rounded = d.quantize(Decimal(10) ** -decimal_places, rounding=ROUND_HALF_UP)
        return float(rounded)
    except (ValueError, TypeError):
        return float(value) if value else 0.0


class ShiftService:
    """Unified shift management"""
    
    def __init__(self, data_store):
        """
        Args:
            data_store: DataStore instance
        """
        self.data_store = data_store
    
    def clock_in(self, user_id: int, user_name: str, account_id: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Clock in - create new shift.
        
        Returns:
            (success, error_msg, shift_record)
        """
        try:
            shifts = self.data_store.load('shifts')
            if shifts is None:
                shifts = []
            
            # Check for existing open shift
            existing_open = next(
                (s for s in shifts 
                 if s.get('userId') == user_id 
                 and s.get('accountId') == account_id
                 and s.get('status') == 'OPEN'),
                None
            )
            
            if existing_open:
                clock_in_time = existing_open.get('clockInTime', 'unknown')
                return False, f'Already clocked in since {clock_in_time}. Clock out first.', None
            
            # Create new shift
            shift_id = max([s.get('id', 0) for s in shifts] + [0]) + 1
            
            shift = {
                'id': shift_id,
                'userId': user_id,
                'userName': user_name,
                'accountId': account_id,
                'clockInTime': datetime.now().isoformat(),
                'clockOutTime': None,
                'status': 'OPEN',
                'durationSeconds': 0,
                'durationDisplay': '0h 0m',
                'salesCount': 0,
                'salesTotal': 0.0,
                'notes': '',
                'createdAt': datetime.now().isoformat()
            }
            
            shifts.append(shift)
            
            if not self.data_store.save('shifts', shifts):
                return False, 'Failed to save shift record', None
            
            print(f"✅ {user_name} clocked IN at {shift['clockInTime']}")
            
            return True, None, shift
            
        except Exception as e:
            print(f"❌ Clock-in error: {str(e)}")
            return False, f'Clock-in failed: {str(e)}', None
    
    def clock_out(self, user_id: int, account_id: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Clock out - close open shift.
        
        Returns:
            (success, error_msg, closed_shift_record)
        """
        try:
            shifts = self.data_store.load('shifts')
            if shifts is None:
                shifts = []
            
            # Find open shift for this user
            open_shift = next(
                (s for s in shifts 
                 if s.get('userId') == user_id 
                 and s.get('accountId') == account_id
                 and s.get('status') == 'OPEN'),
                None
            )
            
            if not open_shift:
                return False, 'Not currently clocked in. No active shift found.', None
            
            # Calculate duration
            try:
                clock_in_time = datetime.fromisoformat(open_shift['clockInTime'])
            except (ValueError, KeyError):
                return False, 'Invalid clock-in time stored in shift record', None
            
            clock_out_time = datetime.now()
            duration_seconds = int((clock_out_time - clock_in_time).total_seconds())
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60
            
            # Update shift
            open_shift['clockOutTime'] = clock_out_time.isoformat()
            open_shift['status'] = 'CLOSED'
            open_shift['durationSeconds'] = duration_seconds
            open_shift['durationDisplay'] = f'{hours}h {minutes}m'
            
            if not self.data_store.save('shifts', shifts):
                return False, 'Failed to save shift closure', None
            
            print(f"✅ {open_shift['userName']} clocked OUT after {hours}h {minutes}m")
            
            return True, None, open_shift
            
        except Exception as e:
            print(f"❌ Clock-out error: {str(e)}")
            return False, f'Clock-out failed: {str(e)}', None
    
    def get_active_shift(self, user_id: int, account_id: str) -> Optional[Dict]:
        """Get current open shift for user (if any)"""
        try:
            shifts = self.data_store.load('shifts')
            if shifts is None:
                return None
            
            open_shift = next(
                (s for s in shifts 
                 if s.get('userId') == user_id 
                 and s.get('accountId') == account_id
                 and s.get('status') == 'OPEN'),
                None
            )
            
            if open_shift:
                # Calculate current elapsed time
                try:
                    clock_in_time = datetime.fromisoformat(open_shift['clockInTime'])
                    elapsed_seconds = int((datetime.now() - clock_in_time).total_seconds())
                    hours = elapsed_seconds // 3600
                    minutes = (elapsed_seconds % 3600) // 60
                    
                    return {
                        **open_shift,
                        'elapsedSeconds': elapsed_seconds,
                        'elapsedDisplay': f'{hours}h {minutes}m'
                    }
                except (ValueError, KeyError):
                    return open_shift
            
            return None
            
        except Exception as e:
            print(f"⚠️  Error getting active shift: {str(e)}")
            return None
    
    def get_user_shifts(self, user_id: int, account_id: str, limit: int = 50) -> List[Dict]:
        """Get all shifts for user, most recent first"""
        try:
            shifts = self.data_store.load('shifts')
            if shifts is None:
                return []
            
            user_shifts = [s for s in shifts 
                          if s.get('userId') == user_id 
                          and s.get('accountId') == account_id]
            
            # Sort by clock-in time, most recent first
            user_shifts.sort(key=lambda x: x.get('clockInTime', ''), reverse=True)
            
            return user_shifts[:limit]
            
        except Exception as e:
            print(f"⚠️  Error getting user shifts: {str(e)}")
            return []
    
    def get_all_shifts(self, account_id: str, limit: int = 100) -> List[Dict]:
        """Get all shifts for account, most recent first"""
        try:
            shifts = self.data_store.load('shifts')
            if shifts is None:
                return []
            
            account_shifts = [s for s in shifts if s.get('accountId') == account_id]
            
            # Sort by clock-in time, most recent first
            account_shifts.sort(key=lambda x: x.get('clockInTime', ''), reverse=True)
            
            return account_shifts[:limit]
            
        except Exception as e:
            print(f"⚠️  Error getting account shifts: {str(e)}")
            return []
    
    def update_shift_sales(self, shift_id: int, sale_total: float, 
                          increment_count: bool = True) -> bool:
        """
        Update shift with sales data when a sale is completed.
        
        Called by sales service after each successful sale.
        """
        try:
            shifts = self.data_store.load('shifts')
            if shifts is None:
                return False
            
            shift = next((s for s in shifts if s.get('id') == shift_id), None)
            if not shift:
                return False
            
            if increment_count:
                shift['salesCount'] = (shift.get('salesCount', 0) or 0) + 1
            
            shift['salesTotal'] = safe_round(
                float(shift.get('salesTotal', 0) or 0) + float(sale_total)
            )
            
            return self.data_store.save('shifts', shifts)
            
        except Exception as e:
            print(f"⚠️  Error updating shift sales: {str(e)}")
            return False
