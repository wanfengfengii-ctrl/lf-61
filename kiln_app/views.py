import json
import csv
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from datetime import timedelta

from .models import (
    Kiln, Batch, TemperatureRecord, DamperRecord,
    SmokeStage, KilnRating, ProcessWarning,
    Supplier, RawMaterialBatch, MoistureTest,
    StockLedger, MaterialIssue, MaterialLoss, StockWarning,
    PurchasePlan, PurchaseOrder, PurchaseArrival, PurchaseCostSplit,
    BatchCost, BatchCostItem, CostWarning, SupplierPriceHistory, StockCostLedger,
    FiringRecipe, RecipeStage, RecipeDeviationRecord, RecipeStatistics
)
from .forms import (
    KilnForm, BatchForm, TemperatureRecordForm,
    DamperRecordForm, SmokeStageForm, KilnRatingForm,
    SupplierForm, RawMaterialBatchForm, MoistureTestForm,
    MaterialIssueForm, MaterialLossForm, StockWarningResolveForm,
    PurchasePlanForm, PurchasePlanApprovalForm, PurchaseOrderForm,
    PurchaseArrivalForm, PurchaseCostSplitForm, BatchCostForm, BatchCostItemForm,
    CostWarningResolveForm, SupplierPriceHistoryForm,
    FiringRecipeForm, RecipeStageForm, RecipeDeviationResolveForm
)
from .services import (
    generate_warnings, detect_burning_stage,
    check_recipe_deviations, save_recipe_deviations,
    calculate_recipe_statistics, suggest_recipe, get_recipe_comparison_data
)


def dashboard(request):
    total_kilns = Kiln.objects.count()
    active_kilns = Kiln.objects.filter(status='active').count()
    total_batches = Batch.objects.count()
    completed_batches = Batch.objects.filter(finish_date__isnull=False).count()
    ongoing_batches = Batch.objects.filter(finish_date__isnull=True).count()

    recent_batches = Batch.objects.all()[:10]

    avg_yield = Batch.objects.filter(
        charcoal_weight__isnull=False,
        material_weight__gt=0
    ).aggregate(avg=Avg('charcoal_weight'))['avg']

    if avg_yield:
        avg_material = Batch.objects.filter(material_weight__gt=0).aggregate(avg=Avg('material_weight'))['avg']
        avg_yield_rate = round(float(avg_yield) / float(avg_material) * 100, 2) if avg_material else 0
    else:
        avg_yield_rate = 0

    abnormal_smoke_count = SmokeStage.objects.filter(is_normal=False).count()

    context = {
        'total_kilns': total_kilns,
        'active_kilns': active_kilns,
        'total_batches': total_batches,
        'completed_batches': completed_batches,
        'ongoing_batches': ongoing_batches,
        'recent_batches': recent_batches,
        'avg_yield_rate': avg_yield_rate,
        'abnormal_smoke_count': abnormal_smoke_count,
    }
    return render(request, 'kiln_app/dashboard.html', context)


def kiln_list(request):
    kilns = Kiln.objects.all()
    status_filter = request.GET.get('status', '')
    if status_filter:
        kilns = kilns.filter(status=status_filter)
    context = {'kilns': kilns, 'status_filter': status_filter}
    return render(request, 'kiln_app/kiln_list.html', context)


def kiln_create(request):
    if request.method == 'POST':
        form = KilnForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '炭窑档案创建成功！')
            return redirect('kiln_app:kiln_list')
    else:
        form = KilnForm()
    return render(request, 'kiln_app/kiln_form.html', {'form': form, 'action': '创建'})


def kiln_edit(request, pk):
    kiln = get_object_or_404(Kiln, pk=pk)
    if request.method == 'POST':
        form = KilnForm(request.POST, instance=kiln)
        if form.is_valid():
            form.save()
            messages.success(request, '炭窑档案更新成功！')
            return redirect('kiln_app:kiln_list')
    else:
        form = KilnForm(instance=kiln)
    return render(request, 'kiln_app/kiln_form.html', {'form': form, 'action': '编辑', 'kiln': kiln})


def kiln_delete(request, pk):
    kiln = get_object_or_404(Kiln, pk=pk)
    try:
        kiln.delete()
        messages.success(request, '炭窑档案已删除！')
    except Exception:
        messages.error(request, '该炭窑有关联的批次记录，无法删除！')
    return redirect('kiln_app:kiln_list')


def batch_list(request):
    batches = Batch.objects.select_related('kiln', 'rating').all()
    material_filter = request.GET.get('material_type', '')
    kiln_filter = request.GET.get('kiln', '')
    if material_filter:
        batches = batches.filter(material_type=material_filter)
    if kiln_filter:
        batches = batches.filter(kiln_id=kiln_filter)
    kilns = Kiln.objects.all()
    context = {
        'batches': batches,
        'material_filter': material_filter,
        'kiln_filter': kiln_filter,
        'kilns': kilns,
    }
    return render(request, 'kiln_app/batch_list.html', context)


def batch_create(request):
    if request.method == 'POST':
        form = BatchForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '烧炭批次创建成功！')
            return redirect('kiln_app:batch_list')
    else:
        form = BatchForm()
    return render(request, 'kiln_app/batch_form.html', {'form': form, 'action': '创建'})


def batch_edit(request, pk):
    batch = get_object_or_404(Batch, pk=pk)
    if request.method == 'POST':
        form = BatchForm(request.POST, instance=batch)
        if form.is_valid():
            form.save()
            messages.success(request, '烧炭批次更新成功！')
            return redirect('kiln_app:batch_detail', pk=batch.pk)
    else:
        form = BatchForm(instance=batch)
    return render(request, 'kiln_app/batch_form.html', {'form': form, 'action': '编辑', 'batch': batch})


def batch_delete(request, pk):
    batch = get_object_or_404(Batch, pk=pk)
    batch.delete()
    messages.success(request, '烧炭批次已删除！')
    return redirect('kiln_app:batch_list')


def batch_detail(request, pk):
    batch = get_object_or_404(Batch.objects.select_related('kiln', 'rating'), pk=pk)
    temperature_records = batch.temperature_records.order_by('record_time')
    damper_records = batch.damper_records.order_by('record_time')
    smoke_stages = batch.smokestage_set.order_by('record_time')

    detected_stage = detect_burning_stage(batch)
    live_warnings = generate_warnings(batch)
    saved_warnings = batch.process_warnings.order_by('-warning_time')
    all_warnings = list(live_warnings) + [w for w in saved_warnings if w not in live_warnings]
    critical_count = sum(1 for w in all_warnings if w.level == 'critical')
    warning_count = sum(1 for w in all_warnings if w.level == 'warning')
    info_count = sum(1 for w in all_warnings if w.level == 'info')

    def format_time(dt):
        if batch.ignition_date and dt:
            delta = dt - batch.ignition_date
            hours = delta.total_seconds() / 3600
            return round(hours, 2)
        return 0

    temp_labels = []
    temp_data = []
    for rec in temperature_records:
        temp_labels.append(format_time(rec.record_time))
        temp_data.append(float(rec.temperature))

    damper_labels = []
    damper_data = []
    for rec in damper_records:
        damper_labels.append(format_time(rec.record_time))
        damper_data.append(rec.damper_opening)

    smoke_color_map = {
        'drying': 'rgba(200, 200, 200, 0.8)',
        'precarbonization': 'rgba(255, 200, 0, 0.8)',
        'carbonization': 'rgba(100, 200, 255, 0.8)',
        'refining': 'rgba(200, 200, 255, 0.5)',
        'cooling': 'rgba(150, 150, 150, 0.6)',
        'abnormal_heavy_smoke': 'rgba(100, 100, 100, 0.9)',
        'abnormal_no_smoke_early': 'rgba(255, 100, 100, 0.8)',
        'abnormal_black_smoke': 'rgba(0, 0, 0, 0.9)',
    }
    smoke_labels = []
    smoke_colors = []
    smoke_stages_display = []
    smoke_is_normal = []
    smoke_warnings = []
    for stage in smoke_stages:
        smoke_labels.append(format_time(stage.record_time))
        smoke_colors.append(smoke_color_map.get(stage.stage, 'rgba(150, 150, 150, 0.6)'))
        smoke_stages_display.append(stage.get_stage_display())
        smoke_is_normal.append(stage.is_normal)
        smoke_warnings.append(stage.warning_message)

    has_rating = hasattr(batch, 'rating')

    context = {
        'batch': batch,
        'temperature_records': temperature_records,
        'damper_records': damper_records,
        'smoke_stages': smoke_stages,
        'temp_labels_json': json.dumps(temp_labels),
        'temp_data_json': json.dumps(temp_data),
        'damper_labels_json': json.dumps(damper_labels),
        'damper_data_json': json.dumps(damper_data),
        'smoke_labels_json': json.dumps(smoke_labels),
        'smoke_colors_json': json.dumps(smoke_colors),
        'smoke_stages_json': json.dumps(smoke_stages_display),
        'smoke_is_normal_json': json.dumps(smoke_is_normal),
        'smoke_warnings_json': json.dumps(smoke_warnings),
        'has_rating': has_rating,
        'detected_stage': detected_stage,
        'all_warnings': all_warnings,
        'critical_count': critical_count,
        'warning_count': warning_count,
        'info_count': info_count,
    }
    return render(request, 'kiln_app/batch_detail.html', context)


def temperature_create(request, batch_pk):
    batch = get_object_or_404(Batch, pk=batch_pk)
    if request.method == 'POST':
        form = TemperatureRecordForm(request.POST, batch=batch)
        if form.is_valid():
            rec = form.save(commit=False)
            rec.batch = batch
            rec.save()
            messages.success(request, '温度记录添加成功！')
            return redirect('kiln_app:batch_detail', pk=batch.pk)
    else:
        form = TemperatureRecordForm(batch=batch)
    return render(request, 'kiln_app/record_form.html', {
        'form': form, 'title': '添加温度记录', 'batch': batch, 'record_type': 'temperature'
    })


def temperature_edit(request, pk):
    rec = get_object_or_404(TemperatureRecord, pk=pk)
    batch = rec.batch
    if request.method == 'POST':
        form = TemperatureRecordForm(request.POST, instance=rec, batch=batch)
        if form.is_valid():
            form.save()
            messages.success(request, '温度记录更新成功！')
            return redirect('kiln_app:batch_detail', pk=batch.pk)
    else:
        form = TemperatureRecordForm(instance=rec, batch=batch)
    return render(request, 'kiln_app/record_form.html', {
        'form': form, 'title': '编辑温度记录', 'batch': batch, 'record_type': 'temperature'
    })


def temperature_delete(request, pk):
    rec = get_object_or_404(TemperatureRecord, pk=pk)
    batch_pk = rec.batch.pk
    rec.delete()
    messages.success(request, '温度记录已删除！')
    return redirect('kiln_app:batch_detail', pk=batch_pk)


def damper_create(request, batch_pk):
    batch = get_object_or_404(Batch, pk=batch_pk)
    if request.method == 'POST':
        form = DamperRecordForm(request.POST, batch=batch)
        if form.is_valid():
            rec = form.save(commit=False)
            rec.batch = batch
            rec.save()
            messages.success(request, '风门调整记录添加成功！')
            return redirect('kiln_app:batch_detail', pk=batch.pk)
    else:
        form = DamperRecordForm(batch=batch)
    return render(request, 'kiln_app/record_form.html', {
        'form': form, 'title': '添加风门调整记录', 'batch': batch, 'record_type': 'damper'
    })


def damper_edit(request, pk):
    rec = get_object_or_404(DamperRecord, pk=pk)
    batch = rec.batch
    if request.method == 'POST':
        form = DamperRecordForm(request.POST, instance=rec, batch=batch)
        if form.is_valid():
            form.save()
            messages.success(request, '风门调整记录更新成功！')
            return redirect('kiln_app:batch_detail', pk=batch.pk)
    else:
        form = DamperRecordForm(instance=rec, batch=batch)
    return render(request, 'kiln_app/record_form.html', {
        'form': form, 'title': '编辑风门调整记录', 'batch': batch, 'record_type': 'damper'
    })


def damper_delete(request, pk):
    rec = get_object_or_404(DamperRecord, pk=pk)
    batch_pk = rec.batch.pk
    rec.delete()
    messages.success(request, '风门调整记录已删除！')
    return redirect('kiln_app:batch_detail', pk=batch_pk)


def smoke_create(request, batch_pk):
    batch = get_object_or_404(Batch, pk=batch_pk)
    if request.method == 'POST':
        form = SmokeStageForm(request.POST, batch=batch)
        if form.is_valid():
            rec = form.save(commit=False)
            rec.batch = batch
            rec.save()
            if not rec.is_normal:
                messages.warning(request, f'烟色阶段异常：{rec.warning_message}')
            else:
                messages.success(request, '烟色阶段记录添加成功！')
            return redirect('kiln_app:batch_detail', pk=batch.pk)
    else:
        form = SmokeStageForm(batch=batch)
    return render(request, 'kiln_app/record_form.html', {
        'form': form, 'title': '添加烟色阶段记录', 'batch': batch, 'record_type': 'smoke'
    })


def smoke_edit(request, pk):
    rec = get_object_or_404(SmokeStage, pk=pk)
    batch = rec.batch
    if request.method == 'POST':
        form = SmokeStageForm(request.POST, instance=rec, batch=batch)
        if form.is_valid():
            form.save()
            if not rec.is_normal:
                messages.warning(request, f'烟色阶段异常：{rec.warning_message}')
            else:
                messages.success(request, '烟色阶段记录更新成功！')
            return redirect('kiln_app:batch_detail', pk=batch.pk)
    else:
        form = SmokeStageForm(instance=rec, batch=batch)
    return render(request, 'kiln_app/record_form.html', {
        'form': form, 'title': '编辑烟色阶段记录', 'batch': batch, 'record_type': 'smoke'
    })


def smoke_delete(request, pk):
    rec = get_object_or_404(SmokeStage, pk=pk)
    batch_pk = rec.batch.pk
    rec.delete()
    messages.success(request, '烟色阶段记录已删除！')
    return redirect('kiln_app:batch_detail', pk=batch_pk)


def rating_create(request, batch_pk):
    batch = get_object_or_404(Batch, pk=batch_pk)
    if hasattr(batch, 'rating'):
        messages.warning(request, '该批次已存在评级，已跳转到编辑页面')
        return redirect('kiln_app:rating_edit', batch_pk=batch.pk)
    if request.method == 'POST':
        form = KilnRatingForm(request.POST)
        if form.is_valid():
            rating = form.save(commit=False)
            rating.batch = batch
            rating.save()
            messages.success(request, '出窑评级完成！')
            return redirect('kiln_app:batch_detail', pk=batch.pk)
    else:
        form = KilnRatingForm()
    return render(request, 'kiln_app/rating_form.html', {
        'form': form, 'batch': batch, 'action': '创建'
    })


def rating_edit(request, batch_pk):
    batch = get_object_or_404(Batch, pk=batch_pk)
    rating = get_object_or_404(KilnRating, batch=batch)
    if request.method == 'POST':
        form = KilnRatingForm(request.POST, instance=rating)
        if form.is_valid():
            form.save()
            messages.success(request, '出窑评级更新成功！')
            return redirect('kiln_app:batch_detail', pk=batch.pk)
    else:
        form = KilnRatingForm(instance=rating)
    return render(request, 'kiln_app/rating_form.html', {
        'form': form, 'batch': batch, 'action': '编辑'
    })


