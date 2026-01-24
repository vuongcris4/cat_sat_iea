# your_app/forms.py
from django import forms

class OptimizationForm(forms.Form):
    stock_length = forms.IntegerField(
        label="Chiều dài cây sắt (mm)", 
        initial=6000
    )
    max_waste_percentage = forms.DecimalField(
        label="Hao hụt sắt tối đa (%)", 
        initial=1.0,
        min_value=0.01,
        max_value=10.0,
        decimal_places=2
    )
    max_surplus = forms.IntegerField(
        label="Số lượng tồn kho tối đa (mỗi loại)", 
        initial=10
    )
    use_priority_constraint = forms.BooleanField(
        label="Ưu tiên pattern có đoạn cuối khoét lỗ ít nhất", 
        required=False, 
        initial=True
    )
    use_combined_mode = forms.BooleanField(
        label="Chế độ cắt kết hợp Laser + Tự động", 
        required=False, 
        initial=False
    )
    optimize_stock_length = forms.BooleanField(
        label="Tự động tìm chiều dài cây sắt tối ưu (5000-6000mm, bước 10mm)",
        required=False,
        initial=False
    )
    time_limit_minutes = forms.IntegerField(
        label="Thời gian chạy tối đa (3x phút)", 
        initial=2
    )