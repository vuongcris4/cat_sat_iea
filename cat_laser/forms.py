from django import forms

class OptimizationLaserForm(forms.Form):
    LENGTH_CHOICES = [(5740, '5740'), (5850, '5850'), (6000, '6000')]

    length = forms.ChoiceField(
        choices=LENGTH_CHOICES,
        label="Chiều dài cây sắt (mm)",
        initial=5850,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    segment_sizes = forms.CharField(
        label="Kích thước đoạn (mm, cách nhau bằng dấu cách hoặc dấu phẩy)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'segment_sizes_input'})
    )

    demands = forms.CharField(
        label="Số lượng cần (từng đoạn, cách nhau bằng dấu cách hoặc dấu phẩy)",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    blade_width_mctd = forms.IntegerField(
        label="Kích thước lưỡi mài MCTĐ (mm)",
        initial=3,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    max_stock_over = forms.IntegerField(
        label="Số lượng tồn kho tối đa (đoạn)",
        initial=3,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
