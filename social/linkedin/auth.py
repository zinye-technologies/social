import frappe
import requests
import urllib.parse
from frappe.utils import get_url, now_datetime, add_to_date
import secrets
import json


class LinkedInAuth:
    """LinkedIn OAuth 2.0 Authentication Handler"""

    def __init__(self):
        from social.doctype.social_settings.social_settings import get_linkedin_credentials

        try:
            credentials = get_linkedin_credentials()
            self.client_id = credentials["client_id"]
            self.client_secret = credentials["client_secret"]
            self.redirect_uri = credentials["callback_url"]
        except Exception as e:
            frappe.throw(f"LinkedIn credentials not configured: {str(e)}")

        # LinkedIn OAuth 2.0 URLs
        self.authorization_base_url = "https://www.linkedin.com/oauth/v2/authorization"
        self.token_url = "https://www.linkedin.com/oauth/v2/accessToken"

        # Required scopes for our LinkedIn integration
        self.scopes = [
            "openid",
            "profile",
            "email",
            "w_member_social",  # Post on personal profile
            "w_organization_social",  # Post on company pages
            "r_organization_social",  # Read company page analytics
            "rw_organization_admin"  # Admin access for company pages
        ]

    def get_authorization_url(self, profile_type="personal", company_id=None):
        """Generate LinkedIn authorization URL"""

        # Generate state parameter for CSRF protection
        state = secrets.token_urlsafe(32)

        # Store state in cache for verification
        frappe.cache().set_value(
            f"linkedin_oauth_state_{state}",
            {
                "profile_type": profile_type,
                "company_id": company_id,
                "user": frappe.session.user,
                "timestamp": now_datetime()
            },
            expires_in_sec=600  # 10 minutes
        )

        # Build authorization URL
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": " ".join(self.scopes)
        }

        auth_url = f"{self.authorization_base_url}?{urllib.parse.urlencode(params)}"

        return {
            "authorization_url": auth_url,
            "state": state
        }

    def exchange_code_for_token(self, authorization_code, state):
        """Exchange authorization code for access token"""

        # Verify state parameter
        state_data = frappe.cache().get_value(f"linkedin_oauth_state_{state}")
        if not state_data:
            frappe.throw("Invalid or expired authorization state")

        # Verify user
        if state_data.get("user") != frappe.session.user:
            frappe.throw("Authorization state user mismatch")

        # Exchange code for token
        token_data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri
        }

        response = requests.post(
            self.token_url,
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if response.status_code != 200:
            frappe.log_error(f"LinkedIn token exchange failed: {response.text}")
            frappe.throw("Failed to get access token from LinkedIn")

        token_response = response.json()

        # Calculate token expiration
        expires_in = token_response.get("expires_in", 5184000)  # Default 60 days
        expires_at = add_to_date(now_datetime(), seconds=expires_in)

        return {
            "access_token": token_response.get("access_token"),
            "refresh_token": token_response.get("refresh_token"),
            "expires_at": expires_at,
            "profile_type": state_data.get("profile_type"),
            "company_id": state_data.get("company_id")
        }

    def refresh_access_token(self, refresh_token):
        """Refresh LinkedIn access token"""

        refresh_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        response = requests.post(
            self.token_url,
            data=refresh_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if response.status_code != 200:
            frappe.log_error(f"LinkedIn token refresh failed: {response.text}")
            frappe.throw("Failed to refresh LinkedIn access token")

        token_response = response.json()

        # Calculate token expiration
        expires_in = token_response.get("expires_in", 5184000)
        expires_at = add_to_date(now_datetime(), seconds=expires_in)

        return {
            "access_token": token_response.get("access_token"),
            "refresh_token": token_response.get("refresh_token", refresh_token),
            "expires_at": expires_at
        }

    def get_profile_info(self, access_token):
        """Get LinkedIn profile information"""

        headers = {"Authorization": f"Bearer {access_token}"}

        # Get basic profile info
        profile_response = requests.get(
            "https://api.linkedin.com/v2/people/~:(id,firstName,lastName,profilePicture)",
            headers=headers
        )

        if profile_response.status_code != 200:
            frappe.throw("Failed to get LinkedIn profile information")

        profile_data = profile_response.json()

        # Get email address
        email_response = requests.get(
            "https://api.linkedin.com/v2/emailAddress?q=members&projection=(elements*(handle~))",
            headers=headers
        )

        email_data = {}
        if email_response.status_code == 200:
            email_data = email_response.json()

        return {
            "profile_id": profile_data.get("id"),
            "first_name": profile_data.get("firstName", {}).get("localized", {}).get("en_US", ""),
            "last_name": profile_data.get("lastName", {}).get("localized", {}).get("en_US", ""),
            "profile_picture": self._extract_profile_picture(profile_data.get("profilePicture", {})),
            "email": self._extract_email(email_data),
            "profile_url": f"https://www.linkedin.com/in/{profile_data.get('id', '')}"
        }

    def get_company_pages(self, access_token):
        """Get LinkedIn company pages the user can administer"""

        headers = {"Authorization": f"Bearer {access_token}"}

        response = requests.get(
            "https://api.linkedin.com/v2/organizationAcls?q=roleAssignee&role=ADMINISTRATOR&state=APPROVED",
            headers=headers
        )

        if response.status_code != 200:
            return []

        acl_data = response.json()
        company_pages = []

        for element in acl_data.get("elements", []):
            organization_urn = element.get("organization")
            if organization_urn:
                org_id = organization_urn.split(":")[-1]

                # Get organization details
                org_response = requests.get(
                    f"https://api.linkedin.com/v2/organizations/{org_id}:(id,name,logoV2)",
                    headers=headers
                )

                if org_response.status_code == 200:
                    org_data = org_response.json()
                    company_pages.append({
                        "id": org_data.get("id"),
                        "name": org_data.get("name", {}).get("localized", {}).get("en_US", ""),
                        "logo": self._extract_company_logo(org_data.get("logoV2", {}))
                    })

        return company_pages

    def _extract_profile_picture(self, profile_picture_data):
        """Extract profile picture URL from LinkedIn API response"""
        try:
            display_image = profile_picture_data.get("displayImage~", {})
            elements = display_image.get("elements", [])
            if elements:
                identifiers = elements[0].get("identifiers", [])
                if identifiers:
                    return identifiers[0].get("identifier", "")
        except:
            pass
        return ""

    def _extract_company_logo(self, logo_data):
        """Extract company logo URL from LinkedIn API response"""
        try:
            original_logo = logo_data.get("original~", {})
            elements = original_logo.get("elements", [])
            if elements:
                identifiers = elements[0].get("identifiers", [])
                if identifiers:
                    return identifiers[0].get("identifier", "")
        except:
            pass
        return ""

    def _extract_email(self, email_data):
        """Extract email from LinkedIn API response"""
        try:
            elements = email_data.get("elements", [])
            if elements:
                handle = elements[0].get("handle~", {})
                return handle.get("emailAddress", "")
        except:
            pass
        return ""


@frappe.whitelist(allow_guest=True)
def start_oauth_flow(profile_type="personal", company_id=None):
    """Start LinkedIn OAuth flow"""

    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw("Please login to connect LinkedIn profile")

    auth = LinkedInAuth()

    if not auth.client_id or not auth.client_secret:
        frappe.throw("LinkedIn OAuth credentials not configured. Please contact administrator.")

    return auth.get_authorization_url(profile_type, company_id)


@frappe.whitelist(allow_guest=True)
def callback(code=None, state=None, error=None):
    """Handle LinkedIn OAuth callback"""

    if error:
        frappe.log_error(f"LinkedIn OAuth error: {error}")
        frappe.respond_as_web_page(
            "LinkedIn Connection Failed",
            f"Failed to connect LinkedIn: {error}",
            http_status_code=400
        )
        return

    if not code or not state:
        frappe.respond_as_web_page(
            "LinkedIn Connection Failed",
            "Missing authorization code or state parameter",
            http_status_code=400
        )
        return

    try:
        auth = LinkedInAuth()

        # Exchange code for token
        token_data = auth.exchange_code_for_token(code, state)

        # Get profile information
        if token_data["profile_type"] == "personal":
            profile_info = auth.get_profile_info(token_data["access_token"])

            # Create or update social profile
            social_profile = create_or_update_social_profile(
                platform="LinkedIn",
                platform_type="Personal Profile",
                token_data=token_data,
                profile_info=profile_info
            )
        else:
            # Handle company page connection
            company_pages = auth.get_company_pages(token_data["access_token"])

            # For now, create profile for the first company page
            # In a full implementation, you'd show a selection UI
            if company_pages:
                company_info = company_pages[0]
                social_profile = create_or_update_social_profile(
                    platform="LinkedIn",
                    platform_type="Company Page",
                    token_data=token_data,
                    profile_info=company_info
                )

        # Redirect to success page
        frappe.respond_as_web_page(
            "LinkedIn Connected Successfully",
            f"Your LinkedIn profile has been connected successfully. You can now start posting content.",
            success=True,
            indicator_color="green"
        )

    except Exception as e:
        frappe.log_error(f"LinkedIn OAuth callback error: {str(e)}")
        frappe.respond_as_web_page(
            "LinkedIn Connection Failed",
            f"Failed to connect LinkedIn: {str(e)}",
            http_status_code=500
        )


def create_or_update_social_profile(platform, platform_type, token_data, profile_info):
    """Create or update social profile"""

    # Check if profile already exists
    existing_profile = frappe.db.get_value(
        "Social Profile",
        {
            "platform": platform,
            "linkedin_profile_id": profile_info.get("id") or profile_info.get("profile_id"),
            "user": frappe.session.user
        }
    )

    if existing_profile:
        # Update existing profile
        profile = frappe.get_doc("Social Profile", existing_profile)
        profile.linkedin_access_token = token_data["access_token"]
        profile.linkedin_refresh_token = token_data.get("refresh_token")
        profile.linkedin_token_expires_at = token_data["expires_at"]
        profile.is_active = 1
        profile.save(ignore_permissions=True)
    else:
        # Create new profile
        profile_name = profile_info.get("name") or f"{profile_info.get('first_name', '')} {profile_info.get('last_name', '')}".strip()

        profile = frappe.get_doc({
            "doctype": "Social Profile",
            "profile_name": f"{profile_name} - LinkedIn",
            "platform": platform,
            "platform_type": platform_type,
            "user": frappe.session.user,
            "is_active": 1,
            "linkedin_profile_id": profile_info.get("id") or profile_info.get("profile_id"),
            "linkedin_access_token": token_data["access_token"],
            "linkedin_refresh_token": token_data.get("refresh_token"),
            "linkedin_token_expires_at": token_data["expires_at"],
            "profile_url": profile_info.get("profile_url", ""),
            "profile_image": profile_info.get("profile_picture") or profile_info.get("logo"),
        })

        if platform_type == "Company Page":
            profile.linkedin_company_id = profile_info.get("id")
            profile.linkedin_company_name = profile_info.get("name")

        profile.insert(ignore_permissions=True)

    return profile