def yield_comparison(request):
    completed_batches = Batch.objects.filter(
        charcoal_weight__isnull=False,
        material_weight__gt=0,
        finish_date__isnull=False
    ).select_related('kiln', 'rating').order_by('-finish_date')

    batch_ids = request.GET.getlist('batch_ids')
    compare_batches = completed_batches
    if batch_ids:
        compare_batches = completed_batches.filter(pk__in=batch_ids)

    labels = []
    yield_data = []
    duration_data = []
    colors = []
    color_palette = [
        'rgba(54, 162, 235, 0.8)',
        'rgba(255, 99, 132, 0.8)',
        'rgba(255, 206, 86, 0.8)',
        'rgba(75, 192, 192, 0.8)',
        'rgba(153, 102, 255, 0.8)',
        'rgba(255, 159, 64, 0.8)',
        'rgba(199, 199, 199, 0.8)',
        'rgba(83, 102, 255, 0.8)',
    ]

    for i, batch in enumerate(compare_batches):
        labels.append(batch.batch_no)
        rate = round(float(batch.charcoal_weight) / float(batch.material_weight) * 100, 2)
        yield_data.append(rate)
        duration_data.append(batch.duration_hours or 0)
        colors.append(color_palette[i % len(color_palette)])

    stats = {
        'count': len(compare_batches),
        'avg_yield': round(sum(yield_data) / len(yield_data), 2) if yield_data else 0,
        'max_yield': max(yield_data) if yield_data else 0,
        'min_yield': min(yield_data) if yield_data else 0,
    }

    context = {
        'all_batches': completed_batches,
        'compare_batches': compare_batches,
        'selected_ids': batch_ids,
        'labels_json': json.dumps(labels),
        'yield_data_json': json.dumps(yield_data),
        'duration_data_json': json.dumps(duration_data),
        'colors_json': json.dumps(colors),
        'stats': stats,
    }
    return render(request, 'kiln_app/yield_comparison.html', context)


def batch_review(request, pk):
    batch = get_object_or_404(Batch.objects.select_related('kiln', 'rating'), pk=pk)
    temp_records = batch.temperature_records.order_by('record_time')
    damper_records = batch.damper_records.order_by('record_time')
    smoke_stages = batch.smokestage_set.order_by('record_time')
    warnings = batch.process_warnings.order_by('warning_time')
    detected_stage = detect_burning_stage(batch)
    live_warnings = generate_warnings(batch)

    def fmt_hours(dt):
        if batch.ignition_date and dt:
            return round((dt - batch.ignition_date).total_seconds() / 3600, 2)
        return 0

    timeline_events = []

    for rec in temp_records:
        timeline_events.append({
            'type': 'temperature',
            'time': rec.record_time,
            'hours': fmt_hours(rec.record_time),
            'value': f'{rec.temperature}℃',
            'detail': rec.position,
            'icon': 'bi-thermometer-half',
            'color': 'danger',
        })

    for rec in damper_records:
        timeline_events.append({
            'type': 'damper',
            'time': rec.record_time,
            'hours': fmt_hours(rec.record_time),
            'value': f'{rec.damper_opening}%',
            'detail': f'{rec.damper_name}{(" - " + rec.reason) if rec.reason else ""}',
            'icon': 'bi-sliders',
            'color': 'success',
        })

    for stage in smoke_stages:
        timeline_events.append({
            'type': 'smoke',
            'time': stage.record_time,
            'hours': fmt_hours(stage.record_time),
            'value': stage.get_stage_display(),
            'detail': f'浓密度: {stage.smoke_density or "-"}',
            'icon': 'bi-cloud-fog2',
            'color': 'danger' if not stage.is_normal else 'secondary',
            'is_abnormal': not stage.is_normal,
            'warning_msg': stage.warning_message if not stage.is_normal else '',
        })

    for w in list(warnings) + live_warnings:
        timeline_events.append({
            'type': 'warning',
            'time': w.warning_time,
            'hours': fmt_hours(w.warning_time),
            'value': w.get_level_display(),
            'detail': w.message,
            'icon': 'bi-exclamation-triangle-fill',
            'color': 'danger' if w.level == 'critical' else 'warning',
        })

    timeline_events.sort(key=lambda e: e['time'])

    temp_labels = [fmt_hours(r.record_time) for r in temp_records]
    temp_data = [float(r.temperature) for r in temp_records]
    damper_labels = [fmt_hours(r.record_time) for r in damper_records]
    damper_data = [r.damper_opening for r in damper_records]

    smoke_color_map = {
        'drying': 'rgba(200, 200, 200, 0.8)',
        'precarbonization': 'rgba(255, 200, 0, 0.8)',
        'carbonization': 'rgba(100, 200, 255, 0.8)',
        'refining': 'rgba(200, 200, 255, 0.5)',
        'cooling': 'rgba(150, 150, 150, 0.6)',
        'abnormal_heavy_smoke': 'rgba(100, 100, 100, 0.9)',
        'abnormal_no_smoke_early': 'rgba(255, 100, 100, 0.8)',
        'abnormal_black_smoke': 'rgba(0, 0, 0, 0.9)',
    }
    smoke_labels = [fmt_hours(s.record_time) for s in smoke_stages]
    smoke_colors = [smoke_color_map.get(s.stage, 'rgba(150,150,150,0.6)') for s in smoke_stages]
    smoke_display = [s.get_stage_display() for s in smoke_stages]

    abnormal_smoke_count = sum(1 for s in smoke_stages if not s.is_normal)
    warning_count = len(live_warnings) + warnings.count()

    has_rating = hasattr(batch, 'rating')

    context = {
        'batch': batch,
        'timeline_events': timeline_events,
        'detected_stage': detected_stage,
        'abnormal_smoke_count': abnormal_smoke_count,
        'warning_count': warning_count,
        'has_rating': has_rating,
        'temp_labels_json': json.dumps(temp_labels),
        'temp_data_json': json.dumps(temp_data),
        'damper_labels_json': json.dumps(damper_labels),
        'damper_data_json': json.dumps(damper_data),
        'smoke_labels_json': json.dumps(smoke_labels),
        'smoke_colors_json': json.dumps(smoke_colors),
        'smoke_display_json': json.dumps(smoke_display),
    }
    return render(request, 'kiln_app/batch_review.html', context)


