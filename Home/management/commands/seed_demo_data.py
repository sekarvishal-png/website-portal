from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from Home.models import (
    UserProfile,
    Team,
    TeamMember,
    ProjectSubmission,
    Query,
    ChatMessage,
    ActivityNotification,
    create_notification,
)


class Command(BaseCommand):
    help = "Seeds initial demo student and teacher accounts with sample projects, queries, and notifications."

    def handle(self, *args, **options):
        # 1. Superuser / Admin Teacher
        teacher_email = "teacher@school.edu"
        teacher_pass = "Teacher@123"
        teacher_user, created_t = User.objects.get_or_create(
            username=teacher_email,
            defaults={
                "email": teacher_email,
                "first_name": "Dr. Sarah Adams",
                "is_staff": True,
                "is_superuser": True
            }
        )
        if created_t:
            teacher_user.set_password(teacher_pass)
            teacher_user.save()
            UserProfile.objects.create(
                user=teacher_user,
                role="teacher",
                post="Administrator",
                department="Design & Technology"
            )
            self.stdout.write(self.style.SUCCESS(f"Created teacher: {teacher_email} / {teacher_pass}"))
        else:
            self.stdout.write(f"Teacher {teacher_email} already exists.")

        # 2. Student User
        student_email = "student@school.edu"
        student_pass = "Student@123"
        student_user, created_s = User.objects.get_or_create(
            username=student_email,
            defaults={
                "email": student_email,
                "first_name": "Aarav Patel"
            }
        )
        if created_s:
            student_user.set_password(student_pass)
            student_user.save()
            UserProfile.objects.create(
                user=student_user,
                role="student",
                post="Team leader",
                department="Design & Technology",
                team_name="Nova Creators"
            )

            # Team
            team = Team.objects.create(
                name="Nova Creators",
                created_by=student_user
            )

            # Leader
            TeamMember.objects.create(
                team=team,
                name="Aarav Patel",
                email=student_email,
                role="Team leader",
                color="blue",
                is_leader=True
            )

            # Teammates
            TeamMember.objects.create(
                team=team,
                name="Mia Chen",
                email="mia@school.edu",
                role="UI / UX designer",
                color="green",
                is_leader=False
            )
            TeamMember.objects.create(
                team=team,
                name="Liam Johnson",
                email="liam@school.edu",
                role="Frontend developer",
                color="orange",
                is_leader=False
            )

            # Project submission
            sample_sub = ProjectSubmission.objects.create(
                owner=student_user,
                team=team,
                title="EcoTracker Prototype",
                project_type="Design & Technology",
                note="First interactive prototype of our carbon footprint tracking app.",
                status="In review",
                color="orange",
                file_name="ecotracker_prototype.pdf",
                remark=""
            )
            sample_sub.file.save(
                "ecotracker_prototype.pdf",
                ContentFile(b"%PDF-1.4 EcoTracker Prototype documentation and wireframes.")
            )

            # Query
            Query.objects.create(
                asked_by=student_user,
                title="Design guidelines clarification",
                details="Should we follow WCAG AA or AAA color contrast for the prototype?",
                answered=True,
                response="WCAG AA is required for this phase, but AAA is a great bonus!"
            )

            # Chat messages
            ChatMessage.objects.create(
                thread="team",
                sender=student_user,
                sender_name="Aarav Patel",
                team=team,
                text="Welcome everyone! Let's build something awesome."
            )

            # Notifications
            create_notification(
                teacher_user,
                "New Student Submission",
                "Aarav Patel (Nova Creators) submitted 'EcoTracker Prototype' for review.",
                notification_type="submission",
                link_page="projects"
            )
            create_notification(
                student_user,
                "Welcome to Idea!",
                "Your student workspace is all set up. Check your team tab to invite more classmates.",
                notification_type="system"
            )

            self.stdout.write(self.style.SUCCESS(f"Created student: {student_email} / {student_pass}"))
        else:
            self.stdout.write(f"Student {student_email} already exists.")

        self.stdout.write(self.style.SUCCESS("Database seeding completed successfully!"))
