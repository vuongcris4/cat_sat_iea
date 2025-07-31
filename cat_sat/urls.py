from django.urls import path
from . import views

app_name = 'cat_sat'  # This defines a namespace for the app's URLs

urlpatterns = [
    # This pattern is for your index view and is named 'index'
    path('', views.index, name='index'),
    path('optimize/', views.optimize, name='optimize'),
]