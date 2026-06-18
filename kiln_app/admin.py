from django.contrib import admin
from .models import (
    Kiln, Batch, TemperatureRecord, DamperRecord,
    SmokeStage, KilnRating, ProcessWarning,
    Supplier, RawMaterialBatch, MoistureTest,
    StockLedger, MaterialIssue, MaterialLoss, StockWarning
)


class TemperatureRecordInline(admin.TabularInline):
    model = TemperatureRecord
    extra = 0
    fields = ('record_time', 'temperature', 'position', 'notes')


class DamperRecordInline(admin.TabularInline):
    model = DamperRecord
    extra = 0
    fields = ('record_time', 'damper_opening', 'damper_name', 'reason')


class SmokeStageInline(admin.TabularInline):
    model = SmokeStage
    extra = 0
    fields = ('record_time', 'stage', 'smoke_density', 'is_normal', 'warning_message')
    readonly_fields = ('is_normal', 'warning_message')


class KilnRatingInline(admin.StackedInline):
    model = KilnRating
    can_delete = False
    fieldsets = (
        (None, {
            'fields': (
                ('grade', 'total_score'),
                ('appearance_score', 'hardness_score'),
                ('moisture_score', 'ash_content_score'),
                ('evaluator', 'evaluation_date'),
                'remarks',
            )
        }),
    )
    readonly_fields = ('total_score',)


@admin.register(Kiln)
class KilnAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'capacity', 'status', 'build_date', 'batch_count')
    list_filter = ('status',)
    search_fields = ('name', 'location')
    list_per_page = 20

    def batch_count(self, obj):
        return obj.batch_set.count()
    batch_count.short_description = '关联批次'


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = (
        'batch_no', 'kiln', 'material_type', 'material_weight',
        'charcoal_weight', 'yield_rate_display', 'ignition_date',
        'finish_date', 'current_stage', 'rating_grade'
    )
    list_filter = ('material_type', 'kiln')
    search_fields = ('batch_no', 'operator', 'notes')
    date_hierarchy = 'ignition_date'
    list_per_page = 20
    inlines = [TemperatureRecordInline, DamperRecordInline, SmokeStageInline, KilnRatingInline]

    def yield_rate_display(self, obj):
        if obj.yield_rate:
            rate = obj.yield_rate
            color = 'green' if rate >= 25 else 'orange' if rate >= 18 else 'red'
            return f'<span style="color:{color};font-weight:bold;">{rate}%</span>'
        return '-'
    yield_rate_display.short_description = '成炭率'
    yield_rate_display.allow_tags = True

    def rating_grade(self, obj):
        if hasattr(obj, 'rating'):
            return obj.rating.get_grade_display()
        return '未评'
    rating_grade.short_description = '评级'


@admin.register(TemperatureRecord)
class TemperatureRecordAdmin(admin.ModelAdmin):
    list_display = ('batch', 'record_time', 'temperature', 'position')
    list_filter = ('position',)
    search_fields = ('batch__batch_no', 'notes')
    date_hierarchy = 'record_time'
    list_per_page = 50


@admin.register(DamperRecord)
class DamperRecordAdmin(admin.ModelAdmin):
    list_display = ('batch', 'record_time', 'damper_opening', 'damper_name')
    list_filter = ('damper_name',)
    search_fields = ('batch__batch_no', 'reason')
    date_hierarchy = 'record_time'
    list_per_page = 50


@admin.register(SmokeStage)
class SmokeStageAdmin(admin.ModelAdmin):
    list_display = ('batch', 'record_time', 'stage_display', 'is_normal', 'smoke_density')
    list_filter = ('stage', 'is_normal')
    search_fields = ('batch__batch_no', 'warning_message', 'notes')
    date_hierarchy = 'record_time'
    list_per_page = 50

    def stage_display(self, obj):
        if not obj.is_normal:
            return f'⚠ {obj.get_stage_display()}'
        return obj.get_stage_display()
    stage_display.short_description = '烟色阶段'


@admin.register(KilnRating)
class KilnRatingAdmin(admin.ModelAdmin):
    list_display = (
        'batch', 'grade', 'total_score', 'appearance_score',
        'hardness_score', 'moisture_score', 'ash_content_score',
        'evaluator', 'evaluation_date'
    )
    list_filter = ('grade',)
    search_fields = ('batch__batch_no', 'evaluator', 'remarks')
    date_hierarchy = 'evaluation_date'
    list_per_page = 30
    readonly_fields = ('total_score',)


@admin.register(ProcessWarning)
class ProcessWarningAdmin(admin.ModelAdmin):
    list_display = (
        'batch', 'warning_time', 'warning_type', 'level',
        'detected_stage', 'temperature', 'damper_opening', 'is_resolved'
    )
    list_filter = ('warning_type', 'level', 'is_resolved')
    search_fields = ('batch__batch_no', 'message')
    date_hierarchy = 'warning_time'
    list_per_page = 30


class MoistureTestInline(admin.TabularInline):
    model = MoistureTest
    extra = 0
    fields = ('test_date', 'moisture_content', 'test_method', 'tester')


class MaterialIssueInline(admin.TabularInline):
    model = MaterialIssue
    extra = 0
    fields = ('issue_no', 'weight', 'issue_date', 'requester', 'status')


class MaterialLossInline(admin.TabularInline):
    model = MaterialLoss
    extra = 0
    fields = ('loss_no', 'loss_type', 'weight', 'loss_date', 'handled')