def batch_analysis(request):
    batches = Batch.objects.select_related('kiln', 'rating').filter(
        finish_date__isnull=False
    ).order_by('-finish_date')

    kiln_filter = request.GET.get('kiln', '')
    material_filter = request.GET.get('material_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if kiln_filter:
        batches = batches.filter(kiln_id=kiln_filter)
    if material_filter:
        batches = batches.filter(material_type=material_filter)
    if date_from:
        batches = batches.filter(ignition_date__date__gte=date_from)
    if date_to:
        batches = batches.filter(ignition_date__date__lte=date_to)

    kilns = Kiln.objects.all()

    analysis_data = []
    for batch in batches:
        abnormal_count = SmokeStage.objects.filter(batch=batch, is_normal=False).count()
        warning_count = ProcessWarning.objects.filter(batch=batch).count()
        has_rating = hasattr(batch, 'rating')
        analysis_data.append({
            'batch': batch,
            'abnormal_count': abnormal_count,
            'warning_count': warning_count,
            'has_rating': has_rating,
        })

    labels = []
    yield_data = []
    duration_data = []
    abnormal_data = []
    grade_data = []
    color_palette = [
        'rgba(54, 162, 235, 0.8)', 'rgba(255, 99, 132, 0.8)',
        'rgba(255, 206, 86, 0.8)', 'rgba(75, 192, 192, 0.8)',
        'rgba(153, 102, 255, 0.8)', 'rgba(255, 159, 64, 0.8)',
        'rgba(199, 199, 199, 0.8)', 'rgba(83, 102, 255, 0.8)',
    ]
    colors = []

    grade_score_map = {'excellent': 5, 'good': 4, 'medium': 3, 'poor': 2, 'reject': 1}

    for i, item in enumerate(analysis_data):
        batch = item['batch']
        labels.append(batch.batch_no)
        yield_data.append(batch.yield_rate or 0)
        duration_data.append(batch.duration_hours or 0)
        abnormal_data.append(item['abnormal_count'] + item['warning_count'])
        if item['has_rating']:
            grade_data.append(grade_score_map.get(batch.rating.grade, 0))
        else:
            grade_data.append(0)
        colors.append(color_palette[i % len(color_palette)])

    avg_yield = round(sum(yield_data) / len(yield_data), 2) if yield_data else 0
    avg_duration = round(sum(duration_data) / len(duration_data), 2) if duration_data else 0
    total_abnormal = sum(abnormal_data)

    by_kiln = {}
    for item in analysis_data:
        b = item['batch']
        kname = b.kiln.name
        if kname not in by_kiln:
            by_kiln[kname] = {'yield_rates': [], 'durations': [], 'abnormals': []}
        by_kiln[kname]['yield_rates'].append(b.yield_rate or 0)
        by_kiln[kname]['durations'].append(b.duration_hours or 0)
        by_kiln[kname]['abnormals'].append(item['abnormal_count'] + item['warning_count'])

    by_material = {}
    material_display = dict(Batch.MATERIAL_TYPE)
    for item in analysis_data:
        b = item['batch']
        mname = material_display.get(b.material_type, b.material_type)
        if mname not in by_material:
            by_material[mname] = {'yield_rates': [], 'durations': [], 'abnormals': []}
        by_material[mname]['yield_rates'].append(b.yield_rate or 0)
        by_material[mname]['durations'].append(b.duration_hours or 0)
        by_material[mname]['abnormals'].append(item['abnormal_count'] + item['warning_count'])

    kiln_labels = list(by_kiln.keys())
    kiln_yield = [round(sum(v['yield_rates']) / len(v['yield_rates']), 2) for v in by_kiln.values()]
    kiln_duration = [round(sum(v['durations']) / len(v['durations']), 2) for v in by_kiln.values()]
    kiln_abnormals = [sum(v['abnormals']) for v in by_kiln.values()]

    material_labels = list(by_material.keys())
    material_yield = [round(sum(v['yield_rates']) / len(v['yield_rates']), 2) for v in by_material.values()]
    material_duration = [round(sum(v['durations']) / len(v['durations']), 2) for v in by_material.values()]
    material_abnormals = [sum(v['abnormals']) for v in by_material.values()]

    context = {
        'analysis_data': analysis_data,
        'kilns': kilns,
        'kiln_filter': kiln_filter,
        'material_filter': material_filter,
        'date_from': date_from,
        'date_to': date_to,
        'material_types': Batch.MATERIAL_TYPE,
        'avg_yield': avg_yield,
        'avg_duration': avg_duration,
        'total_abnormal': total_abnormal,
        'total_batches': len(analysis_data),
        'labels_json': json.dumps(labels),
        'yield_data_json': json.dumps(yield_data),
        'duration_data_json': json.dumps(duration_data),
        'abnormal_data_json': json.dumps(abnormal_data),
        'grade_data_json': json.dumps(grade_data),
        'colors_json': json.dumps(colors),
        'kiln_labels_json': json.dumps(kiln_labels),
        'kiln_yield_json': json.dumps(kiln_yield),
        'kiln_duration_json': json.dumps(kiln_duration),
        'kiln_abnormals_json': json.dumps(kiln_abnormals),
        'material_labels_json': json.dumps(material_labels),
        'material_yield_json': json.dumps(material_yield),
        'material_duration_json': json.dumps(material_duration),
        'material_abnormals_json': json.dumps(material_abnormals),
    }
    return render(request, 'kiln_app/batch_analysis.html', context)


def batch_export_csv(request):
    batches = Batch.objects.select_related('kiln', 'rating').filter(
        finish_date__isnull=False
    ).order_by('-finish_date')

    kiln_filter = request.GET.get('kiln', '')
    material_filter = request.GET.get('material_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if kiln_filter:
        batches = batches.filter(kiln_id=kiln_filter)
    if material_filter:
        batches = batches.filter(material_type=material_filter)
    if date_from:
        batches = batches.filter(ignition_date__date__gte=date_from)
    if date_to:
        batches = batches.filter(ignition_date__date__lte=date_to)

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="batch_analysis_report.csv"'

    writer = csv.writer(response)
    writer.writerow([
        '批次编号', '炭窑', '原料类型', '原料重量(kg)', '成炭重量(kg)',
        '成炭率(%)', '点火日期', '出窑日期', '烧制时长(h)',
        '异常烟色次数', '预警次数', '评级', '综合评分'
    ])

    grade_display = dict(KilnRating.GRADE_CHOICES)
    material_display = dict(Batch.MATERIAL_TYPE)

    for batch in batches:
        abnormal_count = SmokeStage.objects.filter(batch=batch, is_normal=False).count()
        warning_count = ProcessWarning.objects.filter(batch=batch).count()
        grade = ''
        score = ''
        if hasattr(batch, 'rating'):
            grade = grade_display.get(batch.rating.grade, batch.rating.grade)
            score = str(batch.rating.total_score or '')

        writer.writerow([
            batch.batch_no,
            batch.kiln.name,
            material_display.get(batch.material_type, batch.material_type),
            batch.material_weight,
            batch.charcoal_weight or '',
            batch.yield_rate or '',
            batch.ignition_date.strftime('%Y-%m-%d %H:%M') if batch.ignition_date else '',
            batch.finish_date.strftime('%Y-%m-%d %H:%M') if batch.finish_date else '',
            batch.duration_hours or '',
            abnormal_count,
            warning_count,
            grade,
            score,
        ])

    return response


def generate_stock_warnings():
    now = timezone.now()
    today = now.date()
    low_stock_threshold = 500
    expiring_days = 7

    material_batches = RawMaterialBatch.objects.filter(
        storage_status__in=['in_stock', 'partial_used']
    )

    for batch in material_batches:
        remaining = batch.remaining_weight
        storage_days = batch.storage_days

        if remaining < low_stock_threshold:
            existing = StockWarning.objects.filter(
                material_batch=batch,
                warning_type='low_stock',
                is_resolved=False
            ).first()
            if not existing:
                level = 'critical' if remaining < 100 else 'warning'
                StockWarning.objects.create(
                    material_batch=batch,
                    warning_type='low_stock',
                    warning_level=level,
                    warning_date=now,
                    message=f'原料批次{batch.batch_no}库存不足，当前库存{remaining}kg，请及时补充。',
                    current_stock=remaining,
                    threshold=low_stock_threshold,
                )

        if storage_days > batch.expected_shelf_life:
            existing = StockWarning.objects.filter(
                material_batch=batch,
                warning_type='expired',
                is_resolved=False
            ).first()
            if not existing:
                StockWarning.objects.create(
                    material_batch=batch,
                    warning_type='expired',
                    warning_level='critical',
                    warning_date=now,
                    message=f'原料批次{batch.batch_no}已超期存放{storage_days - batch.expected_shelf_life}天，建议尽快处理或检验。',
                    current_stock=remaining,
                    threshold=batch.expected_shelf_life,
                )
        elif storage_days >= batch.expected_shelf_life - expiring_days:
            existing = StockWarning.objects.filter(
                material_batch=batch,
                warning_type='expiring',
                is_resolved=False
            ).first()
            if not existing:
                StockWarning.objects.create(
                    material_batch=batch,
                    warning_type='expiring',
                    warning_level='warning',
                    warning_date=now,
                    message=f'原料批次{batch.batch_no}将在{batch.days_until_expiry}天后到期，请尽快安排使用。',
                    current_stock=remaining,
                    threshold=batch.expected_shelf_life - expiring_days,
                )


def dashboard(request):
    total_kilns = Kiln.objects.count()
    active_kilns = Kiln.objects.filter(status='active').count()
    total_batches = Batch.objects.count()
    completed_batches = Batch.objects.filter(finish_date__isnull=False).count()
    ongoing_batches = Batch.objects.filter(finish_date__isnull=True).count()

    recent_batches = Batch.objects.all()[:10]

    avg_yield = Batch.objects.filter(
        charcoal_weight__isnull=False,
        material_weight__gt=0
    ).aggregate(avg=Avg('charcoal_weight'))['avg']

    if avg_yield:
        avg_material = Batch.objects.filter(material_weight__gt=0).aggregate(avg=Avg('material_weight'))['avg']
        avg_yield_rate = round(float(avg_yield) / float(avg_material) * 100, 2) if avg_material else 0
    else:
        avg_yield_rate = 0

    abnormal_smoke_count = SmokeStage.objects.filter(is_normal=False).count()

    generate_stock_warnings()

    total_suppliers = Supplier.objects.filter(status='active').count()
    total_material_batches = RawMaterialBatch.objects.filter(
        storage_status__in=['in_stock', 'partial_used']
    ).count()
    total_stock = RawMaterialBatch.objects.filter(
        storage_status__in=['in_stock', 'partial_used']
    ).aggregate(
        total=Sum('total_weight')
    )['total'] or 0
    total_used = MaterialIssue.objects.filter(status='completed').aggregate(
        total=Sum('weight')
    )['total'] or 0
    total_loss = MaterialLoss.objects.aggregate(total=Sum('weight'))['total'] or 0

    stock_warnings = StockWarning.objects.filter(is_resolved=False).order_by('-warning_date')
    low_stock_count = stock_warnings.filter(warning_type='low_stock').count()
    expiring_count = stock_warnings.filter(warning_type='expiring').count()
    expired_count = stock_warnings.filter(warning_type='expired').count()

    recent_materials = RawMaterialBatch.objects.all()[:5]
    recent_issues = MaterialIssue.objects.all()[:5]

    context = {
        'total_kilns': total_kilns,
        'active_kilns': active_kilns,
        'total_batches': total_batches,
        'completed_batches': completed_batches,
        'ongoing_batches': ongoing_batches,
        'recent_batches': recent_batches,
        'avg_yield_rate': avg_yield_rate,
        'abnormal_smoke_count': abnormal_smoke_count,
        'total_suppliers': total_suppliers,
        'total_material_batches': total_material_batches,
        'total_stock': total_stock,
        'total_used': total_used,
        'total_loss': total_loss,
        'stock_warnings': stock_warnings,
        'low_stock_count': low_stock_count,
        'expiring_count': expiring_count,
        'expired_count': expired_count,
        'recent_materials': recent_materials,
        'recent_issues': recent_issues,
    }
    return render(request, 'kiln_app/dashboard.html', context)


def supplier_list(request):
    suppliers = Supplier.objects.all()
    status_filter = request.GET.get('status', '')
    if status_filter:
        suppliers = suppliers.filter(status=status_filter)
    context = {'suppliers': suppliers, 'status_filter': status_filter}
    return render(request, 'kiln_app/supplier_list.html', context)


def supplier_create(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '供应商档案创建成功！')
            return redirect('kiln_app:supplier_list')
    else:
        form = SupplierForm()
    return render(request, 'kiln_app/supplier_form.html', {'form': form, 'action': '创建'})


def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, '供应商档案更新成功！')
            return redirect('kiln_app:supplier_list')
    else:
        form = SupplierForm(instance=supplier)
    return render(request, 'kiln_app/supplier_form.html', {'form': form, 'action': '编辑', 'supplier': supplier})


def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    try:
        supplier.delete()
        messages.success(request, '供应商档案已删除！')
    except Exception:
        messages.error(request, '该供应商有关联的原料批次，无法删除！')
    return redirect('kiln_app:supplier_list')


def material_batch_list(request):
    materials = RawMaterialBatch.objects.select_related('supplier').all()
    species_filter = request.GET.get('wood_species', '')
    supplier_filter = request.GET.get('supplier', '')
    status_filter = request.GET.get('storage_status', '')

    if species_filter:
        materials = materials.filter(wood_species=species_filter)
    if supplier_filter:
        materials = materials.filter(supplier_id=supplier_filter)
    if status_filter:
        materials = materials.filter(storage_status=status_filter)

    generate_stock_warnings()

    suppliers = Supplier.objects.all()

    all_materials = RawMaterialBatch.objects.all()
    total_batches = all_materials.count()
    in_stock_materials = all_materials.filter(storage_status__in=['in_stock', 'partial_used'])
    in_stock_count = in_stock_materials.count()
    total_stock_weight = in_stock_materials.aggregate(
        total=Sum('total_weight')
    )['total'] or 0
    total_used_weight = MaterialIssue.objects.filter(status='completed').aggregate(
        total=Sum('weight')
    )['total'] or 0
    remaining_stock = float(total_stock_weight) - float(total_used_weight)
    warning_count = StockWarning.objects.filter(is_resolved=False).count()

    context = {
        'materials': materials,
        'species_filter': species_filter,
        'supplier_filter': supplier_filter,
        'status_filter': status_filter,
        'suppliers': suppliers,
        'wood_species_choices': RawMaterialBatch.WOOD_SPECIES,
        'storage_status_choices': RawMaterialBatch.STORAGE_STATUS,
        'total_batches': total_batches,
        'total_stock_weight': round(remaining_stock, 2),
        'in_stock_count': in_stock_count,
        'warning_count': warning_count,
    }
    return render(request, 'kiln_app/material_batch_list.html', context)


def material_batch_create(request):
    if request.method == 'POST':
        form = RawMaterialBatchForm(request.POST)
        if form.is_valid():
            material = form.save()
            StockLedger.objects.create(
                material_batch=material,
                transaction_type='stock_in',
                transaction_date=timezone.now(),
                quantity=material.total_weight,
                balance_after=material.total_weight,
                reference_no=material.batch_no,
                operator=request.user.username if request.user.is_authenticated else '',
                notes='原料入库登记',
            )
            messages.success(request, '原料入库登记成功！')
            return redirect('kiln_app:material_batch_list')
    else:
        form = RawMaterialBatchForm()
    return render(request, 'kiln_app/material_batch_form.html', {'form': form, 'action': '入库登记'})


def material_batch_edit(request, pk):
    material = get_object_or_404(RawMaterialBatch, pk=pk)
    if request.method == 'POST':
        form = RawMaterialBatchForm(request.POST, instance=material)
        if form.is_valid():
            form.save()
            messages.success(request, '原料批次更新成功！')
            return redirect('kiln_app:material_batch_detail', pk=material.pk)
    else:
        form = RawMaterialBatchForm(instance=material)
    return render(request, 'kiln_app/material_batch_form.html', {'form': form, 'action': '编辑', 'material': material})


def material_batch_delete(request, pk):
    material = get_object_or_404(RawMaterialBatch, pk=pk)
    try:
        material.delete()
        messages.success(request, '原料批次已删除！')
    except Exception as e:
        messages.error(request, f'删除失败：{str(e)}')
    return redirect('kiln_app:material_batch_list')


def material_batch_detail(request, pk):
    material = get_object_or_404(RawMaterialBatch.objects.select_related('supplier'), pk=pk)
    moisture_tests = material.moisture_tests.order_by('-test_date')
    issues = material.issues.select_related('batch').order_by('-issue_date')
    losses = material.losses.order_by('-loss_date')
    ledger = material.ledger_entries.order_by('-transaction_date')

    moisture_labels = []
    moisture_data = []
    for test in moisture_tests[:20]:
        moisture_labels.append(test.test_date.strftime('%m-%d %H:%M'))
        moisture_data.append(float(test.moisture_content))

    context = {
        'material': material,
        'moisture_tests': moisture_tests,
        'issues': issues,
        'losses': losses,
        'ledger': ledger,
        'moisture_labels_json': json.dumps(moisture_labels),
        'moisture_data_json': json.dumps(moisture_data),
    }
    return render(request, 'kiln_app/material_batch_detail.html', context)


def moisture_test_create(request, material_pk):
    material = get_object_or_404(RawMaterialBatch, pk=material_pk)
    if request.method == 'POST':
        form = MoistureTestForm(request.POST, material_batch=material)
        if form.is_valid():
            test = form.save(commit=False)
            test.material_batch = material
            test.save()
            messages.success(request, '含水率检测记录添加成功！')
            return redirect('kiln_app:material_batch_detail', pk=material.pk)
    else:
        form = MoistureTestForm(material_batch=material)
    return render(request, 'kiln_app/moisture_test_form.html', {
        'form': form, 'title': '添加含水率检测', 'material': material
    })


def moisture_test_edit(request, pk):
    test = get_object_or_404(MoistureTest, pk=pk)
    material = test.material_batch
    if request.method == 'POST':
        form = MoistureTestForm(request.POST, instance=test, material_batch=material)
        if form.is_valid():
            form.save()
            messages.success(request, '含水率检测记录更新成功！')
            return redirect('kiln_app:material_batch_detail', pk=material.pk)
    else:
        form = MoistureTestForm(instance=test, material_batch=material)
    return render(request, 'kiln_app/moisture_test_form.html', {
        'form': form, 'title': '编辑含水率检测', 'material': material
    })


def moisture_test_delete(request, pk):
    test = get_object_or_404(MoistureTest, pk=pk)
    material_pk = test.material_batch.pk
    test.delete()
    messages.success(request, '含水率检测记录已删除！')
    return redirect('kiln_app:material_batch_detail', pk=material_pk)


def stock_ledger(request):
    entries = StockLedger.objects.select_related('material_batch').all()
    type_filter = request.GET.get('transaction_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    batch_filter = request.GET.get('batch', '')

    if type_filter:
        entries = entries.filter(transaction_type=type_filter)
    if date_from:
        entries = entries.filter(transaction_date__date__gte=date_from)
    if date_to:
        entries = entries.filter(transaction_date__date__lte=date_to)
    if batch_filter:
        entries = entries.filter(material_batch__batch_no__icontains=batch_filter)

    context = {
        'entries': entries,
        'type_filter': type_filter,
        'date_from': date_from,
        'date_to': date_to,
        'batch_filter': batch_filter,
        'transaction_types': StockLedger.TRANSACTION_TYPE,
    }
    return render(request, 'kiln_app/stock_ledger.html', context)


def material_issue_list(request):
    issues = MaterialIssue.objects.select_related('material_batch', 'batch').all()
    status_filter = request.GET.get('status', '')
    batch_filter = request.GET.get('batch', '')

    if status_filter:
        issues = issues.filter(status=status_filter)
    if batch_filter:
        issues = issues.filter(Q(material_batch__batch_no__icontains=batch_filter) | Q(batch__batch_no__icontains=batch_filter))

    context = {
        'issues': issues,
        'status_filter': status_filter,
        'batch_filter': batch_filter,
    }
    return render(request, 'kiln_app/material_issue_list.html', context)


def material_issue_create(request):
    if request.method == 'POST':
        form = MaterialIssueForm(request.POST)
        if form.is_valid():
            issue = form.save()
            if issue.status == 'completed':
                StockLedger.objects.create(
                    material_batch=issue.material_batch,
                    transaction_type='stock_out',
                    transaction_date=issue.issue_date,
                    quantity=issue.weight,
                    balance_after=issue.material_batch.remaining_weight,
                    reference_no=issue.issue_no,
                    operator=issue.stock_keeper,
                    notes=f'领料出库，关联烧炭批次：{issue.batch.batch_no if issue.batch else "未关联"}',
                )
                material = issue.material_batch
                if material.remaining_weight <= 0:
                    material.storage_status = 'used_up'
                else:
                    material.storage_status = 'partial_used'
                material.save()
            messages.success(request, '领料出库记录创建成功！')
            return redirect('kiln_app:material_issue_list')
    else:
        form = MaterialIssueForm()
    return render(request, 'kiln_app/material_issue_form.html', {'form': form, 'action': '创建'})


def material_issue_edit(request, pk):
    issue = get_object_or_404(MaterialIssue.objects.select_related('material_batch', 'batch'), pk=pk)
    old_status = issue.status
    old_weight = issue.weight
    if request.method == 'POST':
        form = MaterialIssueForm(request.POST, instance=issue)
        if form.is_valid():
            issue = form.save()
            if issue.status == 'completed' and old_status != 'completed':
                StockLedger.objects.create(
                    material_batch=issue.material_batch,
                    transaction_type='stock_out',
                    transaction_date=issue.issue_date,
                    quantity=issue.weight,
                    balance_after=issue.material_batch.remaining_weight,
                    reference_no=issue.issue_no,
                    operator=issue.stock_keeper,
                    notes=f'领料出库，关联烧炭批次：{issue.batch.batch_no if issue.batch else "未关联"}',
                )
                material = issue.material_batch
                if material.remaining_weight <= 0:
                    material.storage_status = 'used_up'
                else:
                    material.storage_status = 'partial_used'
                material.save()
            messages.success(request, '领料出库记录更新成功！')
            return redirect('kiln_app:material_issue_list')
    else:
        form = MaterialIssueForm(instance=issue)
    return render(request, 'kiln_app/material_issue_form.html', {'form': form, 'action': '编辑', 'issue': issue})


def material_issue_delete(request, pk):
    issue = get_object_or_404(MaterialIssue, pk=pk)
    if issue.status == 'completed':
        material = issue.material_batch
        remaining = material.remaining_weight + float(issue.weight)
        StockLedger.objects.create(
            material_batch=material,
            transaction_type='return',
            transaction_date=timezone.now(),
            quantity=issue.weight,
            balance_after=remaining,
            reference_no=issue.issue_no,
            operator=request.user.username if request.user.is_authenticated else '',
            notes='删除领料记录，退回库存',
        )
        if remaining >= float(material.total_weight):
            material.storage_status = 'in_stock'
        else:
            material.storage_status = 'partial_used'
        material.save()
    issue.delete()
    messages.success(request, '领料出库记录已删除！')
    return redirect('kiln_app:material_issue_list')


def material_loss_list(request):
    losses = MaterialLoss.objects.select_related('material_batch').all()
    type_filter = request.GET.get('loss_type', '')
    handled_filter = request.GET.get('handled', '')

    if type_filter:
        losses = losses.filter(loss_type=type_filter)
    if handled_filter:
        losses = losses.filter(handled=(handled_filter == 'true'))

    total_loss_weight = losses.aggregate(total=Sum('weight'))['total'] or 0

    context = {
        'losses': losses,
        'type_filter': type_filter,
        'handled_filter': handled_filter,
        'total_loss_weight': total_loss_weight,
        'loss_types': MaterialLoss.LOSS_TYPE,
    }
    return render(request, 'kiln_app/material_loss_list.html', context)


def material_loss_create(request):
    if request.method == 'POST':
        form = MaterialLossForm(request.POST)
        if form.is_valid():
            loss = form.save()
            StockLedger.objects.create(
                material_batch=loss.material_batch,
                transaction_type='loss',
                transaction_date=timezone.now(),
                quantity=loss.weight,
                balance_after=loss.material_batch.remaining_weight,
                reference_no=loss.loss_no,
                operator=loss.discovered_by,
                notes=f'{loss.get_loss_type_display()}：{loss.description}',
            )
            material = loss.material_batch
            if material.remaining_weight <= 0:
                material.storage_status = 'used_up'
            elif material.remaining_weight < float(material.total_weight):
                material.storage_status = 'partial_used'
            material.save()
            messages.success(request, '损耗记录创建成功！')
            return redirect('kiln_app:material_loss_list')
    else:
        form = MaterialLossForm()
    return render(request, 'kiln_app/material_loss_form.html', {'form': form, 'action': '创建'})


def material_loss_edit(request, pk):
    loss = get_object_or_404(MaterialLoss.objects.select_related('material_batch'), pk=pk)
    if request.method == 'POST':
        form = MaterialLossForm(request.POST, instance=loss)
        if form.is_valid():
            form.save()
            messages.success(request, '损耗记录更新成功！')
            return redirect('kiln_app:material_loss_list')
    else:
        form = MaterialLossForm(instance=loss)
    return render(request, 'kiln_app/material_loss_form.html', {'form': form, 'action': '编辑', 'loss': loss})


def material_loss_delete(request, pk):
    loss = get_object_or_404(MaterialLoss, pk=pk)
    material = loss.material_batch
    remaining = material.remaining_weight + float(loss.weight)
    StockLedger.objects.create(
        material_batch=material,
        transaction_type='return',
        transaction_date=timezone.now(),
        quantity=loss.weight,
        balance_after=remaining,
        reference_no=loss.loss_no,
        operator=request.user.username if request.user.is_authenticated else '',
        notes='删除损耗记录，恢复库存',
    )
    if remaining >= float(material.total_weight):
        material.storage_status = 'in_stock'
    else:
        material.storage_status = 'partial_used'
    material.save()
    loss.delete()
    messages.success(request, '损耗记录已删除！')
    return redirect('kiln_app:material_loss_list')


def stock_warning_list(request):
    generate_stock_warnings()
    warnings = StockWarning.objects.select_related('material_batch').all()
    type_filter = request.GET.get('warning_type', '')
    level_filter = request.GET.get('warning_level', '')
    resolved_filter = request.GET.get('is_resolved', '')

    if type_filter:
        warnings = warnings.filter(warning_type=type_filter)
    if level_filter:
        warnings = warnings.filter(warning_level=level_filter)
    if resolved_filter:
        warnings = warnings.filter(is_resolved=(resolved_filter == 'true'))

    context = {
        'warnings': warnings,
        'type_filter': type_filter,
        'level_filter': level_filter,
        'resolved_filter': resolved_filter,
        'warning_types': StockWarning.WARNING_TYPE,
        'warning_levels': StockWarning.WARNING_LEVEL,
    }
    return render(request, 'kiln_app/stock_warning_list.html', context)


def stock_warning_resolve(request, pk):
    warning = get_object_or_404(StockWarning.objects.select_related('material_batch'), pk=pk)
    if request.method == 'POST':
        form = StockWarningResolveForm(request.POST, instance=warning)
        if form.is_valid():
            warning = form.save(commit=False)
            if warning.is_resolved and not warning.resolved_date:
                warning.resolved_date = timezone.now()
            warning.save()
            messages.success(request, '预警处理完成！')
            return redirect('kiln_app:stock_warning_list')
    else:
        form = StockWarningResolveForm(instance=warning)
    return render(request, 'kiln_app/stock_warning_resolve.html', {'form': form, 'warning': warning})


def batch_traceability(request, pk):
    batch = get_object_or_404(Batch.objects.select_related('kiln', 'rating'), pk=pk)
    material_issues = batch.material_issues.select_related('material_batch__supplier').all()

    material_batches = []
    for issue in material_issues:
        mb = issue.material_batch
        supplier = mb.supplier
        moisture_tests = mb.moisture_tests.order_by('-test_date')[:3]
        material_batches.append({
            'issue': issue,
            'material': mb,
            'supplier': supplier,
            'moisture_tests': moisture_tests,
        })

    context = {
        'batch': batch,
        'material_batches': material_batches,
    }
    return render(request, 'kiln_app/batch_traceability.html', context)


def material_impact_analysis(request):
    batches = Batch.objects.select_related('kiln', 'rating').filter(
        finish_date__isnull=False,
        charcoal_weight__isnull=False
    ).prefetch_related('material_issues__material_batch__supplier').order_by('-finish_date')

    analysis_data = []
    for batch in batches:
        material_issues = batch.material_issues.select_related('material_batch__supplier').all()
        if not material_issues:
            continue

        total_material_weight = sum(float(issue.weight) for issue in material_issues)
        avg_moisture = 0
        avg_storage_days = 0
        suppliers = []
        wood_species = []

        for issue in material_issues:
            mb = issue.material_batch
            suppliers.append(mb.supplier.name)
            wood_species.append(mb.get_wood_species_display())
            if mb.moisture_content:
                avg_moisture += float(mb.moisture_content) * float(issue.weight)
            avg_storage_days += mb.storage_days * float(issue.weight)

        if total_material_weight > 0:
            avg_moisture = round(avg_moisture / total_material_weight, 2)
            avg_storage_days = round(avg_storage_days / total_material_weight, 1)

        has_rating = hasattr(batch, 'rating')
        analysis_data.append({
            'batch': batch,
            'yield_rate': batch.yield_rate or 0,
            'avg_moisture': avg_moisture,
            'avg_storage_days': avg_storage_days,
            'suppliers': list(set(suppliers)),
            'wood_species': list(set(wood_species)),
            'grade': batch.rating.grade if has_rating else None,
            'total_score': batch.rating.total_score if has_rating else None,
        })

    by_supplier = {}
    by_moisture = {'<15%': [], '15-25%': [], '>25%': []}
    by_storage = {'<30天': [], '30-60天': [], '>60天': []}

    for item in analysis_data:
        for supplier in item['suppliers']:
            if supplier not in by_supplier:
                by_supplier[supplier] = {'yield_rates': [], 'count': 0, 'grades': []}
            by_supplier[supplier]['yield_rates'].append(item['yield_rate'])
            by_supplier[supplier]['count'] += 1
            if item['grade']:
                by_supplier[supplier]['grades'].append(item['grade'])

        if item['avg_moisture'] > 0:
            if item['avg_moisture'] < 15:
                by_moisture['<15%'].append(item)
            elif item['avg_moisture'] <= 25:
                by_moisture['15-25%'].append(item)
            else:
                by_moisture['>25%'].append(item)

        if item['avg_storage_days'] < 30:
            by_storage['<30天'].append(item)
        elif item['avg_storage_days'] <= 60:
            by_storage['30-60天'].append(item)
        else:
            by_storage['>60天'].append(item)

    supplier_labels = list(by_supplier.keys())
    supplier_yield = []
    supplier_count = []
    for v in by_supplier.values():
        avg_y = round(sum(v['yield_rates']) / len(v['yield_rates']), 2) if v['yield_rates'] else 0
        supplier_yield.append(avg_y)
        supplier_count.append(v['count'])

    moisture_labels = list(by_moisture.keys())
    moisture_yield = [
        round(sum(x['yield_rate'] for x in v) / len(v), 2) if v else 0
        for v in by_moisture.values()
    ]
    moisture_count = [len(v) for v in by_moisture.values()]

    storage_labels = list(by_storage.keys())
    storage_yield = [
        round(sum(x['yield_rate'] for x in v) / len(v), 2) if v else 0
        for v in by_storage.values()
    ]
    storage_count = [len(v) for v in by_storage.values()]

    grade_score_map = {'excellent': 5, 'good': 4, 'medium': 3, 'poor': 2, 'reject': 1}
    moisture_grades = {}
    for key, items in by_moisture.items():
        grades = [grade_score_map.get(x['grade'], 0) for x in items if x['grade']]
        moisture_grades[key] = round(sum(grades) / len(grades), 2) if grades else 0

    storage_grades = {}
    for key, items in by_storage.items():
        grades = [grade_score_map.get(x['grade'], 0) for x in items if x['grade']]
        storage_grades[key] = round(sum(grades) / len(grades), 2) if grades else 0

    context = {
        'analysis_data': analysis_data,
        'supplier_labels_json': json.dumps(supplier_labels),
        'supplier_yield_json': json.dumps(supplier_yield),
        'supplier_count_json': json.dumps(supplier_count),
        'moisture_labels_json': json.dumps(moisture_labels),
        'moisture_yield_json': json.dumps(moisture_yield),
        'moisture_count_json': json.dumps(moisture_count),
        'moisture_grades_json': json.dumps([moisture_grades[k] for k in moisture_labels]),
        'storage_labels_json': json.dumps(storage_labels),
        'storage_yield_json': json.dumps(storage_yield),
        'storage_count_json': json.dumps(storage_count),
        'storage_grades_json': json.dumps([storage_grades[k] for k in storage_labels]),
    }
    return render(request, 'kiln_app/material_impact_analysis.html', context)


def material_usage_report(request):
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    supplier_filter = request.GET.get('supplier', '')
    species_filter = request.GET.get('wood_species', '')

    issues = MaterialIssue.objects.select_related(
        'material_batch__supplier', 'batch'
    ).filter(status='completed').order_by('-issue_date')

    if date_from:
        issues = issues.filter(issue_date__date__gte=date_from)
    if date_to:
        issues = issues.filter(issue_date__date__lte=date_to)
    if supplier_filter:
        issues = issues.filter(material_batch__supplier_id=supplier_filter)
    if species_filter:
        issues = issues.filter(material_batch__wood_species=species_filter)

    total_used = issues.aggregate(total=Sum('weight'))['total'] or 0
    total_cost = 0
    for issue in issues:
        if issue.material_batch.unit_price:
            total_cost += float(issue.weight) * float(issue.material_batch.unit_price)
    total_cost = round(total_cost, 2)

    by_species = {}
    by_supplier = {}
    for issue in issues:
        species = issue.material_batch.get_wood_species_display()
        supplier = issue.material_batch.supplier.name
        weight = float(issue.weight)
        if species not in by_species:
            by_species[species] = {'weight': 0, 'count': 0}
        by_species[species]['weight'] += weight
        by_species[species]['count'] += 1
        if supplier not in by_supplier:
            by_supplier[supplier] = {'weight': 0, 'count': 0}
        by_supplier[supplier]['weight'] += weight
        by_supplier[supplier]['count'] += 1

    species_labels = list(by_species.keys())
    species_weights = [round(v['weight'], 2) for v in by_species.values()]
    supplier_labels = list(by_supplier.keys())
    supplier_weights = [round(v['weight'], 2) for v in by_supplier.values()]

    suppliers = Supplier.objects.all()

    context = {
        'issues': issues,
        'date_from': date_from,
        'date_to': date_to,
        'supplier_filter': supplier_filter,
        'species_filter': species_filter,
        'total_used': total_used,
        'total_cost': total_cost,
        'suppliers': suppliers,
        'wood_species_choices': RawMaterialBatch.WOOD_SPECIES,
        'species_labels_json': json.dumps(species_labels),
        'species_weights_json': json.dumps(species_weights),
        'supplier_labels_json': json.dumps(supplier_labels),
        'supplier_weights_json': json.dumps(supplier_weights),
    }
    return render(request, 'kiln_app/material_usage_report.html', context)


def export_material_csv(request):
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    type_filter = request.GET.get('type', 'usage')

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')

    if type_filter == 'usage':
        response['Content-Disposition'] = 'attachment; filename="material_usage_report.csv"'
        issues = MaterialIssue.objects.select_related(
            'material_batch__supplier', 'batch'
        ).filter(status='completed').order_by('-issue_date')
        if date_from:
            issues = issues.filter(issue_date__date__gte=date_from)
        if date_to:
            issues = issues.filter(issue_date__date__lte=date_to)

        writer = csv.writer(response)
        writer.writerow([
            '领料单号', '原料批次号', '供应商', '木材种类', '领用重量(kg)',
            '关联烧炭批次', '领料日期', '领料人', '发料人', '单价(元/kg)', '成本(元)'
        ])
        for issue in issues:
            mb = issue.material_batch
            unit_price = mb.unit_price or 0
            cost = round(float(issue.weight) * float(unit_price), 2)
            writer.writerow([
                issue.issue_no,
                mb.batch_no,
                mb.supplier.name,
                mb.get_wood_species_display(),
                issue.weight,
                issue.batch.batch_no if issue.batch else '',
                issue.issue_date.strftime('%Y-%m-%d %H:%M'),
                issue.requester,
                issue.stock_keeper,
                unit_price,
                cost,
            ])

    elif type_filter == 'loss':
        response['Content-Disposition'] = 'attachment; filename="material_loss_report.csv"'
        losses = MaterialLoss.objects.select_related('material_batch__supplier').all().order_by('-loss_date')
        if date_from:
            losses = losses.filter(loss_date__gte=date_from)
        if date_to:
            losses = losses.filter(loss_date__lte=date_to)

        writer = csv.writer(response)
        writer.writerow([
            '损耗单号', '原料批次号', '供应商', '木材种类', '损耗类型',
            '损耗重量(kg)', '损耗日期', '发现人', '是否处理', '处理人', '损耗原因'
        ])
        for loss in losses:
            mb = loss.material_batch
            writer.writerow([
                loss.loss_no,
                mb.batch_no,
                mb.supplier.name,
                mb.get_wood_species_display(),
                loss.get_loss_type_display(),
                loss.weight,
                loss.loss_date.strftime('%Y-%m-%d'),
                loss.discovered_by,
                '是' if loss.handled else '否',
                loss.handler or '',
                loss.description,
            ])

    elif type_filter == 'stock':
        response['Content-Disposition'] = 'attachment; filename="stock_report.csv"'
        materials = RawMaterialBatch.objects.select_related('supplier').all().order_by('-arrival_date')

        writer = csv.writer(response)
        writer.writerow([
            '原料批次号', '供应商', '木材种类', '入库重量(kg)', '已用重量(kg)',
            '剩余重量(kg)', '入库日期', '存放天数', '初始含水率(%)',
            '库存状态', '单价(元/kg)', '总成本(元)', '存放位置'
        ])
        for mb in materials:
            writer.writerow([
                mb.batch_no,
                mb.supplier.name,
                mb.get_wood_species_display(),
                mb.total_weight,
                mb.used_weight,
                mb.remaining_weight,
                mb.arrival_date.strftime('%Y-%m-%d'),
                mb.storage_days,
                mb.moisture_content or '',
                mb.get_storage_status_display(),
                mb.unit_price or '',
                mb.total_cost or '',
                mb.storage_location or '',
            ])

    return response


def purchase_plan_list(request):
    plans = PurchasePlan.objects.select_related('supplier').all()
    status_filter = request.GET.get('status', '')
    supplier_filter = request.GET.get('supplier', '')
    species_filter = request.GET.get('wood_species', '')

    if status_filter:
        plans = plans.filter(status=status_filter)
    if supplier_filter:
        plans = plans.filter(supplier_id=supplier_filter)
    if species_filter:
        plans = plans.filter(wood_species=species_filter)

    suppliers = Supplier.objects.all()

    context = {
        'plans': plans,
        'status_filter': status_filter,
        'supplier_filter': supplier_filter,
        'species_filter': species_filter,
        'suppliers': suppliers,
        'wood_species_choices': RawMaterialBatch.WOOD_SPECIES,
        'plan_status_choices': PurchasePlan.PLAN_STATUS,
    }
    return render(request, 'kiln_app/purchase_plan_list.html', context)


def purchase_plan_create(request):
    if request.method == 'POST':
        form = PurchasePlanForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '采购计划创建成功！')
            return redirect('kiln_app:purchase_plan_list')
    else:
        form = PurchasePlanForm()
    return render(request, 'kiln_app/purchase_plan_form.html', {'form': form, 'action': '创建'})


def purchase_plan_edit(request, pk):
    plan = get_object_or_404(PurchasePlan, pk=pk)
    if request.method == 'POST':
        form = PurchasePlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, '采购计划更新成功！')
            return redirect('kiln_app:purchase_plan_detail', pk=plan.pk)
    else:
        form = PurchasePlanForm(instance=plan)
    return render(request, 'kiln_app/purchase_plan_form.html', {'form': form, 'action': '编辑', 'plan': plan})


