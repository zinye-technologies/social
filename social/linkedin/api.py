import frappe
import requests
import json
from frappe.utils import get_url


class LinkedInAPI:
    """LinkedIn API Client for posting and analytics"""

    def __init__(self, access_token):
        self.access_token = access_token
        self.base_url = "https://api.linkedin.com/v2"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

    def get_profile_info(self):
        """Get LinkedIn profile information"""
        response = requests.get(
            f"{self.base_url}/me?projection=(id,firstName,lastName,profilePicture(displayImage~:playableStreams))",
            headers=self.headers
        )

        if response.status_code != 200:
            raise Exception(f"Failed to get profile info: {response.text}")

        return response.json()

    def get_company_info(self, company_id):
        """Get LinkedIn company page information"""
        response = requests.get(
            f"{self.base_url}/organizations/{company_id}?projection=(id,name,logo(elements*))",
            headers=self.headers
        )

        if response.status_code != 200:
            raise Exception(f"Failed to get company info: {response.text}")

        return response.json()

    def create_text_post(self, profile_id, content, visibility="PUBLIC", is_company=False):
        """Create a text post on LinkedIn"""

        # Determine the author URN
        if is_company:
            author_urn = f"urn:li:organization:{profile_id}"
        else:
            author_urn = f"urn:li:person:{profile_id}"

        post_data = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": content
                    },
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            }
        }

        response = requests.post(
            f"{self.base_url}/ugcPosts",
            headers=self.headers,
            json=post_data
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to create post: {response.text}")

        return response.json()

    def create_image_post(self, profile_id, content, image_url, visibility="PUBLIC", is_company=False):
        """Create an image post on LinkedIn"""

        # First, register the image upload
        image_urn = self.upload_image(image_url, profile_id, is_company)

        # Determine the author URN
        if is_company:
            author_urn = f"urn:li:organization:{profile_id}"
        else:
            author_urn = f"urn:li:person:{profile_id}"

        post_data = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": content
                    },
                    "shareMediaCategory": "IMAGE",
                    "media": [
                        {
                            "status": "READY",
                            "description": {
                                "text": content
                            },
                            "media": image_urn,
                            "title": {
                                "text": "Image Post"
                            }
                        }
                    ]
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            }
        }

        response = requests.post(
            f"{self.base_url}/ugcPosts",
            headers=self.headers,
            json=post_data
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to create image post: {response.text}")

        return response.json()

    def create_link_post(self, profile_id, content, link_url, link_title=None, link_description=None, visibility="PUBLIC", is_company=False):
        """Create a link post on LinkedIn"""

        # Determine the author URN
        if is_company:
            author_urn = f"urn:li:organization:{profile_id}"
        else:
            author_urn = f"urn:li:person:{profile_id}"

        post_data = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": content
                    },
                    "shareMediaCategory": "ARTICLE",
                    "media": [
                        {
                            "status": "READY",
                            "originalUrl": link_url,
                            "title": {
                                "text": link_title or link_url
                            },
                            "description": {
                                "text": link_description or ""
                            }
                        }
                    ]
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            }
        }

        response = requests.post(
            f"{self.base_url}/ugcPosts",
            headers=self.headers,
            json=post_data
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to create link post: {response.text}")

        return response.json()

    def upload_image(self, image_url, profile_id, is_company=False):
        """Upload image to LinkedIn and return media URN"""

        # Register upload
        if is_company:
            owner_urn = f"urn:li:organization:{profile_id}"
        else:
            owner_urn = f"urn:li:person:{profile_id}"

        register_data = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": owner_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent"
                    }
                ]
            }
        }

        response = requests.post(
            f"{self.base_url}/assets?action=registerUpload",
            headers=self.headers,
            json=register_data
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to register image upload: {response.text}")

        upload_data = response.json()
        upload_url = upload_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset_urn = upload_data["value"]["asset"]

        # Download image from URL
        image_response = requests.get(image_url)
        if image_response.status_code != 200:
            raise Exception(f"Failed to download image from {image_url}")

        # Upload image
        upload_response = requests.put(
            upload_url,
            data=image_response.content,
            headers={"Content-Type": "application/octet-stream"}
        )

        if upload_response.status_code not in [200, 201]:
            raise Exception(f"Failed to upload image: {upload_response.text}")

        return asset_urn

    def get_profile_analytics(self, profile_id, is_company=False, start_date=None, end_date=None):
        """Get profile analytics"""

        if is_company:
            # Company page analytics
            return self.get_company_analytics(profile_id, start_date, end_date)
        else:
            # Personal profile analytics (limited)
            return self.get_personal_analytics(profile_id, start_date, end_date)

    def get_company_analytics(self, company_id, start_date=None, end_date=None):
        """Get company page analytics"""

        # Follower statistics
        follower_response = requests.get(
            f"{self.base_url}/networkSizes/urn:li:organization:{company_id}?edgeType=CompanyFollowedByMember",
            headers=self.headers
        )

        analytics_data = {}

        if follower_response.status_code == 200:
            follower_data = follower_response.json()
            analytics_data["followers"] = follower_data.get("firstDegreeSize", 0)

        # Page statistics
        page_stats_response = requests.get(
            f"{self.base_url}/organizationalEntityStatistics?q=organizationalEntity&organizationalEntity=urn:li:organization:{company_id}",
            headers=self.headers
        )

        if page_stats_response.status_code == 200:
            page_data = page_stats_response.json()
            if page_data.get("elements"):
                stats = page_data["elements"][0].get("totalPageStatistics", {})
                analytics_data.update({
                    "page_views": stats.get("views", {}).get("allPageViews", {}).get("pageViews", 0),
                    "unique_page_views": stats.get("views", {}).get("allPageViews", {}).get("uniquePageViews", 0)
                })

        return analytics_data

    def get_personal_analytics(self, profile_id, start_date=None, end_date=None):
        """Get personal profile analytics (limited data available)"""

        # Connection count
        connection_response = requests.get(
            f"{self.base_url}/networkSizes/urn:li:person:{profile_id}?edgeType=ConnectedToMember",
            headers=self.headers
        )

        analytics_data = {}

        if connection_response.status_code == 200:
            connection_data = connection_response.json()
            analytics_data["connections"] = connection_data.get("firstDegreeSize", 0)

        return analytics_data

    def get_post_engagement_stats(self, post_urn):
        """Get engagement statistics for a post"""

        response = requests.get(
            f"{self.base_url}/socialActions/{post_urn}",
            headers=self.headers
        )

        if response.status_code != 200:
            return {}

        data = response.json()

        return {
            "likes": data.get("likes", {}).get("summary", 0),
            "comments": data.get("comments", {}).get("summary", 0),
            "shares": data.get("shares", {}).get("summary", 0),
            "reposts": 0  # Not directly available, included in shares
        }