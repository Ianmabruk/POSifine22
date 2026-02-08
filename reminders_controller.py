"""
REMINDERS SYSTEM CONTROLLER
===========================
Handles admin-created reminders that appear once in cashier dashboards.
Supports rich text, priority levels, and automatic expiration.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import logging

logger = logging.getLogger(__name__)


class RemindersController:
    """
    Reminders system controller
    """
    
    def __init__(self, datastore):
        """
        Initialize reminders controller
        
        Args:
            datastore: DataStore instance
        """
        self.ds = datastore
    
    def create_reminder(
        self, 
        account_id: str, 
        created_by: int, 
        title: str, 
        message: str,
        priority: str = 'normal',
        expires_at: Optional[str] = None,
        target_users: Optional[List[int]] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Create a new reminder
        
        Args:
            account_id: Account ID
            created_by: Admin user ID who created the reminder
            title: Reminder title
            message: Reminder message
            priority: Priority level ('low', 'normal', 'high', 'urgent')
            expires_at: Optional expiration datetime (ISO format)
            target_users: Optional list of specific user IDs (None = all users)
        
        Returns:
            (success, error_message, reminder)
        """
        try:
            if not title or not message:
                return False, "Title and message are required", None
            
            # Auto-expire in 7 days if not specified
            if not expires_at:
                expires_at = (datetime.now() + timedelta(days=7)).isoformat()
            
            reminder = {
                'account_id': account_id,
                'title': title.strip(),
                'message': message.strip(),
                'priority': priority,
                'created_by': created_by,
                'created_at': datetime.now().isoformat(),
                'expires_at': expires_at,
                'target_users': target_users or [],  # Empty list = all users
                'seen_by': [],  # List of user IDs who have seen this reminder
                'is_active': True,
                'status': 'pending',
                'admin_note': '',
                'cashier_note': '',
                'admin_signature': '',
                'cashier_signature': '',
                'admin_signed_at': None,
                'cashier_signed_at': None
            }
            created_reminder = self.ds.create('reminders', reminder)
            
            logger.info(f"✅ Reminder created: '{title}' by user {created_by}")
            
            return True, None, created_reminder
            
        except Exception as e:
            logger.error(f"❌ Failed to create reminder: {e}")
            return False, f"Failed to create reminder: {str(e)}", None
    
    def get_unseen_reminders(self, account_id: str, user_id: int) -> List[Dict]:
        """
        Get unseen reminders for a specific user
        
        Args:
            account_id: Account ID
            user_id: User ID
        
        Returns:
            List of unseen reminders
        """
        try:
            all_reminders = self.ds.get_all('reminders', account_id)
            now = datetime.now()
            
            unseen_reminders = []
            
            for reminder in all_reminders:
                # Skip inactive reminders
                if not reminder.get('is_active', True):
                    continue
                
                # Skip expired reminders
                expires_at = reminder.get('expires_at')
                if expires_at:
                    try:
                        expiry_date = datetime.fromisoformat(expires_at)
                        if now > expiry_date:
                            continue
                    except ValueError:
                        # Invalid date format, skip
                        continue
                
                # Check if user has already seen this reminder
                seen_by = reminder.get('seen_by', [])
                if user_id in seen_by:
                    continue
                
                # Check if reminder is targeted to specific users
                target_users = reminder.get('target_users', [])
                if target_users and user_id not in target_users:
                    continue
                
                unseen_reminders.append(reminder)
            
            # Sort by priority and creation date
            priority_order = {'urgent': 0, 'high': 1, 'normal': 2, 'low': 3}
            unseen_reminders.sort(key=lambda r: (
                priority_order.get(r.get('priority', 'normal'), 2),
                r.get('created_at', '')
            ))
            
            logger.info(f"📋 Found {len(unseen_reminders)} unseen reminders for user {user_id}")
            
            return unseen_reminders
            
        except Exception as e:
            logger.error(f"❌ Failed to get unseen reminders for user {user_id}: {e}")
            return []
    
    def mark_reminder_seen(self, reminder_id: int, user_id: int, account_id: str) -> bool:
        """
        Mark a reminder as seen by a user
        
        Args:
            reminder_id: Reminder ID
            user_id: User ID
            account_id: Account ID
        
        Returns:
            Success status
        """
        try:
            reminder = self.ds.get_by_id('reminders', reminder_id, account_id)
            if not reminder:
                logger.warning(f"Reminder {reminder_id} not found")
                return False
            
            seen_by = reminder.get('seen_by', [])
            if user_id not in seen_by:
                seen_by.append(user_id)
                
                success = self.ds.update('reminders', reminder_id, {
                    'seen_by': seen_by
                }, account_id)
                
                if success:
                    logger.info(f"✅ Reminder {reminder_id} marked as seen by user {user_id}")
                    return True
                else:
                    logger.error(f"❌ Failed to update reminder {reminder_id}")
                    return False
            else:
                # Already seen
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to mark reminder {reminder_id} as seen: {e}")
            return False
    
    def get_all_reminders(self, account_id: str, include_expired: bool = False) -> List[Dict]:
        """
        Get all reminders for admin dashboard
        
        Args:
            account_id: Account ID
            include_expired: Whether to include expired reminders
        
        Returns:
            List of reminders with statistics
        """
        try:
            reminders = self.ds.get_all('reminders', account_id)
            now = datetime.now()
            
            result = []
            for reminder in reminders:
                # Check expiration
                is_expired = False
                expires_at = reminder.get('expires_at')
                if expires_at:
                    try:
                        expiry_date = datetime.fromisoformat(expires_at)
                        is_expired = now > expiry_date
                    except ValueError:
                        is_expired = True
                
                if is_expired and not include_expired:
                    continue
                
                # Add statistics
                seen_by = reminder.get('seen_by', [])
                target_users = reminder.get('target_users', [])
                
                # Get total target user count
                if target_users:
                    total_targets = len(target_users)
                else:
                    # All users in account
                    all_users = self.ds.get_all('users', account_id)
                    total_targets = len([u for u in all_users if u.get('role') != 'admin'])

                reminder_with_stats = {
                    **reminder,
                    'is_expired': is_expired,
                    'seen_count': len(seen_by),
                    'total_targets': total_targets,
                    'completion_rate': (len(seen_by) / max(total_targets, 1)) * 100
                }

                result.append(reminder_with_stats)

            # Sort by creation date (newest first)
            result.sort(key=lambda r: r.get('created_at', ''), reverse=True)

            return result

        except Exception as e:
            logger.error(f"❌ Failed to get all reminders: {e}")
            return []

    def update_reminder(self, reminder_id: int, account_id: str, updates: Dict) -> Tuple[bool, Optional[str]]:
        """
        Update a reminder

        Args:
            reminder_id: Reminder ID
            account_id: Account ID
            updates: Fields to update

        Returns:
            (success, error_message)
        """
        try:
            # Add updated timestamp
            updates['updated_at'] = datetime.now().isoformat()

            success = self.ds.update('reminders', reminder_id, updates, account_id)

            if success:
                logger.info(f"✅ Reminder {reminder_id} updated")
                return True, None
            else:
                return False, "Reminder not found"

        except Exception as e:
            logger.error(f"❌ Failed to update reminder {reminder_id}: {e}")
            return False, f"Update failed: {str(e)}"

    def delete_reminder(self, reminder_id: int, account_id: str) -> bool:
        """
        Delete a reminder

        Args:
            reminder_id: Reminder ID
            account_id: Account ID

        Returns:
            Success status
        """
        try:
            success = self.ds.delete('reminders', reminder_id, account_id)

            if success:
                logger.info(f"✅ Reminder {reminder_id} deleted")
            else:
                logger.warning(f"Reminder {reminder_id} not found for deletion")

            return success

        except Exception as e:
            logger.error(f"❌ Failed to delete reminder {reminder_id}: {e}")
            return False

    def cleanup_expired_reminders(self, account_id: str) -> int:
        """
        Clean up expired reminders (optional maintenance task)

        Args:
            account_id: Account ID

        Returns:
            Number of reminders cleaned up
        """
        try:
            reminders = self.ds.get_all('reminders', account_id)
            now = datetime.now()
            cleaned_count = 0

            for reminder in reminders:
                expires_at = reminder.get('expires_at')
                if expires_at:
                    try:
                        expiry_date = datetime.fromisoformat(expires_at)
                        # Delete reminders expired more than 30 days ago
                        if now > expiry_date + timedelta(days=30):
                            if self.ds.delete('reminders', reminder['id'], account_id):
                                cleaned_count += 1
                    except ValueError:
                        # Invalid date, delete it
                        if self.ds.delete('reminders', reminder['id'], account_id):
                            cleaned_count += 1

            if cleaned_count > 0:
                logger.info(f"🧹 Cleaned up {cleaned_count} expired reminders")

            return cleaned_count

        except Exception as e:
            logger.error(f"❌ Failed to cleanup expired reminders: {e}")
            return 0