def purchase_plan_delete(request, pk):
    plan = get_object_or_404(PurchasePlan, pk=pk)
    try:
        plan.delete()
        messages.success(request, '采购计划已删除！')
    except Exception:
        messages.error(request, '该采购计划有关联的采购订单，无法删除！')
    return redirect('kiln_app:purchase_plan_list')


def purchase_plan_detail(request, pk):
    plan = get_object_or_404(PurchasePlan.objects.select_related('supplier'), pk=pk)
    orders = plan.purchase_orders.select_related('supplier').all()
    total_ordered = orders.aggregate(total=Sum('ordered_weight'))['total'] or 0
    total_arrived = orders.aggregate(total=Sum('arrivals__accepted_weight'))['total'] or 0

    context = {
        'plan': plan,
        'orders': orders,
        'total_ordered': total_ordered,
        'total_arrived': total_arrived,
    }
    return render(request, 'kiln_app/purchase_plan_detail.html', context)


def purchase_plan_approve(request, pk):
    plan = get_object_or_404(PurchasePlan, pk=pk)
    if request.method == 'POST':
        form = PurchasePlanApprovalForm(request.POST, instance=plan)
        if form.is_valid():
            plan = form.save(commit=False)
            if plan.status in ['approved', 'rejected'] and not plan.approval_date:
                plan.approval_date = timezone.now().date()
            plan.save()
            if plan.status == 'approved':
                messages.success(request, '采购计划已批准！')
            else:
                messages.success(request, '采购计划审批完成！')
            return redirect('kiln_app:purchase_plan_detail', pk=plan.pk)
    else:
        form = PurchasePlanApprovalForm(instance=plan)
    return render(request, 'kiln_app/purchase_plan_approve.html', {'form': form, 'plan': plan})


