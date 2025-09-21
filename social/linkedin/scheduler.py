import frappe
from frappe.utils import now_datetime, get_datetime, add_minutes
from social.linkedin.publisher import LinkedInPublisher


def process_scheduled_posts():
    """Process scheduled posts that are due for publishing"""

    try:
        # Get posts that are scheduled and due for publishing
        current_time = now_datetime()

        scheduled_posts = frappe.get_all(
            "Content Post",
            filters={
                "status": "Scheduled",
                "platform": "LinkedIn",
                "scheduled_time": ["<=", current_time],
                "approval_status": ["!=", "Pending"]
            },
            fields=["name", "scheduled_time", "title"]
        )

        if not scheduled_posts:
            return

        publisher = LinkedInPublisher()
        processed_count = 0
        failed_count = 0

        for post_data in scheduled_posts:
            try:
                post = frappe.get_doc("Content Post", post_data.name)

                # Double-check that post is still scheduled and ready
                if post.status != "Scheduled" or post.approval_status == "Pending":
                    continue

                # Publish the post
                result = publisher.publish_post(post)

                if result["success"]:
                    # Update post status to Published
                    post.db_set("status", "Published")
                    post.db_set("published_at", now_datetime())
                    post.db_set("linkedin_post_id", result["post_id"])
                    post.db_set("linkedin_post_url", result["post_url"])
                    post.db_set("linkedin_urn", result["urn"])

                    # Schedule analytics sync for later
                    frappe.enqueue(
                        "social.linkedin.analytics.sync_post_analytics",
                        post_id=post.name,
                        queue="short",
                        delay=300  # Wait 5 minutes before first analytics sync
                    )

                    processed_count += 1
                    frappe.log_error(f"Successfully published scheduled post: {post.name}")

                else:
                    # Mark as failed
                    post.db_set("status", "Failed")
                    post.db_set("failed_at", now_datetime())
                    post.db_set("failure_reason", result["error"])
                    post.db_set("retry_count", (post.retry_count or 0) + 1)

                    failed_count += 1
                    frappe.log_error(f"Failed to publish scheduled post {post.name}: {result['error']}")

                    # Schedule retry if enabled and under retry limit
                    schedule_retry_if_needed(post)

            except Exception as e:
                frappe.log_error(f"Error processing scheduled post {post_data.name}: {str(e)}")
                failed_count += 1

        if processed_count > 0 or failed_count > 0:
            frappe.log_error(f"Scheduled posts processing complete: {processed_count} published, {failed_count} failed")

    except Exception as e:
        frappe.log_error(f"Error in process_scheduled_posts: {str(e)}")


def schedule_retry_if_needed(post_doc):
    """Schedule retry for failed post if retry is enabled"""

    try:
        from social.doctype.social_settings.social_settings import get_posting_settings

        settings = get_posting_settings()

        if not settings.get("retry_failed_posts"):
            return

        max_attempts = settings.get("max_retry_attempts", 3)
        retry_delay = settings.get("retry_delay_minutes", 30)
        current_retries = post_doc.retry_count or 0

        if current_retries < max_attempts:
            # Schedule retry
            retry_time = add_minutes(now_datetime(), retry_delay)

            frappe.enqueue(
                "social.linkedin.scheduler.retry_failed_post",
                post_id=post_doc.name,
                queue="long",
                timeout=300,
                enqueue_after_commit=True,
                job_name=f"retry_linkedin_post_{post_doc.name}_{current_retries + 1}",
                scheduled_time=retry_time
            )

            frappe.log_error(f"Scheduled retry for post {post_doc.name} in {retry_delay} minutes (attempt {current_retries + 1}/{max_attempts})")

    except Exception as e:
        frappe.log_error(f"Error scheduling retry for post {post_doc.name}: {str(e)}")


