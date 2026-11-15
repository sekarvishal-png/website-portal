from django.contrib import admin
from .models import UserProfile, Team, TeamMember, ProjectSubmission, Query, ChatMessage, ActivityNotification


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'post', 'department', 'team_name')
    list_filter = ('role', 'department')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__email', 'department', 'team_name')


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 1


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_at')
    search_fields = ('name', 'created_by__username')
    inlines = [TeamMemberInline]


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'role', 'team', 'is_leader')
    list_filter = ('role', 'is_leader', 'team')
    search_fields = ('name', 'email', 'team__name')


@admin.register(ProjectSubmission)
class ProjectSubmissionAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'team', 'project_type', 'status', 'submitted_at')
    list_filter = ('status', 'project_type', 'submitted_at')
    search_fields = ('title', 'owner__username', 'owner__email', 'team__name', 'remark')


@admin.register(Query)
class QueryAdmin(admin.ModelAdmin):
    list_display = ('title', 'asked_by', 'answered', 'responded_by', 'created_at')
    list_filter = ('answered', 'created_at')
    search_fields = ('title', 'details', 'response', 'asked_by__username')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('thread', 'sender_name', 'sender', 'created_at')
    list_filter = ('thread', 'created_at')
    search_fields = ('sender_name', 'text')


@admin.register(ActivityNotification)
class ActivityNotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'user__username')
