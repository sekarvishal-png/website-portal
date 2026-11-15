import json
import os
import re
import logging
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.utils import timezone
from django.db.models import Prefetch

from .models import (
    UserProfile,
    Team,
    TeamMember,
    ProjectSubmission,
    Query,
    ChatMessage,
    ActivityNotification,
    create_notification,
)

logger = logging.getLogger(__name__)

# File Upload Constraints
ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
    '.zip', '.tar.gz', '.png', '.jpg', '.jpeg', '.gif', '.txt', '.md', '.fig'
}
MAX_FILE_SIZE = 30 * 1024 * 1024  # 30 MB


def validate_uploaded_file(uploaded_file):
    """Validates file extension and size, and sanitizes filename."""
    if not uploaded_file:
        return True, None
    if uploaded_file.size > MAX_FILE_SIZE:
        return False, "File exceeds maximum size of 30 MB."
    _, ext = os.path.splitext(uploaded_file.name.lower())
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"File format '{ext}' is not permitted. Please upload a PDF, document, archive, or image."
    # Sanitize filename
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', os.path.basename(uploaded_file.name))
    uploaded_file.name = clean_name
    return True, None


def _get_user_profile(user):
    if not user:
        return None
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def _format_date(dt):
    if not dt:
        return ""
    return dt.strftime("%B %d, %Y")


def _serialize_submission(sub):
    file_url = sub.file.url if sub.file else ""
    download_url = f"/api/projects/{sub.id}/download/" if sub.file else ""
    return {
        "id": sub.id,
        "name": sub.title,
        "type": sub.project_type,
        "date": f"Submitted {_format_date(sub.submitted_at)}",
        "submittedAt": sub.submitted_at.isoformat() if sub.submitted_at else "",
        "status": sub.status,
        "color": sub.color or "orange",
        "fileName": sub.file_name or (sub.file.name.split("/")[-1] if sub.file else ""),
        "fileUrl": file_url,
        "downloadUrl": download_url,
        "remark": sub.remark,
        "note": sub.note,
    }


def _serialize_submission_for_teacher(sub):
    data = _serialize_submission(sub)
    owner_profile = getattr(sub.owner, 'profile', None) if sub.owner else None
    team = sub.team

    members = list(team.members.all()) if team else []
    leader_member = next((m for m in members if m.is_leader), None)
    team_leader = leader_member.name if leader_member else (owner_profile.display_name if owner_profile and owner_profile.post == "Team leader" else "Not set")
    other_members = [m.name for m in members if not m.is_leader]

    data.update({
        "studentName": owner_profile.display_name if owner_profile else (sub.owner.username if sub.owner else "Unknown"),
        "studentEmail": sub.owner.email if sub.owner else "",
        "department": (owner_profile.department if owner_profile else "") or "Not provided",
        "teamName": team.name if team else ((owner_profile.team_name if owner_profile else "") or "Team name not set"),
        "teamLeader": team_leader,
        "teamMembers": ", ".join(other_members) if other_members else "No other members added",
        "ownerEmail": sub.owner.email if sub.owner else "",
    })
    return data


@ensure_csrf_cookie
def home(request):
    """Serves the main IDEA application template."""
    return render(request, 'IDEA.html')


