from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    # Auth endpoints
    path('api/auth/session/', views.api_auth_session, name='api_auth_session'),
    path('api/auth/signup/', views.api_signup, name='api_signup'),
    path('api/auth/login/', views.api_login, name='api_login'),
    path('api/auth/logout/', views.api_logout, name='api_logout'),

    # Workspace data
    path('api/workspace/', views.api_workspace_data, name='api_workspace_data'),

    # Projects
    path('api/projects/upload/', views.api_upload_project, name='api_upload_project'),
    path('api/projects/<int:project_id>/attach/', views.api_attach_project_file, name='api_attach_project_file'),
    path('api/projects/<int:project_id>/review/', views.api_review_project, name='api_review_project'),
    path('api/projects/<int:project_id>/download/', views.api_download_file, name='api_download_file'),
    path('api/projects/<int:project_id>/delete/', views.api_delete_project, name='api_delete_project'),

    # Team
    path('api/team/add-member/', views.api_add_teammate, name='api_add_teammate'),

    # Queries
    path('api/queries/create/', views.api_ask_query, name='api_ask_query'),
    path('api/queries/<int:query_id>/reply/', views.api_reply_query, name='api_reply_query'),

    # Chat & Real-time Polling
    path('api/messages/', views.api_get_messages, name='api_get_messages'),
    path('api/messages/send/', views.api_send_message, name='api_send_message'),

    # Notifications
    path('api/notifications/', views.api_get_notifications, name='api_get_notifications'),
    path('api/notifications/read/', views.api_mark_notifications_read, name='api_mark_notifications_read'),
]
