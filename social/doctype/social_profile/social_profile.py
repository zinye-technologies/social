import frappe
from frappe.model.document import Document
from frappe.utils import now


class SocialProfile(Document):
    def validate(self):
        """Validate Social Profile before saving"""
        self.validate_platform_requirements()
        self.set_timestamps()

    def validate_platform_requirements(self):
        """Validate platform-specific requirements"""
        if self.platform == "LinkedIn":
            if not self.platform_type:
                frappe.throw("Platform Type is required for LinkedIn profiles")

            if self.platform_type == "Company Page" and not self.linkedin_company_id:
                if self.linkedin_access_token:  # Only validate if we have a token
                    frappe.throw("LinkedIn Company ID is required for Company Pages")

    def set_timestamps(self):
        """Set creation and modification timestamps"""
        if self.is_new():
            self.created_at = now()
        self.modified_at = now()

    def before_insert(self):
        """Actions before inserting new Social Profile"""
        # Set default profile name if not provided
        if not self.profile_name:
            if self.platform == "LinkedIn" and self.linkedin_company_name:
                self.profile_name = f"{self.linkedin_company_name} - LinkedIn"
            else:
                self.profile_name = f"{self.platform} - {self.user}"

    def on_update(self):
        """Actions after updating Social Profile"""
        # Trigger analytics sync if profile becomes active
        if self.is_active and self.analytics_enabled and self.linkedin_access_token:
            frappe.enqueue(
                "social.linkedin.analytics.sync_profile_analytics",
                profile=self.name,
                queue="short"
            )

    @frappe.whitelist()
    def test_linkedin_connection(self):
        """Test LinkedIn API connection"""
        try:
            if not self.linkedin_access_token:
                return {"success": False, "error": "No access token found"}

            from social.linkedin.api import LinkedInAPI
            api = LinkedInAPI(self.linkedin_access_token)

            if self.platform_type == "Personal Profile":
                profile_info = api.get_profile_info()
            else:
                profile_info = api.get_company_info(self.linkedin_company_id)

            return {"success": True, "data": profile_info}

        except Exception as e:
            frappe.log_error(f"LinkedIn connection test failed: {str(e)}")
            return {"success": False, "error": str(e)}

    @frappe.whitelist()
    def refresh_linkedin_token(self):
        """Refresh LinkedIn access token"""
        try:
            if not self.linkedin_refresh_token:
                frappe.throw("No refresh token available")

            from social.linkedin.auth import LinkedInAuth
            auth = LinkedInAuth()

            token_data = auth.refresh_access_token(self.linkedin_refresh_token)

            self.linkedin_access_token = token_data.get("access_token")
            self.linkedin_token_expires_at = token_data.get("expires_at")

            if token_data.get("refresh_token"):
                self.linkedin_refresh_token = token_data.get("refresh_token")

            self.save()

            return {"success": True, "message": "Token refreshed successfully"}

        except Exception as e:
            frappe.log_error(f"Token refresh failed: {str(e)}")
            return {"success": False, "error": str(e)}

    @frappe.whitelist()
    def sync_analytics(self):
        """Manually trigger analytics sync"""
        if not self.is_active or not self.analytics_enabled:
            frappe.throw("Profile is not active or analytics is disabled")

        frappe.enqueue(
            "social.linkedin.analytics.sync_profile_analytics",
            profile=self.name,
            queue="short"
        )

        return {"success": True, "message": "Analytics sync started"}

    def get_posting_permissions(self):
        """Get posting permissions for this profile"""
        permissions = {
            "can_post": False,
            "can_schedule": False,
            "requires_approval": self.post_approval_required
        }

        if self.is_active and self.linkedin_access_token:
            permissions["can_post"] = True
            permissions["can_schedule"] = True

        return permissions