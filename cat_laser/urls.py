from django.urls import path
from . import views

app_name = 'cat_laser'

urlpatterns = [
    path('', views.index, name='index'),
    # Các routes khác tương tự như cat_sat khi cần
]
