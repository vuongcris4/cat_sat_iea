from django.contrib import admin
from .models import OptimizationLog


@admin.register(OptimizationLog)
class OptimizationLogAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'user', 'module', 'status',
        'duration_display', 'input_summary'
    ]
    list_filter = ['module', 'status', 'user', 'created_at']
    search_fields = ['user__username', 'error_message']
    readonly_fields = [
        'user', 'module', 'created_at', 'duration_seconds',
        'input_data', 'parameters', 'output_summary',
        'status', 'error_message'
    ]
    ordering = ['-created_at']

    def duration_display(self, obj):
        if obj.duration_seconds:
            return f"{obj.duration_seconds:.1f}s"
        return "-"
    duration_display.short_description = 'Thời gian'

    def input_summary(self, obj):
        pieces = obj.input_data.get('pieces', [])
        return f"{len(pieces)} loại đoạn"
    input_summary.short_description = 'Đầu vào'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
