import frappe
from frappe.model.document import Document
from frappe.utils import get_url, now_datetime


class SocialSettings(Document):
    def validate(self):
        if self.linkedin_enabled:
            if not self.linkedin_client_id or not self.linkedin_client_secret:
                frappe.throw("LinkedIn Client ID and Secret are required when LinkedIn is enabled")

        # Set callback URL automatically
        if not self.linkedin_callback_url:
            self.linkedin_callback_url = get_url("/api/method/social.linkedin.auth.callback")

    def on_update(self):
        # Clear cache when settings are updated
        frappe.cache().delete_value("social_settings")

    @frappe.whitelist()
    def test_linkedin_connection(self):
        """Test LinkedIn API connection with current credentials"""
        if not self.linkedin_enabled:
            frappe.throw("LinkedIn integration is not enabled")

        if not self.linkedin_client_id or not self.linkedin_client_secret:
            frappe.throw("LinkedIn credentials are not configured")

        try:
            # Test by making a simple API call to LinkedIn
            import requests

            # Test OAuth endpoint availability
            response = requests.get(
                "https://www.linkedin.com/oauth/v2/authorization",
                params={"response_type": "code", "client_id": self.linkedin_client_id},
                timeout=10
            )

            if response.status_code in [200, 302]:  # 302 is redirect which is expected
                self.linkedin_last_tested = now_datetime()
                self.save()
                return {"success": True, "message": "LinkedIn API connection successful"}
            else:
                return {"success": False, "message": f"LinkedIn API returned status {response.status_code}"}

        except Exception as e:
            frappe.log_error(f"LinkedIn connection test failed: {str(e)}")
            return {"success": False, "message": f"Connection failed: {str(e)}"}


@frappe.whitelist()
def get_social_settings():
    """Get Social Settings singleton document"""
    settings = frappe.get_single("Social Settings")
    return settings


def get_linkedin_credentials():
    """Get LinkedIn OAuth credentials from settings"""
    settings = frappe.get_single("Social Settings")

    if not settings.linkedin_enabled:
        frappe.throw("LinkedIn integration is not enabled in Social Settings")

    if not settings.linkedin_client_id or not settings.linkedin_client_secret:
        frappe.throw("LinkedIn credentials are not configured in Social Settings")

    return {
        "client_id": settings.linkedin_client_id,
        "client_secret": settings.linkedin_client_secret,
        "callback_url": settings.linkedin_callback_url
    }


def get_posting_settings():
    """Get posting configuration from settings"""
    settings = frappe.get_single("Social Settings")

    return {
        "default_visibility": settings.default_visibility or "PUBLIC",
        "auto_schedule_optimization": settings.auto_schedule_optimization,
        "max_posts_per_day": settings.max_posts_per_day or 10,
        "retry_failed_posts": settings.retry_failed_posts,
        "max_retry_attempts": settings.max_retry_attempts or 3,
        "retry_delay_minutes": settings.retry_delay_minutes or 30
    }


def get_analytics_settings():
    """Get analytics configuration from settings"""
    settings = frappe.get_single("Social Settings")

    return {
        "analytics_enabled": settings.analytics_enabled,
        "sync_frequency": settings.analytics_sync_frequency or "Every 6 hours",
        "retention_days": settings.analytics_retention_days or 90,
        "last_sync": settings.last_analytics_sync,
        "api_quota_used": settings.analytics_api_quota_used or 0
    }


@frappe.whitelist()
def update_analytics_sync_status(quota_used=None):
    """Update analytics sync status"""
    settings = frappe.get_single("Social Settings")
    settings.last_analytics_sync = now_datetime()

    if quota_used is not None:
        settings.analytics_api_quota_used = quota_used

    settings.save(ignore_permissions=True)