"""
Email Service using SendGrid (Twilio)
Handles transactional emails: welcome, password reset, notifications, etc.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import sendgrid
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content, TemplateId
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    logger.warning("SendGrid not installed. Run: pip install sendgrid")


class EmailService:
    """Email service using SendGrid (Twilio)."""

    def __init__(self):
        self.api_key = os.environ.get("SENDGRID_API_KEY") or os.environ.get("TWILIO_SENDGRID_API_KEY") or os.environ.get("EMAIL_API_KEY")
        self.from_email = os.environ.get("FROM_EMAIL", "noreply@posify.co.ke")
        self.from_name = os.environ.get("FROM_NAME", "POSIFY")
        self.reply_to = os.environ.get("REPLY_TO", "support@posify.co.ke")
        self.available = SENDGRID_AVAILABLE and bool(self.api_key)
        
        if not self.available:
            logger.warning("EmailService disabled: missing SENDGRID_API_KEY or sendgrid library")

    def _build_message(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Mail:
        """Build a SendGrid Mail object."""
        from_email = Email(self.from_email, from_name or self.from_name)
        to = To(to_email)
        content = Content("text/html", html_content)
        if text_content:
            content.text_content = text_content
        
        mail = Mail(from_email, to, subject, content)
        mail.reply_to = Email(reply_to or self.reply_to)
        mail.bcc = Email(self.from_email)  # BCC admin for record
        return mail

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a single email."""
        if not self.available:
            logger.error("EmailService not available - cannot send email")
            return {"success": False, "error": "Email service not configured"}

        try:
            mail = self._build_message(to_email, subject, html_content, text_content, from_name, reply_to)
            sg = SendGridAPIClient(self.api_key)
            response = sg.send(mail)
            
            logger.info(f"Email sent to {to_email} | Subject: {subject} | Status: {response.status_code}")
            
            return {
                "success": True,
                "status_code": response.status_code,
                "to": to_email,
                "subject": subject,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return {"success": False, "error": str(e), "to": to_email, "subject": subject}

    def send_bulk_email(
        self,
        recipients: List[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send email to multiple recipients (personalized )."""
        results = {"success": [], "failed": []}
        
        for email in recipients:
            result = self.send_email(email, subject, html_content, text_content)
            if result.get("success"):
                results["success"].append(email)
            else:
                results["failed"].append({"email": email, "error": result.get("error")})
        
        return results

    def send_welcome_email(self, to_email: str, name: str, business_name: str = "", login_url: str = "") -> Dict[str, Any]:
        """Welcome email sent when a new user signs up."""
        subject = "Welcome to POSIFY - Your Business Journey Starts Now"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Welcome to POSIFY</title>
        </head>
        <body style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f8fafc;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%); padding: 32px 40px; text-align: center;">
                    <div style="width: 48px; height: 48px; background: white; border-radius: 12px; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center;">
                        <span style="font-size: 24px; font-weight: 800; color: #2563EB;">P</span>
                    </div>
                    <h1 style="color: white; font-size: 24px; font-weight: 700; margin: 0 0 8px;">Welcome to POSIFY</h1>
                    <p style="color: rgba(255,255,255,0.85); font-size: 14px; margin: 0;">Your business transformation starts today</p>
                </div>
                
                <!-- Content -->
                <div style="padding: 40px;">
                    <p style="color: #334155; font-size: 16px; line-height: 1.7; margin: 0 0 20px;">
                        Hi <strong>{name}</strong>,
                    </p>
                    <p style="color: #475569; font-size: 15px; line-height: 1.7; margin: 0 0 24px;">
                        Welcome to <strong>POSIFY</strong>! Your account is ready and your 15-day free trial has started.
                        We're excited to help you run your entire business from one powerful platform.
                    </p>
                    
                    {business_name and f'''
                    <div style="background: #F8FAFC; border-radius: 12px; padding: 20px; margin: 24px 0; border: 1px solid #E2E8F0;">
                        <p style="color: #64748B; font-size: 13px; margin: 0 0 4px; text-transform: uppercase; letter-spacing: 0.5px;">Business</p>
                        <p style="color: #1E293B; font-size: 16px; font-weight: 600; margin: 0;">{business_name}</p>
                    </div>
                    '''}
                    
                    <!-- CTA -->
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{login_url or 'https://posify.co.ke/auth/login'}" style="background: #2563EB; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 600; font-size: 15px; display: inline-block;">
                            Go to Dashboard
                        </a>
                    </div>
                    
                    <!-- Divider -->
                    <div style="border-top: 1px solid #E2E8F0; margin: 32px 0;"></div>
                    
                    <!-- Features -->
                    <div style="margin: 24px 0;">
                        <h3 style="color: #1E293B; font-size: 16px; font-weight: 600; margin: 0 0 16px;">What you can do with POSIFY:</h3>
                        <div style="display: grid; gap: 12px;">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <div style="width: 32px; height: 32px; background: #EFF6FF; border-radius: 8px; display: flex; align-items: center; justify-content: center;">
                                    <span style="color: #2563EB; font-size: 14px;">✓</span>
                                </div>
                                <span style="color: #475569; font-size: 14px;">POS & Sales Management</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <div style="width: 32px; height: 32px; background: #EFF6FF; border-radius: 8px; display: flex; align-items: center; justify-content: center;">
                                    <span style="color: #2563EB; font-size: 14px;">✓</span>
                                </div>
                                <span style="color: #475569; font-size: 14px;">Inventory & Stock Control</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <div style="width: 32px; height: 32px; background: #EFF6FF; border-radius: 8px; display: flex; align-items: center; justify-content: center;">
                                    <span style="color: #2563EB; font-size: 14px;">✓</span>
                                </div>
                                <span style="color: #475569; font-size: 14px;">CRM & Customer Loyalty</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <div style="width: 32px; height: 32px; background: #EFF6FF; border-radius: 8px; display: flex; align-items: center; justify-content: center;">
                                    <span style="color: #2563EB; font-size: 14px;">✓</span>
                                </div>
                                <span style="color: #475569; font-size: 14px;">Analytics & Reporting</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Support -->
                    <div style="background: #FFFBEB; border-radius: 12px; padding: 16px; margin: 24px 0; border: 1px solid #FEF3C7;">
                        <p style="color: #92400E; font-size: 13px; margin: 0;">
                            <strong>Need help?</strong> Our support team is here for you. Reply to this email or visit our help center.
                        </p>
                    </div>
                </div>
                
                <!-- Footer -->
                <div style="background: #F8FAFC; padding: 24px 40px; text-align: center; border-top: 1px solid #E2E8F0;">
                    <p style="color: #94A3B8; font-size: 12px; margin: 0 0 8px;">
                        © {datetime.utcnow().year} POSIFY. All rights reserved.
                    </p>
                    <p style="color: #94A3B8; font-size: 11px; margin: 0;">
                        This email was sent to {to_email}
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Welcome to POSIFY, {name}!
        
        Your account is ready and your 15-day free trial has started.
        
        Go to your dashboard: {login_url or 'https://posify.co.ke/auth/login'}
        
        Need help? Reply to this email or visit our help center.
        
        © {datetime.utcnow().year} POSIFY. All rights reserved.
        """
        
        return self.send_email(to_email, subject, html_content, text_content)

    def send_password_reset_email(self, to_email: str, name: str, reset_link: str) -> Dict[str, Any]:
        """Password reset email."""
        subject = "Reset Your POSIFY Password"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: 'Inter', -apple-system, sans-serif; margin: 0; padding: 0; background-color: #f8fafc;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%); padding: 32px 40px; text-align: center;">
                    <div style="width: 48px; height: 48px; background: white; border-radius: 12px; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center;">
                        <span style="font-size: 24px; font-weight: 800; color: #2563EB;">P</span>
                    </div>
                    <h1 style="color: white; font-size: 24px; font-weight: 700; margin: 0 0 8px;">Reset Your Password</h1>
                    <p style="color: rgba(255,255,255,0.85); font-size: 14px; margin: 0;">We received a request to reset your password</p>
                </div>
                
                <div style="padding: 40px;">
                    <p style="color: #334155; font-size: 16px; line-height: 1.7; margin: 0 0 20px;">
                        Hi <strong>{name}</strong>,
                    </p>
                    <p style="color: #475569; font-size: 15px; line-height: 1.7; margin: 0 0 24px;">
                        Click the button below to reset your password. This link expires in 1 hour.
                    </p>
                    
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{reset_link}" style="background: #2563EB; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 600; font-size: 15px; display: inline-block;">
                            Reset Password
                        </a>
                    </div>
                    
                    <p style="color: #94A3B8; font-size: 13px; line-height: 1.6; margin: 24px 0 0;">
                        If you didn't request this, please ignore this email. Your password remains unchanged.
                    </p>
                </div>
                
                <div style="background: #F8FAFC; padding: 24px 40px; text-align: center; border-top: 1px solid #E2E8F0;">
                    <p style="color: #94A3B8; font-size: 12px; margin: 0;">© {datetime.utcnow().year} POSIFY. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(to_email, subject, html_content)

    def send_subscription_reminder(self, to_email: str, name: str, days_left: int, plan: str, renew_url: str) -> Dict[str, Any]:
        """Subscription renewal reminder email."""
        subject = f"Your {plan} plan expires in {days_left} days"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: 'Inter', -apple-system, sans-serif; margin: 0; padding: 0; background-color: #f8fafc;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #F97316 0%, #EA580C 100%); padding: 32px 40px; text-align: center;">
                    <div style="width: 48px; height: 48px; background: white; border-radius: 12px; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center;">
                        <span style="font-size: 24px; font-weight: 800; color: #F97316;">P</span>
                    </div>
                    <h1 style="color: white; font-size: 24px; font-weight: 700; margin: 0 0 8px;">Subscription Reminder</h1>
                    <p style="color: rgba(255,255,255,0.85); font-size: 14px; margin: 0;">Your {plan} plan expires soon</p>
                </div>
                
                <div style="padding: 40px;">
                    <p style="color: #334155; font-size: 16px; line-height: 1.7; margin: 0 0 20px;">
                        Hi <strong>{name}</strong>,
                    </p>
                    <p style="color: #475569; font-size: 15px; line-height: 1.7; margin: 0 0 24px;">
                        Your <strong>{plan}</strong> plan expires in <strong>{days_left} days</strong>.
                        Renew now to avoid service interruption.
                    </p>
                    
                    <div style="background: #FFF7ED; border-radius: 12px; padding: 20px; margin: 24px 0; border: 1px solid #FFEDD5;">
                        <p style="color: #9A3412; font-size: 14px; margin: 0;">
                            <strong>Action required:</strong> Update your payment method to continue using all features.
                        </p>
                    </div>
                    
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{renew_url}" style="background: #F97316; color: white; padding: 14px 32px; border-radius: 12px; text-decoration: none; font-weight: 600; font-size: 15px; display: inline-block;">
                            Renew Subscription
                        </a>
                    </div>
                </div>
                
                <div style="background: #F8FAFC; padding: 24px 40px; text-align: center; border-top: 1px solid #E2E8F0;">
                    <p style="color: #94A3B8; font-size: 12px; margin: 0;">© {datetime.utcnow().year} POSIFY. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(to_email, subject, html_content)


# Singleton instance
email_service = EmailService()
