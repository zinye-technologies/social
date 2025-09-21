import frappe
from frappe.utils import now_datetime, add_months, getdate, get_first_day, get_last_day


@frappe.whitelist()
def get_dashboard_stats():
    """Get dashboard statistics for the current user"""

    user = frappe.session.user
    current_date = getdate()
    month_start = get_first_day(current_date)
    month_end = get_last_day(current_date)

    # Get connected profiles count
    connected_profiles = frappe.db.count(
        "Social Profile",
        filters={
            "user": user,
            "is_active": 1
        }
    )

    # Get posts this month
    posts_this_month = frappe.db.count(
        "Content Post",
        filters={
            "owner": user,
            "creation": ["between", [month_start, month_end]]
        }
    )

    # Get total engagement (sum of likes, comments, shares from LinkedIn Analytics)
    total_engagement = get_total_engagement(user)

    # Get scheduled posts count
    scheduled_posts = frappe.db.count(
        "Content Post",
        filters={
            "owner": user,
            "status": "Scheduled",
            "scheduled_time": [">", now_datetime()]
        }
    )

    return {
        "connectedProfiles": connected_profiles,
        "postsThisMonth": posts_this_month,
        "totalEngagement": total_engagement,
        "scheduledPosts": scheduled_posts
    }


def get_total_engagement(user):
    """Calculate total engagement across all user's posts"""

    # Get all published posts for the user
    posts = frappe.get_all(
        "Content Post",
        filters={
            "owner": user,
            "status": "Published",
            "linkedin_post_id": ["!=", ""]
        },
        fields=["name", "linkedin_post_id"]
    )

    total_engagement = 0

    for post in posts:
        # Get latest analytics for this post
        analytics = frappe.get_all(
            "LinkedIn Analytics",
            filters={
                "content_post": post.name
            },
            fields=["likes", "comments", "shares", "reposts"],
            order_by="creation desc",
            limit=1
        )

        if analytics:
            data = analytics[0]
            engagement = (data.get("likes", 0) +
                         data.get("comments", 0) +
                         data.get("shares", 0) +
                         data.get("reposts", 0))
            total_engagement += engagement

    return total_engagement


@frappe.whitelist()
def get_recent_activity():
    """Get recent activity for the dashboard"""

    user = frappe.session.user

    # Get recent posts
    recent_posts = frappe.get_all(
        "Content Post",
        filters={"owner": user},
        fields=[
            "name", "title", "platform", "status",
            "creation", "scheduled_time", "published_at"
        ],
        order_by="creation desc",
        limit=10
    )

    # Get recent analytics updates
    recent_analytics = frappe.get_all(
        "LinkedIn Analytics",
        filters={
            "creation": [">", add_months(now_datetime(), -1)]
        },
        fields=[
            "content_post", "likes", "comments", "shares",
            "impressions", "creation"
        ],
        order_by="creation desc",
        limit=5
    )

    return {
        "recent_posts": recent_posts,
        "recent_analytics": recent_analytics
    }


@frappe.whitelist()
def get_engagement_trends():
    """Get engagement trends for charts"""

    user = frappe.session.user

    # Get engagement data for the last 30 days
    from frappe.utils import add_days

    end_date = getdate()
    start_date = add_days(end_date, -30)

    # Daily engagement data
    daily_engagement = frappe.db.sql("""
        SELECT
            DATE(la.creation) as date,
            SUM(la.likes + la.comments + la.shares + la.reposts) as total_engagement,
            SUM(la.impressions) as total_impressions
        FROM
            `tabLinkedIn Analytics` la
        INNER JOIN
            `tabContent Post` cp ON la.content_post = cp.name
        WHERE
            cp.owner = %s
            AND DATE(la.creation) BETWEEN %s AND %s
        GROUP BY
            DATE(la.creation)
        ORDER BY
            DATE(la.creation)
    """, (user, start_date, end_date), as_dict=True)

    return {
        "daily_engagement": daily_engagement,
        "period": {"start": start_date, "end": end_date}
    }


@frappe.whitelist()
def get_platform_stats():
    """Get statistics by platform"""

    user = frappe.session.user

    # Platform-wise post count
    platform_posts = frappe.db.sql("""
        SELECT
            platform,
            COUNT(*) as post_count,
            SUM(CASE WHEN status = 'Published' THEN 1 ELSE 0 END) as published_count,
            SUM(CASE WHEN status = 'Scheduled' THEN 1 ELSE 0 END) as scheduled_count,
            SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed_count
        FROM
            `tabContent Post`
        WHERE
            owner = %s
        GROUP BY
            platform
    """, (user,), as_dict=True)

    return {"platform_stats": platform_posts}


@frappe.whitelist()
def get_posting_schedule_data():
    """Get data for posting schedule visualization"""

    user = frappe.session.user

    # Get posting times analysis
    posting_times = frappe.db.sql("""
        SELECT
            HOUR(published_at) as hour,
            DAYOFWEEK(published_at) as day_of_week,
            COUNT(*) as post_count
        FROM
            `tabContent Post`
        WHERE
            owner = %s
            AND status = 'Published'
            AND published_at IS NOT NULL
        GROUP BY
            HOUR(published_at), DAYOFWEEK(published_at)
    """, (user,), as_dict=True)

    return {"posting_times": posting_times}