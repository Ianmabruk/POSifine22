"""
NOTIFICATION SERVICE
====================

Centralized WebSocket broadcasting for real-time updates.
Ensures all connected clients receive consistent notifications.
"""

import json
from datetime import datetime
from typing import Optional, Dict, List, Any


class NotificationService:
    """WebSocket broadcast notifications"""
    
    def __init__(self, connected_clients_list: list = None):
        """
        Args:
            connected_clients_list: Reference to the connected WebSocket clients list
                                   (from app.py's global connected_clients)
        """
        self.connected_clients = connected_clients_list or []
    
    def broadcast(self, message_type: str, data: Dict, account_id: Optional[str] = None) -> int:
        """
        Broadcast a message to all connected clients (optionally filtered by account).
        
        Args:
            message_type: Type of message (e.g., 'sale_completed', 'stock_updated')
            data: Message payload
            account_id: If provided, only send to clients for this account
        
        Returns:
            Number of clients successfully notified
        """
        message = {
            'type': message_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        
        disconnected = []
        notified_count = 0
        
        try:
            for client in self.connected_clients:
                try:
                    # If account_id specified, filter by account
                    if account_id:
                        client_account = getattr(client, 'account_id', None)
                        if client_account != account_id:
                            continue
                    
                    # Send message
                    client.send(json.dumps(message))
                    notified_count += 1
                    
                except Exception as e:
                    print(f"⚠️  Error sending to client: {str(e)}")
                    disconnected.append(client)
            
            # Remove disconnected clients
            for client in disconnected:
                if client in self.connected_clients:
                    self.connected_clients.remove(client)
        
        except Exception as e:
            print(f"❌ Broadcast error: {str(e)}")
        
        return notified_count
    
    def broadcast_sale_completed(self, account_id: str, sale: Dict, 
                                deductions: Dict, updated_products: List[Dict],
                                low_stock: List[Dict], processing_time: str) -> None:
        """
        Broadcast sale completion to all dashboards.
        
        This notification triggers:
        - Cashier dashboard: Product list refresh + success feedback
        - Admin dashboard: Sales list update + inventory view refresh
        """
        notified = self.broadcast('sale_completed', {
            'saleId': sale['id'],
            'total': sale['total'],
            'itemCount': len(sale['items']),
            'paymentMethod': sale['paymentMethod'],
            'completedBy': sale.get('completedBy', 'cashier'),
            'deductions': deductions,
            'updatedProducts': updated_products,
            'lowStockWarnings': low_stock,
            'processingTime': processing_time,
            'timestamp': datetime.now().isoformat()
        }, account_id=account_id)
        
        print(f"📡 Notified {notified} clients of sale #{sale['id']}")
    
    def broadcast_product_updated(self, account_id: str, product: Dict) -> None:
        """Broadcast individual product update (stock change, price change, etc.)"""
        self.broadcast('product_updated', {
            'productId': product['id'],
            'name': product['name'],
            'quantity': product.get('quantity'),
            'price': product.get('price'),
            'unit': product.get('unit'),
            'timestamp': datetime.now().isoformat()
        }, account_id=account_id)
    
    def broadcast_inventory_updated(self, account_id: str, 
                                   updated_products: List[Dict]) -> None:
        """Broadcast full inventory update"""
        self.broadcast('inventory_updated', {
            'allProducts': updated_products,
            'count': len(updated_products),
            'timestamp': datetime.now().isoformat()
        }, account_id=account_id)
    
    def broadcast_stock_warning(self, account_id: str, 
                               warnings: List[Dict]) -> None:
        """Broadcast low stock warnings"""
        if not warnings:
            return
        
        self.broadcast('stock_warning', {
            'warnings': warnings,
            'criticalCount': sum(1 for w in warnings if w.get('severity') == 'CRITICAL'),
            'warningCount': sum(1 for w in warnings if w.get('severity') == 'WARNING'),
            'timestamp': datetime.now().isoformat()
        }, account_id=account_id)
    
    def broadcast_shift_event(self, account_id: str, shift: Dict, 
                             event_type: str = 'shift_opened') -> None:
        """
        Broadcast shift event (open/close).
        
        Args:
            event_type: 'shift_opened', 'shift_closed'
        """
        self.broadcast(event_type, {
            'shiftId': shift['id'],
            'userId': shift['userId'],
            'userName': shift['userName'],
            'clockInTime': shift.get('clockInTime'),
            'clockOutTime': shift.get('clockOutTime'),
            'durationDisplay': shift.get('durationDisplay'),
            'status': shift['status'],
            'timestamp': datetime.now().isoformat()
        }, account_id=account_id)
    
    def broadcast_error(self, account_id: str, 
                       error_code: str, error_msg: str) -> None:
        """Broadcast error notification to dashboards"""
        self.broadcast('error_occurred', {
            'errorCode': error_code,
            'errorMessage': error_msg,
            'timestamp': datetime.now().isoformat()
        }, account_id=account_id)
