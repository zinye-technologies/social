app_name = "social"
app_title = "Social"
app_publisher = "Zinye"
app_description = "Comprehensive Social Media Management Platform"
app_email = "hello@zinye.com"
app_license = "MIT"

# Required Apps
required_apps = ["frappe"]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# Temporarily disabled to fix build issues - using standalone Vue.js frontend
# app_include_css = "/assets/social/css/social.css"
# app_include_js = "/assets/social/js/social.js"

# include js, css files in header of web template
# web_include_css = "/assets/social/css/social.css"
# web_include_js = "/assets/social/js/social.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "social/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "social/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "social.utils.jinja_methods",
# 	"filters": "social.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "social.install.before_install"
# after_install = "social.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "social.uninstall.before_uninstall"
# after_uninstall = "social.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "social.utils.before_app_install"
# after_app_install = "social.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "social.utils.before_app_uninstall"
# after_app_uninstall = "social.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "social.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"*/5 * * * *": [
			"social.linkedin.scheduler.process_scheduled_posts"
		],
		"0 */6 * * *": [
			"social.linkedin.analytics.sync_linkedin_analytics"
		],
		"0 2 * * *": [
			"social.linkedin.scheduler.cleanup_old_scheduled_jobs"
		]
	}
}

# Testing
# -------

# before_tests = "social.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "social.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "social.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["social.utils.before_request"]
# after_request = ["social.utils.after_request"]

# Job Events
# ----------
# before_job = ["social.utils.before_job"]
# after_job = ["social.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"social.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True