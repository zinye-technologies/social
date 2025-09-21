import frappe
from social.linkedin.api import LinkedInAPI
from frappe.utils import now_datetime, add_days, get_datetime
import json


class LinkedInAnalytics:
    """LinkedIn Analytics Manager"""

    def __init__(self):
        pass

    def sync_post_analytics(self, post_doc):
        """Sync analytics for a specific post"""

        if not post_doc.linkedin_urn or not post_doc.social_profile:
            return {"success": False, "error": "Missing LinkedIn URN or social profile"}

        try:
            # Get social profile
            profile = frappe.get_doc("Social Profile", post_doc.social_profile)

            if not profile.linkedin_access_token:
                return {"success": False, "error": "No LinkedIn access token"}

            # Initialize LinkedIn API
            api = LinkedInAPI(profile.linkedin_access_token)

            # Get post analytics from LinkedIn
            analytics_data = api.get_post_engagement_stats(post_doc.linkedin_post_id)

            if not analytics_data:
                return {"success": False, "error": "No analytics data returned from LinkedIn"}

            # Create or update analytics record
            self.create_analytics_record(post_doc, analytics_data)

            return {"success": True, "data": analytics_data}

        except Exception as e:
            frappe.log_error(f"LinkedIn analytics sync error for post {post_doc.name}: {str(e)}")
            return {"success": False, "error": str(e)}

    def create_analytics_record(self, post_doc, analytics_data):
        """Create LinkedIn Analytics record"""

        # Check if analytics record already exists for today
        existing_record = frappe.db.get_value(
            "LinkedIn Analytics",
            {
                "content_post": post_doc.name,
                "date": frappe.utils.today()
            }
        )

        if existing_record:
            # Update existing record
            analytics_doc = frappe.get_doc("LinkedIn Analytics", existing_record)
            analytics_doc.update({
                "likes": analytics_data.get("likes", 0),
                "comments": analytics_data.get("comments", 0),
                "shares": analytics_data.get("shares", 0),
                "reposts": analytics_data.get("reposts", 0),
                "impressions": analytics_data.get("impressions", 0),
                "clicks": analytics_data.get("clicks", 0),
                "engagement_rate": self.calculate_engagement_rate(analytics_data),
                "last_synced": now_datetime(),
                "raw_data": json.dumps(analytics_data)
            })
            analytics_doc.save(ignore_permissions=True)
        else:
            # Create new record
            analytics_doc = frappe.get_doc({
                "doctype": "LinkedIn Analytics",
                "content_post": post_doc.name,
                "social_profile": post_doc.social_profile,
                "linkedin_post_id": post_doc.linkedin_post_id,
                "linkedin_urn": post_doc.linkedin_urn,
                "date": frappe.utils.today(),
                "likes": analytics_data.get("likes", 0),
                "comments": analytics_data.get("comments", 0),
                "shares": analytics_data.get("shares", 0),
                "reposts": analytics_data.get("reposts", 0),
                "impressions": analytics_data.get("impressions", 0),
                "clicks": analytics_data.get("clicks", 0),
                "engagement_rate": self.calculate_engagement_rate(analytics_data),
                "last_synced": now_datetime(),
                "raw_data": json.dumps(analytics_data)
            })
            analytics_doc.insert(ignore_permissions=True)

        return analytics_doc

    def calculate_engagement_rate(self, analytics_data):
        """Calculate engagement rate"""
        impressions = analytics_data.get("impressions", 0)
        if impressions == 0:
            return 0

        total_engagement = (
            analytics_data.get("likes", 0) +
            analytics_data.get("comments", 0) +
            analytics_data.get("shares", 0) +
            analytics_data.get("reposts", 0)
        )

        return round((total_engagement / impressions) * 100, 2)

    def sync_profile_analytics(self, profile_doc):
        """Sync analytics for a LinkedIn profile"""

        if not profile_doc.linkedin_access_token:
            return {"success": False, "error": "No LinkedIn access token"}

        try:
            api = LinkedInAPI(profile_doc.linkedin_access_token)

            is_company = profile_doc.platform_type == "Company Page"
            profile_id = profile_doc.linkedin_company_id if is_company else profile_doc.linkedin_profile_id

            # Get profile analytics
            analytics_data = api.get_profile_analytics(profile_id, is_company)

            # Update profile with analytics data
            profile_doc.db_set("followers_count", analytics_data.get("followers", 0))
            if is_company:
                profile_doc.db_set("page_views", analytics_data.get("page_views", 0))
                profile_doc.db_set("unique_page_views", analytics_data.get("unique_page_views", 0))
            else:
                profile_doc.db_set("connections_count", analytics_data.get("connections", 0))

            profile_doc.db_set("last_analytics_sync", now_datetime())

            return {"success": True, "data": analytics_data}

        except Exception as e:
            frappe.log_error(f"LinkedIn profile analytics sync error for {profile_doc.name}: {str(e)}")
            return {"success": False, "error": str(e)}


