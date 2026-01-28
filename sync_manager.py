"""
REAL-TIME SYNC MANAGER
======================
Manages real-time synchronization between admin and cashier dashboards using WebSockets.
Broadcasts updates for:
- Sales completion
- Stock changes
- Time tracking (clock in/out)
- Credit requests
- User actions
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)


class SyncManager:
    """
    Real-time synchronization manager
    
    Manages WebSocket connections and broadcasts updates
    to all connected clients (admin and cashier dashboards)
    """
    
    def __init__(self):
        """Initialize sync manager"""
        self.connections: Dict[str, Set] = {}  # {account_id: set of websocket connections}
        self.user_connections: Dict[int, Set] = {}  # {user_id: set of connections}
    
    def register_connection(self, ws, account_id: str, user_id: int):
        """
        Register a new WebSocket connection
        
        Args:
            ws: WebSocket connection object
            account_id: Account ID
            user_id: User ID
        """
        # Store by account
        if account_id not in self.connections:
            self.connections[account_id] = set()
        self.connections[account_id].add(ws)
        
        # Store by user
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(ws)
        
        # Set connection metadata
        ws.account_id = account_id
        ws.user_id = user_id
        
        logger.info(f"Connection registered: account={account_id}, user={user_id}")
    
    def unregister_connection(self, ws):
        """
        Unregister a WebSocket connection
        
        Args:
            ws: WebSocket connection object
        """
        account_id = getattr(ws, 'account_id', None)
        user_id = getattr(ws, 'user_id', None)
        
        if account_id and account_id in self.connections:
            self.connections[account_id].discard(ws)
            if not self.connections[account_id]:
                del self.connections[account_id]
        
        if user_id and user_id in self.user_connections:
            self.user_connections[user_id].discard(ws)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        logger.info(f"Connection unregistered: account={account_id}, user={user_id}")
    
    def broadcast_to_account(self, account_id: str, event_type: str, data: Dict):
        """
        Broadcast message to all connections for an account
        
        Args:
            account_id: Account ID
            event_type: Type of event (sale, stock_update, etc.)
            data: Event data
        """
        if account_id not in self.connections:
            return
        
        message = {
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        
        disconnected = []
        for ws in self.connections[account_id]:
            try:
                ws.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending to connection: {e}")
                disconnected.append(ws)
        
        # Remove disconnected connections
        for ws in disconnected:
            self.unregister_connection(ws)
    
    def broadcast_to_user(self, user_id: int, event_type: str, data: Dict):
        """
        Broadcast message to specific user
        
        Args:
            user_id: User ID
            event_type: Type of event
            data: Event data
        """
        if user_id not in self.user_connections:
            return
        
        message = {
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        
        disconnected = []
        for ws in self.user_connections[user_id]:
            try:
                ws.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending to user connection: {e}")
                disconnected.append(ws)
        
        # Remove disconnected connections
        for ws in disconnected:
            self.unregister_connection(ws)
    
    def broadcast_sale_completed(self, account_id: str, sale: Dict):
        """
        Broadcast sale completion to all dashboards
        
        Args:
            account_id: Account ID
            sale: Sale record
        """
        self.broadcast_to_account(account_id, 'sale_completed', {
            'sale_id': sale.get('id'),
            'total': sale.get('total'),
            'cashier_name': sale.get('cashier_name'),
            'created_at': sale.get('created_at')
        })
    
    def broadcast_stock_update(self, account_id: str, product_id: int, new_quantity: float):
        """
        Broadcast stock update
        
        Args:
            account_id: Account ID
            product_id: Product ID
            new_quantity: New stock quantity
        """
        self.broadcast_to_account(account_id, 'stock_updated', {
            'product_id': product_id,
            'quantity': new_quantity
        })
    
    def broadcast_clock_in(self, account_id: str, user_id: int, user_name: str, time_entry: Dict):
        """
        Broadcast clock in event
        
        Args:
            account_id: Account ID
            user_id: User ID
            user_name: User name
            time_entry: Time entry record
        """
        self.broadcast_to_account(account_id, 'clock_in', {
            'user_id': user_id,
            'user_name': user_name,
            'clock_in_time': time_entry.get('clock_in_time'),
            'entry_id': time_entry.get('id')
        })
    
    def broadcast_clock_out(self, account_id: str, user_id: int, user_name: str, time_entry: Dict):
        """
        Broadcast clock out event
        
        Args:
            account_id: Account ID
            user_id: User ID
            user_name: User name
            time_entry: Time entry record
        """
        self.broadcast_to_account(account_id, 'clock_out', {
            'user_id': user_id,
            'user_name': user_name,
            'clock_out_time': time_entry.get('clock_out_time'),
            'duration_minutes': time_entry.get('duration_minutes'),
            'entry_id': time_entry.get('id')
        })
    
    def broadcast_credit_request(self, account_id: str, credit_request: Dict):
        """
        Broadcast new credit request to admins
        
        Args:
            account_id: Account ID
            credit_request: Credit request record
        """
        self.broadcast_to_account(account_id, 'credit_request', {
            'request_id': credit_request.get('id'),
            'cashier_id': credit_request.get('cashier_id'),
            'cashier_name': credit_request.get('cashier_name'),
            'amount': credit_request.get('amount'),
            'reason': credit_request.get('reason'),
            'created_at': credit_request.get('created_at')
        })
    
    def broadcast_credit_response(self, account_id: str, cashier_id: int, credit_request: Dict):
        """
        Broadcast credit request response to cashier
        
        Args:
            account_id: Account ID
            cashier_id: Cashier user ID
            credit_request: Updated credit request record
        """
        # Send to specific cashier
        self.broadcast_to_user(cashier_id, 'credit_response', {
            'request_id': credit_request.get('id'),
            'status': credit_request.get('status'),
            'admin_notes': credit_request.get('admin_notes'),
            'reviewed_at': credit_request.get('reviewed_at')
        })
    
    def broadcast_reminder(self, account_id: str, reminder: Dict):
        """
        Broadcast new reminder to all users
        
        Args:
            account_id: Account ID
            reminder: Reminder record
        """
        self.broadcast_to_account(account_id, 'new_reminder', {
            'reminder_id': reminder.get('id'),
            'title': reminder.get('title'),
            'message': reminder.get('message'),
            'created_at': reminder.get('created_at')
        })
    
    def broadcast_product_update(self, account_id: str, product: Dict, action: str = 'updated'):
        """
        Broadcast product update (create, update, delete)
        
        Args:
            account_id: Account ID
            product: Product record
            action: 'created', 'updated', or 'deleted'
        """
        self.broadcast_to_account(account_id, 'product_' + action, {
            'product_id': product.get('id'),
            'name': product.get('name'),
            'quantity': product.get('quantity'),
            'price': product.get('price')
        })
    
    def broadcast_user_update(self, account_id: str, user: Dict, action: str = 'updated'):
        """
        Broadcast user update
        
        Args:
            account_id: Account ID
            user: User record
            action: 'created', 'updated', or 'deleted'
        """
        self.broadcast_to_account(account_id, 'user_' + action, {
            'user_id': user.get('id'),
            'name': user.get('name'),
            'role': user.get('role'),
            'is_active': user.get('is_active')
        })
    
    def broadcast_expense_created(self, account_id: str, expense: Dict):
        """
        Broadcast expense creation
        
        Args:
            account_id: Account ID
            expense: Expense record
        """
        self.broadcast_to_account(account_id, 'expense_created', {
            'expense_id': expense.get('id'),
            'name': expense.get('name'),
            'amount': expense.get('amount'),
            'created_at': expense.get('created_at')
        })
    
    def get_connection_count(self, account_id: Optional[str] = None) -> int:
        """
        Get number of active connections
        
        Args:
            account_id: Optional account ID to filter by
        
        Returns:
            Number of connections
        """
        if account_id:
            return len(self.connections.get(account_id, set()))
        else:
            return sum(len(conns) for conns in self.connections.values())


# Global sync manager instance
sync_manager = SyncManager()
