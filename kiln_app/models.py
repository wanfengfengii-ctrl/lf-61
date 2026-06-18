from django.db import models
from django.db.models import Sum
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

    @property
    def detected_stage(self):
        from .services import detect_burning_stage
        return detect_burning_stage(self)

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


class ProcessWarning(models.Model):
    WARNING_LEVEL = (
        ('info', '提示'),
        ('warning', '警告'),
        ('critical', '严重'),
    )
    WARNING_TYPE = (
        ('stage_mismatch', '阶段不匹配'),
        ('temp_anomaly', '温度异常'),
        ('damper_anomaly', '风门异常'),
        ('combo_anomaly', '组合异常'),
        ('smoke_anomaly', '烟色异常'),
    )

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, verbose_name='所属批次', related_name='process_warnings')
    warning_time = models.DateTimeField('预警时间')
    warning_type = models.CharField('预警类型', max_length=30, choices=WARNING_TYPE)
    level = models.CharField('预警级别', max_length=20, choices=WARNING_LEVEL, default='warning')
    detected_stage = models.CharField('识别烧制阶段', max_length=30, blank=True)
    temperature = models.DecimalField('当时窑温(℃)', max_digits=6, decimal_places=1, null=True, blank=True)
    damper_opening = models.IntegerField('当时风门开度(%)', null=True, blank=True)
    smoke_stage = models.CharField('当时烟色阶段', max_length=30, blank=True)
    message = models.TextField('预警信息')
    is_resolved = models.BooleanField('是否已处理', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '工艺预警'
        verbose_name_plural = verbose_name
        ordering = ['-warning_time']

    def __str__(self):
        return f'{self.batch.batch_no} - {self.get_warning_type_display()} [{self.get_level_display()}]'


class Supplier(models.Model):
    SUPPLIER_STATUS = (
        ('active', '合作中'),
        ('inactive', '暂停合作'),
        ('blacklisted', '黑名单'),
    )

    name = models.CharField('供应商名称', max_length=200, unique=True)
    contact_person = models.CharField('联系人', max_length=50, blank=True)
    phone = models.CharField('联系电话', max_length=20, blank=True)
    address = models.CharField('地址', max_length=300, blank=True)
    wood_species = models.CharField('供应树种', max_length=200, blank=True)
    supply_capacity = models.DecimalField('月供应量(kg)', max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField('合作状态', max_length=20, choices=SUPPLIER_STATUS, default='active')
    credit_rating = models.IntegerField('信用评分(1-100)', null=True, blank=True)
    remarks = models.TextField('备注', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '供应商档案'
        verbose_name_plural = verbose_name
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'

    def clean(self):
        super().clean()
        if self.credit_rating is not None:
            if self.credit_rating < 1 or self.credit_rating > 100:
                raise ValidationError({'credit_rating': '信用评分必须在1-100范围内'})
        if self.supply_capacity is not None and self.supply_capacity < 0:
            raise ValidationError({'supply_capacity': '月供应量不能为负数'})


class RawMaterialBatch(models.Model):
    WOOD_SPECIES = (
        ('oak', '橡木'),
        ('pine', '松木'),
        ('bamboo', '竹材'),
        ('fruitwood', '果木'),
        ('birch', '桦木'),
        ('fir', '杉木'),
        ('mixed', '杂木'),
        ('other', '其他'),
    )

    QUALITY_GRADE = (
        ('excellent', '特级'),
        ('good', '一级'),
        ('medium', '二级'),
        ('poor', '三级'),
        ('reject', '不合格'),
    )

    STORAGE_STATUS = (
        ('in_stock', '在库'),
        ('partial_used', '部分领用'),
        ('used_up', '已用完'),
        ('discarded', '已报废'),
    )

    batch_no = models.CharField('原料批次号', max_length=50, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, verbose_name='供应商', related_name='material_batches')
    wood_species = models.CharField('木材种类', max_length=20, choices=WOOD_SPECIES)
    arrival_date = models.DateField('到货日期', default=timezone.now)
    total_weight = models.DecimalField('入库总重量(kg)', max_digits=10, decimal_places=2)
    moisture_content = models.DecimalField('初始含水率(%)', max_digits=5, decimal_places=2, null=True, blank=True)
    piece_count = models.IntegerField('根数/件数', null=True, blank=True)
    average_diameter = models.DecimalField('平均直径(cm)', max_digits=5, decimal_places=1, null=True, blank=True)
    average_length = models.DecimalField('平均长度(cm)', max_digits=6, decimal_places=1, null=True, blank=True)
    storage_location = models.CharField('存放位置', max_length=100, blank=True)
    quality_grade = models.CharField('质检等级', max_length=20, choices=QUALITY_GRADE, null=True, blank=True)
    inspection_notes = models.TextField('质检说明', blank=True)
    inspector = models.CharField('检验员', max_length=50, blank=True)
    inspection_date = models.DateField('检验日期', null=True, blank=True)
    storage_status = models.CharField('库存状态', max_length=20, choices=STORAGE_STATUS, default='in_stock')
    expected_shelf_life = models.IntegerField('保质期(天)', default=90)
    unit_price = models.DecimalField('单价(元/kg)', max_digits=8, decimal_places=2, null=True, blank=True)
    total_cost = models.DecimalField('总成本(元)', max_digits=12, decimal_places=2, null=True, blank=True)
    remarks = models.TextField('备注', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '原料批次'
        verbose_name_plural = verbose_name
        ordering = ['-arrival_date']

    def __str__(self):
        return f'{self.batch_no} - {self.get_wood_species_display()}'

    @property
    def used_weight(self):
        return self.issues.filter(status='completed').aggregate(
            total=Sum('weight')
        )['total'] or 0

    @property
    def remaining_weight(self):
        return float(self.total_weight) - float(self.used_weight)

    @property
    def storage_days(self):
        today = timezone.now().date()
        return (today - self.arrival_date).days

    @property
    def is_expired(self):
        return self.storage_days > self.expected_shelf_life

    @property
    def days_until_expiry(self):
        return self.expected_shelf_life - self.storage_days

    @property
    def used_ratio(self):
        if self.total_weight > 0:
            return round(float(self.used_weight) / float(self.total_weight) * 100, 2)
        return 0

    def save(self, *args, **kwargs):
        if self.total_weight and self.unit_price:
            self.total_cost = round(float(self.total_weight) * float(self.unit_price), 2)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.total_weight <= 0:
            raise ValidationError({'total_weight': '入库重量必须大于0'})
        if self.moisture_content is not None:
            if self.moisture_content < 0 or self.moisture_content > 100:
                raise ValidationError({'moisture_content': '含水率必须在0-100%范围内'})
        if self.piece_count is not None and self.piece_count < 0:
            raise ValidationError({'piece_count': '根数不能为负数'})
        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({'unit_price': '单价不能为负数'})
        if self.expected_shelf_life <= 0:
            raise ValidationError({'expected_shelf_life': '保质期必须大于0天'})


class MoistureTest(models.Model):
    material_batch = models.ForeignKey(RawMaterialBatch, on_delete=models.CASCADE, verbose_name='原料批次', related_name='moisture_tests')
    test_date = models.DateTimeField('检测时间', default=timezone.now)
    moisture_content = models.DecimalField('检测含水率(%)', max_digits=5, decimal_places=2)
    test_method = models.CharField('检测方法', max_length=100, default='快速水分测定仪')
    sample_location = models.CharField('取样位置', max_length=100, blank=True)
    tester = models.CharField('检测人', max_length=50, blank=True)
    notes = models.CharField('备注', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '含水率检测记录'
        verbose_name_plural = verbose_name
        ordering = ['-test_date']

    def __str__(self):
        return f'{self.material_batch.batch_no} - {self.moisture_content}% @ {self.test_date}'

    def clean(self):
        super().clean()
        if self.moisture_content < 0 or self.moisture_content > 100:
            raise ValidationError({'moisture_content': '含水率必须在0-100%范围内'})


class StockLedger(models.Model):
    TRANSACTION_TYPE = (
        ('stock_in', '入库'),
        ('stock_out', '领料出库'),
        ('loss', '损耗'),
        ('adjust', '库存调整'),
        ('return', '退库'),
    )

    material_batch = models.ForeignKey(RawMaterialBatch, on_delete=models.CASCADE, verbose_name='原料批次', related_name='ledger_entries')
    transaction_type = models.CharField('交易类型', max_length=20, choices=TRANSACTION_TYPE)
    transaction_date = models.DateTimeField('交易时间', default=timezone.now)
    quantity = models.DecimalField('数量(kg)', max_digits=10, decimal_places=2)
    balance_after = models.DecimalField('结存数量(kg)', max_digits=10, decimal_places=2)
    reference_no = models.CharField('关联单号', max_length=50, blank=True)
    operator = models.CharField('操作人', max_length=50, blank=True)
    notes = models.CharField('备注', max_length=300, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '库存台账'
        verbose_name_plural = verbose_name
        ordering = ['-transaction_date']

    def __str__(self):
        return f'{self.material_batch.batch_no} - {self.get_transaction_type_display()} {self.quantity}kg'


class MaterialIssue(models.Model):
    ISSUE_STATUS = (
        ('pending', '待出库'),
        ('completed', '已出库'),
        ('cancelled', '已取消'),
    )

    issue_no = models.CharField('领料单号', max_length=50, unique=True)
    material_batch = models.ForeignKey(RawMaterialBatch, on_delete=models.PROTECT, verbose_name='原料批次', related_name='issues')
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, verbose_name='烧炭批次', related_name='material_issues', null=True, blank=True)
    weight = models.DecimalField('领用重量(kg)', max_digits=10, decimal_places=2)
    issue_date = models.DateTimeField('领料日期', default=timezone.now)
    requester = models.CharField('领料人', max_length=50, blank=True)
    stock_keeper = models.CharField('发料人', max_length=50, blank=True)
    status = models.CharField('状态', max_length=20, choices=ISSUE_STATUS, default='pending')
    notes = models.TextField('备注', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '领料出库'
        verbose_name_plural = verbose_name
        ordering = ['-issue_date']

    def __str__(self):
        return f'{self.issue_no} - {self.material_batch.batch_no} {self.weight}kg'

    def clean(self):
        super().clean()
        if self.weight <= 0:
            raise ValidationError({'weight': '领用重量必须大于0'})
        if self.status == 'completed':
            available = self.material_batch.remaining_weight
            if float(self.weight) > available:
                raise ValidationError({'weight': f'领用重量不能超过当前库存量({available}kg)'})


class MaterialLoss(models.Model):
    LOSS_TYPE = (
        ('natural', '自然损耗'),
        ('spoilage', '变质损坏'),
        ('damage', '人为损坏'),
        ('theft', '失窃'),
        ('other', '其他'),
    )

    loss_no = models.CharField('损耗单号', max_length=50, unique=True)
    material_batch = models.ForeignKey(RawMaterialBatch, on_delete=models.PROTECT, verbose_name='原料批次', related_name='losses')
    loss_type = models.CharField('损耗类型', max_length=20, choices=LOSS_TYPE)
    weight = models.DecimalField('损耗重量(kg)', max_digits=10, decimal_places=2)
    loss_date = models.DateField('损耗日期', default=timezone.now)
    discovered_by = models.CharField('发现人', max_length=50, blank=True)
    description = models.TextField('损耗原因说明')
    handled = models.BooleanField('是否已处理', default=False)
    handler = models.CharField('处理人', max_length=50, blank=True)
    handling_method = models.TextField('处理方式', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '损耗记录'
        verbose_name_plural = verbose_name
        ordering = ['-loss_date']

    def __str__(self):
        return f'{self.loss_no} - {self.get_loss_type_display()} {self.weight}kg'

    def clean(self):
        super().clean()
        if self.weight <= 0:
            raise ValidationError({'weight': '损耗重量必须大于0'})


class StockWarning(models.Model):
    WARNING_TYPE = (
        ('low_stock', '低库存预警'),
        ('expiring', '临期预警'),
        ('expired', '超期存放预警'),
    )

    WARNING_LEVEL = (
        ('info', '提示'),
        ('warning', '警告'),
        ('critical', '严重'),
    )

    material_batch = models.ForeignKey(RawMaterialBatch, on_delete=models.CASCADE, verbose_name='原料批次', related_name='warnings')
    warning_type = models.CharField('预警类型', max_length=20, choices=WARNING_TYPE)
    warning_level = models.CharField('预警级别', max_length=20, choices=WARNING_LEVEL, default='warning')
    warning_date = models.DateTimeField('预警时间', default=timezone.now)
    message = models.TextField('预警信息')
    current_stock = models.DecimalField('当前库存(kg)', max_digits=10, decimal_places=2)
    threshold = models.DecimalField('预警阈值', max_digits=10, decimal_places=2, null=True, blank=True)
    is_resolved = models.BooleanField('是否已处理', default=False)
    resolved_by = models.CharField('处理人', max_length=50, blank=True)
    resolved_date = models.DateTimeField('处理时间', null=True, blank=True)
    resolution_notes = models.TextField('处理说明', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '库存预警'
        verbose_name_plural = verbose_name
        ordering = ['-warning_date']

    def __str__(self):
        return f'{self.material_batch.batch_no} - {self.get_warning_type_display()}'
