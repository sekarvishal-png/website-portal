from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student', db_index=True)
    post = models.CharField(max_length=100, blank=True, default='')
    department = models.CharField(max_length=150, blank=True, default='')
    team_name = models.CharField(max_length=150, blank=True, default='')

    def __str__(self):
        full_name = self.user.get_full_name() or self.user.username
        return f"{full_name} ({self.role})"

    @property
    def display_name(self):
        return self.user.get_full_name() or self.user.username


class Team(models.Model):
    name = models.CharField(max_length=150)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_teams')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class TeamMember(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='members')
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True, default='')
    role = models.CharField(max_length=100, default='Project contributor')
    color = models.CharField(max_length=30, blank=True, default='blue')
    is_leader = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.team.name})"

    @property
    def initials(self):
        parts = self.name.strip().split()
        if not parts:
            return "??"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()


class ProjectSubmission(models.Model):
    STATUS_CHOICES = (
        ('In review', 'In review'),
        ('Approved', 'Approved'),
        ('Needs changes', 'Needs changes'),
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='submissions')
    title = models.CharField(max_length=255)
    project_type = models.CharField(max_length=100, default='Project submission')
    file = models.FileField(upload_to='submissions/', blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True, default='')
    note = models.TextField(blank=True, default='')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='In review', db_index=True)
    color = models.CharField(max_length=30, default='orange')
    remark = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.title} - {self.owner.username} ({self.status})"


class Query(models.Model):
    asked_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='queries')
    title = models.CharField(max_length=255)
    details = models.TextField(blank=True, default='')
    answered = models.BooleanField(default=False, db_index=True)
    response = models.TextField(blank=True, default='')
    responded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='responses')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({'Answered' if self.answered else 'Pending'})"


class ChatMessage(models.Model):
    THREAD_CHOICES = (
        ('team', 'Team'),
        ('studio', 'Other teams / Studio'),
        ('teacher', 'Teacher'),
    )

    thread = models.CharField(max_length=30, choices=THREAD_CHOICES, default='team', db_index=True)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages')
    sender_name = models.CharField(max_length=150)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='messages')
    text = models.TextField()
    color = models.CharField(max_length=30, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.thread}] {self.sender_name}: {self.text[:30]}"


class ActivityNotification(models.Model):
    TYPE_CHOICES = (
        ('submission', 'Submission'),
        ('review', 'Review'),
        ('query', 'Query'),
        ('chat', 'Chat'),
        ('system', 'System'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', db_index=True)
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='system')
    link_page = models.CharField(max_length=50, blank=True, default='')
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.notification_type}] {self.user.username}: {self.title}"


def create_notification(user, title, message, notification_type='system', link_page=''):
    """Helper to dispatch in-app notifications to a user."""
    if not user:
        return None
    return ActivityNotification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        link_page=link_page
    )
