from django.contrib import admin
from .models import (
    Kiln, Batch, TemperatureRecord, DamperRecord,
    SmokeStage, KilnRating, ProcessWarning
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