class StockLedgerInline(admin.TabularInline):
    model = StockLedger
    extra = 0
    fields = ('transaction_type', 'transaction_date', 'quantity', 'balance_after', 'operator')
    readonly_fields = ('transaction_type', 'transaction_date', 'quantity', 'balance_after', 'operator')


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'phone', 'wood_species', 'status', 'credit_rating', 'batch_count')
    list_filter = ('status',)
    search_fields = ('name', 'contact_person', 'phone', 'wood_species')
    list_per_page = 20

    def batch_count(self, obj):
        return obj.material_batches.count()
    batch_count.short_description = '原料批次'


@admin.register(RawMaterialBatch)
class RawMaterialBatchAdmin(admin.ModelAdmin):
    list_display = (
        'batch_no', 'supplier', 'wood_species_display', 'total_weight',
        'remaining_weight_display', 'moisture_content', 'arrival_date',
        'storage_days', 'status_display', 'warning_display'
    )
    list_filter = ('wood_species', 'quality_grade', 'storage_status', 'supplier')
    search_fields = ('batch_no', 'storage_location', 'remarks')
    date_hierarchy = 'arrival_date'
    list_per_page = 20
    inlines = [MoistureTestInline, MaterialIssueInline, MaterialLossInline, StockLedgerInline]

    def wood_species_display(self, obj):
        return obj.get_wood_species_display()
    wood_species_display.short_description = '木材种类'

    def remaining_weight_display(self, obj):
        remaining = obj.remaining_weight
        ratio = obj.used_ratio
        color = 'red' if remaining < 100 else 'orange' if remaining < 500 else 'green'
        return f'<span style="color:{color};font-weight:bold;">{remaining}kg ({100-ratio}%)</span>'
    remaining_weight_display.short_description = '剩余库存'
    remaining_weight_display.allow_tags = True

    def status_display(self, obj):
        status_map = {
            'in_stock': 'bg-success',
            'partial_used': 'bg-info',
            'used_up': 'bg-secondary',
            'discarded': 'bg-danger',
        }
        return f'<span class="badge {status_map.get(obj.storage_status, "bg-secondary")}">{obj.get_storage_status_display()}</span>'
    status_display.short_description = '库存状态'
    status_display.allow_tags = True

    def warning_display(self, obj):
        warnings = []
        if obj.is_expired:
            warnings.append('<span class="badge bg-danger">已超期</span>')
        elif obj.days_until_expiry <= 7:
            warnings.append(f'<span class="badge bg-warning text-dark">临期{obj.days_until_expiry}天</span>')
        if obj.remaining_weight < 100:
            warnings.append('<span class="badge bg-warning text-dark">低库存</span>')
        return ' '.join(warnings) if warnings else '-'
    warning_display.short_description = '预警'
    warning_display.allow_tags = True


@admin.register(MaterialIssue)
class MaterialIssueAdmin(admin.ModelAdmin):
    list_display = (
        'issue_no', 'material_batch', 'batch', 'weight',
        'issue_date', 'requester', 'status'
    )
    list_filter = ('status',)
    search_fields = ('issue_no', 'requester', 'material_batch__batch_no', 'batch__batch_no')
    date_hierarchy = 'issue_date'
    list_per_page = 30


@admin.register(MaterialLoss)
class MaterialLossAdmin(admin.ModelAdmin):
    list_display = (
        'loss_no', 'material_batch', 'loss_type_display', 'weight',
        'loss_date', 'discovered_by', 'handled'
    )
    list_filter = ('loss_type', 'handled')
    search_fields = ('loss_no', 'description', 'material_batch__batch_no')
    date_hierarchy = 'loss_date'
    list_per_page = 30

    def loss_type_display(self, obj):
        return obj.get_loss_type_display()
    loss_type_display.short_description = '损耗类型'


@admin.register(StockLedger)
class StockLedgerAdmin(admin.ModelAdmin):
    list_display = (
        'material_batch', 'transaction_type_display', 'transaction_date',
        'quantity', 'balance_after', 'operator', 'reference_no'
    )
    list_filter = ('transaction_type',)
    search_fields = ('material_batch__batch_no', 'reference_no', 'operator')
    date_hierarchy = 'transaction_date'
    list_per_page = 50
    readonly_fields = ('material_batch', 'transaction_type', 'transaction_date', 'quantity', 'balance_after', 'operator', 'reference_no', 'notes')

    def transaction_type_display(self, obj):
        return obj.get_transaction_type_display()
    transaction_type_display.short_description = '交易类型'


@admin.register(StockWarning)
class StockWarningAdmin(admin.ModelAdmin):
    list_display = (
        'material_batch', 'warning_type_display', 'warning_level_display',
        'warning_date', 'current_stock', 'is_resolved'
    )
    list_filter = ('warning_type', 'warning_level', 'is_resolved')
    search_fields = ('material_batch__batch_no', 'message')
    date_hierarchy = 'warning_date'
    list_per_page = 30

    def warning_type_display(self, obj):
        return obj.get_warning_type_display()
    warning_type_display.short_description = '预警类型'

    def warning_level_display(self, obj):
        level_map = {
            'info': 'bg-info',
            'warning': 'bg-warning text-dark',
            'critical': 'bg-danger',
        }
        return f'<span class="badge {level_map.get(obj.warning_level, "bg-secondary")}">{obj.get_warning_level_display()}</span>'
    warning_level_display.short_description = '预警级别'
    warning_level_display.allow_tags = True


@admin.register(MoistureTest)
class MoistureTestAdmin(admin.ModelAdmin):
    list_display = (
        'material_batch', 'test_date', 'moisture_content',
        'test_method', 'tester'
    )
    list_filter = ('test_method',)
    search_fields = ('material_batch__batch_no', 'tester')
    date_hierarchy = 'test_date'
    list_per_page = 50