def purchase_order_list(request):
    orders = PurchaseOrder.objects.select_related('supplier', 'purchase_plan').all()
    status_filter = request.GET.get('status', '')
    supplier_filter = request.GET.get('supplier', '')

    if status_filter:
        orders = orders.filter(status=status_filter)
    if supplier_filter:
        orders = orders.filter(supplier_id=supplier_filter)

    suppliers = Supplier.objects.all()

    context = {
        'orders': orders,
        'status_filter': status_filter,
        'supplier_filter': supplier_filter,
        'suppliers': suppliers,
        'order_status_choices': PurchaseOrder.ORDER_STATUS,
    }
    return render(request, 'kiln_app/purchase_order_list.html', context)


def purchase_order_create(request):
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        if form.is_valid():
            order = form.save()
            if order.purchase_plan:
                plan = order.purchase_plan
                if plan.status == 'approved':
                    if plan.executed_weight >= plan.total_weight:
                        plan.status = 'completed'
                    elif plan.executed_weight > 0:
                        plan.status = 'partial'
                    plan.save()
            messages.success(request, '采购订单创建成功！')
            return redirect('kiln_app:purchase_order_list')
    else:
        form = PurchaseOrderForm()
    return render(request, 'kiln_app/purchase_order_form.html', {'form': form, 'action': '创建'})


def purchase_order_edit(request, pk):
    order = get_object_or_404(PurchaseOrder.objects.select_related('supplier', 'purchase_plan'), pk=pk)
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, '采购订单更新成功！')
            return redirect('kiln_app:purchase_order_detail', pk=order.pk)
    else:
        form = PurchaseOrderForm(instance=order)
    return render(request, 'kiln_app/purchase_order_form.html', {'form': form, 'action': '编辑', 'order': order})


def purchase_order_delete(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk)
    try:
        order.delete()
        messages.success(request, '采购订单已删除！')
    except Exception:
        messages.error(request, '该采购订单有关联的到货记录，无法删除！')
    return redirect('kiln_app:purchase_order_list')


def purchase_order_detail(request, pk):
    order = get_object_or_404(PurchaseOrder.objects.select_related('supplier', 'purchase_plan'), pk=pk)
    arrivals = order.arrivals.all()
    total_arrived = arrivals.aggregate(total=Sum('accepted_weight'))['total'] or 0

    context = {
        'order': order,
        'arrivals': arrivals,
        'total_arrived': total_arrived,
    }
    return render(request, 'kiln_app/purchase_order_detail.html', context)


def purchase_arrival_list(request):
    arrivals = PurchaseArrival.objects.select_related('purchase_order__supplier').all()
    result_filter = request.GET.get('inspection_result', '')

    if result_filter:
        arrivals = arrivals.filter(inspection_result=result_filter)

    context = {
        'arrivals': arrivals,
        'result_filter': result_filter,
        'inspection_results': PurchaseArrival.INSPECTION_RESULT,
    }
    return render(request, 'kiln_app/purchase_arrival_list.html', context)


def purchase_arrival_create(request):
    if request.method == 'POST':
        form = PurchaseArrivalForm(request.POST)
        if form.is_valid():
            arrival = form.save()
            if arrival.inspection_result in ['qualified', 'partial'] and arrival.accepted_weight > 0:
                order = arrival.purchase_order
                material_batch = RawMaterialBatch.objects.create(
                    batch_no=f'RM-{arrival.arrival_no}',
                    supplier=order.supplier,
                    wood_species=order.wood_species,
                    arrival_date=arrival.arrival_date.date(),
                    total_weight=arrival.accepted_weight,
                    moisture_content=arrival.moisture_content,
                    quality_grade=arrival.quality_grade,
                    inspection_notes=arrival.inspection_notes,
                    inspector=arrival.inspector,
                    inspection_date=arrival.arrival_date.date(),
                    unit_price=order.unit_price,
                    remarks=f'来源采购订单: {order.order_no}',
                )
                arrival.material_batch = material_batch
                arrival.save()

                StockLedger.objects.create(
                    material_batch=material_batch,
                    transaction_type='stock_in',
                    transaction_date=arrival.arrival_date,
                    quantity=arrival.accepted_weight,
                    balance_after=arrival.accepted_weight,
                    reference_no=arrival.arrival_no,
                    operator=arrival.warehouse_keeper,
                    notes=f'采购到货入库，来源订单: {order.order_no}',
                )

                if order.remaining_weight <= 0:
                    order.status = 'completed'
                elif order.arrival_rate > 0:
                    order.status = 'partial'
                order.save()

                if order.purchase_plan:
                    plan = order.purchase_plan
                    if plan.execution_rate >= 100:
                        plan.status = 'completed'
                    elif plan.execution_rate > 0:
                        plan.status = 'partial'
                    plan.save()

            messages.success(request, '到货验收单创建成功！')
            return redirect('kiln_app:purchase_arrival_list')
    else:
        form = PurchaseArrivalForm()
    return render(request, 'kiln_app/purchase_arrival_form.html', {'form': form, 'action': '创建'})


def purchase_arrival_edit(request, pk):
    arrival = get_object_or_404(PurchaseArrival.objects.select_related('purchase_order__supplier'), pk=pk)
    if request.method == 'POST':
        form = PurchaseArrivalForm(request.POST, instance=arrival)
        if form.is_valid():
            form.save()
            messages.success(request, '到货验收单更新成功！')
            return redirect('kiln_app:purchase_arrival_detail', pk=arrival.pk)
    else:
        form = PurchaseArrivalForm(instance=arrival)
    return render(request, 'kiln_app/purchase_arrival_form.html', {'form': form, 'action': '编辑', 'arrival': arrival})


def purchase_arrival_delete(request, pk):
    arrival = get_object_or_404(PurchaseArrival, pk=pk)
    try:
        if arrival.material_batch:
            arrival.material_batch.delete()
        arrival.delete()
        messages.success(request, '到货验收单已删除！')
    except Exception as e:
        messages.error(request, f'删除失败：{str(e)}')
    return redirect('kiln_app:purchase_arrival_list')


def purchase_arrival_detail(request, pk):
    arrival = get_object_or_404(PurchaseArrival.objects.select_related(
        'purchase_order__supplier', 'purchase_order__purchase_plan', 'material_batch'
    ), pk=pk)
    cost_splits = arrival.cost_splits.all()
    total_cost = cost_splits.aggregate(total=Sum('cost_amount'))['total'] or 0

    context = {
        'arrival': arrival,
        'cost_splits': cost_splits,
        'total_cost': total_cost,
    }
    return render(request, 'kiln_app/purchase_arrival_detail.html', context)


def cost_split_list(request):
    splits = PurchaseCostSplit.objects.select_related('purchase_arrival__purchase_order__supplier').all()
    type_filter = request.GET.get('cost_type', '')

    if type_filter:
        splits = splits.filter(cost_type=type_filter)

    context = {
        'splits': splits,
        'type_filter': type_filter,
        'cost_types': PurchaseCostSplit.COST_TYPE,
    }
    return render(request, 'kiln_app/cost_split_list.html', context)


def cost_split_create(request):
    if request.method == 'POST':
        form = PurchaseCostSplitForm(request.POST)
        if form.is_valid():
            split = form.save()
            if split.purchase_arrival and split.purchase_arrival.material_batch:
                mb = split.purchase_arrival.material_batch
                old_unit_cost = mb.unit_price or 0
                old_total_cost = mb.total_cost or 0
                new_total_cost = float(old_total_cost) + float(split.cost_amount)
                new_unit_cost = round(new_total_cost / float(mb.total_weight), 4) if mb.total_weight > 0 else 0

                StockCostLedger.objects.create(
                    material_batch=mb,
                    transaction_date=timezone.now(),
                    change_type='purchase',
                    old_unit_cost=old_unit_cost,
                    new_unit_cost=new_unit_cost,
                    old_total_cost=old_total_cost,
                    new_total_cost=new_total_cost,
                    quantity=mb.total_weight,
                    reference_no=split.split_no,
                    operator=split.operator,
                    reason=f'{split.get_cost_type_display()}分摊',
                )

                mb.unit_price = new_unit_cost
                mb.total_cost = new_total_cost
                mb.save()

                split.is_allocated = True
                split.allocated_date = timezone.now()
                split.save()

            messages.success(request, '费用分摊创建成功！')
            return redirect('kiln_app:cost_split_list')
    else:
        form = PurchaseCostSplitForm()
    return render(request, 'kiln_app/cost_split_form.html', {'form': form, 'action': '创建'})


def cost_split_edit(request, pk):
    split = get_object_or_404(PurchaseCostSplit.objects.select_related('purchase_arrival'), pk=pk)
    if request.method == 'POST':
        form = PurchaseCostSplitForm(request.POST, instance=split)
        if form.is_valid():
            form.save()
            messages.success(request, '费用分摊更新成功！')
            return redirect('kiln_app:cost_split_list')
    else:
        form = PurchaseCostSplitForm(instance=split)
    return render(request, 'kiln_app/cost_split_form.html', {'form': form, 'action': '编辑', 'split': split})


def cost_split_delete(request, pk):
    split = get_object_or_404(PurchaseCostSplit, pk=pk)
    try:
        split.delete()
        messages.success(request, '费用分摊已删除！')
    except Exception as e:
        messages.error(request, f'删除失败：{str(e)}')
    return redirect('kiln_app:cost_split_list')


