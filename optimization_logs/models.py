from django.db import models
from django.contrib.auth.models import User


class OptimizationLog(models.Model):
    """Stores the history of every optimization run (input -> output)."""

    STATUS_CHOICES = [
        ('success', 'Thành công'),
        ('error', 'Lỗi'),
        ('timeout', 'Hết thời gian'),
    ]

    MODULE_CHOICES = [
        ('cat_sat', 'MC Tự Động (MCTĐ)'),
        ('cat_laser_roi', 'MC Laser'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Người dùng'
    )
    module = models.CharField(
        max_length=30, choices=MODULE_CHOICES, verbose_name='Module'
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name='Thời điểm'
    )
    duration_seconds = models.FloatField(
        null=True, blank=True, verbose_name='Thời gian (giây)'
    )
    input_data = models.JSONField(
        default=dict, verbose_name='Dữ liệu đầu vào'
    )
    parameters = models.JSONField(
        default=dict, verbose_name='Tham số'
    )
    output_summary = models.JSONField(
        default=dict, blank=True, verbose_name='Kết quả tổng kết'
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='success',
        verbose_name='Trạng thái'
    )
    error_message = models.TextField(
        blank=True, default='', verbose_name='Chi tiết lỗi'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Optimization Log'
        verbose_name_plural = 'Optimization Logs'

    def __str__(self):
        return f"{self.get_module_display()} - {self.user} - {self.created_at:%Y-%m-%d %H:%M}"
