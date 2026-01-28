"""
AI Alert Engine
================
Background service for monitoring business metrics and sending alerts
- Scheduled anomaly detection
- Automatic email/WhatsApp notifications
- Configurable thresholds
"""

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from threading import Thread
import time

from ai_service import get_ai_service
from notify_service import get_notification_service

logger = logging.getLogger(__name__)


class AlertEngine:
    """
    Background alert engine with scheduled checks
    """
    
    def __init__(self, datastore, check_interval: int = 3600):
        """
        Initialize alert engine
        
        Args:
            datastore: Database connection
            check_interval: Seconds between checks (default: 1 hour)
        """
        self.datastore = datastore
        self.check_interval = check_interval
        self.ai_service = get_ai_service()
        self.notify_service = get_notification_service()
        
        self.running = False
        self.thread: Optional[Thread] = None
        
        # Alert configuration
        self.alert_config = {
            'revenue_drop_threshold': 0.3,  # 30% drop
            'expense_spike_threshold': 0.5,  # 50% increase
            'low_sales_threshold': 5,  # Minimum sales per day
            'enabled_channels': ['email', 'whatsapp']
        }
    
    # ============================================================
    # ENGINE CONTROL
    # ============================================================
    
    def start(self):
        """Start alert engine in background thread"""
        if self.running:
            logger.warning("Alert engine already running")
            return
        
        self.running = True
        self.thread = Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info(f"Alert engine started (checking every {self.check_interval}s)")
    
    def stop(self):
        """Stop alert engine"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Alert engine stopped")
    
    def _run_loop(self):
        """Main background loop"""
        while self.running:
            try:
                # Run checks
                asyncio.run(self._check_all_accounts())
            except Exception as e:
                logger.error(f"Alert check failed: {e}")
            
            # Sleep until next check
            time.sleep(self.check_interval)
    
    # ============================================================
    # ALERT CHECKS
    # ============================================================
    
    async def _check_all_accounts(self):
        """Check all active accounts for alerts"""
        try:
            # Get all active accounts
            accounts = self.datastore.get_all('accounts')
            active_accounts = [
                acc for acc in accounts
                if acc.get('is_active') and not acc.get('is_locked')
            ]
            
            logger.info(f"Checking {len(active_accounts)} accounts for alerts")
            
            for account in active_accounts:
                try:
                    await self._check_account(account)
                except Exception as e:
                    logger.error(f"Alert check failed for account {account['id']}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to check accounts: {e}")
    
    async def _check_account(self, account: Dict):
        """Check single account for alerts"""
        account_id = account['id']
        
        # Get recent data
        sales = self._get_recent_sales(account_id, days=7)
        expenses = self._get_recent_expenses(account_id, days=7)
        
        # Skip if no data
        if not sales and not expenses:
            return
        
        # Detect anomalies with AI
        anomalies = await self.ai_service.detect_anomalies(
            sales,
            expenses,
            threshold=self.alert_config['revenue_drop_threshold']
        )
        
        # Send alerts for critical issues
        critical_alerts = [
            alert for alert in anomalies
            if alert.get('severity') in ['critical', 'high']
        ]
        
        if critical_alerts:
            await self._send_alerts(account, critical_alerts)
    
    def _get_recent_sales(self, account_id: str, days: int = 7) -> List[Dict]:
        """Get recent sales for account"""
        try:
            all_sales = self.datastore.get_by_field('sales', 'account_id', account_id)
            cutoff = datetime.now() - timedelta(days=days)
            
            recent = [
                sale for sale in all_sales
                if datetime.fromisoformat(sale.get('created_at', '')) > cutoff
            ]
            
            return recent
        except Exception as e:
            logger.error(f"Failed to get sales: {e}")
            return []
    
    def _get_recent_expenses(self, account_id: str, days: int = 7) -> List[Dict]:
        """Get recent expenses for account"""
        try:
            all_expenses = self.datastore.get_by_field('expenses', 'account_id', account_id)
            cutoff = datetime.now() - timedelta(days=days)
            
            recent = [
                exp for exp in all_expenses
                if datetime.fromisoformat(exp.get('created_at', '')) > cutoff
            ]
            
            return recent
        except Exception as e:
            logger.error(f"Failed to get expenses: {e}")
            return []
    
    # ============================================================
    # NOTIFICATION
    # ============================================================
    
    async def _send_alerts(self, account: Dict, alerts: List[Dict]):
        """Send alerts to account owner"""
        account_id = account['id']
        owner_email = account.get('owner_email')
        business_name = account.get('business_name', 'Your Business')
        
        if not owner_email:
            logger.warning(f"No owner email for account {account_id}")
            return
        
        # Format alert message
        alert_text = self._format_alerts(alerts)
        
        # Send via configured channels
        if 'email' in self.alert_config['enabled_channels']:
            await self._send_email_alert(
                owner_email,
                business_name,
                alerts[0].get('type', 'alert'),
                alert_text
            )
        
        # Get phone number from account settings (if configured)
        phone = account.get('owner_phone') or account.get('alert_phone')
        if phone and 'whatsapp' in self.alert_config['enabled_channels']:
            await self._send_whatsapp_alert(
                phone,
                business_name,
                alerts[0].get('type', 'alert'),
                alert_text
            )
    
    def _format_alerts(self, alerts: List[Dict]) -> str:
        """Format alerts into readable message"""
        lines = []
        
        for i, alert in enumerate(alerts, 1):
            severity = alert.get('severity', 'medium').upper()
            alert_type = alert.get('type', 'unknown')
            message = alert.get('message', 'No details')
            action = alert.get('action', 'Review your dashboard')
            
            lines.append(f"{i}. [{severity}] {alert_type}")
            lines.append(f"   {message}")
            lines.append(f"   Action: {action}")
            lines.append("")
        
        return "\n".join(lines)
    
    async def _send_email_alert(
        self,
        email: str,
        business_name: str,
        alert_type: str,
        details: str
    ):
        """Send email alert"""
        try:
            success = self.notify_service.send_business_alert(
                email,
                business_name,
                alert_type,
                details
            )
            
            if success:
                logger.info(f"Email alert sent to {email}")
            else:
                logger.warning(f"Email alert failed for {email}")
                
        except Exception as e:
            logger.error(f"Email alert error: {e}")
    
    async def _send_whatsapp_alert(
        self,
        phone: str,
        business_name: str,
        alert_type: str,
        details: str
    ):
        """Send WhatsApp alert"""
        try:
            success = self.notify_service.send_business_whatsapp(
                phone,
                business_name,
                alert_type,
                details
            )
            
            if success:
                logger.info(f"WhatsApp alert sent to {phone}")
            else:
                logger.warning(f"WhatsApp alert failed for {phone}")
                
        except Exception as e:
            logger.error(f"WhatsApp alert error: {e}")
    
    # ============================================================
    # MANUAL TRIGGERS
    # ============================================================
    
    async def check_account_now(self, account_id: str) -> List[Dict]:
        """
        Manually check account for alerts
        
        Args:
            account_id: Account to check
            
        Returns:
            List of detected alerts
        """
        account = self.datastore.get_by_id('accounts', account_id)
        if not account:
            return []
        
        sales = self._get_recent_sales(account_id, days=7)
        expenses = self._get_recent_expenses(account_id, days=7)
        
        anomalies = await self.ai_service.detect_anomalies(sales, expenses)
        
        return anomalies
    
    def configure_alerts(
        self,
        revenue_threshold: Optional[float] = None,
        expense_threshold: Optional[float] = None,
        channels: Optional[List[str]] = None
    ):
        """
        Update alert configuration
        
        Args:
            revenue_threshold: Revenue drop threshold (0-1)
            expense_threshold: Expense spike threshold (0-1)
            channels: Enabled channels ['email', 'whatsapp']
        """
        if revenue_threshold is not None:
            self.alert_config['revenue_drop_threshold'] = revenue_threshold
        
        if expense_threshold is not None:
            self.alert_config['expense_spike_threshold'] = expense_threshold
        
        if channels is not None:
            self.alert_config['enabled_channels'] = channels
        
        logger.info(f"Alert config updated: {self.alert_config}")


# Global alert engine instance
_alert_engine = None


def get_alert_engine(datastore=None) -> AlertEngine:
    """Get or create alert engine singleton"""
    global _alert_engine
    if _alert_engine is None and datastore is not None:
        _alert_engine = AlertEngine(datastore)
    return _alert_engine


def start_alert_engine(datastore, auto_start: bool = True):
    """
    Initialize and start alert engine
    
    Args:
        datastore: Database connection
        auto_start: Whether to start immediately
    """
    engine = get_alert_engine(datastore)
    if auto_start and engine:
        engine.start()
    return engine
