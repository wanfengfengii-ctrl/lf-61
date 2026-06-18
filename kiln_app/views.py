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
    StockLedger, MaterialIssue, MaterialLoss, StockWarning
)
from .forms import (
    KilnForm, BatchForm, TemperatureRecordForm,
    DamperRecordForm, SmokeStageForm, KilnRatingForm,
    SupplierForm, RawMaterialBatchForm, MoistureTestForm,
    MaterialIssueForm, MaterialLossForm, StockWarningResolveForm
)
from .services import generate_warnings, detect_burning_stage


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
