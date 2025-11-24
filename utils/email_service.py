# utils/email_service.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from core.config import settings
import logging
from jinja2 import Template

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP"""
    
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.use_tls = settings.SMTP_TLS
        self.use_ssl = settings.SMTP_SSL
    
    def _create_smtp_connection(self):
        """Create SMTP connection"""
        try:
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            
            if self.use_tls and not self.use_ssl:
                server.starttls()
            
            server.login(self.smtp_user, self.smtp_password)
            return server
        except Exception as e:
            logger.error(f"SMTP connection error: {str(e)}")
            raise
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Send an email
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email content
            text_content: Plain text email content (optional)
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email
            
            # Add text version
            if text_content:
                part1 = MIMEText(text_content, "plain")
                message.attach(part1)
            
            # Add HTML version
            part2 = MIMEText(html_content, "html")
            message.attach(part2)
            
            # Send email
            server = self._create_smtp_connection()
            server.send_message(message)
            server.quit()
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
    def send_password_reset_email(
        self,
        to_email: str,
        reset_token: str,
        user_name: str = "User"
    ) -> bool:
        """
        Send password reset email
        
        Args:
            to_email: Recipient email
            reset_token: Password reset token
            user_name: User's name
            
        Returns:
            True if sent successfully
        """
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        
        subject = "Password Reset Request - IntgraServe-AI"
        
        # HTML template
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }
                .container {
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }
                .header {
                    background-color: #4CAF50;
                    color: white;
                    padding: 20px;
                    text-align: center;
                }
                .content {
                    padding: 20px;
                    background-color: #f9f9f9;
                }
                .button {
                    display: inline-block;
                    padding: 12px 24px;
                    background-color: #4CAF50;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                    margin: 20px 0;
                }
                .footer {
                    text-align: center;
                    padding: 20px;
                    font-size: 12px;
                    color: #666;
                }
                .warning {
                    background-color: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 12px;
                    margin: 20px 0;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{{ app_name }}</h1>
                </div>
                <div class="content">
                    <h2>Password Reset Request</h2>
                    <p>Hello {{ user_name }},</p>
                    <p>We received a request to reset your password. Click the button below to reset it:</p>
                    <center>
                        <a href="{{ reset_link }}" class="button">Reset Password</a>
                    </center>
                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #0066cc;">{{ reset_link }}</p>
                    
                    <div class="warning">
                        <strong>⚠️ Important:</strong> This link will expire in {{ expire_minutes }} minutes.
                    </div>
                    
                    <p>If you didn't request a password reset, please ignore this email or contact support if you have concerns.</p>
                </div>
                <div class="footer">
                    <p>© 2024 {{ app_name }}. All rights reserved.</p>
                    <p>This is an automated email, please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = Template(html_template)
        html_content = template.render(
            app_name=settings.APP_NAME,
            user_name=user_name,
            reset_link=reset_link,
            expire_minutes=settings.RESET_TOKEN_EXPIRE_MINUTES
        )
        
        # Plain text version
        text_content = f"""
        Password Reset Request
        
        Hello {user_name},
        
        We received a request to reset your password. Click the link below to reset it:
        
        {reset_link}
        
        This link will expire in {settings.RESET_TOKEN_EXPIRE_MINUTES} minutes.
        
        If you didn't request a password reset, please ignore this email.
        
        © 2024 {settings.APP_NAME}
        """
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )
    
    def send_password_reset_confirmation_email(
        self,
        to_email: str,
        user_name: str = "User"
    ) -> bool:
        """
        Send confirmation email after successful password reset
        
        Args:
            to_email: Recipient email
            user_name: User's name
            
        Returns:
            True if sent successfully
        """
        subject = "Password Reset Successful - IntgraServe-AI"
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }
                .container {
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }
                .header {
                    background-color: #4CAF50;
                    color: white;
                    padding: 20px;
                    text-align: center;
                }
                .content {
                    padding: 20px;
                    background-color: #f9f9f9;
                }
                .success {
                    background-color: #d4edda;
                    border-left: 4px solid #28a745;
                    padding: 12px;
                    margin: 20px 0;
                }
                .footer {
                    text-align: center;
                    padding: 20px;
                    font-size: 12px;
                    color: #666;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{{ app_name }}</h1>
                </div>
                <div class="content">
                    <h2>Password Reset Successful</h2>
                    <p>Hello {{ user_name }},</p>
                    
                    <div class="success">
                        <strong>✓ Success!</strong> Your password has been reset successfully.
                    </div>
                    
                    <p>You can now log in to your account using your new password.</p>
                    <p>If you did not make this change, please contact our support team immediately.</p>
                </div>
                <div class="footer">
                    <p>© 2024 {{ app_name }}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = Template(html_template)
        html_content = template.render(
            app_name=settings.APP_NAME,
            user_name=user_name
        )
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content
        )
    
    # ==================== Ticket Email Notifications ====================
    
    def send_ticket_status_update(
        self,
        to_email: str,
        customer_name: str,
        ticket_id: str,
        ticket_title: str,
        old_status: str,
        new_status: str,
        updated_by: str
    ) -> bool:
        """Send email when ticket status changes"""
        subject = f"Ticket Status Updated - {ticket_title}"
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #4CAF50; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background-color: #f9f9f9; }
                .status-box { background-color: #e3f2fd; border-left: 4px solid #2196F3; padding: 12px; margin: 20px 0; }
                .footer { text-align: center; padding: 20px; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{{ app_name }}</h1>
                </div>
                <div class="content">
                    <h2>Ticket Status Updated</h2>
                    <p>Hello {{ customer_name }},</p>
                    <p>Your support ticket has been updated:</p>
                    
                    <div class="status-box">
                        <strong>Ticket ID:</strong> {{ ticket_id }}<br>
                        <strong>Title:</strong> {{ ticket_title }}<br>
                        <strong>Previous Status:</strong> {{ old_status }}<br>
                        <strong>New Status:</strong> {{ new_status }}<br>
                        <strong>Updated By:</strong> {{ updated_by }}
                    </div>
                    
                    <p>You can track your ticket status or add messages by contacting our support team.</p>
                </div>
                <div class="footer">
                    <p>© 2025 {{ app_name }}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = Template(html_template)
        html_content = template.render(
            app_name=settings.APP_NAME,
            customer_name=customer_name,
            ticket_id=ticket_id,
            ticket_title=ticket_title,
            old_status=old_status,
            new_status=new_status,
            updated_by=updated_by
        )
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content
        )
    
    def send_ticket_assigned(
        self,
        to_email: str,
        customer_name: str,
        ticket_id: str,
        ticket_title: str,
        assignee_name: str
    ) -> bool:
        """Send email when ticket is assigned"""
        subject = f"Your Ticket Has Been Assigned - {ticket_title}"
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #4CAF50; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background-color: #f9f9f9; }
                .info-box { background-color: #d4edda; border-left: 4px solid #28a745; padding: 12px; margin: 20px 0; }
                .footer { text-align: center; padding: 20px; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{{ app_name }}</h1>
                </div>
                <div class="content">
                    <h2>Ticket Assigned</h2>
                    <p>Hello {{ customer_name }},</p>
                    <p>Good news! Your support ticket has been assigned to one of our team members:</p>
                    
                    <div class="info-box">
                        <strong>Ticket ID:</strong> {{ ticket_id }}<br>
                        <strong>Title:</strong> {{ ticket_title }}<br>
                        <strong>Assigned To:</strong> {{ assignee_name }}
                    </div>
                    
                    <p>Our team is now working on your issue and will update you soon.</p>
                </div>
                <div class="footer">
                    <p>© 2025 {{ app_name }}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = Template(html_template)
        html_content = template.render(
            app_name=settings.APP_NAME,
            customer_name=customer_name,
            ticket_id=ticket_id,
            ticket_title=ticket_title,
            assignee_name=assignee_name
        )
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content
        )
    
    def send_ticket_resolved(
        self,
        to_email: str,
        customer_name: str,
        ticket_id: str,
        ticket_title: str,
        resolution_notes: str
    ) -> bool:
        """Send email when ticket is resolved"""
        subject = f"Your Ticket Has Been Resolved - {ticket_title}"
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #4CAF50; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background-color: #f9f9f9; }
                .success-box { background-color: #d4edda; border-left: 4px solid #28a745; padding: 12px; margin: 20px 0; }
                .footer { text-align: center; padding: 20px; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{{ app_name }}</h1>
                </div>
                <div class="content">
                    <h2>✓ Ticket Resolved</h2>
                    <p>Hello {{ customer_name }},</p>
                    <p>Great news! Your support ticket has been resolved:</p>
                    
                    <div class="success-box">
                        <strong>Ticket ID:</strong> {{ ticket_id }}<br>
                        <strong>Title:</strong> {{ ticket_title }}<br><br>
                        <strong>Resolution:</strong><br>
                        {{ resolution_notes }}
                    </div>
                    
                    <p>If you have any further questions or if the issue persists, please don't hesitate to contact us.</p>
                </div>
                <div class="footer">
                    <p>© 2025 {{ app_name }}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = Template(html_template)
        html_content = template.render(
            app_name=settings.APP_NAME,
            customer_name=customer_name,
            ticket_id=ticket_id,
            ticket_title=ticket_title,
            resolution_notes=resolution_notes
        )
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content
        )
    
    def send_new_message_notification(
        self,
        to_email: str,
        customer_name: str,
        ticket_id: str,
        ticket_title: str,
        sender_name: str,
        message_text: str
    ) -> bool:
        """Send email when new message is added to ticket"""
        subject = f"New Message on Your Ticket - {ticket_title}"
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #4CAF50; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background-color: #f9f9f9; }
                .message-box { background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 12px; margin: 20px 0; }
                .footer { text-align: center; padding: 20px; font-size: 12px; color: #666; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{{ app_name }}</h1>
                </div>
                <div class="content">
                    <h2>New Message</h2>
                    <p>Hello {{ customer_name }},</p>
                    <p>You have a new message on your support ticket:</p>
                    
                    <div class="message-box">
                        <strong>Ticket ID:</strong> {{ ticket_id }}<br>
                        <strong>Title:</strong> {{ ticket_title }}<br>
                        <strong>From:</strong> {{ sender_name }}<br><br>
                        <strong>Message:</strong><br>
                        {{ message_text }}
                    </div>
                    
                    <p>You can reply to this message by contacting our support team.</p>
                </div>
                <div class="footer">
                    <p>© 2025 {{ app_name }}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        template = Template(html_template)
        html_content = template.render(
            app_name=settings.APP_NAME,
            customer_name=customer_name,
            ticket_id=ticket_id,
            ticket_title=ticket_title,
            sender_name=sender_name,
            message_text=message_text[:500]
        )
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content
        )


# Singleton instance
email_service = EmailService()