import frappe
from frappe.model.document import Document
from frappe.utils import now, add_to_date, get_datetime
from frappe import _


class ContentPost(Document):
    def validate(self):
        """Validate Content Post before saving"""
        self.validate_scheduling()
        self.validate_content_requirements()
        self.set_timestamps()
        self.check_approval_requirements()

    def validate_scheduling(self):
        """Validate scheduling logic"""
        if not self.publish_now and not self.scheduled_time:
            frappe.throw(_("Either 'Publish Now' must be checked or 'Scheduled Time' must be set"))

        if self.scheduled_time and get_datetime(self.scheduled_time) <= get_datetime(now()):
            if not self.publish_now:
                frappe.throw(_("Scheduled time cannot be in the past"))

    def validate_content_requirements(self):
        """Validate content based on type"""
        if self.content_type == "Link" and not self.link_url:
            frappe.throw(_("Link URL is required for Link content type"))

        # LinkedIn character limit
        if self.platform == "LinkedIn" and len(self.content or "") > 3000:
            frappe.throw(_("LinkedIn posts cannot exceed 3000 characters"))

    def check_approval_requirements(self):
        """Check if approval is required"""
        if self.social_profile:
            profile = frappe.get_doc("Social Profile", self.social_profile)
            if profile.post_approval_required and self.status == "Draft":
                self.approval_status = "Pending"

    def set_timestamps(self):
        """Set creation and modification timestamps"""
        if self.is_new():
            self.created_at = now()
        self.modified_at = now()

    def before_insert(self):
        """Actions before inserting new Content Post"""
        # Auto-generate title if not provided
        if not self.title:
            content_preview = (self.content or "")[:50]
            self.title = f"{content_preview}..." if len(content_preview) == 50 else content_preview

    def on_update(self):
        """Actions after updating Content Post"""
        # Schedule post if conditions are met
        if self.status == "Draft" and self.should_schedule():
            self.schedule_post()

        # Publish immediately if requested
        if self.publish_now and self.status == "Draft" and self.approval_status in ["Not Required", "Approved"]:
            self.publish_post()

    def should_schedule(self):
        """Check if post should be scheduled"""
        return (
            self.scheduled_time
            and not self.publish_now
            and self.approval_status in ["Not Required", "Approved"]
            and get_datetime(self.scheduled_time) > get_datetime(now())
        )

    def schedule_post(self):
        """Schedule the post for publishing"""
        self.status = "Scheduled"

        # Enqueue the post for publishing
        frappe.enqueue(
            "social.linkedin.scheduler.schedule_post",
            post_id=self.name,
            scheduled_time=self.scheduled_time,
            queue="long",
            timeout=300
        )

    def publish_post(self):
        """Publish the post immediately"""
        try:
            if self.platform == "LinkedIn":
                from social.linkedin.publisher import LinkedInPublisher
                publisher = LinkedInPublisher()
                result = publisher.publish_post(self)

                if result.get("success"):
                    self.status = "Published"
                    self.published_at = now()
                    self.linkedin_post_id = result.get("post_id")
                    self.linkedin_post_url = result.get("post_url")
                    self.linkedin_urn = result.get("urn")

                    # Schedule analytics sync
                    frappe.enqueue(
                        "social.linkedin.analytics.sync_post_analytics",
                        post_id=self.name,
                        queue="short",
                        delay=300  # Wait 5 minutes before first analytics sync
                    )
                else:
                    self.handle_publish_failure(result.get("error", "Unknown error"))

        except Exception as e:
            self.handle_publish_failure(str(e))

    def handle_publish_failure(self, error_message):
        """Handle publishing failure"""
        self.status = "Failed"
        self.failed_at = now()
        self.failure_reason = error_message
        self.retry_count = (self.retry_count or 0) + 1

        # Schedule retry if under limit
        if self.retry_count < 3:
            retry_delay = self.retry_count * 300  # Exponential backoff
            self.next_retry_at = add_to_date(now(), seconds=retry_delay)

            frappe.enqueue(
                "social.linkedin.scheduler.retry_post",
                post_id=self.name,
                queue="long",
                delay=retry_delay
            )

        frappe.log_error(f"Failed to publish post {self.name}: {error_message}")

    @frappe.whitelist()
    def submit_for_approval(self):
        """Submit post for approval"""
        if self.approval_status != "Pending":
            self.approval_status = "Pending"
            self.submitted_for_approval_at = now()
            self.save()

        # Send notification to approvers
        self.notify_approvers()

        return {"success": True, "message": "Post submitted for approval"}

    @frappe.whitelist()
    def approve_post(self, notes=None):
        """Approve the post"""
        self.approval_status = "Approved"
        self.approved_by = frappe.session.user
        self.approved_at = now()
        if notes:
            self.approval_notes = notes

        self.save()

        # Auto-schedule or publish if ready
        if self.should_schedule():
            self.schedule_post()
        elif self.publish_now:
            self.publish_post()

        return {"success": True, "message": "Post approved successfully"}

    @frappe.whitelist()
    def reject_post(self, notes=None):
        """Reject the post"""
        self.approval_status = "Rejected"
        self.approved_by = frappe.session.user
        self.approved_at = now()
        if notes:
            self.approval_notes = notes

        self.save()

        return {"success": True, "message": "Post rejected"}

    @frappe.whitelist()
    def duplicate_post(self):
        """Create a duplicate of this post"""
        new_post = frappe.copy_doc(self)
        new_post.status = "Draft"
        new_post.approval_status = "Not Required"
        new_post.published_at = None
        new_post.linkedin_post_id = None
        new_post.linkedin_post_url = None
        new_post.linkedin_urn = None
        new_post.failed_at = None
        new_post.failure_reason = None
        new_post.retry_count = 0
        new_post.title = f"Copy of {self.title}"

        new_post.insert()

        return {"success": True, "post_id": new_post.name}

    @frappe.whitelist()
    def get_analytics_summary(self):
        """Get analytics summary for this post"""
        if not self.linkedin_post_id:
            return {"error": "Post not yet published"}

        total_engagement = (self.likes or 0) + (self.comments or 0) + (self.shares or 0)

        return {
            "impressions": self.impressions or 0,
            "clicks": self.clicks or 0,
            "total_engagement": total_engagement,
            "engagement_rate": self.engagement_rate or 0,
            "click_through_rate": self.click_through_rate or 0,
            "last_sync": self.last_analytics_sync
        }

    def notify_approvers(self):
        """Send notifications to users who can approve posts"""
        # Get users with approval permissions
        approvers = frappe.get_all(
            "Has Role",
            filters={"role": ["in", ["Social Media Manager", "System Manager"]], "parent": ["!=", self.created_by_user]},
            fields=["parent as user"]
        )

        for approver in approvers:
            # Create notification
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": f"Post approval required: {self.title}",
                "for_user": approver.user,
                "type": "Alert",
                "document_type": "Content Post",
                "document_name": self.name,
                "email_content": f"A new post '{self.title}' is pending your approval."
            }).insert(ignore_permissions=True)