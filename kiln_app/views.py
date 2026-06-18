import json
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta

from .models import (
    Kiln, Batch, TemperatureRecord, DamperRecord,
    SmokeStage, KilnRating
)
from .forms import (
    KilnForm, BatchForm, TemperatureRecordForm,
    DamperRecordForm, SmokeStageForm, KilnRatingForm
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
            return redirect('kiln_list')
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
            return redirect('kiln_list')
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
    return redirect('kiln_list')


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
            return redirect('batch_list')
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
            return redirect('batch_detail', pk=batch.pk)
    else:
        form = BatchForm(instance=batch)
    return render(request, 'kiln_app/batch_form.html', {'form': form, 'action': '编辑', 'batch': batch})


def batch_delete(request, pk):
    batch = get_object_or_404(Batch, pk=pk)
    batch.delete()
    messages.success(request, '烧炭批次已删除！')
    return redirect('batch_list')


def batch_detail(request, pk):
    batch = get_object_or_404(Batch.objects.select_related('kiln', 'rating'), pk=pk)
    temperature_records = batch.temperature_records.order_by('record_time')
    damper_records = batch.damper_records.order_by('record_time')
    smoke_stages = batch.smokestage_set.order_by('record_time')

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
            return redirect('batch_detail', pk=batch.pk)
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
            return redirect('batch_detail', pk=batch.pk)
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
    return redirect('batch_detail', pk=batch_pk)


def damper_create(request, batch_pk):
    batch = get_object_or_404(Batch, pk=batch_pk)
    if request.method == 'POST':
        form = DamperRecordForm(request.POST, batch=batch)
        if form.is_valid():
            rec = form.save(commit=False)
            rec.batch = batch
            rec.save()
            messages.success(request, '风门调整记录添加成功！')
            return redirect('batch_detail', pk=batch.pk)
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
            return redirect('batch_detail', pk=batch.pk)
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
    return redirect('batch_detail', pk=batch_pk)


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
            return redirect('batch_detail', pk=batch.pk)
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
            return redirect('batch_detail', pk=batch.pk)
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
    return redirect('batch_detail', pk=batch_pk)


def rating_create(request, batch_pk):
    batch = get_object_or_404(Batch, pk=batch_pk)
    if request.method == 'POST':
        form = KilnRatingForm(request.POST)
        if form.is_valid():
            rating = form.save(commit=False)
            rating.batch = batch
            rating.save()
            messages.success(request, '出窑评级完成！')
            return redirect('batch_detail', pk=batch.pk)
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
            return redirect('batch_detail', pk=batch.pk)
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
