"""
CREDIT REQUESTS CONTROLLER
==========================
Handles cashier credit requests with admin approval workflow.
Supports request tracking, approval/rejection, and notification system.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class CreditRequestsController:
    """
    Credit requests controller for cashier-admin workflow
    """
    
    def __init__(self, datastore):
        """
        Initialize credit requests controller
        
        Args:
            datastore: DataStore instance
        """
        self.ds = datastore
    
    def create_request(
        self, 
        account_id: str, 
        cashier_id: int, 
        cashier_name: str,
        customer_name: str,
        amount: float, 
        reason: str,
        notes: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Create a new credit request
        
        Args:
            account_id: Account ID
            cashier_id: Cashier user ID
            cashier_name: Cashier name
            customer_name: Customer name
            amount: Credit amount requested
            reason: Reason for credit request
            notes: Optional additional notes
        
        Returns:
            (success, error_message, credit_request)
        """
        try:
            if amount <= 0:
                return False, "Credit amount must be positive", None
            
            if not customer_name or not reason:
                return False, "Customer name and reason are required", None
            
            credit_request = {
                'account_id': account_id,
                'cashier_id': cashier_id,
                'cashier_name': cashier_name,
                'customer_name': customer_name.strip(),
                'amount': float(amount),
                'reason': reason.strip(),
                'notes': notes.strip() if notes else None,
                'status': 'pending',
                'reviewed_by': None,
                'reviewed_at': None,
                'admin_notes': None,
                'created_at': datetime.now().isoformat()
            }
            
            created_request = self.ds.create('credit_requests', credit_request)
            
            logger.info(f"✅ Credit request created: {customer_name} - KSH {amount} by {cashier_name}")
            
            return True, None, created_request
            
        except Exception as e:
            logger.error(f"❌ Failed to create credit request: {e}")
            return False, f"Failed to create credit request: {str(e)}", None
    
    def get_pending_requests(self, account_id: str) -> List[Dict]:
        """
        Get all pending credit requests for admin review
        
        Args:
            account_id: Account ID
        
        Returns:
            List of pending credit requests
        """
        try:
            all_requests = self.ds.get_all('credit_requests', account_id)
            
            pending_requests = [
                req for req in all_requests 
                if req.get('status') == 'pending'
            ]
            
            # Sort by creation date (oldest first for FIFO processing)
            pending_requests.sort(key=lambda r: r.get('created_at', ''))
            
            logger.info(f"📋 Found {len(pending_requests)} pending credit requests")
            
            return pending_requests
            
        except Exception as e:
            logger.error(f"❌ Failed to get pending requests: {e}")
            return []
    
    def get_all_requests(self, account_id: str, cashier_id: Optional[int] = None) -> List[Dict]:
        """
        Get all credit requests with optional cashier filter
        
        Args:
            account_id: Account ID
            cashier_id: Optional cashier ID filter
        
        Returns:
            List of credit requests
        """
        try:
            requests = self.ds.get_all('credit_requests', account_id)
            
            if cashier_id:
                requests = [req for req in requests if req.get('cashier_id') == cashier_id]
            
            # Sort by creation date (newest first)
            requests.sort(key=lambda r: r.get('created_at', ''), reverse=True)
            
            return requests
            
        except Exception as e:
            logger.error(f"❌ Failed to get credit requests: {e}")
            return []
    
    def approve_request(
        self, 
        request_id: int, 
        account_id: str, 
        admin_id: int,
        admin_notes: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Approve a credit request
        
        Args:
            request_id: Credit request ID
            account_id: Account ID
            admin_id: Admin user ID
            admin_notes: Optional admin notes
        
        Returns:
            (success, error_message, updated_request)
        """
        try:
            request = self.ds.get_by_id('credit_requests', request_id, account_id)
            if not request:
                return False, "Credit request not found", None
            
            if request.get('status') != 'pending':
                return False, f"Request is already {request.get('status')}", None
            
            updates = {
                'status': 'approved',
                'reviewed_by': admin_id,
                'reviewed_at': datetime.now().isoformat(),
                'admin_notes': admin_notes.strip() if admin_notes else None
            }
            
            success = self.ds.update('credit_requests', request_id, updates, account_id)
            if not success:
                return False, "Failed to update request", None
            
            updated_request = self.ds.get_by_id('credit_requests', request_id, account_id)
            
            logger.info(f"✅ Credit request {request_id} approved by admin {admin_id}")
            
            return True, None, updated_request
            
        except Exception as e:
            logger.error(f"❌ Failed to approve request {request_id}: {e}")
            return False, f"Approval failed: {str(e)}", None
    
    def reject_request(
        self, 
        request_id: int, 
        account_id: str, 
        admin_id: int,
        admin_notes: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Reject a credit request
        
        Args:
            request_id: Credit request ID
            account_id: Account ID
            admin_id: Admin user ID
            admin_notes: Optional admin notes (recommended for rejections)
        
        Returns:
            (success, error_message, updated_request)
        """
        try:
            request = self.ds.get_by_id('credit_requests', request_id, account_id)
            if not request:
                return False, "Credit request not found", None
            
            if request.get('status') != 'pending':
                return False, f"Request is already {request.get('status')}", None
            
            updates = {
                'status': 'rejected',
                'reviewed_by': admin_id,
                'reviewed_at': datetime.now().isoformat(),
                'admin_notes': admin_notes.strip() if admin_notes else None
            }
            
            success = self.ds.update('credit_requests', request_id, updates, account_id)
            if not success:
                return False, "Failed to update request", None
            
            updated_request = self.ds.get_by_id('credit_requests', request_id, account_id)
            
            logger.info(f"❌ Credit request {request_id} rejected by admin {admin_id}")
            
            return True, None, updated_request
            
        except Exception as e:
            logger.error(f"❌ Failed to reject request {request_id}: {e}")
            return False, f"Rejection failed: {str(e)}", None
    
    def get_request_by_id(self, request_id: int, account_id: str) -> Optional[Dict]:
        """
        Get a specific credit request by ID
        
        Args:
            request_id: Credit request ID
            account_id: Account ID
        
        Returns:
            Credit request or None
        """
        try:
            return self.ds.get_by_id('credit_requests', request_id, account_id)
        except Exception as e:
            logger.error(f"❌ Failed to get request {request_id}: {e}")
            return None
    
    def get_cashier_requests(self, account_id: str, cashier_id: int) -> List[Dict]:
        """
        Get credit requests for a specific cashier
        
        Args:
            account_id: Account ID
            cashier_id: Cashier user ID
        
        Returns:
            List of cashier's credit requests
        """
        try:
            requests = self.get_all_requests(account_id, cashier_id)
            
            logger.info(f"📋 Found {len(requests)} credit requests for cashier {cashier_id}")
            
            return requests
            
        except Exception as e:
            logger.error(f"❌ Failed to get cashier requests: {e}")
            return []
    
    def get_statistics(self, account_id: str) -> Dict:
        """
        Get credit request statistics for admin dashboard
        
        Args:
            account_id: Account ID
        
        Returns:
            Statistics dictionary
        """
        try:
            all_requests = self.ds.get_all('credit_requests', account_id)
            
            total_requests = len(all_requests)
            pending_count = len([r for r in all_requests if r.get('status') == 'pending'])
            approved_count = len([r for r in all_requests if r.get('status') == 'approved'])
            rejected_count = len([r for r in all_requests if r.get('status') == 'rejected'])
            
            total_approved_amount = sum(
                r.get('amount', 0) for r in all_requests 
                if r.get('status') == 'approved'
            )
            
            total_pending_amount = sum(
                r.get('amount', 0) for r in all_requests 
                if r.get('status') == 'pending'
            )
            
            # Calculate approval rate
            reviewed_count = approved_count + rejected_count
            approval_rate = (approved_count / max(reviewed_count, 1)) * 100
            
            return {
                'totalRequests': total_requests,
                'pendingCount': pending_count,
                'approvedCount': approved_count,
                'rejectedCount': rejected_count,
                'totalApprovedAmount': total_approved_amount,
                'totalPendingAmount': total_pending_amount,
                'approvalRate': round(approval_rate, 1)
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get credit request statistics: {e}")
            return {
                'totalRequests': 0,
                'pendingCount': 0,
                'approvedCount': 0,
                'rejectedCount': 0,
                'totalApprovedAmount': 0,
                'totalPendingAmount': 0,
                'approvalRate': 0
            }
    
    def delete_request(self, request_id: int, account_id: str) -> bool:
        """
        Delete a credit request (admin only)
        
        Args:
            request_id: Credit request ID
            account_id: Account ID
        
        Returns:
            Success status
        """
        try:
            success = self.ds.delete('credit_requests', request_id, account_id)
            
            if success:
                logger.info(f"🗑️ Credit request {request_id} deleted")
            else:
                logger.warning(f"Credit request {request_id} not found for deletion")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Failed to delete credit request {request_id}: {e}")
            return False