def sync_post_analytics(post_id):
    """Background job to sync post analytics"""

    try:
        post = frappe.get_doc("Content Post", post_id)

        if post.platform != "LinkedIn" or post.status != "Published":
            return

        analytics = LinkedInAnalytics()
        result = analytics.sync_post_analytics(post)

        if not result["success"]:
            frappe.log_error(f"Failed to sync analytics for post {post_id}: {result['error']}")

    except Exception as e:
        frappe.log_error(f"Error in sync_post_analytics for {post_id}: {str(e)}")


def sync_linkedin_analytics():
    """Scheduled job to sync LinkedIn analytics for all active posts"""

    try:
        # Get all published LinkedIn posts that need analytics sync
        posts = frappe.get_all(
            "Content Post",
            filters={
                "platform": "LinkedIn",
                "status": "Published",
                "linkedin_post_id": ["!=", ""]
            },
            fields=["name", "linkedin_post_id", "published_at"],
            limit=50  # Limit to avoid API rate limits
        )

        analytics = LinkedInAnalytics()
        synced_count = 0
        failed_count = 0

        for post_data in posts:
            post = frappe.get_doc("Content Post", post_data.name)

            # Skip if post is too old (older than 30 days)
            if post.published_at and (now_datetime() - get_datetime(post.published_at)).days > 30:
                continue

            result = analytics.sync_post_analytics(post)

            if result["success"]:
                synced_count += 1
            else:
                failed_count += 1

            # Add delay to respect rate limits
            import time
            time.sleep(1)

        # Update settings with sync status
        from social.doctype.social_settings.social_settings import update_analytics_sync_status
        update_analytics_sync_status()

        frappe.log_error(f"LinkedIn analytics sync completed: {synced_count} synced, {failed_count} failed")

    except Exception as e:
        frappe.log_error(f"Error in sync_linkedin_analytics: {str(e)}")


@frappe.whitelist()
def manual_sync_post_analytics(post_id):
    """Manually trigger analytics sync for a specific post"""

    try:
        post = frappe.get_doc("Content Post", post_id)

        # Check permissions
        if not frappe.has_permission("Content Post", "read", post):
            frappe.throw("Insufficient permissions")

        analytics = LinkedInAnalytics()
        result = analytics.sync_post_analytics(post)

        return result

    except Exception as e:
        frappe.log_error(f"Manual analytics sync error for post {post_id}: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_post_analytics_history(post_id, days=30):
    """Get analytics history for a post"""

    try:
        start_date = add_days(frappe.utils.today(), -days)

        analytics_data = frappe.get_all(
            "LinkedIn Analytics",
            filters={
                "content_post": post_id,
                "date": [">=", start_date]
            },
            fields=[
                "date", "likes", "comments", "shares", "reposts",
                "impressions", "clicks", "engagement_rate"
            ],
            order_by="date desc"
        )

        return {"success": True, "data": analytics_data}

    except Exception as e:
        frappe.log_error(f"Error getting analytics history for post {post_id}: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_analytics_summary(profile_id=None, days=30):
    """Get analytics summary for dashboard"""

    try:
        filters = {}
        if profile_id:
            filters["social_profile"] = profile_id

        start_date = add_days(frappe.utils.today(), -days)
        filters["date"] = [">=", start_date]

        # If no profile specified, filter by user's posts
        if not profile_id:
            user_posts = frappe.get_all(
                "Content Post",
                filters={"owner": frappe.session.user},
                fields=["name"]
            )
            if user_posts:
                filters["content_post"] = ["in", [p.name for p in user_posts]]

        analytics_data = frappe.get_all(
            "LinkedIn Analytics",
            filters=filters,
            fields=[
                "date", "likes", "comments", "shares", "reposts",
                "impressions", "clicks", "engagement_rate"
            ],
            order_by="date desc"
        )

        # Calculate totals and averages
        total_likes = sum(d.get("likes", 0) for d in analytics_data)
        total_comments = sum(d.get("comments", 0) for d in analytics_data)
        total_shares = sum(d.get("shares", 0) for d in analytics_data)
        total_impressions = sum(d.get("impressions", 0) for d in analytics_data)
        total_clicks = sum(d.get("clicks", 0) for d in analytics_data)

        avg_engagement_rate = 0
        if analytics_data:
            avg_engagement_rate = sum(d.get("engagement_rate", 0) for d in analytics_data) / len(analytics_data)

        summary = {
            "total_engagement": total_likes + total_comments + total_shares,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "average_engagement_rate": round(avg_engagement_rate, 2),
            "post_count": len(analytics_data),
            "daily_data": analytics_data
        }

        return {"success": True, "data": summary}

    except Exception as e:
        frappe.log_error(f"Error getting analytics summary: {str(e)}")
        return {"success": False, "error": str(e)}