def retry_failed_post(post_id):
    """Retry publishing a failed post"""

    try:
        post = frappe.get_doc("Content Post", post_id)

        if post.status != "Failed":
            frappe.log_error(f"Post {post_id} is not in failed status, skipping retry")
            return

        publisher = LinkedInPublisher()
        result = publisher.retry_failed_post(post)

        if result["success"]:
            frappe.log_error(f"Successfully retried and published post: {post_id}")

            # Schedule analytics sync
            frappe.enqueue(
                "social.linkedin.analytics.sync_post_analytics",
                post_id=post_id,
                queue="short",
                delay=300
            )
        else:
            frappe.log_error(f"Retry failed for post {post_id}: {result['error']}")

            # Schedule another retry if under limit
            schedule_retry_if_needed(post)

    except Exception as e:
        frappe.log_error(f"Error in retry_failed_post for {post_id}: {str(e)}")


def cleanup_old_scheduled_jobs():
    """Clean up old scheduled jobs that may be stuck"""

    try:
        # Find posts that are scheduled but past their time and seem stuck
        import frappe.utils

        cutoff_time = frappe.utils.add_hours(now_datetime(), -2)  # 2 hours ago

        stuck_posts = frappe.get_all(
            "Content Post",
            filters={
                "status": "Scheduled",
                "platform": "LinkedIn",
                "scheduled_time": ["<", cutoff_time]
            },
            fields=["name", "scheduled_time", "title"]
        )

        for post_data in stuck_posts:
            post = frappe.get_doc("Content Post", post_data.name)

            frappe.log_error(f"Found stuck scheduled post: {post.name}, rescheduling or marking as failed")

            # Try to publish immediately
            publisher = LinkedInPublisher()
            result = publisher.publish_post(post)

            if result["success"]:
                post.db_set("status", "Published")
                post.db_set("published_at", now_datetime())
                post.db_set("linkedin_post_id", result["post_id"])
                post.db_set("linkedin_post_url", result["post_url"])
                post.db_set("linkedin_urn", result["urn"])
            else:
                post.db_set("status", "Failed")
                post.db_set("failed_at", now_datetime())
                post.db_set("failure_reason", f"Post was stuck in scheduled status: {result['error']}")

    except Exception as e:
        frappe.log_error(f"Error in cleanup_old_scheduled_jobs: {str(e)}")


@frappe.whitelist()
def get_scheduled_posts():
    """Get upcoming scheduled posts"""

    try:
        current_time = now_datetime()

        scheduled_posts = frappe.get_all(
            "Content Post",
            filters={
                "status": "Scheduled",
                "platform": "LinkedIn",
                "scheduled_time": [">", current_time],
                "owner": frappe.session.user
            },
            fields=[
                "name", "title", "scheduled_time", "social_profile",
                "content_type", "approval_status"
            ],
            order_by="scheduled_time asc"
        )

        return {"success": True, "data": scheduled_posts}

    except Exception as e:
        frappe.log_error(f"Error getting scheduled posts: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def reschedule_post(post_id, new_time):
    """Reschedule a post to a new time"""

    try:
        post = frappe.get_doc("Content Post", post_id)

        # Check permissions
        if not frappe.has_permission("Content Post", "write", post):
            frappe.throw("Insufficient permissions to reschedule this post")

        if post.status != "Scheduled":
            frappe.throw("Only scheduled posts can be rescheduled")

        # Validate new time is in the future
        new_datetime = get_datetime(new_time)
        if new_datetime <= now_datetime():
            frappe.throw("Scheduled time must be in the future")

        # Update scheduled time
        post.db_set("scheduled_time", new_datetime)

        return {"success": True, "message": "Post rescheduled successfully"}

    except Exception as e:
        frappe.log_error(f"Error rescheduling post {post_id}: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def cancel_scheduled_post(post_id):
    """Cancel a scheduled post"""

    try:
        post = frappe.get_doc("Content Post", post_id)

        # Check permissions
        if not frappe.has_permission("Content Post", "write", post):
            frappe.throw("Insufficient permissions to cancel this post")

        if post.status != "Scheduled":
            frappe.throw("Only scheduled posts can be cancelled")

        # Change status back to Draft
        post.db_set("status", "Draft")
        post.db_set("scheduled_time", None)

        return {"success": True, "message": "Scheduled post cancelled successfully"}

    except Exception as e:
        frappe.log_error(f"Error cancelling scheduled post {post_id}: {str(e)}")
        return {"success": False, "error": str(e)}