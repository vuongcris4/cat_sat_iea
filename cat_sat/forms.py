from django import forms

class OptimizationForm(forms.Form):
    LENGTH_CHOICES = [(5740, '5740'), (5850, '5850'), (6000, '6000')]
    BLADE_WIDTH_CHOICES = [(2.5, '2.5'), (3, '3')]

    length = forms.ChoiceField(
        choices=LENGTH_CHOICES,
        label="Chiều dài thanh sắt",
        initial=5850,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    segment_sizes = forms.CharField(
        label="Kích thước đoạn",
        initial="500 255 600 615",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    demands = forms.CharField(
        label="Số lượng cần",
        initial="782 1564 1508 1508",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    blade_width = forms.ChoiceField(
        choices=BLADE_WIDTH_CHOICES,
        label="Độ dày lưỡi cắt",
        initial=2.5,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    factors = forms.CharField(
        label="Cây/bó",
        initial="14.16.18.20",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    max_manual_cuts = forms.IntegerField(
        label="Số lần cắt thủ công tối đa",
        initial=5,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    max_stock_over = forms.IntegerField(
        label="Phần dư mỗi đoạn tối đa",
        initial=20,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