def batch_cost_list(request):
    costs = BatchCost.objects.select_related('batch', 'batch__kiln').all()
    batch_filter = request.GET.get('batch', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if batch_filter:
        costs = costs.filter(Q(batch__batch_no__icontains=batch_filter))
    if date_from:
        costs = costs.filter(calculate_date__date__gte=date_from)
    if date_to:
        costs = costs.filter(calculate_date__date__lte=date_to)

    context = {
        'costs': costs,
        'batch_filter': batch_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'kiln_app/batch_cost_list.html', context)


def batch_cost_create(request):
    if request.method == 'POST':
        form = BatchCostForm(request.POST)
        if form.is_valid():
            cost = form.save(commit=False)
            if cost.batch:
                issues = cost.batch.material_issues.filter(status='completed').select_related('material_batch')
                material_cost = 0
                for issue in issues:
                    if issue.material_batch.unit_price:
                        material_cost += float(issue.weight) * float(issue.material_batch.unit_price)
                cost.material_cost = round(material_cost, 2)
            cost.save()
            messages.success(request, '批次成本创建成功！')
            return redirect('kiln_app:batch_cost_detail', pk=cost.pk)
    else:
        form = BatchCostForm()
    return render(request, 'kiln_app/batch_cost_form.html', {'form': form, 'action': '创建'})


def batch_cost_edit(request, pk):
    cost = get_object_or_404(BatchCost.objects.select_related('batch'), pk=pk)
    if request.method == 'POST':
        form = BatchCostForm(request.POST, instance=cost)
        if form.is_valid():
            form.save()
            messages.success(request, '批次成本更新成功！')
            return redirect('kiln_app:batch_cost_detail', pk=cost.pk)
    else:
        form = BatchCostForm(instance=cost)
    return render(request, 'kiln_app/batch_cost_form.html', {'form': form, 'action': '编辑', 'cost': cost})


def batch_cost_delete(request, pk):
    cost = get_object_or_404(BatchCost, pk=pk)
    try:
        cost.delete()
        messages.success(request, '批次成本已删除！')
    except Exception as e:
        messages.error(request, f'删除失败：{str(e)}')
    return redirect('kiln_app:batch_cost_list')


def batch_cost_detail(request, pk):
    cost = get_object_or_404(BatchCost.objects.select_related('batch', 'batch__kiln', 'batch__rating'), pk=pk)
    items = cost.cost_items.all()

    cost_breakdown_labels = []
    cost_breakdown_data = []
    cost_breakdown_colors = [
        'rgba(54, 162, 235, 0.8)', 'rgba(255, 99, 132, 0.8)',
        'rgba(255, 206, 86, 0.8)', 'rgba(75, 192, 192, 0.8)',
        'rgba(153, 102, 255, 0.8)', 'rgba(255, 159, 64, 0.8)',
        'rgba(199, 199, 199, 0.8)',
    ]

    cost_fields = [
        ('原料成本', cost.material_cost),
        ('人工成本', cost.labor_cost),
        ('燃料成本', cost.fuel_cost),
        ('电力成本', cost.electricity_cost),
        ('设备折旧', cost.depreciation_cost),
        ('维护成本', cost.maintenance_cost),
        ('其他成本', cost.other_cost),
    ]

    for label, value in cost_fields:
        if value and float(value) > 0:
            cost_breakdown_labels.append(label)
            cost_breakdown_data.append(float(value))

    profit_labels = ['总成本', '销售收入', '利润']
    profit_data = [
        float(cost.total_cost) if cost.total_cost else 0,
        float(cost.sales_amount) if cost.sales_amount else 0,
        float(cost.profit) if cost.profit else 0,
    ]
    profit_colors = [
        'rgba(255, 99, 132, 0.8)',
        'rgba(75, 192, 192, 0.8)',
        'rgba(54, 162, 235, 0.8)',
    ]

    context = {
        'cost': cost,
        'items': items,
        'cost_breakdown_labels_json': json.dumps(cost_breakdown_labels),
        'cost_breakdown_data_json': json.dumps(cost_breakdown_data),
        'cost_breakdown_colors_json': json.dumps(cost_breakdown_colors[:len(cost_breakdown_labels)]),
        'profit_labels_json': json.dumps(profit_labels),
        'profit_data_json': json.dumps(profit_data),
        'profit_colors_json': json.dumps(profit_colors),
    }
    return render(request, 'kiln_app/batch_cost_detail.html', context)


def batch_cost_item_add(request, cost_pk):
    cost = get_object_or_404(BatchCost, pk=cost_pk)
    if request.method == 'POST':
        form = BatchCostItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.batch_cost = cost
            item.save()

            cost_type_map = {
                'material': 'material_cost',
                'labor': 'labor_cost',
                'fuel': 'fuel_cost',
                'electricity': 'electricity_cost',
                'depreciation': 'depreciation_cost',
                'maintenance': 'maintenance_cost',
                'other': 'other_cost',
            }
            field_name = cost_type_map.get(item.cost_type)
            if field_name:
                current = float(getattr(cost, field_name) or 0)
                setattr(cost, field_name, round(current + float(item.amount), 2))
                cost.save()

            messages.success(request, '成本明细项添加成功！')
            return redirect('kiln_app:batch_cost_detail', pk=cost.pk)
    else:
        form = BatchCostItemForm()
    return render(request, 'kiln_app/batch_cost_item_form.html', {'form': form, 'cost': cost})


def batch_cost_item_delete(request, pk):
    item = get_object_or_404(BatchCostItem, pk=pk)
    cost_pk = item.batch_cost.pk
    cost = item.batch_cost

    cost_type_map = {
        'material': 'material_cost',
        'labor': 'labor_cost',
        'fuel': 'fuel_cost',
        'electricity': 'electricity_cost',
        'depreciation': 'depreciation_cost',
        'maintenance': 'maintenance_cost',
        'other': 'other_cost',
    }
    field_name = cost_type_map.get(item.cost_type)
    if field_name:
        current = float(getattr(cost, field_name) or 0)
        setattr(cost, field_name, round(max(0, current - float(item.amount)), 2))
        cost.save()

    item.delete()
    messages.success(request, '成本明细项已删除！')
    return redirect('kiln_app:batch_cost_detail', pk=cost_pk)


def cost_warning_list(request):
    generate_cost_warnings()
    warnings = CostWarning.objects.all()
    type_filter = request.GET.get('warning_type', '')
    level_filter = request.GET.get('warning_level', '')
    resolved_filter = request.GET.get('is_resolved', '')

    if type_filter:
        warnings = warnings.filter(warning_type=type_filter)
    if level_filter:
        warnings = warnings.filter(warning_level=level_filter)
    if resolved_filter:
        warnings = warnings.filter(is_resolved=(resolved_filter == 'true'))

    context = {
        'warnings': warnings,
        'type_filter': type_filter,
        'level_filter': level_filter,
        'resolved_filter': resolved_filter,
        'warning_types': CostWarning.WARNING_TYPE,
        'warning_levels': CostWarning.WARNING_LEVEL,
    }
    return render(request, 'kiln_app/cost_warning_list.html', context)


def cost_warning_resolve(request, pk):
    warning = get_object_or_404(CostWarning, pk=pk)
    if request.method == 'POST':
        form = CostWarningResolveForm(request.POST, instance=warning)
        if form.is_valid():
            warning = form.save(commit=False)
            if warning.is_resolved and not warning.resolved_date:
                warning.resolved_date = timezone.now()
            warning.save()
            messages.success(request, '成本预警处理完成！')
            return redirect('kiln_app:cost_warning_list')
    else:
        form = CostWarningResolveForm(instance=warning)
    return render(request, 'kiln_app/cost_warning_resolve.html', {'form': form, 'warning': warning})


def supplier_price_comparison(request):
    species_filter = request.GET.get('wood_species', '')

    price_records = SupplierPriceHistory.objects.select_related('supplier').all()
    if species_filter:
        price_records = price_records.filter(wood_species=species_filter)

    comparison_data = {}
    for record in price_records:
        key = (record.wood_species, record.supplier.id)
        if key not in comparison_data:
            comparison_data[key] = {
                'wood_species': record.wood_species,
                'wood_species_display': record.get_wood_species_display(),
                'supplier': record.supplier,
                'prices': [],
                'dates': [],
                'avg_price': 0,
                'min_price': None,
                'max_price': None,
            }
        comparison_data[key]['prices'].append(float(record.price))
        comparison_data[key]['dates'].append(record.quote_date.strftime('%Y-%m-%d'))

    for key, data in comparison_data.items():
        if data['prices']:
            data['avg_price'] = round(sum(data['prices']) / len(data['prices']), 2)
            data['min_price'] = min(data['prices'])
            data['max_price'] = max(data['prices'])

    species_groups = {}
    for key, data in comparison_data.items():
        species = data['wood_species_display']
        if species not in species_groups:
            species_groups[species] = []
        species_groups[species].append(data)

    chart_labels = []
    chart_datasets = []
    color_palette = [
        'rgba(54, 162, 235, 0.8)', 'rgba(255, 99, 132, 0.8)',
        'rgba(255, 206, 86, 0.8)', 'rgba(75, 192, 192, 0.8)',
        'rgba(153, 102, 255, 0.8)', 'rgba(255, 159, 64, 0.8)',
    ]

    all_dates = set()
    for data in comparison_data.values():
        all_dates.update(data['dates'])
    all_dates = sorted(all_dates)
    chart_labels = all_dates

    for idx, (key, data) in enumerate(comparison_data.items()):
        dataset_data = []
        for date in all_dates:
            if date in data['dates']:
                pos = data['dates'].index(date)
                dataset_data.append(data['prices'][pos])
            else:
                dataset_data.append(None)
        chart_datasets.append({
            'label': f'{data["supplier"].name} - {data["wood_species_display"]}',
            'data': dataset_data,
            'borderColor': color_palette[idx % len(color_palette)],
            'backgroundColor': color_palette[idx % len(color_palette)].replace('0.8', '0.2'),
            'tension': 0.3,
        })

    context = {
        'species_filter': species_filter,
        'wood_species_choices': RawMaterialBatch.WOOD_SPECIES,
        'comparison_data': list(comparison_data.values()),
        'species_groups': species_groups,
        'chart_labels_json': json.dumps(chart_labels),
        'chart_datasets_json': json.dumps(chart_datasets),
    }
    return render(request, 'kiln_app/supplier_price_comparison.html', context)


def supplier_price_history_list(request):
    history = SupplierPriceHistory.objects.select_related('supplier').all()
    supplier_filter = request.GET.get('supplier', '')
    species_filter = request.GET.get('wood_species', '')

    if supplier_filter:
        history = history.filter(supplier_id=supplier_filter)
    if species_filter:
        history = history.filter(wood_species=species_filter)

    suppliers = Supplier.objects.all()

    context = {
        'history': history,
        'supplier_filter': supplier_filter,
        'species_filter': species_filter,
        'suppliers': suppliers,
        'wood_species_choices': RawMaterialBatch.WOOD_SPECIES,
    }
    return render(request, 'kiln_app/supplier_price_history_list.html', context)


def supplier_price_history_create(request):
    if request.method == 'POST':
        form = SupplierPriceHistoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '价格记录添加成功！')
            return redirect('kiln_app:supplier_price_history_list')
    else:
        form = SupplierPriceHistoryForm()
    return render(request, 'kiln_app/supplier_price_history_form.html', {'form': form, 'action': '添加'})


def supplier_price_history_edit(request, pk):
    history = get_object_or_404(SupplierPriceHistory.objects.select_related('supplier'), pk=pk)
    if request.method == 'POST':
        form = SupplierPriceHistoryForm(request.POST, instance=history)
        if form.is_valid():
            form.save()
            messages.success(request, '价格记录更新成功！')
            return redirect('kiln_app:supplier_price_history_list')
    else:
        form = SupplierPriceHistoryForm(instance=history)
    return render(request, 'kiln_app/supplier_price_history_form.html', {'form': form, 'action': '编辑', 'history': history})


def supplier_price_history_delete(request, pk):
    history = get_object_or_404(SupplierPriceHistory, pk=pk)
    history.delete()
    messages.success(request, '价格记录已删除！')
    return redirect('kiln_app:supplier_price_history_list')


def cost_analysis(request):
    batch_costs = BatchCost.objects.select_related('batch', 'batch__kiln').filter(
        batch__finish_date__isnull=False,
        total_cost__isnull=False
    ).prefetch_related(
        'batch__material_issues__material_batch__supplier'
    ).order_by('-calculate_date')

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if date_from:
        batch_costs = batch_costs.filter(calculate_date__date__gte=date_from)
    if date_to:
        batch_costs = batch_costs.filter(calculate_date__date__lte=date_to)

    by_supplier = {}
    by_species = {}
    by_moisture = {'<15%': [], '15-25%': [], '>25%': []}
    by_storage = {'<30天': [], '30-60天': [], '>60天': []}
    yield_by_supplier = {}
    yield_by_species = {}
    grade_by_supplier = {}
    grade_by_species = {}

    for bc in batch_costs:
        batch = bc.batch
        issues = batch.material_issues.filter(status='completed').select_related('material_batch__supplier')

        total_material_weight = sum(float(issue.weight) for issue in issues)
        avg_moisture = 0
        avg_storage_days = 0
        suppliers = []
        wood_species = []

        for issue in issues:
            mb = issue.material_batch
            suppliers.append(mb.supplier.name)
            wood_species.append(mb.get_wood_species_display())
            if mb.moisture_content:
                avg_moisture += float(mb.moisture_content) * float(issue.weight)
            avg_storage_days += mb.storage_days * float(issue.weight)

        if total_material_weight > 0:
            avg_moisture = round(avg_moisture / total_material_weight, 2)
            avg_storage_days = round(avg_storage_days / total_material_weight, 1)

        unit_cost = float(bc.unit_cost) if bc.unit_cost else 0
        yield_rate = float(batch.yield_rate) if batch.yield_rate else 0

        data_point = {
            'batch_no': batch.batch_no,
            'unit_cost': unit_cost,
            'yield_rate': yield_rate,
            'avg_moisture': avg_moisture,
            'avg_storage_days': avg_storage_days,
        }

        for supplier in list(set(suppliers)):
            if supplier not in by_supplier:
                by_supplier[supplier] = []
                yield_by_supplier[supplier] = []
                grade_by_supplier[supplier] = {'excellent': 0, 'good': 0, 'medium': 0, 'poor': 0, 'reject': 0}
            by_supplier[supplier].append(unit_cost)
            yield_by_supplier[supplier].append(yield_rate)
            if hasattr(batch, 'rating'):
                grade_by_supplier[supplier][batch.rating.grade] += 1

        for species in list(set(wood_species)):
            if species not in by_species:
                by_species[species] = []
                yield_by_species[species] = []
                grade_by_species[species] = {'excellent': 0, 'good': 0, 'medium': 0, 'poor': 0, 'reject': 0}
            by_species[species].append(unit_cost)
            yield_by_species[species].append(yield_rate)
            if hasattr(batch, 'rating'):
                grade_by_species[species][batch.rating.grade] += 1

        if avg_moisture > 0:
            if avg_moisture < 15:
                by_moisture['<15%'].append(data_point)
            elif avg_moisture <= 25:
                by_moisture['15-25%'].append(data_point)
            else:
                by_moisture['>25%'].append(data_point)

        if avg_storage_days > 0:
            if avg_storage_days < 30:
                by_storage['<30天'].append(data_point)
            elif avg_storage_days <= 60:
                by_storage['30-60天'].append(data_point)
            else:
                by_storage['>60天'].append(data_point)

    supplier_cost_data = []
    for supplier, costs in by_supplier.items():
        if costs:
            supplier_cost_data.append({
                'name': supplier,
                'avg_cost': round(sum(costs) / len(costs), 2),
                'min_cost': min(costs),
                'max_cost': max(costs),
                'count': len(costs),
            })

    species_cost_data = []
    for species, costs in by_species.items():
        if costs:
            species_cost_data.append({
                'name': species,
                'avg_cost': round(sum(costs) / len(costs), 2),
                'min_cost': min(costs),
                'max_cost': max(costs),
                'count': len(costs),
            })

    moisture_cost_data = []
    for key, items in by_moisture.items():
        if items:
            costs = [x['unit_cost'] for x in items if x['unit_cost'] > 0]
            moisture_cost_data.append({
                'name': key,
                'avg_cost': round(sum(costs) / len(costs), 2) if costs else 0,
                'count': len(items),
            })

    storage_cost_data = []
    for key, items in by_storage.items():
        if items:
            costs = [x['unit_cost'] for x in items if x['unit_cost'] > 0]
            storage_cost_data.append({
                'name': key,
                'avg_cost': round(sum(costs) / len(costs), 2) if costs else 0,
                'count': len(items),
            })

    supplier_yield_data = []
    for supplier, yields in yield_by_supplier.items():
        if yields:
            supplier_yield_data.append({
                'name': supplier,
                'avg_yield': round(sum(yields) / len(yields), 2),
            })

    species_yield_data = []
    for species, yields in yield_by_species.items():
        if yields:
            species_yield_data.append({
                'name': species,
                'avg_yield': round(sum(yields) / len(yields), 2),
            })

    trend_labels = []
    trend_cost_data = []
    for bc in batch_costs[:30]:
        trend_labels.append(bc.calculate_date.strftime('%Y-%m-%d'))
        trend_cost_data.append(float(bc.unit_cost) if bc.unit_cost else 0)

    context = {
        'batch_costs': batch_costs,
        'date_from': date_from,
        'date_to': date_to,
        'supplier_cost_data': supplier_cost_data,
        'species_cost_data': species_cost_data,
        'moisture_cost_data': moisture_cost_data,
        'storage_cost_data': storage_cost_data,
        'supplier_yield_data': supplier_yield_data,
        'species_yield_data': species_yield_data,
        'grade_by_supplier': grade_by_supplier,
        'grade_by_species': grade_by_species,
        'trend_labels_json': json.dumps(trend_labels),
        'trend_cost_data_json': json.dumps(trend_cost_data),
    }
    return render(request, 'kiln_app/cost_analysis.html', context)


