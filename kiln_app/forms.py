from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    Kiln, Batch, TemperatureRecord, DamperRecord,
    SmokeStage, KilnRating, Supplier, RawMaterialBatch,
    MoistureTest, MaterialIssue, MaterialLoss, StockWarning
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


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            'name', 'contact_person', 'phone', 'address',
            'wood_species', 'supply_capacity', 'status',
            'credit_rating', 'remarks'
        ]
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'remarks': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in ['status', 'remarks']:
                field.widget.attrs['class'] = 'form-control'
            elif field_name == 'status':
                field.widget.attrs['class'] = 'form-select'

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name:
            raise ValidationError('供应商名称不能为空')
        qs = Supplier.objects.filter(name=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('该供应商名称已存在，不能重复')
        return name


class RawMaterialBatchForm(forms.ModelForm):
    class Meta:
        model = RawMaterialBatch
        fields = [
            'batch_no', 'supplier', 'wood_species', 'arrival_date',
            'total_weight', 'moisture_content', 'piece_count',
            'average_diameter', 'average_length', 'storage_location',
            'quality_grade', 'inspection_notes', 'inspector',
            'inspection_date', 'expected_shelf_life', 'unit_price', 'remarks'
        ]
        widgets = {
            'arrival_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'inspection_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'wood_species': forms.Select(attrs={'class': 'form-select'}),
            'quality_grade': forms.Select(attrs={'class': 'form-select'}),
            'inspection_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'remarks': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in [
                'arrival_date', 'inspection_date', 'supplier',
                'wood_species', 'quality_grade', 'inspection_notes', 'remarks'
            ]:
                field.widget.attrs['class'] = 'form-control'

    def clean_batch_no(self):
        batch_no = self.cleaned_data.get('batch_no')
        if not batch_no:
            raise ValidationError('原料批次号不能为空')
        qs = RawMaterialBatch.objects.filter(batch_no=batch_no)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('该原料批次号已存在，不能重复')
        return batch_no


class MoistureTestForm(forms.ModelForm):
    test_date = forms.DateTimeField(
        label='检测时间',
        input_formats=['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-control'},
            format='%Y-%m-%dT%H:%M'
        ),
    )

    class Meta:
        model = MoistureTest
        fields = [
            'test_date', 'moisture_content', 'test_method',
            'sample_location', 'tester', 'notes'
        ]

    def __init__(self, *args, **kwargs):
        self.material_batch = kwargs.pop('material_batch', None)
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name != 'test_date':
                field.widget.attrs['class'] = 'form-control'
        if self.instance and self.instance.test_date:
            local_time = timezone.localtime(self.instance.test_date)
            self.initial['test_date'] = local_time.strftime('%Y-%m-%dT%H:%M')

    def clean_moisture_content(self):
        value = self.cleaned_data.get('moisture_content')
        if value is None:
            raise ValidationError('请输入含水率')
        if value < 0 or value > 100:
            raise ValidationError('含水率必须在0-100%范围内')
        return value

    def clean_test_date(self):
        test_date = self.cleaned_data.get('test_date')
        if not test_date:
            raise ValidationError('请输入检测时间')
        local_now = timezone.localtime(timezone.now())
        if timezone.localtime(test_date).replace(second=0, microsecond=0) > local_now.replace(second=0, microsecond=0):
            raise ValidationError('检测时间不能晚于当前时间')
        return test_date


class MaterialIssueForm(forms.ModelForm):
    issue_date = forms.DateTimeField(
        label='领料日期',
        input_formats=['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local', 'class': 'form-control'},
            format='%Y-%m-%dT%H:%M'
        ),
    )

    class Meta:
        model = MaterialIssue
        fields = [
            'issue_no', 'material_batch', 'batch', 'weight',
            'issue_date', 'requester', 'stock_keeper', 'status', 'notes'
        ]
        widgets = {
            'material_batch': forms.Select(attrs={'class': 'form-select'}),
            'batch': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in [
                'issue_date', 'material_batch', 'batch', 'status', 'notes'
            ]:
                field.widget.attrs['class'] = 'form-control'
        if self.instance and self.instance.issue_date:
            local_time = timezone.localtime(self.instance.issue_date)
            self.initial['issue_date'] = local_time.strftime('%Y-%m-%dT%H:%M')

    def clean_issue_no(self):
        issue_no = self.cleaned_data.get('issue_no')
        if not issue_no:
            raise ValidationError('领料单号不能为空')
        qs = MaterialIssue.objects.filter(issue_no=issue_no)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('该领料单号已存在，不能重复')
        return issue_no

    def clean(self):
        cleaned_data = super().clean()
        weight = cleaned_data.get('weight')
        material_batch = cleaned_data.get('material_batch')
        status = cleaned_data.get('status')

        if weight and material_batch and status == 'completed':
            available = material_batch.remaining_weight
            if self.instance and self.instance.pk and self.instance.status == 'completed':
                available = available + float(self.instance.weight)
            if float(weight) > available:
                self.add_error('weight', f'领用重量不能超过当前库存量({available}kg)')

        return cleaned_data


class MaterialLossForm(forms.ModelForm):
    class Meta:
        model = MaterialLoss
        fields = [
            'loss_no', 'material_batch', 'loss_type', 'weight',
            'loss_date', 'discovered_by', 'description',
            'handled', 'handler', 'handling_method'
        ]
        widgets = {
            'loss_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'material_batch': forms.Select(attrs={'class': 'form-select'}),
            'loss_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'handling_method': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in [
                'loss_date', 'material_batch', 'loss_type',
                'description', 'handling_method', 'handled'
            ]:
                field.widget.attrs['class'] = 'form-control'

    def clean_loss_no(self):
        loss_no = self.cleaned_data.get('loss_no')
        if not loss_no:
            raise ValidationError('损耗单号不能为空')
        qs = MaterialLoss.objects.filter(loss_no=loss_no)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('该损耗单号已存在，不能重复')
        return loss_no

    def clean(self):
        cleaned_data = super().clean()
        weight = cleaned_data.get('weight')
        material_batch = cleaned_data.get('material_batch')

        if weight and material_batch:
            available = material_batch.remaining_weight
            if float(weight) > available:
                self.add_error('weight', f'损耗重量不能超过当前库存量({available}kg)')

        return cleaned_data


class StockWarningResolveForm(forms.ModelForm):
    class Meta:
        model = StockWarning
        fields = ['is_resolved', 'resolved_by', 'resolution_notes']
        widgets = {
            'resolution_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['resolved_by'].widget.attrs['class'] = 'form-control'