@require_http_methods(["GET"])
def api_auth_session(request):
    """Returns current user session details if authenticated."""
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False})

    profile = _get_user_profile(request.user)
    unread_notifs = ActivityNotification.objects.filter(user=request.user, is_read=False).count()

    return JsonResponse({
        "authenticated": True,
        "user": {
            "name": profile.display_name,
            "email": request.user.email,
            "role": profile.role,
            "post": profile.post or ("Administrator" if profile.role == "teacher" else "Team leader"),
            "department": profile.department,
            "teamName": profile.team_name,
            "unreadNotifications": unread_notifs,
        }
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_signup(request):
    """Registers a new user and logs them in."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        data = request.POST

    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    name = str(data.get("name") or "").strip()
    role = str(data.get("role") or "student").strip().lower()
    post = str(data.get("post") or ("Administrator" if role == "teacher" else "Team leader")).strip()
    department = str(data.get("department") or "").strip()
    team_name = str(data.get("teamName") or "").strip()

    if not email or not password:
        return JsonResponse({"success": False, "error": "Enter your email and password to continue."}, status=400)
    if not name:
        return JsonResponse({"success": False, "error": "Enter your name to create an account."}, status=400)

    if User.objects.filter(username__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
        return JsonResponse({"success": False, "error": "An account with this email already exists. Choose Log in."}, status=400)

    # Create Django User
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        first_name=name
    )

    # Create UserProfile
    profile = UserProfile.objects.create(
        user=user,
        role=role,
        post=post,
        department=department,
        team_name=team_name
    )

    # If student, set up Team and Leader Member
    if role == "student":
        team = Team.objects.create(
            name=team_name or f"{name}'s Team",
            created_by=user
        )
        is_leader = post != "Team member"
        TeamMember.objects.create(
            team=team,
            name=name,
            email=email,
            role=post or "Team leader",
            color="blue",
            is_leader=is_leader
        )

    # Welcome notification
    create_notification(
        user,
        "Welcome to Idea!",
        f"Hi {name}, your {role} workspace is ready. Explore projects, team collaboration, and teacher queries.",
        notification_type="system"
    )

    login(request, user)

    return JsonResponse({
        "success": True,
        "user": {
            "name": profile.display_name,
            "email": user.email,
            "role": profile.role,
            "post": profile.post,
            "department": profile.department,
            "teamName": profile.team_name,
        }
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_login(request):
    """Authenticates and logs in a user."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        data = request.POST

    email = str(data.get("email") or "").strip()
    password = str(data.get("password") or "")

    if not email or not password:
        return JsonResponse({"success": False, "error": "Enter your email and password to continue."}, status=400)

    # Support login by email (case-insensitive) or username
    user_obj = User.objects.filter(email__iexact=email).first() or User.objects.filter(username__iexact=email).first()
    username_to_auth = user_obj.username if user_obj else email

    user = authenticate(request, username=username_to_auth, password=password)
    if not user:
        return JsonResponse({
            "success": False,
            "error": "We couldn’t find a matching account. Check your details or create an account."
        }, status=400)

    login(request, user)
    profile = _get_user_profile(user)

    return JsonResponse({
        "success": True,
        "user": {
            "name": profile.display_name if profile else (user.get_full_name() or user.username),
            "email": user.email,
            "role": profile.role if profile else "student",
            "post": profile.post if profile else "",
            "department": profile.department if profile else "",
            "teamName": profile.team_name if profile else "",
        }
    })


@csrf_exempt
@require_http_methods(["POST", "GET"])
def api_logout(request):
    """Logs out the active user."""
    logout(request)
    return JsonResponse({"success": True})


@require_http_methods(["GET"])
def api_workspace_data(request):
    """Returns optimized workspace data for student or teacher."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    profile = _get_user_profile(request.user)

    # Fetch all chat messages in a single query
    chat_msgs = ChatMessage.objects.filter(
        thread__in=["team", "studio", "teacher"]
    ).select_related("sender", "sender__profile").order_by("created_at")

    messages_data = {"team": [], "studio": [], "teacher": []}
    for m in chat_msgs:
        sender_profile = getattr(m.sender, 'profile', None) if m.sender else None
        is_teacher = sender_profile and sender_profile.role == "teacher"
        messages_data[m.thread].append({
            "id": m.id,
            "name": m.sender_name,
            "initials": "".join([part[0] for part in m.sender_name.strip().split()[:2]]).upper() or "?",
            "color": m.color or ("orange" if is_teacher else ""),
            "text": m.text,
            "time": m.created_at.strftime("%I:%M %p"),
            "mine": m.sender_id == request.user.id,
        })

    # Unread notifications count
    if profile.role == "teacher":
        pending_subs_count = ProjectSubmission.objects.filter(status="In review").count()
        unanswered_q_count = Query.objects.filter(answered=False).count()
        unread_db_notifs = ActivityNotification.objects.filter(user=request.user, is_read=False).count()
        unread_notifs = pending_subs_count + unanswered_q_count + unread_db_notifs
    else:
        unread_notifs = ActivityNotification.objects.filter(user=request.user, is_read=False).count()

    if profile.role == "teacher":
        # Highly optimized query with joins and prefetch (eliminates N+1 queries)
        submissions = ProjectSubmission.objects.all().select_related(
            "owner", "owner__profile", "team"
        ).prefetch_related(
            "team__members"
        ).order_by("-submitted_at")

        submissions_list = [_serialize_submission_for_teacher(sub) for sub in submissions]

        queries = Query.objects.all().select_related("asked_by").order_by("-created_at")
        queries_list = [{
            "id": q.id,
            "title": q.title,
            "details": q.details,
            "meta": f"Asked by {(q.asked_by.first_name or q.asked_by.username) if q.asked_by else 'Student'} · {_format_date(q.created_at)}",
            "answered": q.answered,
            "response": q.response,
        } for q in queries]

        return JsonResponse({
            "role": "teacher",
            "account": {
                "name": profile.display_name,
                "email": request.user.email,
                "role": "teacher",
                "post": profile.post or "Administrator",
                "department": profile.department,
                "unreadNotifications": unread_notifs,
            },
            "submissions": submissions_list,
            "queries": queries_list,
            "messages": messages_data,
        })

    # Student workspace
    team = Team.objects.filter(created_by=request.user).prefetch_related("members").first()
    if not team:
        member_record = TeamMember.objects.filter(email__iexact=request.user.email).select_related("team").first()
        if member_record:
            team = member_record.team

    team_name = team.name if team else (profile.team_name or "Your team")
    members_list = []
    if team:
        for m in team.members.all():
            members_list.append({
                "id": m.id,
                "name": m.name,
                "initials": m.initials,
                "role": m.role,
                "color": m.color,
                "leader": m.is_leader,
            })
    else:
        initials = "".join([part[0] for part in profile.display_name.strip().split()[:2]]).upper() or "ME"
        members_list = [{
            "name": profile.display_name,
            "initials": initials,
            "role": profile.post or "Team leader",
            "color": "blue",
            "leader": profile.post != "Team member",
        }]

    my_submissions = ProjectSubmission.objects.filter(owner=request.user).order_by("-submitted_at")
    submissions_list = [_serialize_submission(sub) for sub in my_submissions]

    my_queries = Query.objects.filter(asked_by=request.user).order_by("-created_at")
    queries_list = [{
        "id": q.id,
        "title": q.title,
        "details": q.details,
        "meta": "Answered · Teacher" if q.answered else f"Asked {_format_date(q.created_at)} · Awaiting teacher reply",
        "answered": q.answered,
        "response": q.response,
    } for q in my_queries]

    return JsonResponse({
        "role": "student",
        "account": {
            "name": profile.display_name,
            "email": request.user.email,
            "role": "student",
            "post": profile.post or "Team leader",
            "department": profile.department,
            "unreadNotifications": unread_notifs,
        },
        "teamName": team_name,
        "members": members_list,
        "projects": submissions_list,
        "queries": queries_list,
        "messages": messages_data,
    })


@require_http_methods(["POST"])
def api_upload_project(request):
    """Handles project submission upload with file validation and notifications."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    title = str(request.POST.get("title") or "").strip()
    project_type = str(request.POST.get("type") or "Project submission").strip()
    note = str(request.POST.get("note") or "").strip()
    uploaded_file = request.FILES.get("file")

    if not title:
        return JsonResponse({"success": False, "error": "Project title is required."}, status=400)

    # Validate file
    if uploaded_file:
        valid, err_msg = validate_uploaded_file(uploaded_file)
        if not valid:
            return JsonResponse({"success": False, "error": err_msg}, status=400)

    team = Team.objects.filter(created_by=request.user).first()
    if not team:
        member = TeamMember.objects.filter(email__iexact=request.user.email).first()
        team = member.team if member else None

    sub = ProjectSubmission.objects.create(
        owner=request.user,
        team=team,
        title=title,
        project_type=project_type,
        note=note,
        status="In review",
        color="orange",
        file=uploaded_file,
        file_name=uploaded_file.name if uploaded_file else "",
    )

    # Dispatch notification to all teachers
    profile = _get_user_profile(request.user)
    team_label = team.name if team else "Independent"
    teachers = UserProfile.objects.filter(role="teacher").select_related("user")
    for t in teachers:
        create_notification(
            t.user,
            "New Student Submission",
            f"{profile.display_name} ({team_label}) submitted '{title}' for review.",
            notification_type="submission",
            link_page="projects"
        )

    return JsonResponse({
        "success": True,
        "project": _serialize_submission(sub)
    })


@require_http_methods(["POST"])
def api_attach_project_file(request, project_id):
    """Replaces or attaches a file to an existing project submission."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    sub = get_object_or_404(ProjectSubmission, id=project_id, owner=request.user)
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse({"success": False, "error": "No file provided."}, status=400)

    valid, err_msg = validate_uploaded_file(uploaded_file)
    if not valid:
        return JsonResponse({"success": False, "error": err_msg}, status=400)

    # Clean old file if present
    if sub.file:
        try:
            sub.file.delete(save=False)
        except Exception:
            pass

    sub.file = uploaded_file
    sub.file_name = uploaded_file.name
    sub.save()

    return JsonResponse({
        "success": True,
        "project": _serialize_submission(sub)
    })


@require_http_methods(["GET"])
def api_download_file(request, project_id):
    """Securely downloads a project file with access control."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    sub = get_object_or_404(ProjectSubmission, id=project_id)
    if not sub.file:
        raise Http404("No file attached to this project.")

    profile = _get_user_profile(request.user)
    is_teacher = profile and profile.role == "teacher"
    is_owner = sub.owner_id == request.user.id
    is_teammate = False
    if sub.team and not is_owner and not is_teacher:
        is_teammate = sub.team.members.filter(email__iexact=request.user.email).exists()

    if not (is_teacher or is_owner or is_teammate):
        return JsonResponse({"error": "You do not have permission to download this file."}, status=403)

    try:
        response = FileResponse(
            sub.file.open('rb'),
            as_attachment=True,
            filename=sub.file_name or os.path.basename(sub.file.name)
        )
        return response
    except FileNotFoundError:
        raise Http404("File not found on server.")


@require_http_methods(["POST", "DELETE"])
def api_delete_project(request, project_id):
    """Allows student to delete their project if not yet approved, or teacher to remove."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    profile = _get_user_profile(request.user)
    if profile.role == "teacher":
        sub = get_object_or_404(ProjectSubmission, id=project_id)
    else:
        sub = get_object_or_404(ProjectSubmission, id=project_id, owner=request.user)
        if sub.status == "Approved":
            return JsonResponse({"success": False, "error": "Approved projects cannot be deleted."}, status=400)

    # Delete attached file from storage if present
    if sub.file:
        try:
            sub.file.delete(save=False)
        except Exception:
            pass

    sub.delete()
    return JsonResponse({"success": True})


@require_http_methods(["POST"])
def api_review_project(request, project_id):
    """Allows teacher to review submission and give feedback."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    profile = _get_user_profile(request.user)
    if profile.role != "teacher":
        return JsonResponse({"error": "Only teachers can review projects."}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    status_val = str(data.get("status") or "In review")
    remark_val = str(data.get("remark") or "").strip()

    sub = get_object_or_404(ProjectSubmission.objects.select_related("owner", "team"), id=project_id)
    sub.status = status_val
    sub.remark = remark_val
    sub.save()

    # Dispatch notification to student owner
    if sub.owner:
        create_notification(
            sub.owner,
            f"Project {status_val}",
            f"Your project '{sub.title}' was updated to '{status_val}'. Remark: {remark_val or 'No remark given.'}",
            notification_type="review",
            link_page="projects"
        )

    return JsonResponse({
        "success": True,
        "project": _serialize_submission_for_teacher(sub)
    })


@require_http_methods(["POST"])
def api_add_teammate(request):
    """Invites a teammate to the student's team."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    profile = _get_user_profile(request.user)
    if profile.role != "student":
        return JsonResponse({"error": "Only students can manage project teams."}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    email = str(data.get("email") or "").strip()
    role = str(data.get("role") or "Project contributor").strip()

    if not email:
        return JsonResponse({"success": False, "error": "Email is required."}, status=400)

    # Get or create team
    team = Team.objects.filter(created_by=request.user).first()
    if not team:
        team = Team.objects.create(
            name=profile.team_name or f"{profile.display_name}'s Team",
            created_by=request.user
        )

    # Derive clean name from email
    name = email.split("@")[0].replace(".", " ").replace("-", " ").replace("_", " ").title()
    colors = ["blue", "green", "orange", "rose"]
    color = colors[team.members.count() % 4]

    member = TeamMember.objects.create(
        team=team,
        name=name,
        email=email,
        role=role,
        color=color,
        is_leader=False
    )

    return JsonResponse({
        "success": True,
        "member": {
            "id": member.id,
            "name": member.name,
            "initials": member.initials,
            "role": member.role,
            "color": member.color,
            "leader": False,
        }
    })


@require_http_methods(["POST"])
def api_ask_query(request):
    """Submits a student question to the teacher and sends notifications."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    subject = str(data.get("subject") or "").strip()
    details = str(data.get("details") or "").strip()

    if not subject:
        return JsonResponse({"success": False, "error": "Question subject is required."}, status=400)

    q = Query.objects.create(
        asked_by=request.user,
        title=subject,
        details=details
    )

    # Notify teachers
    profile = _get_user_profile(request.user)
    teachers = UserProfile.objects.filter(role="teacher").select_related("user")
    for t in teachers:
        create_notification(
            t.user,
            "New Student Question",
            f"{profile.display_name} asked: '{subject}'.",
            notification_type="query",
            link_page="queries"
        )

    return JsonResponse({
        "success": True,
        "query": {
            "id": q.id,
            "title": q.title,
            "details": q.details,
            "meta": "Asked just now · Awaiting teacher reply",
            "answered": False,
            "response": "",
        }
    })


@require_http_methods(["POST"])
def api_reply_query(request, query_id):
    """Allows teacher to respond to student question and notifies the student."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    profile = _get_user_profile(request.user)
    if profile.role != "teacher":
        return JsonResponse({"error": "Only teachers can respond to queries."}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    reply_text = str(data.get("reply") or "").strip()
    if not reply_text:
        return JsonResponse({"success": False, "error": "Reply cannot be empty."}, status=400)

    q = get_object_or_404(Query, id=query_id)
    q.response = reply_text
    q.answered = True
    q.responded_by = request.user
    q.save()

    # Notify student
    if q.asked_by:
        create_notification(
            q.asked_by,
            "Question Answered",
            f"Your teacher answered '{q.title}': {reply_text[:100]}",
            notification_type="query",
            link_page="queries"
        )

    return JsonResponse({
        "success": True,
        "query": {
            "id": q.id,
            "title": q.title,
            "details": q.details,
            "meta": "Answered just now · Teacher",
            "answered": True,
            "response": q.response,
        }
    })


@require_http_methods(["GET"])
def api_get_messages(request):
    """Fetches messages for a thread, with optional polling via since_id."""
    if not request.user.is_authenticated:
        return JsonResponse({"messages": [], "authenticated": False}, status=200)

    thread = request.GET.get("thread", "team")
    since_id = request.GET.get("since_id")

    qs = ChatMessage.objects.filter(thread=thread)
    if since_id and since_id.isdigit():
        qs = qs.filter(id__gt=int(since_id))

    qs = qs.select_related("sender").order_by("created_at")[:100]

    messages = []
    for m in qs:
        sender_profile = getattr(m.sender, 'profile', None) if m.sender else None
        is_teacher = sender_profile and sender_profile.role == "teacher"
        messages.append({
            "id": m.id,
            "name": m.sender_name,
            "initials": "".join([part[0] for part in m.sender_name.strip().split()[:2]]).upper() or "?",
            "color": m.color or ("orange" if is_teacher else ""),
            "text": m.text,
            "time": m.created_at.strftime("%I:%M %p"),
            "mine": m.sender_id == request.user.id,
        })

    return JsonResponse({
        "success": True,
        "thread": thread,
        "messages": messages
    })


@require_http_methods(["POST"])
def api_send_message(request):
    """Sends a chat message to a thread."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    thread = str(data.get("thread") or "team")
    text = str(data.get("text") or "").strip()

    if not text:
        return JsonResponse({"success": False, "error": "Message cannot be empty."}, status=400)

    profile = _get_user_profile(request.user)
    team = Team.objects.filter(created_by=request.user).first()

    msg = ChatMessage.objects.create(
        thread=thread,
        sender=request.user,
        sender_name=profile.display_name,
        team=team,
        text=text,
        color="orange" if profile.role == "teacher" else ""
    )

    initials = "".join([part[0] for part in profile.display_name.strip().split()[:2]]).upper() or "?"

    return JsonResponse({
        "success": True,
        "message": {
            "id": msg.id,
            "name": msg.sender_name,
            "initials": initials,
            "color": msg.color,
            "text": msg.text,
            "time": "Now",
            "mine": True,
        }
    })


@require_http_methods(["GET"])
def api_get_notifications(request):
    """Returns user's notifications and unread count with smart dynamic alerts."""
    if not request.user.is_authenticated:
        return JsonResponse({"notifications": [], "unreadCount": 0, "authenticated": False}, status=200)

    profile = _get_user_profile(request.user)
    items = []
    unread_count = 0

    if profile and profile.role == "teacher":
        # 1. Submissions awaiting teacher review
        pending_subs = ProjectSubmission.objects.filter(status="In review").select_related("owner", "team").order_by("-submitted_at")[:15]
        for sub in pending_subs:
            owner_name = sub.owner.first_name or sub.owner.username if sub.owner else "Student"
            team_label = sub.team.name if sub.team else "Student Team"
            items.append({
                "id": f"sub-{sub.id}",
                "rawId": sub.id,
                "title": f"Submission Awaiting Review",
                "message": f"'{sub.title}' by {owner_name} ({team_label}) is awaiting your evaluation.",
                "type": "submission",
                "linkPage": "projects",
                "isRead": False,
                "time": _format_date(sub.submitted_at) or "Awaiting review",
                "actionType": "review",
                "actionLabel": "Review Project",
            })
            unread_count += 1

        # 2. Student questions needing teacher reply
        unanswered_queries = Query.objects.filter(answered=False).select_related("asked_by").order_by("-created_at")[:15]
        for q in unanswered_queries:
            student_name = q.asked_by.first_name or q.asked_by.username if q.asked_by else "Student"
            items.append({
                "id": f"query-{q.id}",
                "rawId": q.id,
                "title": f"Question Needs Reply",
                "message": f"{student_name}: '{q.title}' - {q.details[:60] if q.details else 'Student is waiting for guidance'}",
                "type": "query",
                "linkPage": "queries",
                "isRead": False,
                "time": _format_date(q.created_at) or "Needs reply",
                "actionType": "reply",
                "actionLabel": "Reply Now",
            })
            unread_count += 1

    # 3. Explicit Activity Notifications for the user
    user_notifs = ActivityNotification.objects.filter(user=request.user).order_by("-created_at")[:20]
    for n in user_notifs:
        items.append({
            "id": f"notif-{n.id}",
            "rawId": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.notification_type,
            "linkPage": n.link_page or "overview",
            "isRead": n.is_read,
            "time": n.created_at.strftime("%b %d, %I:%M %p"),
            "actionType": "navigate",
            "actionLabel": "View",
        })
        if not n.is_read:
            unread_count += 1

    return JsonResponse({
        "success": True,
        "unreadCount": unread_count,
        "notifications": items
    })


@require_http_methods(["POST"])
def api_mark_notifications_read(request):
    """Marks notifications as read."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    notif_id = data.get("id")
    if notif_id:
        ActivityNotification.objects.filter(user=request.user, id=notif_id).update(is_read=True)
    else:
        ActivityNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)

    return JsonResponse({"success": True})
