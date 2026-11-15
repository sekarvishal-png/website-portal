import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import (
    UserProfile,
    Team,
    TeamMember,
    ProjectSubmission,
    Query,
    ChatMessage,
    ActivityNotification,
)


class IdeaAppTests(TestCase):
    def setUp(self):
        self.client = Client()

    def _create_student(self, email="jane@example.com", name="Jane Student", team_name="Byte Force"):
        payload = {
            "name": name,
            "email": email,
            "password": "Password123!",
            "role": "student",
            "post": "Team leader",
            "department": "Computer Science",
            "teamName": team_name
        }
        return self.client.post("/api/auth/signup/", data=json.dumps(payload), content_type="application/json")

    def _create_teacher(self, email="turing@university.edu", name="Prof. Alan Turing"):
        payload = {
            "name": name,
            "email": email,
            "password": "Password123!",
            "role": "teacher",
            "post": "Administrator",
            "department": "Computer Science",
            "teamName": ""
        }
        return self.client.post("/api/auth/signup/", data=json.dumps(payload), content_type="application/json")

    def test_signup_student(self):
        res = self._create_student()
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["email"], "jane@example.com")

        # Verify database
        user = User.objects.get(email="jane@example.com")
        self.assertEqual(user.profile.role, "student")
        self.assertEqual(user.profile.department, "Computer Science")

        team = Team.objects.get(name="Byte Force")
        self.assertEqual(team.created_by, user)
        self.assertEqual(team.members.count(), 1)
        self.assertTrue(team.members.first().is_leader)

    def test_login_and_workspace(self):
        self._create_student()

        # Session check
        res = self.client.get("/api/auth/session/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["authenticated"])

        # Fetch workspace
        res = self.client.get("/api/workspace/")
        self.assertEqual(res.status_code, 200)
        ws = res.json()
        self.assertEqual(ws["role"], "student")
        self.assertEqual(ws["teamName"], "Byte Force")
        self.assertEqual(len(ws["members"]), 1)

    def test_project_upload_and_attach(self):
        self._create_student()

        # Upload a project with file
        file_content = b"Sample project prototype content"
        upload_file = SimpleUploadedFile("design_spec.pdf", file_content, content_type="application/pdf")

        res = self.client.post("/api/projects/upload/", {
            "title": "Smart Campus App",
            "type": "Design & Technology",
            "note": "Here is our initial wireframe.",
            "file": upload_file
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        project_id = data["project"]["id"]
        self.assertEqual(data["project"]["name"], "Smart Campus App")
        self.assertEqual(data["project"]["fileName"], "design_spec.pdf")
        self.assertTrue(data["project"]["fileUrl"].startswith("/media/submissions/"))

        # Re-attach / replace file
        new_file = SimpleUploadedFile("updated_spec.pdf", b"Updated spec content", content_type="application/pdf")
        res2 = self.client.post(f"/api/projects/{project_id}/attach/", {
            "file": new_file
        })
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(data2["success"])
        self.assertEqual(data2["project"]["fileName"], "updated_spec.pdf")

    def test_file_validation_rejects_executable(self):
        self._create_student()

        malicious_file = SimpleUploadedFile("virus.exe", b"malicious code", content_type="application/x-msdownload")
        res = self.client.post("/api/projects/upload/", {
            "title": "Test Exploit",
            "type": "Project submission",
            "file": malicious_file
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("not permitted", res.json()["error"])

    def test_add_teammate_and_query(self):
        self._create_student()

        # Add teammate
        res = self.client.post("/api/team/add-member/", data=json.dumps({
            "email": "alex.smith@example.com",
            "role": "UI / UX designer"
        }), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        self.assertEqual(res.json()["member"]["name"], "Alex Smith")

        # Ask question
        res_q = self.client.post("/api/queries/create/", data=json.dumps({
            "subject": "Due date question",
            "details": "Is the prototype due on Friday or Monday?"
        }), content_type="application/json")
        self.assertEqual(res_q.status_code, 200)
        self.assertTrue(res_q.json()["success"])

    def test_teacher_workflow(self):
        # Student creates account, project, teammate, and query
        self._create_student()

        upload_file = SimpleUploadedFile("prototype.pdf", b"Prototype test content", content_type="application/pdf")
        res_p = self.client.post("/api/projects/upload/", {
            "title": "Smart Campus App",
            "type": "Design & Technology",
            "note": "Final prototype for grading.",
            "file": upload_file
        })
        self.assertEqual(res_p.status_code, 200)
        sub_id = res_p.json()["project"]["id"]

        res_q = self.client.post("/api/queries/create/", data=json.dumps({
            "subject": "Due date question",
            "details": "Is the prototype due on Friday or Monday?"
        }), content_type="application/json")
        self.assertEqual(res_q.status_code, 200)

        # Logout student
        self.client.post("/api/auth/logout/")

        # Signup teacher
        res_t = self._create_teacher()
        self.assertEqual(res_t.status_code, 200)

        # Teacher workspace
        res_ws = self.client.get("/api/workspace/")
        self.assertEqual(res_ws.status_code, 200)
        ws = res_ws.json()
        self.assertEqual(ws["role"], "teacher")
        self.assertEqual(len(ws["submissions"]), 1)
        sub = ws["submissions"][0]
        self.assertEqual(sub["name"], "Smart Campus App")
        self.assertEqual(sub["teamName"], "Byte Force")

        # Teacher reviews project
        res_rev = self.client.post(f"/api/projects/{sub['id']}/review/", data=json.dumps({
            "status": "Approved",
            "remark": "Excellent wireframes and documentation!"
        }), content_type="application/json")
        self.assertEqual(res_rev.status_code, 200)
        self.assertTrue(res_rev.json()["success"])

        # Teacher answers query
        query_id = ws["queries"][0]["id"]
        res_rep = self.client.post(f"/api/queries/{query_id}/reply/", data=json.dumps({
            "reply": "The prototype is due on Monday at 5 PM."
        }), content_type="application/json")
        self.assertEqual(res_rep.status_code, 200)
        self.assertTrue(res_rep.json()["success"])

        # Send chat message
        res_chat = self.client.post("/api/messages/send/", data=json.dumps({
            "thread": "teacher",
            "text": "Hello class! Office hours are open today."
        }), content_type="application/json")
        self.assertEqual(res_chat.status_code, 200)
        self.assertTrue(res_chat.json()["success"])

        # Test message polling
        res_msgs = self.client.get("/api/messages/?thread=teacher")
        self.assertEqual(res_msgs.status_code, 200)
        self.assertEqual(len(res_msgs.json()["messages"]), 1)

    def test_secure_download_and_deletion(self):
        # 1. Student creates submission
        res_s = self._create_student("student2@school.edu", "Bob Dylan", "MusicTech")
        upload_file = SimpleUploadedFile("track_notes.txt", b"Notes on audio synthesis", content_type="text/plain")
        res_p = self.client.post("/api/projects/upload/", {
            "title": "Audio Synthesis",
            "type": "Research documentation",
            "file": upload_file
        })
        project_id = res_p.json()["project"]["id"]

        # Student downloads their own file
        dl_res = self.client.get(f"/api/projects/{project_id}/download/")
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(b"".join(dl_res.streaming_content), b"Notes on audio synthesis")

        # Another unauthorized student cannot download
        self.client.post("/api/auth/logout/")
        self._create_student("other@school.edu", "Eve Hacker", "OtherTeam")
        dl_unauth = self.client.get(f"/api/projects/{project_id}/download/")
        self.assertEqual(dl_unauth.status_code, 403)

        # But a teacher CAN download
        self.client.post("/api/auth/logout/")
        self._create_teacher("prof@school.edu", "Prof. Higgins")
        dl_teacher = self.client.get(f"/api/projects/{project_id}/download/")
        self.assertEqual(dl_teacher.status_code, 200)

        # Teacher approves project
        self.client.post(f"/api/projects/{project_id}/review/", data=json.dumps({"status": "Approved"}), content_type="application/json")

        # Student logs back in and tries to delete approved project (should fail)
        self.client.post("/api/auth/logout/")
        self.client.post("/api/auth/login/", {"email": "student2@school.edu", "password": "Password123!"}, content_type="application/json")
        del_fail = self.client.post(f"/api/projects/{project_id}/delete/")
        self.assertEqual(del_fail.status_code, 400)
        self.assertIn("Approved projects cannot be deleted", del_fail.json()["error"])

    def test_notifications_lifecycle(self):
        # Create teacher
        self._create_teacher("teachernotif@school.edu", "Teacher Notif")
        self.client.post("/api/auth/logout/")

        # Student creates project (this should trigger notification to teacher)
        self._create_student("studentnotif@school.edu", "Notif Student", "Notif Team")
        self.client.post("/api/projects/upload/", {
            "title": "Robotics Hand",
            "type": "Project submission"
        })

        # Switch to teacher and check notifications
        self.client.post("/api/auth/logout/")
        self.client.post("/api/auth/login/", {"email": "teachernotif@school.edu", "password": "Password123!"}, content_type="application/json")

        notif_res = self.client.get("/api/notifications/")
        self.assertEqual(notif_res.status_code, 200)
        data = notif_res.json()
        self.assertTrue(data["unreadCount"] >= 1)
        self.assertIn("New Student Submission", [n["title"] for n in data["notifications"]])

        # Mark as read
        mark_res = self.client.post("/api/notifications/read/", data=json.dumps({}), content_type="application/json")
        self.assertEqual(mark_res.status_code, 200)

        # Teacher reviews the pending project
        sub_item = next(n for n in data["notifications"] if n.get("actionType") == "review")
        self.client.post(f"/api/projects/{sub_item['rawId']}/review/", data=json.dumps({"status": "Approved"}), content_type="application/json")

        notif_res_after = self.client.get("/api/notifications/")
        self.assertEqual(notif_res_after.json()["unreadCount"], 0)
