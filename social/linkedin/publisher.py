import frappe
from social.linkedin.api import LinkedInAPI
from frappe.utils import now


class LinkedInPublisher:
    """LinkedIn Post Publisher"""

    def __init__(self):
        pass

    def publish_post(self, post_doc):
        """Publish a Content Post to LinkedIn"""

        try:
            # Get social profile
            profile = frappe.get_doc("Social Profile", post_doc.social_profile)

            if not profile.linkedin_access_token:
                raise Exception("No LinkedIn access token found for this profile")

            # Initialize LinkedIn API
            api = LinkedInAPI(profile.linkedin_access_token)

            # Determine if this is a company page or personal profile
            is_company = profile.platform_type == "Company Page"
            profile_id = profile.linkedin_company_id if is_company else profile.linkedin_profile_id

            if not profile_id:
                raise Exception("No LinkedIn profile ID found")

            # Publish based on content type
            if post_doc.content_type == "Text":
                result = api.create_text_post(
                    profile_id=profile_id,
                    content=post_doc.content,
                    visibility=post_doc.linkedin_visibility or "PUBLIC",
                    is_company=is_company
                )

            elif post_doc.content_type == "Image":
                # Get first image attachment
                if not post_doc.media_attachments:
                    raise Exception("No image attachments found for image post")

                image_attachment = post_doc.media_attachments[0]
                image_url = frappe.utils.get_url(image_attachment.attachment)

                result = api.create_image_post(
                    profile_id=profile_id,
                    content=post_doc.content,
                    image_url=image_url,
                    visibility=post_doc.linkedin_visibility or "PUBLIC",
                    is_company=is_company
                )

            elif post_doc.content_type == "Link":
                result = api.create_link_post(
                    profile_id=profile_id,
                    content=post_doc.content,
                    link_url=post_doc.link_url,
                    link_title=post_doc.link_title,
                    link_description=post_doc.link_description,
                    visibility=post_doc.linkedin_visibility or "PUBLIC",
                    is_company=is_company
                )

            else:
                raise Exception(f"Unsupported content type: {post_doc.content_type}")

            # Extract post information from LinkedIn response
            post_id = result.get("id", "").split(":")[-1]
            post_urn = result.get("id", "")

            # Generate post URL
            if is_company:
                post_url = f"https://www.linkedin.com/feed/update/{post_urn}/"
            else:
                post_url = f"https://www.linkedin.com/feed/update/{post_urn}/"

            return {
                "success": True,
                "post_id": post_id,
                "post_url": post_url,
                "urn": post_urn,
                "linkedin_response": result
            }

        except Exception as e:
            frappe.log_error(f"LinkedIn publish error for post {post_doc.name}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def schedule_post(self, post_doc, scheduled_time):
        """Schedule a post for future publishing"""

        # For now, we'll use Frappe's scheduler to handle this
        # In a production environment, you might want to use a more robust job queue

        frappe.enqueue(
            method="social.linkedin.publisher.publish_scheduled_post",
            post_id=post_doc.name,
            queue="long",
            timeout=300,
            enqueue_after_commit=True,
            at_front=False,
            job_name=f"publish_linkedin_post_{post_doc.name}",
            scheduled_time=scheduled_time
        )

        return {"success": True, "message": "Post scheduled successfully"}

    def retry_failed_post(self, post_doc):
        """Retry publishing a failed post"""

        # Reset failure fields
        post_doc.db_set("status", "Draft")
        post_doc.db_set("failed_at", None)
        post_doc.db_set("failure_reason", None)

        # Attempt to publish again
        result = self.publish_post(post_doc)

        if result["success"]:
            post_doc.db_set("status", "Published")
            post_doc.db_set("published_at", now())
            post_doc.db_set("linkedin_post_id", result["post_id"])
            post_doc.db_set("linkedin_post_url", result["post_url"])
            post_doc.db_set("linkedin_urn", result["urn"])
        else:
            post_doc.db_set("status", "Failed")
            post_doc.db_set("failed_at", now())
            post_doc.db_set("failure_reason", result["error"])
            post_doc.db_set("retry_count", (post_doc.retry_count or 0) + 1)

        return result


def publish_scheduled_post(post_id):
    """Background job to publish scheduled posts"""

    try:
        post = frappe.get_doc("Content Post", post_id)

        if post.status != "Scheduled":
            frappe.log_error(f"Post {post_id} is not in scheduled status")
            return

        publisher = LinkedInPublisher()
        result = publisher.publish_post(post)

        if result["success"]:
            post.db_set("status", "Published")
            post.db_set("published_at", now())
            post.db_set("linkedin_post_id", result["post_id"])
            post.db_set("linkedin_post_url", result["post_url"])
            post.db_set("linkedin_urn", result["urn"])

            # Schedule analytics sync
            frappe.enqueue(
                "social.linkedin.analytics.sync_post_analytics",
                post_id=post_id,
                queue="short",
                delay=300  # Wait 5 minutes before first analytics sync
            )

        else:
            post.db_set("status", "Failed")
            post.db_set("failed_at", now())
            post.db_set("failure_reason", result["error"])
            post.db_set("retry_count", (post.retry_count or 0) + 1)

            frappe.log_error(f"Failed to publish scheduled post {post_id}: {result['error']}")

    except Exception as e:
        frappe.log_error(f"Error in publish_scheduled_post for {post_id}: {str(e)}")


@frappe.whitelist()
def test_linkedin_connection(social_profile):
    """Test LinkedIn connection for a social profile"""

    try:
        profile = frappe.get_doc("Social Profile", social_profile)

        if not profile.linkedin_access_token:
            return {"success": False, "error": "No access token found"}

        api = LinkedInAPI(profile.linkedin_access_token)

        if profile.platform_type == "Company Page":
            info = api.get_company_info(profile.linkedin_company_id)
        else:
            info = api.get_profile_info()

        return {"success": True, "data": info}

    except Exception as e:
        frappe.log_error(f"LinkedIn connection test failed: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def publish_post_now(post_id):
    """Manually publish a post immediately"""

    try:
        post = frappe.get_doc("Content Post", post_id)

        # Check permissions
        if not frappe.has_permission("Content Post", "write", post):
            frappe.throw("Insufficient permissions to publish this post")

        # Check if post can be published
        if post.status not in ["Draft", "Failed"]:
            frappe.throw(f"Post cannot be published. Current status: {post.status}")

        if post.approval_status == "Pending":
            frappe.throw("Post is pending approval and cannot be published")

        publisher = LinkedInPublisher()
        result = publisher.publish_post(post)

        if result["success"]:
            post.db_set("status", "Published")
            post.db_set("published_at", now())
            post.db_set("linkedin_post_id", result["post_id"])
            post.db_set("linkedin_post_url", result["post_url"])
            post.db_set("linkedin_urn", result["urn"])

            return {"success": True, "message": "Post published successfully", "post_url": result["post_url"]}
        else:
            post.db_set("status", "Failed")
            post.db_set("failed_at", now())
            post.db_set("failure_reason", result["error"])

            return {"success": False, "error": result["error"]}

    except Exception as e:
        frappe.log_error(f"Error publishing post {post_id}: {str(e)}")
        return {"success": False, "error": str(e)}