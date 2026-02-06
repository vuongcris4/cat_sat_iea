from django.contrib import admin
from django.contrib.sessions.models import Session
from django.contrib.auth.models import User
from django.utils import timezone


class SessionAdmin(admin.ModelAdmin):
    list_display = ['session_key_short', 'get_username', 'expire_date', 'is_active']
    list_filter = ['expire_date']
    search_fields = ['session_key']
    readonly_fields = ['session_key', 'session_data', 'expire_date', 'get_username', 'get_decoded_data']
    
    def session_key_short(self, obj):
        return obj.session_key[:20] + '...'
    session_key_short.short_description = 'Session Key'
    
    def get_username(self, obj):
        data = obj.get_decoded()
        user_id = data.get('_auth_user_id')
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
                return user.username
            except User.DoesNotExist:
                return f'Unknown (ID: {user_id})'
        return 'Anonymous'
    get_username.short_description = 'User'
    
    def is_active(self, obj):
        return obj.expire_date > timezone.now()
    is_active.boolean = True
    is_active.short_description = 'Active'
    
    def get_decoded_data(self, obj):
        return str(obj.get_decoded())
    get_decoded_data.short_description = 'Decoded Data'
    
    actions = ['delete_selected']


# Register Session model
admin.site.register(Session, SessionAdmin)
