from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    Kiln, Batch, TemperatureRecord, DamperRecord,
    SmokeStage, KilnRating
)


class KilnForm(forms.ModelForm):
    class Meta:
        model = Kiln
        fields = ['name', 'location', 'capacity', 'build_date', 'status', 'description']
        widgets = {
            'build_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.Textarea, forms.Select)):
                field.widget.attrs['class'] = 'form-control'
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'

    def clean_capacity(self):
        capacity = self.cleaned_data.get('capacity')
        if capacity and capacity <= 0:
            raise ValidationError('装窑容量必须大于0')
        return capacity


class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = [
            'batch_no', 'kiln', 'material_type', 'material_weight',
            'charcoal_weight', 'ignition_date', 'finish_date',
            'operator', 'notes'
        ]
        widgets = {
            'ignition_date': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M'
            ),
            'finish_date': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-control'},
                format='%Y-%m-%dT%H:%M'
            ),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in ['ignition_date', 'finish_date', 'notes', 'kiln', 'material_type']:
                field.widget.attrs['class'] = 'form-control'
            elif field_name in ['kiln', 'material_type']:
                field.widget.attrs['class'] = 'form-select'
        if self.instance and self.instance.pk:
            if self.instance.ignition_date:
                local_ignition = timezone.localtime(self.instance.ignition_date)
                self.initial['ignition_date'] = local_ignition.strftime('%Y-%m-%dT%H:%M:%S')
            if self.instance.finish_date:
                local_finish = timezone.localtime(self.instance.finish_date)
                self.initial['finish_date'] = local_finish.strftime('%Y-%m-%dT%H:%M:%S')

    def clean_batch_no(self):
        batch_no = self.cleaned_data.get('batch_no')
        if not batch_no:
            raise ValidationError('批次编号不能为空')
        qs = Batch.objects.filter(batch_no=batch_no)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('该批次编号已存在，不能重复')
        return batch_no

    def clean_material_weight(self):
        weight = self.cleaned_data.get('material_weight')
        if weight is None:
            raise ValidationError('请输入原料重量')
        if weight <= 0:
            raise ValidationError('原料重量必须大于0')
        return weight

    def clean_charcoal_weight(self):
        weight = self.cleaned_data.get('charcoal_weight')
        if weight is not None and weight < 0:
            raise ValidationError('成炭重量不能为负数')
        return weight

    def clean_ignition_date(self):
        date = self.cleaned_data.get('ignition_date')
        if not date:
            raise ValidationError('请输入点火日期')
        if date > timezone.now():
            raise ValidationError('点火日期不能晚于当前时间')
        return date

    def clean(self):
        cleaned_data = super().clean()
        material_weight = cleaned_data.get('material_weight')
        charcoal_weight = cleaned_data.get('charcoal_weight')
        ignition_date = cleaned_data.get('ignition_date')
        finish_date = cleaned_data.get('finish_date')

        if charcoal_weight is not None and material_weight is not None:
            if charcoal_weight > material_weight:
                self.add_error('charcoal_weight', '成炭重量不能超过原料重量')

        if finish_date and ignition_date:
            if finish_date < ignition_date:
                self.add_error('finish_date', '出窑日期不能早于点火日期')

        return cleaned_data


