from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


class Kiln(models.Model):
    KILN_STATUS = (
        ('active', '使用中'),
        ('idle', '闲置'),
        ('maintenance', '维修中'),
        ('retired', '报废'),
    )

    name = models.CharField('窑号', max_length=50, unique=True)
    location = models.CharField('所在位置', max_length=200, blank=True)
    capacity = models.DecimalField('装窑容量(kg)', max_digits=10, decimal_places=2)
    build_date = models.DateField('建造日期', null=True, blank=True)
    status = models.CharField('状态', max_length=20, choices=KILN_STATUS, default='idle')
    description = models.TextField('备注说明', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '炭窑档案'
        verbose_name_plural = verbose_name
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'


class Batch(models.Model):
    MATERIAL_TYPE = (
        ('oak', '橡木'),
        ('pine', '松木'),
        ('bamboo', '竹材'),
        ('fruitwood', '果木'),
        ('mixed', '杂木'),
        ('other', '其他'),
    )

    batch_no = models.CharField('批次编号', max_length=50, unique=True)
    kiln = models.ForeignKey(Kiln, on_delete=models.PROTECT, verbose_name='炭窑')
    material_type = models.CharField('原料类型', max_length=20, choices=MATERIAL_TYPE)
    material_weight = models.DecimalField('原料重量(kg)', max_digits=10, decimal_places=2)
    charcoal_weight = models.DecimalField('成炭重量(kg)', max_digits=10, decimal_places=2, null=True, blank=True)
    ignition_date = models.DateTimeField('点火日期')
    finish_date = models.DateTimeField('出窑日期', null=True, blank=True)
    operator = models.CharField('操作人', max_length=50, blank=True)
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '烧炭批次'
        verbose_name_plural = verbose_name
        ordering = ['-ignition_date']

    def __str__(self):
        return self.batch_no

    @property
    def yield_rate(self):
        if self.material_weight and self.charcoal_weight and self.material_weight > 0:
            return round(float(self.charcoal_weight) / float(self.material_weight) * 100, 2)
        return None

    @property
    def duration_hours(self):
        if self.ignition_date and self.finish_date:
            delta = self.finish_date - self.ignition_date
            return round(delta.total_seconds() / 3600, 2)
        return None

    @property
    def current_stage(self):
        latest_smoke = self.smokestage_set.order_by('-record_time').first()
        if latest_smoke:
            return latest_smoke.get_stage_display()
        return '未开始'

    def clean(self):
        super().clean()
        if self.material_weight and self.material_weight <= 0:
            raise ValidationError({'material_weight': '原料重量必须大于0'})
        if self.charcoal_weight and self.charcoal_weight < 0:
            raise ValidationError({'charcoal_weight': '成炭重量不能为负数'})
        if self.charcoal_weight and self.material_weight:
            if self.charcoal_weight > self.material_weight:
                raise ValidationError({'charcoal_weight': '成炭重量不能超过原料重量'})
        if self.finish_date and self.ignition_date:
            if self.finish_date < self.ignition_date:
                raise ValidationError({'finish_date': '出窑日期不能早于点火日期'})


class TemperatureRecord(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, verbose_name='所属批次', related_name='temperature_records')
    record_time = models.DateTimeField('记录时间')
    temperature = models.DecimalField('窑温(℃)', max_digits=6, decimal_places=1)
    position = models.CharField('测温位置', max_length=50, default='窑中心')
    notes = models.CharField('备注', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '温度记录'
        verbose_name_plural = verbose_name
        ordering = ['record_time']

    def __str__(self):
        return f'{self.batch.batch_no} - {self.temperature}℃ @ {self.record_time}'

    def clean(self):
        super().clean()
        if self.temperature < 0 or self.temperature > 1200:
            raise ValidationError({'temperature': '窑温必须在0-1200℃范围内'})
        if self.record_time and self.batch.ignition_date:
            if self.record_time < self.batch.ignition_date:
                raise ValidationError({'record_time': '记录时间不能早于点火时间'})


class DamperRecord(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, verbose_name='所属批次', related_name='damper_records')
    record_time = models.DateTimeField('记录时间')
    damper_opening = models.IntegerField('风门开度(%)')
    damper_name = models.CharField('风门名称', max_length=50, default='主风门')
    reason = models.CharField('调整原因', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '风门调整记录'
        verbose_name_plural = verbose_name
        ordering = ['record_time']

    def __str__(self):
        return f'{self.batch.batch_no} - {self.damper_opening}% @ {self.record_time}'

    def clean(self):
        super().clean()
        if self.damper_opening < 0 or self.damper_opening > 100:
            raise ValidationError({'damper_opening': '风门开度必须在0-100范围内'})
        if self.record_time and self.batch.ignition_date:
            if self.record_time < self.batch.ignition_date:
                raise ValidationError({'record_time': '记录时间不能早于点火时间'})


class SmokeStage(models.Model):
    STAGE_CHOICES = (
        ('drying', '干燥期（白烟）'),
        ('precarbonization', '预炭化（黄烟）'),
        ('carbonization', '炭化期（青烟）'),
        ('refining', '精炼期（淡烟/无烟）'),
        ('cooling', '冷却期'),
        ('abnormal_heavy_smoke', '异常浓烟'),
        ('abnormal_no_smoke_early', '异常过早无烟'),
        ('abnormal_black_smoke', '异常黑烟'),
    )

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, verbose_name='所属批次', related_name='smokestage_set')
    record_time = models.DateTimeField('记录时间')
    stage = models.CharField('烟色阶段', max_length=30, choices=STAGE_CHOICES)
    smoke_density = models.IntegerField('烟浓密度(1-10)', null=True, blank=True)
    is_normal = models.BooleanField('是否正常', default=True)
    warning_message = models.CharField('异常提示', max_length=500, blank=True)
    notes = models.CharField('备注', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '烟色阶段记录'
        verbose_name_plural = verbose_name
        ordering = ['record_time']

    def __str__(self):
        return f'{self.batch.batch_no} - {self.get_stage_display()}'

    def save(self, *args, **kwargs):
        abnormal_stages = ['abnormal_heavy_smoke', 'abnormal_no_smoke_early', 'abnormal_black_smoke']
        if self.stage in abnormal_stages:
            self.is_normal = False
            if self.stage == 'abnormal_heavy_smoke':
                self.warning_message = '警告：浓烟持续，可能温度不足导致炭化不良（欠火风险），请检查风门开度和温度。'
            elif self.stage == 'abnormal_no_smoke_early':
                self.warning_message = '警告：过早无烟，可能温度过高导致过火，炭料有灰化风险，请降温并检查。'
            elif self.stage == 'abnormal_black_smoke':
                self.warning_message = '警告：出现黑烟，燃烧不完全或有焦油堆积，存在过火和安全隐患，请立即检查。'
        else:
            self.is_normal = True
            self.warning_message = ''
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.smoke_density is not None:
            if self.smoke_density < 1 or self.smoke_density > 10:
                raise ValidationError({'smoke_density': '烟浓密度必须在1-10范围内'})
        if self.record_time and self.batch.ignition_date:
            if self.record_time < self.batch.ignition_date:
                raise ValidationError({'record_time': '记录时间不能早于点火时间'})


class KilnRating(models.Model):
    GRADE_CHOICES = (
        ('excellent', '特级'),
        ('good', '一级'),
        ('medium', '二级'),
        ('poor', '三级'),
        ('reject', '等外品'),
    )

    batch = models.OneToOneField(Batch, on_delete=models.CASCADE, verbose_name='所属批次', related_name='rating')
    grade = models.CharField('质量等级', max_length=20, choices=GRADE_CHOICES)
    appearance_score = models.IntegerField('外观评分(1-100)', null=True, blank=True)
    hardness_score = models.IntegerField('硬度评分(1-100)', null=True, blank=True)
    moisture_score = models.IntegerField('含水率评分(1-100)', null=True, blank=True)
    ash_content_score = models.IntegerField('灰分评分(1-100)', null=True, blank=True)
    total_score = models.DecimalField('综合评分', max_digits=5, decimal_places=2, null=True, blank=True)
    evaluator = models.CharField('评定人', max_length=50, blank=True)
    evaluation_date = models.DateField('评定日期', default=timezone.now)
    remarks = models.TextField('评语', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '出窑评级'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.batch.batch_no} - {self.get_grade_display()}'

    def save(self, *args, **kwargs):
        scores = [self.appearance_score, self.hardness_score, self.moisture_score, self.ash_content_score]
        valid_scores = [s for s in scores if s is not None]
        if valid_scores:
            self.total_score = round(sum(valid_scores) / len(valid_scores), 2)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        score_fields = [
            ('appearance_score', self.appearance_score),
            ('hardness_score', self.hardness_score),
            ('moisture_score', self.moisture_score),
            ('ash_content_score', self.ash_content_score),
        ]
        for field_name, value in score_fields:
            if value is not None and (value < 0 or value > 100):
                raise ValidationError({field_name: '评分必须在0-100范围内'})
