from django.urls import path, re_path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_page, name="login"),
    path("register/", views.register_page, name="register"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("logout/", views.logout, name="logout"),
    path("quote_request/", views.quote_request, name="quote_request"),
    path('quote_request_info/<str:quote_id>/', views.quote_request_info, name='quote_request_info'),
    path('guide/', views.guide, name='guide'),
    # Catch-all pattern
    re_path(r"^.*$", views.home),
]