def batch_profit_analysis(request):
    batch_costs = BatchCost.objects.select_related('batch', 'batch__kiln', 'batch__rating').filter(
        total_cost__isnull=False
    ).order_by('-calculate_date')

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    profit_filter = request.GET.get('profit_status', '')

    if date_from:
        batch_costs = batch_costs.filter(calculate_date__date__gte=date_from)
    if date_to:
        batch_costs = batch_costs.filter(calculate_date__date__lte=date_to)
    if profit_filter == 'profit':
        batch_costs = batch_costs.filter(profit__gt=0)
    elif profit_filter == 'loss':
        batch_costs = batch_costs.filter(Q(profit__lte=0) | Q(profit__isnull=True))

    profit_data = []
    for bc in batch_costs:
        profit_data.append({
            'batch_no': bc.batch.batch_no,
            'total_cost': float(bc.total_cost) if bc.total_cost else 0,
            'sales_amount': float(bc.sales_amount) if bc.sales_amount else 0,
            'profit': float(bc.profit) if bc.profit else 0,
            'profit_rate': float(bc.profit_rate) if bc.profit_rate else 0,
            'charcoal_weight': float(bc.charcoal_weight) if bc.charcoal_weight else 0,
            'unit_cost': float(bc.unit_cost) if bc.unit_cost else 0,
            'grade': bc.batch.rating.grade if hasattr(bc.batch, 'rating') else None,
            'finish_date': bc.batch.finish_date,
        })

    labels = [x['batch_no'] for x in profit_data]
    cost_data = [x['total_cost'] for x in profit_data]
    sales_data = [x['sales_amount'] for x in profit_data]
    profit_data_list = [x['profit'] for x in profit_data]

    total_cost = sum(cost_data)
    total_sales = sum(sales_data)
    total_profit = sum(profit_data_list)
    avg_profit_rate = round(sum(x['profit_rate'] for x in profit_data) / len(profit_data), 2) if profit_data else 0
    profit_count = sum(1 for x in profit_data if x['profit'] > 0)
    loss_count = sum(1 for x in profit_data if x['profit'] <= 0)

    context = {
        'profit_data': profit_data,
        'date_from': date_from,
        'date_to': date_to,
        'profit_filter': profit_filter,
        'total_cost': round(total_cost, 2),
        'total_sales': round(total_sales, 2),
        'total_profit': round(total_profit, 2),
        'avg_profit_rate': avg_profit_rate,
        'profit_count': profit_count,
        'loss_count': loss_count,
        'labels_json': json.dumps(labels),
        'cost_data_json': json.dumps(cost_data),
        'sales_data_json': json.dumps(sales_data),
        'profit_data_json': json.dumps(profit_data_list),
    }
    return render(request, 'kiln_app/batch_profit_analysis.html', context)


def purchase_progress(request):
    plans = PurchasePlan.objects.select_related('supplier').all().order_by('-created_at')
    orders = PurchaseOrder.objects.select_related('supplier', 'purchase_plan').all().order_by('-order_date')

    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if status_filter:
        plans = plans.filter(status=status_filter)
        orders = orders.filter(status=status_filter)
    if date_from:
        plans = plans.filter(created_at__date__gte=date_from)
        orders = orders.filter(order_date__gte=date_from)
    if date_to:
        plans = plans.filter(created_at__date__lte=date_to)
        orders = orders.filter(order_date__lte=date_to)

    total_plans = plans.count()
    total_orders = orders.count()
    total_ordered_weight = orders.aggregate(total=Sum('ordered_weight'))['total'] or 0
    total_arrived_weight = orders.aggregate(total=Sum('arrivals__accepted_weight'))['total'] or 0
    overall_progress = round(float(total_arrived_weight) / float(total_ordered_weight) * 100, 2) if total_ordered_weight > 0 else 0

    plan_progress_data = []
    for plan in plans:
        plan_progress_data.append({
            'plan': plan,
            'ordered_weight': plan.executed_weight,
            'arrived_weight': plan.arrival_weight,
            'progress': plan.execution_rate,
        })

    order_progress_data = []
    for order in orders:
        order_progress_data.append({
            'order': order,
            'arrived_weight': order.arrived_weight,
            'remaining_weight': order.remaining_weight,
            'progress': order.arrival_rate,
        })

    context = {
        'plan_progress_data': plan_progress_data,
        'order_progress_data': order_progress_data,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'total_plans': total_plans,
        'total_orders': total_orders,
        'total_ordered_weight': total_ordered_weight,
        'total_arrived_weight': total_arrived_weight,
        'overall_progress': overall_progress,
        'plan_status_choices': PurchasePlan.PLAN_STATUS,
    }
    return render(request, 'kiln_app/purchase_progress.html', context)


def cost_warning_dashboard(request):
    generate_cost_warnings()
    warnings = CostWarning.objects.all()

    total_count = warnings.count()
    unresolved_count = warnings.filter(is_resolved=False).count()
    critical_count = warnings.filter(warning_level='critical', is_resolved=False).count()
    warning_count = warnings.filter(warning_level='warning', is_resolved=False).count()
    info_count = warnings.filter(warning_level='info', is_resolved=False).count()

    type_counts = {}
    for wtype, wdisplay in CostWarning.WARNING_TYPE:
        type_counts[wdisplay] = warnings.filter(warning_type=wtype, is_resolved=False).count()

    recent_warnings = warnings.order_by('-warning_date')[:10]

    type_labels = list(type_counts.keys())
    type_values = list(type_counts.values())
    type_colors = [
        'rgba(255, 99, 132, 0.8)', 'rgba(54, 162, 235, 0.8)',
        'rgba(255, 206, 86, 0.8)', 'rgba(75, 192, 192, 0.8)',
        'rgba(153, 102, 255, 0.8)', 'rgba(255, 159, 64, 0.8)',
    ]

    level_labels = ['严重', '警告', '提示']
    level_values = [critical_count, warning_count, info_count]
    level_colors = ['rgba(220, 53, 69, 0.8)', 'rgba(255, 193, 7, 0.8)', 'rgba(13, 202, 240, 0.8)']

    context = {
        'total_count': total_count,
        'unresolved_count': unresolved_count,
        'critical_count': critical_count,
        'warning_count': warning_count,
        'info_count': info_count,
        'type_counts': type_counts,
        'recent_warnings': recent_warnings,
        'type_labels_json': json.dumps(type_labels),
        'type_values_json': json.dumps(type_values),
        'type_colors_json': json.dumps(type_colors[:len(type_labels)]),
        'level_labels_json': json.dumps(level_labels),
        'level_values_json': json.dumps(level_values),
        'level_colors_json': json.dumps(level_colors),
    }
    return render(request, 'kiln_app/cost_warning_dashboard.html', context)


def generate_cost_warnings():
    now = timezone.now()

    price_records = SupplierPriceHistory.objects.all().order_by('quote_date')
    supplier_species_prices = {}
    for record in price_records:
        key = (record.supplier_id, record.wood_species)
        if key not in supplier_species_prices:
            supplier_species_prices[key] = []
        supplier_species_prices[key].append(record)

    for key, records in supplier_species_prices.items():
        if len(records) >= 2:
            sorted_records = sorted(records, key=lambda x: x.quote_date)
            old_price = float(sorted_records[-2].price)
            new_price = float(sorted_records[-1].price)
            if old_price > 0:
                increase_pct = ((new_price - old_price) / old_price) * 100
                if increase_pct >= 10:
                    level = 'critical' if increase_pct >= 20 else 'warning'
                    existing = CostWarning.objects.filter(
                        warning_type='price_increase',
                        related_object_type='SupplierPriceHistory',
                        related_object_id=sorted_records[-1].id,
                        is_resolved=False
                    ).first()
                    if not existing:
                        CostWarning.objects.create(
                            warning_type='price_increase',
                            warning_level=level,
                            related_object_type='SupplierPriceHistory',
                            related_object_id=sorted_records[-1].id,
                            related_object_name=f'{sorted_records[-1].supplier.name} - {sorted_records[-1].get_wood_species_display()}',
                            current_value=new_price,
                            threshold_value=old_price * 1.1,
                            deviation_percent=round(increase_pct, 2),
                            message=f'供应商{sorted_records[-1].supplier.name}的{sorted_records[-1].get_wood_species_display()}价格上涨{round(increase_pct, 2)}%，从{old_price}元/kg涨至{new_price}元/kg。',
                        )

    batch_costs = BatchCost.objects.filter(total_cost__isnull=False)
    for bc in batch_costs:
        if bc.selling_price and bc.total_cost:
            sales_amount = float(bc.selling_price) * float(bc.charcoal_weight) if bc.charcoal_weight else 0
            profit = sales_amount - float(bc.total_cost)
            profit_rate = (profit / sales_amount * 100) if sales_amount > 0 else 0

            if profit < 0:
                existing = CostWarning.objects.filter(
                    warning_type='negative_profit',
                    related_object_type='BatchCost',
                    related_object_id=bc.id,
                    is_resolved=False
                ).first()
                if not existing:
                    CostWarning.objects.create(
                        warning_type='negative_profit',
                        warning_level='critical',
                        related_object_type='BatchCost',
                        related_object_id=bc.id,
                        related_object_name=bc.batch.batch_no,
                        current_value=round(profit, 2),
                        threshold_value=0,
                        deviation_percent=round(profit_rate, 2),
                        message=f'批次{bc.batch.batch_no}出现亏损，亏损金额{abs(round(profit, 2))}元，利润率{round(profit_rate, 2)}%。',
                    )
            elif profit_rate < 10:
                existing = CostWarning.objects.filter(
                    warning_type='low_margin',
                    related_object_type='BatchCost',
                    related_object_id=bc.id,
                    is_resolved=False
                ).first()
                if not existing:
                    CostWarning.objects.create(
                        warning_type='low_margin',
                        warning_level='warning',
                        related_object_type='BatchCost',
                        related_object_id=bc.id,
                        related_object_name=bc.batch.batch_no,
                        current_value=round(profit_rate, 2),
                        threshold_value=10,
                        deviation_percent=round(profit_rate - 10, 2),
                        message=f'批次{bc.batch.batch_no}利润率偏低，仅{round(profit_rate, 2)}%，低于10%的预警阈值。',
                    )

    plans = PurchasePlan.objects.filter(status='approved')
    for plan in plans:
        if plan.total_budget and plan.executed_weight > 0:
            actual_cost = 0
            for order in plan.purchase_orders.all():
                if order.total_amount:
                    actual_cost += float(order.total_amount)
            budget = float(plan.total_budget)
            if budget > 0 and actual_cost > budget:
                overrun_pct = ((actual_cost - budget) / budget) * 100
                level = 'critical' if overrun_pct >= 20 else 'warning'
                existing = CostWarning.objects.filter(
                    warning_type='budget_overrun',
                    related_object_type='PurchasePlan',
                    related_object_id=plan.id,
                    is_resolved=False
                ).first()
                if not existing:
                    CostWarning.objects.create(
                        warning_type='budget_overrun',
                        warning_level=level,
                        related_object_type='PurchasePlan',
                        related_object_id=plan.id,
                        related_object_name=plan.plan_name,
                        current_value=round(actual_cost, 2),
                        threshold_value=budget,
                        deviation_percent=round(overrun_pct, 2),
                        message=f'采购计划{plan.plan_name}预算超支{round(overrun_pct, 2)}%，预算{budget}元，实际{round(actual_cost, 2)}元。',
                    )


def export_purchase_csv(request):
    report_type = request.GET.get('type', 'plan')

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')

    if report_type == 'plan':
        response['Content-Disposition'] = 'attachment; filename="purchase_plans.csv"'
        plans = PurchasePlan.objects.select_related('supplier').all().order_by('-created_at')

        writer = csv.writer(response)
        writer.writerow([
            '计划编号', '计划名称', '木材种类', '计划采购量(kg)', '预期单价(元/kg)',
            '预算金额(元)', '需求日期', '意向供应商', '状态', '申请人',
            '审批人', '审批日期', '执行进度(%)', '已到货量(kg)', '创建时间'
        ])

        for plan in plans:
            writer.writerow([
                plan.plan_no,
                plan.plan_name,
                plan.get_wood_species_display(),
                plan.total_weight,
                plan.expected_price or '',
                plan.total_budget or '',
                plan.required_date.strftime('%Y-%m-%d') if plan.required_date else '',
                plan.supplier.name if plan.supplier else '',
                plan.get_status_display(),
                plan.applicant or '',
                plan.approver or '',
                plan.approval_date.strftime('%Y-%m-%d') if plan.approval_date else '',
                plan.execution_rate,
                plan.arrival_weight,
                plan.created_at.strftime('%Y-%m-%d %H:%M'),
            ])

    elif report_type == 'order':
        response['Content-Disposition'] = 'attachment; filename="purchase_orders.csv"'
        orders = PurchaseOrder.objects.select_related('supplier', 'purchase_plan').all().order_by('-order_date')

        writer = csv.writer(response)
        writer.writerow([
            '订单编号', '所属计划', '供应商', '木材种类', '订购重量(kg)',
            '单价(元/kg)', '订单金额(元)', '付款方式', '预计交货日期',
            '状态', '下单日期', '采购员', '已到货量(kg)', '到货进度(%)'
        ])

        for order in orders:
            writer.writerow([
                order.order_no,
                order.purchase_plan.plan_no if order.purchase_plan else '',
                order.supplier.name,
                order.get_wood_species_display(),
                order.ordered_weight,
                order.unit_price,
                order.total_amount or '',
                order.get_payment_terms_display(),
                order.expected_delivery_date.strftime('%Y-%m-%d') if order.expected_delivery_date else '',
                order.get_status_display(),
                order.order_date.strftime('%Y-%m-%d') if order.order_date else '',
                order.buyer or '',
                order.arrived_weight,
                order.arrival_rate,
            ])

    elif report_type == 'arrival':
        response['Content-Disposition'] = 'attachment; filename="purchase_arrivals.csv"'
        arrivals = PurchaseArrival.objects.select_related(
            'purchase_order__supplier', 'purchase_order__purchase_plan', 'material_batch'
        ).all().order_by('-arrival_date')

        writer = csv.writer(response)
        writer.writerow([
            '到货单号', '采购订单', '供应商', '到货时间', '送货重量(kg)',
            '验收重量(kg)', '拒收重量(kg)', '实测含水率(%)', '检验结果',
            '质量等级', '检验员', '仓管员', '关联原料批次'
        ])

        for arrival in arrivals:
            writer.writerow([
                arrival.arrival_no,
                arrival.purchase_order.order_no,
                arrival.purchase_order.supplier.name,
                arrival.arrival_date.strftime('%Y-%m-%d %H:%M') if arrival.arrival_date else '',
                arrival.delivered_weight,
                arrival.accepted_weight,
                arrival.rejected_weight,
                arrival.moisture_content or '',
                arrival.get_inspection_result_display(),
                arrival.get_quality_grade_display() if arrival.quality_grade else '',
                arrival.inspector or '',
                arrival.warehouse_keeper or '',
                arrival.material_batch.batch_no if arrival.material_batch else '',
            ])

    return response


