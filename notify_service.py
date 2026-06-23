"""
Notification Service
====================
Email and WhatsApp alert system for POS
- Email via SMTP (Gmail, SendGrid, etc.)
- WhatsApp via Twilio
- Template-based messaging
"""

import os
import logging
from typing import Optional, List, Dict
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests not installed. WhatsApp alerts unavailable.")

try:
    from email_service import email_service as _email_service_instance
    EMAIL_SERVICE_AVAILABLE = True
    email_service = _email_service_instance
except ImportError:
    EMAIL_SERVICE_AVAILABLE = False
    email_service = None


class NotificationService:
    """
    Multi-channel notification service
    """
    
    def __init__(self):
        """Initialize notification service"""
        # Email configuration - SMTP
        self.smtp_enabled = bool(os.environ.get('EMAIL_USER') and os.environ.get('EMAIL_PASS'))
        self.email_user = os.environ.get('EMAIL_USER')
        self.email_pass = os.environ.get('EMAIL_PASS')
        self.email_host = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
        self.email_port = int(os.environ.get('EMAIL_PORT', '587'))
        
        # Email configuration - SendGrid (Twilio) fallback
        self.sendgrid_enabled = EMAIL_SERVICE_AVAILABLE and email_service and email_service.available
        
        # Overall email enabled if either backend works
        self.email_enabled = self.smtp_enabled or self.sendgrid_enabled
        
        # WhatsApp/Twilio configuration
        self.whatsapp_enabled = bool(
            os.environ.get('TWILIO_ACCOUNT_SID') and 
            os.environ.get('TWILIO_AUTH_TOKEN') and
            os.environ.get('TWILIO_WHATSAPP_FROM')
        )
        self.twilio_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        self.twilio_token = os.environ.get('TWILIO_AUTH_TOKEN')
        self.twilio_from = os.environ.get('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')
        
        logger.info(f"Notifications: Email={'✓' if self.email_enabled else '✗'}, WhatsApp={'✓' if self.whatsapp_enabled else '✗'}")
    
    # ============================================================
    # EMAIL ALERTS
    # ============================================================
    
    async def send_email_alert(
        self,
        to: str,
        subject: str,
        message: str,
        html: Optional[str] = None
    ) -> bool:
        """
        Send email alert via SMTP or SendGrid (Twilio) fallback.
        """
        if not self.email_enabled:
            logger.warning("Email not configured. Skipping email alert.")
            return False
        
        # Try SendGrid first if SMTP is not configured
        if not self.smtp_enabled and self.sendgrid_enabled:
            try:
                result = email_service.send_email(to, subject, html or message, message)
                return result.get("success", False)
            except Exception as e:
                logger.error(f"SendGrid email failed to {to}: {e}")
                return False
        
        # Fall back to SMTP
        if not self.smtp_enabled:
            logger.warning("No email backend configured (SMTP or SendGrid).")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.email_user
            msg['To'] = to
            msg['Subject'] = subject
            msg['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
            
            msg.attach(MIMEText(message, 'plain'))
            if html:
                msg.attach(MIMEText(html, 'html'))
            
            with smtplib.SMTP(self.email_host, self.email_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_pass)
                server.send_message(msg)
            
            logger.info(f"Email sent to {to}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Email send failed to {to}: {e}")
            return False
    
    def send_business_alert(
        self,
        to: str,
        business_name: str,
        alert_type: str,
        details: str
    ) -> bool:
        """
        Send formatted business alert email
        
        Args:
            to: Recipient email
            business_name: Business name
            alert_type: Type of alert
            details: Alert details
        """
        subject = f"🚨 {alert_type.upper()} Alert - {business_name}"
        
        message = f"""
POS System Alert
================

Business: {business_name}
Alert Type: {alert_type}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Details:
{details}

---
This is an automated alert from your POS system.
"""
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px; }}
        .container {{ background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ color: #d32f2f; font-size: 24px; margin-bottom: 20px; }}
        .alert-type {{ background-color: #ffebee; color: #c62828; padding: 10px; border-radius: 4px; margin: 15px 0; }}
        .details {{ background-color: #f5f5f5; padding: 15px; border-left: 4px solid #2196F3; margin: 15px 0; }}
        .footer {{ color: #666; font-size: 12px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">🚨 POS System Alert</div>
        <p><strong>Business:</strong> {business_name}</p>
        <div class="alert-type"><strong>Alert Type:</strong> {alert_type}</div>
        <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <div class="details">
            <strong>Details:</strong><br>
            {details.replace(chr(10), '<br>')}
        </div>
        <div class="footer">
            This is an automated alert from your POS system.
        </div>
    </div>
</body>
</html>
"""
        
        import asyncio
        return asyncio.run(self.send_email_alert(to, subject, message, html))
    
    # ============================================================
    # WHATSAPP ALERTS
    # ============================================================
    
    async def send_whatsapp_alert(
        self,
        to: str,
        message: str
    ) -> bool:
        """
        Send WhatsApp alert via Twilio
        
        Args:
            to: Phone number (E.164 format, e.g., +254712345678)
            message: Message text
            
        Returns:
            True if sent successfully
        """
        if not self.whatsapp_enabled:
            logger.warning("WhatsApp not configured. Skipping WhatsApp alert.")
            return False
        
        if not HAS_REQUESTS:
            logger.error("requests library required for WhatsApp")
            return False
        
        try:
            # Format phone number for WhatsApp
            if not to.startswith('whatsapp:'):
                to = f'whatsapp:{to}'
            
            # Twilio API
            url = f'https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json'
            
            response = requests.post(
                url,
                auth=(self.twilio_sid, self.twilio_token),
                data={
                    'From': self.twilio_from,
                    'To': to,
                    'Body': message
                }
            )
            
            if response.status_code == 201:
                logger.info(f"WhatsApp sent to {to}")
                return True
            else:
                logger.error(f"WhatsApp send failed: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"WhatsApp send failed to {to}: {e}")
            return False
    
    def send_business_whatsapp(
        self,
        to: str,
        business_name: str,
        alert_type: str,
        details: str
    ) -> bool:
        """
        Send formatted business alert via WhatsApp
        
        Args:
            to: Phone number
            business_name: Business name
            alert_type: Type of alert
            details: Alert details
        """
        message = f"""
🚨 *POS Alert*

*Business:* {business_name}
*Alert:* {alert_type}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M')}

{details}

_Automated alert from your POS system_
"""
        
        import asyncio
        return asyncio.run(self.send_whatsapp_alert(to, message))
    
    # ============================================================
    # BATCH NOTIFICATIONS
    # ============================================================
    
    async def send_to_multiple(
        self,
        recipients: List[str],
        subject: str,
        message: str,
        channel: str = 'email'
    ) -> Dict[str, bool]:
        """
        Send notification to multiple recipients
        
        Args:
            recipients: List of email addresses or phone numbers
            subject: Subject/title
            message: Message content
            channel: 'email' or 'whatsapp'
            
        Returns:
            Dict mapping recipient to success status
        """
        results = {}
        
        for recipient in recipients:
            try:
                if channel == 'email':
                    results[recipient] = await self.send_email_alert(recipient, subject, message)
                elif channel == 'whatsapp':
                    results[recipient] = await self.send_whatsapp_alert(recipient, message)
                else:
                    results[recipient] = False
            except Exception as e:
                logger.error(f"Failed to send to {recipient}: {e}")
                results[recipient] = False
        
        return results


# Global notification service instance
_notification_service = None


def get_notification_service() -> NotificationService:
    """Get or create notification service singleton"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