class TemperatureRecordForm(forms.ModelForm):
    record_time = forms.DateTimeField(
        label='记录时间',
        input_formats=['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-control'},
            format='%Y-%m-%dT%H:%M'
        ),
    )

    class Meta:
        model = TemperatureRecord
        fields = ['record_time', 'temperature', 'position', 'notes']
        widgets = {
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.batch = kwargs.pop('batch', None)
        super().__init__(*args, **kwargs)
        self.fields['temperature'].widget.attrs['class'] = 'form-control'
        self.fields['position'].widget.attrs['class'] = 'form-control'
        if self.instance and self.instance.record_time:
            local_time = timezone.localtime(self.instance.record_time)
            self.initial['record_time'] = local_time.strftime('%Y-%m-%dT%H:%M')

    def clean_temperature(self):
        temp = self.cleaned_data.get('temperature')
        if temp is None:
            raise ValidationError('请输入窑温')
        if temp < 0 or temp > 1200:
            raise ValidationError('窑温必须在0-1200℃范围内')
        return temp

    def clean_record_time(self):
        record_time = self.cleaned_data.get('record_time')
        if not record_time:
            raise ValidationError('请输入记录时间')
        if self.batch and self.batch.ignition_date:
            local_record = timezone.localtime(record_time).replace(second=0, microsecond=0)
            local_ignition = timezone.localtime(self.batch.ignition_date).replace(second=0, microsecond=0)
            if local_record < local_ignition:
                raise ValidationError('记录时间不能早于点火时间')
        local_now = timezone.localtime(timezone.now())
        if timezone.localtime(record_time).replace(second=0, microsecond=0) > local_now.replace(second=0, microsecond=0):
            raise ValidationError('记录时间不能晚于当前时间')
        return record_time


class DamperRecordForm(forms.ModelForm):
    record_time = forms.DateTimeField(
        label='记录时间',
        input_formats=['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-control'},
            format='%Y-%m-%dT%H:%M'
        ),
    )

    class Meta:
        model = DamperRecord
        fields = ['record_time', 'damper_opening', 'damper_name', 'reason']
        widgets = {
            'damper_name': forms.TextInput(attrs={'class': 'form-control'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.batch = kwargs.pop('batch', None)
        super().__init__(*args, **kwargs)
        self.fields['damper_opening'].widget.attrs['class'] = 'form-control'
        if self.instance and self.instance.record_time:
            local_time = timezone.localtime(self.instance.record_time)
            self.initial['record_time'] = local_time.strftime('%Y-%m-%dT%H:%M')

    def clean_damper_opening(self):
        opening = self.cleaned_data.get('damper_opening')
        if opening is None:
            raise ValidationError('请输入风门开度')
        if opening < 0 or opening > 100:
            raise ValidationError('风门开度必须在0-100范围内')
        return opening

    def clean_record_time(self):
        record_time = self.cleaned_data.get('record_time')
        if not record_time:
            raise ValidationError('请输入记录时间')
        if self.batch and self.batch.ignition_date:
            local_record = timezone.localtime(record_time).replace(second=0, microsecond=0)
            local_ignition = timezone.localtime(self.batch.ignition_date).replace(second=0, microsecond=0)
            if local_record < local_ignition:
                raise ValidationError('记录时间不能早于点火时间')
        local_now = timezone.localtime(timezone.now())
        if timezone.localtime(record_time).replace(second=0, microsecond=0) > local_now.replace(second=0, microsecond=0):
            raise ValidationError('记录时间不能晚于当前时间')
        return record_time


class SmokeStageForm(forms.ModelForm):
    record_time = forms.DateTimeField(
        label='记录时间',
        input_formats=['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-control'},
            format='%Y-%m-%dT%H:%M'
        ),
    )

    class Meta:
        model = SmokeStage
        fields = ['record_time', 'stage', 'smoke_density', 'notes']
        widgets = {
            'stage': forms.Select(attrs={'class': 'form-select'}),
            'smoke_density': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 10}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.batch = kwargs.pop('batch', None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.record_time:
            local_time = timezone.localtime(self.instance.record_time)
            self.initial['record_time'] = local_time.strftime('%Y-%m-%dT%H:%M')

    def clean_smoke_density(self):
        density = self.cleaned_data.get('smoke_density')
        if density is not None:
            if density < 1 or density > 10:
                raise ValidationError('烟浓密度必须在1-10范围内')
        return density

    def clean_record_time(self):
        record_time = self.cleaned_data.get('record_time')
        if not record_time:
            raise ValidationError('请输入记录时间')
        if self.batch and self.batch.ignition_date:
            local_record = timezone.localtime(record_time).replace(second=0, microsecond=0)
            local_ignition = timezone.localtime(self.batch.ignition_date).replace(second=0, microsecond=0)
            if local_record < local_ignition:
                raise ValidationError('记录时间不能早于点火时间')
        local_now = timezone.localtime(timezone.now())
        if timezone.localtime(record_time).replace(second=0, microsecond=0) > local_now.replace(second=0, microsecond=0):
            raise ValidationError('记录时间不能晚于当前时间')
        return record_time


class KilnRatingForm(forms.ModelForm):
    class Meta:
        model = KilnRating
        fields = [
            'grade', 'appearance_score', 'hardness_score',
            'moisture_score', 'ash_content_score', 'evaluator',
            'evaluation_date', 'remarks'
        ]
        widgets = {
            'grade': forms.Select(attrs={'class': 'form-select'}),
            'evaluation_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'remarks': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        score_fields = ['appearance_score', 'hardness_score', 'moisture_score', 'ash_content_score']
        for field in score_fields:
            self.fields[field].widget.attrs['class'] = 'form-control'
            self.fields[field].widget.attrs['min'] = 0
            self.fields[field].widget.attrs['max'] = 100
        self.fields['evaluator'].widget.attrs['class'] = 'form-control'

    def clean(self):
        cleaned_data = super().clean()
        score_fields = ['appearance_score', 'hardness_score', 'moisture_score', 'ash_content_score']
        for field in score_fields:
            value = cleaned_data.get(field)
            if value is not None and (value < 0 or value > 100):
                self.add_error(field, '评分必须在0-100范围内')
        return cleaned_data
