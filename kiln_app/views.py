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
    SmokeStage, KilnRating, ProcessWarning
)
from .forms import (
    KilnForm, BatchForm, TemperatureRecordForm,
    DamperRecordForm, SmokeStageForm, KilnRatingForm
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
        batches = batches.filter(ignition_date__gte=date_from)
    if date_to:
        batches = batches.filter(ignition_date__lte=date_to)

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
        batches = batches.filter(ignition_date__gte=date_from)
    if date_to:
        batches = batches.filter(ignition_date__lte=date_to)

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
