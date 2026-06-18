from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Application, AuditLog, Certificate, Initiative, InitiativeCategory, Message,
    MessageThread, Notification, Organization, Shift, Skill, User,
    VolunteerAvailability, VolunteerHour, VolunteerSkill,
)


@admin.register(User)
class HubUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Платформа", {"fields": ("full_name", "phone", "role", "status", "city", "bio", "avatar", "last_login_at")}),)
    list_display = ("email", "full_name", "role", "status", "is_staff")
    search_fields = ("email", "full_name", "username")


for model in [Organization, InitiativeCategory, Skill, Initiative, Shift, Application,
              VolunteerSkill, VolunteerAvailability, VolunteerHour, Certificate,
              MessageThread, Message, Notification, AuditLog]:
    admin.site.register(model)
