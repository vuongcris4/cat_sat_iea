from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include

def home_redirect(request):
    return redirect('cat_laser_roi:index')  # Chuyển hướng về /cat_sat/

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('cat_sat/', include(('cat_sat.urls', 'cat_sat'), namespace='cat_sat')),
    path('cat_laser/', include(('cat_laser.urls', 'cat_laser'), namespace='cat_laser')),
    path('cat_laser_roi/', include(('cat_laser_roi.urls', 'cat_laser_roi'), namespace='cat_laser_roi')),

    # Trang chính tự động chuyển hướng đến /cat_sat/
    path('', home_redirect, name='home'),
]
