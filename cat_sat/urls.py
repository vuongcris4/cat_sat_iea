from django.contrib import admin
from django.urls import path
from . import views  

urlpatterns = [
    path('', views.index, name='index'),
    path('optimize/', views.optimize, name='optimize'),
    path('stop-server/', views.stop_server, name='stop_server'),

]