def export_cost_csv(request):
    report_type = request.GET.get('type', 'batch_cost')

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')

    if report_type == 'batch_cost':
        response['Content-Disposition'] = 'attachment; filename="batch_costs.csv"'
        costs = BatchCost.objects.select_related('batch', 'batch__kiln').all().order_by('-calculate_date')

        writer = csv.writer(response)
        writer.writerow([
            '成本编号', '烧炭批次', '炭窑', '计算时间', '原料成本(元)', '人工成本(元)',
            '燃料成本(元)', '电力成本(元)', '设备折旧(元)', '维护成本(元)',
            '其他成本(元)', '总成本(元)', '成炭重量(kg)', '单位成本(元/kg)',
            '销售单价(元/kg)', '销售收入(元)', '利润(元)', '利润率(%)'
        ])

        for cost in costs:
            writer.writerow([
                cost.cost_no,
                cost.batch.batch_no,
                cost.batch.kiln.name,
                cost.calculate_date.strftime('%Y-%m-%d %H:%M') if cost.calculate_date else '',
                cost.material_cost,
                cost.labor_cost,
                cost.fuel_cost,
                cost.electricity_cost,
                cost.depreciation_cost,
                cost.maintenance_cost,
                cost.other_cost,
                cost.total_cost or '',
                cost.charcoal_weight or '',
                cost.unit_cost or '',
                cost.selling_price or '',
                cost.sales_amount or '',
                cost.profit or '',
                cost.profit_rate or '',
            ])

    elif report_type == 'profit':
        response['Content-Disposition'] = 'attachment; filename="profit_analysis.csv"'
        costs = BatchCost.objects.select_related('batch', 'batch__rating').filter(
            total_cost__isnull=False
        ).order_by('-calculate_date')

        writer = csv.writer(response)
        writer.writerow([
            '批次编号', '成炭重量(kg)', '总成本(元)', '单位成本(元/kg)',
            '销售单价(元/kg)', '销售收入(元)', '利润(元)', '利润率(%)',
            '质量等级', '出窑日期'
        ])

        grade_display = dict(KilnRating.GRADE_CHOICES)

        for cost in costs:
            grade = ''
            if hasattr(cost.batch, 'rating'):
                grade = grade_display.get(cost.batch.rating.grade, cost.batch.rating.grade)
            writer.writerow([
                cost.batch.batch_no,
                cost.charcoal_weight or '',
                cost.total_cost,
                cost.unit_cost or '',
                cost.selling_price or '',
                cost.sales_amount or '',
                cost.profit or '',
                cost.profit_rate or '',
                grade,
                cost.batch.finish_date.strftime('%Y-%m-%d') if cost.batch.finish_date else '',
            ])

    return response


def export_price_comparison_csv(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="price_comparison.csv"'

    history = SupplierPriceHistory.objects.select_related('supplier').all().order_by('-quote_date')

    writer = csv.writer(response)
    writer.writerow([
        '供应商', '木材种类', '报价(元/kg)', '报价日期', '最小订量(kg)',
        '有效期至', '质量等级', '联系人', '备注'
    ])

    for record in history:
        writer.writerow([
            record.supplier.name,
            record.get_wood_species_display(),
            record.price,
            record.quote_date.strftime('%Y-%m-%d') if record.quote_date else '',
            record.min_order_qty or '',
            record.valid_until.strftime('%Y-%m-%d') if record.valid_until else '',
            record.get_quality_grade_display() if record.quality_grade else '',
            record.contact_person or '',
            record.notes or '',
        ])

    return response


def recipe_list(request):
    recipes = FiringRecipe.objects.all()
    status_filter = request.GET.get('status', '')
    species_filter = request.GET.get('wood_species', '')
    grade_filter = request.GET.get('target_grade', '')
    search = request.GET.get('search', '')

    if status_filter:
        recipes = recipes.filter(status=status_filter)
    if species_filter:
        recipes = recipes.filter(wood_species=species_filter)
    if grade_filter:
        recipes = recipes.filter(target_grade=grade_filter)
    if search:
        recipes = recipes.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )

    total_recipes = recipes.count()
    active_recipes = recipes.filter(status='active').count()

    context = {
        'recipes': recipes,
        'status_filter': status_filter,
        'species_filter': species_filter,
        'grade_filter': grade_filter,
        'search': search,
        'total_recipes': total_recipes,
        'active_recipes': active_recipes,
        'status_choices': FiringRecipe.RECIPE_STATUS,
        'wood_species_choices': FiringRecipe.WOOD_SPECIES,
        'grade_choices': FiringRecipe.TARGET_GRADE,
    }
    return render(request, 'kiln_app/recipe_list.html', context)


def recipe_detail(request, pk):
    recipe = get_object_or_404(FiringRecipe, pk=pk)
    stages = recipe.stages.order_by('stage_order')
    batches = recipe.batches.select_related('rating').order_by('-ignition_date')[:20]

    try:
        stats = recipe.statistics
    except RecipeStatistics.DoesNotExist:
        stats = calculate_recipe_statistics(recipe)

    deviations = RecipeDeviationRecord.objects.filter(
        batch__recipe=recipe
    ).select_related('batch').order_by('-record_time')[:20]

    deviation_by_type = {}
    for d in deviations:
        dtype = d.deviation_type
        if dtype not in deviation_by_type:
            deviation_by_type[dtype] = {'count': 0, 'severe': 0}
        deviation_by_type[dtype]['count'] += 1
        if d.deviation_level == 'severe':
            deviation_by_type[dtype]['severe'] += 1

    context = {
        'recipe': recipe,
        'stages': stages,
        'batches': batches,
        'stats': stats,
        'deviations': deviations,
        'deviation_by_type': deviation_by_type,
    }
    return render(request, 'kiln_app/recipe_detail.html', context)


def recipe_create(request):
    if request.method == 'POST':
        form = FiringRecipeForm(request.POST)
        if form.is_valid():
            recipe = form.save()
            messages.success(request, '烧制配方创建成功！')
            return redirect('kiln_app:recipe_detail', pk=recipe.pk)
    else:
        form = FiringRecipeForm()
    return render(request, 'kiln_app/recipe_form.html', {'form': form, 'action': '创建'})


def recipe_edit(request, pk):
    recipe = get_object_or_404(FiringRecipe, pk=pk)
    if request.method == 'POST':
        form = FiringRecipeForm(request.POST, instance=recipe)
        if form.is_valid():
            form.save()
            messages.success(request, '烧制配方更新成功！')
            return redirect('kiln_app:recipe_detail', pk=recipe.pk)
    else:
        form = FiringRecipeForm(instance=recipe)
    return render(request, 'kiln_app/recipe_form.html', {'form': form, 'action': '编辑', 'recipe': recipe})


def recipe_delete(request, pk):
    recipe = get_object_or_404(FiringRecipe, pk=pk)
    try:
        recipe.delete()
        messages.success(request, '烧制配方已删除！')
    except Exception as e:
        messages.error(request, f'删除失败：{str(e)}')
    return redirect('kiln_app:recipe_list')


def recipe_stage_create(request, recipe_pk):
    recipe = get_object_or_404(FiringRecipe, pk=recipe_pk)
    if request.method == 'POST':
        form = RecipeStageForm(request.POST, recipe=recipe)
        if form.is_valid():
            stage = form.save(commit=False)
            stage.recipe = recipe
            stage.save()
            messages.success(request, '配方阶段添加成功！')
            return redirect('kiln_app:recipe_detail', pk=recipe.pk)
    else:
        form = RecipeStageForm(recipe=recipe)
    return render(request, 'kiln_app/recipe_stage_form.html', {
        'form': form, 'recipe': recipe, 'action': '添加阶段'
    })


def recipe_stage_edit(request, pk):
    stage = get_object_or_404(RecipeStage.objects.select_related('recipe'), pk=pk)
    recipe = stage.recipe
    if request.method == 'POST':
        form = RecipeStageForm(request.POST, instance=stage, recipe=recipe)
        if form.is_valid():
            form.save()
            messages.success(request, '配方阶段更新成功！')
            return redirect('kiln_app:recipe_detail', pk=recipe.pk)
    else:
        form = RecipeStageForm(instance=stage, recipe=recipe)
    return render(request, 'kiln_app/recipe_stage_form.html', {
        'form': form, 'recipe': recipe, 'stage': stage, 'action': '编辑阶段'
    })


def recipe_stage_delete(request, pk):
    stage = get_object_or_404(RecipeStage.objects.select_related('recipe'), pk=pk)
    recipe_pk = stage.recipe.pk
    stage.delete()
    messages.success(request, '配方阶段已删除！')
    return redirect('kiln_app:recipe_detail', pk=recipe_pk)


def recipe_deviation_list(request):
    deviations = RecipeDeviationRecord.objects.select_related(
        'batch', 'recipe_stage'
    ).all()
    type_filter = request.GET.get('deviation_type', '')
    level_filter = request.GET.get('deviation_level', '')
    is_resolved_filter = request.GET.get('is_resolved', '')

    if type_filter:
        deviations = deviations.filter(deviation_type=type_filter)
    if level_filter:
        deviations = deviations.filter(deviation_level=level_filter)
    if is_resolved_filter:
        deviations = deviations.filter(is_resolved=(is_resolved_filter == 'true'))

    normal_count = deviations.filter(deviation_level='normal').count()
    slight_count = deviations.filter(deviation_level='slight').count()
    moderate_count = deviations.filter(deviation_level='moderate').count()
    severe_count = deviations.filter(deviation_level='severe').count()

    context = {
        'deviations': deviations,
        'type_filter': type_filter,
        'level_filter': level_filter,
        'is_resolved_filter': is_resolved_filter,
        'normal_count': normal_count,
        'slight_count': slight_count,
        'moderate_count': moderate_count,
        'severe_count': severe_count,
        'type_choices': RecipeDeviationRecord.DEVIATION_TYPE,
        'level_choices': RecipeDeviationRecord.DEVIATION_LEVEL,
    }
    return render(request, 'kiln_app/recipe_deviation_list.html', context)


def recipe_deviation_resolve(request, pk):
    deviation = get_object_or_404(RecipeDeviationRecord.objects.select_related('batch'), pk=pk)
    if request.method == 'POST':
        form = RecipeDeviationResolveForm(request.POST, instance=deviation)
        if form.is_valid():
            deviation = form.save(commit=False)
            if deviation.is_resolved and not deviation.resolved_time:
                deviation.resolved_time = timezone.now()
            deviation.save()
            messages.success(request, '偏差处理完成！')
            return redirect('kiln_app:recipe_deviation_list')
    else:
        form = RecipeDeviationResolveForm(instance=deviation)
    return render(request, 'kiln_app/recipe_deviation_resolve.html', {
        'form': form, 'deviation': deviation
    })


def recipe_analysis(request):
    species_filter = request.GET.get('wood_species', '')
    grade_filter = request.GET.get('target_grade', '')

    recipes = FiringRecipe.objects.filter(status='active')
    if species_filter:
        recipes = recipes.filter(wood_species=species_filter)
    if grade_filter:
        recipes = recipes.filter(target_grade=grade_filter)

    for recipe in recipes:
        try:
            recipe.statistics
        except RecipeStatistics.DoesNotExist:
            calculate_recipe_statistics(recipe)

    comparison_data = get_recipe_comparison_data(
        recipe_ids=list(recipes.values_list('id', flat=True))
    )

    species_stats = {}
    grade_stats = {}
    total_recipes = recipes.count()
    for recipe in recipes:
        species_label = recipe.get_wood_species_display()
        grade_label = recipe.get_target_grade_display()
        if species_label not in species_stats:
            species_stats[species_label] = {'count': 0}
        species_stats[species_label]['count'] += 1
        if grade_label not in grade_stats:
            grade_stats[grade_label] = {'count': 0}
        grade_stats[grade_label]['count'] += 1

    for label, data in species_stats.items():
        data['percentage'] = round(data['count'] / total_recipes * 100, 1) if total_recipes > 0 else 0
    for label, data in grade_stats.items():
        data['percentage'] = round(data['count'] / total_recipes * 100, 1) if total_recipes > 0 else 0

    context = {
        'comparison_data': comparison_data,
        'species_filter': species_filter,
        'grade_filter': grade_filter,
        'wood_species_choices': FiringRecipe.WOOD_SPECIES,
        'grade_choices': FiringRecipe.TARGET_GRADE,
        'species_stats': species_stats,
        'grade_stats': grade_stats,
    }
    return render(request, 'kiln_app/recipe_analysis.html', context)


def batch_recipe_apply(request, batch_pk):
    batch = get_object_or_404(Batch, pk=batch_pk)
    if request.method == 'POST':
        recipe_id = request.POST.get('recipe_id')
        if recipe_id:
            recipe = get_object_or_404(FiringRecipe, pk=recipe_id)
            batch.recipe = recipe
            batch.save()
            messages.success(request, f'已套用配方：{recipe.name}')
        return redirect('kiln_app:batch_detail', pk=batch.pk)

    recipes = FiringRecipe.objects.filter(status='active').order_by('code')
    current_recipe = batch.recipe
    suggestions = suggest_recipe(
        wood_species=batch.material_type if batch.material_type else None
    )

    context = {
        'batch': batch,
        'recipes': recipes,
        'current_recipe': current_recipe,
        'suggestions': suggestions,
    }
    return render(request, 'kiln_app/batch_recipe_apply.html', context)


def batch_recipe_check(request, pk):
    batch = get_object_or_404(Batch.objects.select_related('recipe'), pk=pk)
    if not batch.recipe:
        messages.warning(request, '该批次未套用配方，请先套用配方！')
        return redirect('kiln_app:batch_recipe_apply', batch_pk=pk)

    deviations = check_recipe_deviations(batch)
    expected_stage = batch.expected_recipe_stage
    progress_percent = batch.recipe_progress_percent

    severe_count = sum(1 for d in deviations if d.deviation_level == 'severe')
    moderate_count = sum(1 for d in deviations if d.deviation_level == 'moderate')
    slight_count = sum(1 for d in deviations if d.deviation_level == 'slight')
    has_severe = severe_count > 0
    has_moderate = moderate_count > 0

    deviation_history = RecipeDeviationRecord.objects.filter(
        batch=batch
    ).order_by('-record_time')[:50]

    if request.method == 'POST':
        saved = save_recipe_deviations(batch)
        messages.success(request, f'已保存 {len(saved)} 条偏差记录')
        return redirect('kiln_app:batch_detail', pk=pk)

    context = {
        'batch': batch,
        'deviations': deviations,
        'expected_stage': expected_stage,
        'progress_percent': progress_percent,
        'severe_count': severe_count,
        'moderate_count': moderate_count,
        'slight_count': slight_count,
        'has_severe': has_severe,
        'has_moderate': has_moderate,
        'deviation_history': deviation_history,
    }
    return render(request, 'kiln_app/batch_recipe_check.html', context)

