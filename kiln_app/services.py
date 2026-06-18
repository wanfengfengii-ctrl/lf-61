from django.utils import timezone
from .models import ProcessWarning


STAGE_TEMP_RANGES = {
    'drying': (0, 200),
    'precarbonization': (200, 400),
    'carbonization': (400, 700),
    'refining': (700, 900),
    'cooling': (0, 300),
}

STAGE_DAMPER_RANGES = {
    'drying': (60, 100),
    'precarbonization': (40, 80),
    'carbonization': (20, 60),
    'refining': (10, 40),
    'cooling': (0, 30),
}

STAGE_DISPLAY = {
    'drying': '干燥期（白烟）',
    'precarbonization': '预炭化（黄烟）',
    'carbonization': '炭化期（青烟）',
    'refining': '精炼期（淡烟/无烟）',
    'cooling': '冷却期',
    'unknown': '未知阶段',
}


def detect_burning_stage(batch):
    latest_temp = batch.temperature_records.order_by('-record_time').first()
    latest_damper = batch.damper_records.order_by('-record_time').first()
    latest_smoke = batch.smokestage_set.order_by('-record_time').first()

    if not latest_temp and not latest_smoke:
        return '未开始'

    if latest_smoke and latest_smoke.stage in ['abnormal_heavy_smoke', 'abnormal_no_smoke_early', 'abnormal_black_smoke']:
        normal_stages = ['drying', 'precarbonization', 'carbonization', 'refining', 'cooling']
        if latest_temp:
            temp = float(latest_temp.temperature)
            for stage in ['drying', 'precarbonization', 'carbonization', 'refining']:
                low, high = STAGE_TEMP_RANGES[stage]
                if low <= temp <= high:
                    return f'异常→推断应为{STAGE_DISPLAY[stage]}'
        return STAGE_DISPLAY.get(latest_smoke.stage, '异常状态')

    smoke_stage = latest_smoke.stage if latest_smoke else None

    if smoke_stage and smoke_stage in STAGE_DISPLAY:
        return STAGE_DISPLAY[smoke_stage]

    if latest_temp:
        temp = float(latest_temp.temperature)
        for stage in ['refining', 'carbonization', 'precarbonization', 'drying']:
            low, high = STAGE_TEMP_RANGES[stage]
            if low <= temp <= high:
                return STAGE_DISPLAY[stage]
        if temp > 900:
            return '超高温（异常）'
        return STAGE_DISPLAY['drying']

    return '未开始'


def generate_warnings(batch):
    warnings = []
    latest_temp = batch.temperature_records.order_by('-record_time').first()
    latest_damper = batch.damper_records.order_by('-record_time').first()
    latest_smoke = batch.smokestage_set.order_by('-record_time').first()

    if not latest_temp and not latest_damper and not latest_smoke:
        return warnings

    now = timezone.now()
    temp = float(latest_temp.temperature) if latest_temp else None
    damper = latest_damper.damper_opening if latest_damper else None
    smoke_stage = latest_smoke.stage if latest_smoke else None

    inferred_stage = _infer_stage_from_temp(temp)

    if smoke_stage and smoke_stage not in ['abnormal_heavy_smoke', 'abnormal_no_smoke_early', 'abnormal_black_smoke'] and inferred_stage:
        if smoke_stage != inferred_stage:
            warning = ProcessWarning(
                batch=batch,
                warning_time=now,
                warning_type='stage_mismatch',
                level='warning',
                detected_stage=inferred_stage,
                temperature=temp,
                damper_opening=damper,
                smoke_stage=smoke_stage,
                message=f'阶段不匹配：烟色记录为{STAGE_DISPLAY.get(smoke_stage, smoke_stage)}，'
                        f'但当前窑温{temp}℃更接近{STAGE_DISPLAY.get(inferred_stage, inferred_stage)}阶段，'
                        f'请核实烟色判断是否准确。',
            )
            warnings.append(warning)

    if temp is not None:
        if inferred_stage:
            low, high = STAGE_TEMP_RANGES.get(inferred_stage, (0, 1200))
            if temp < low * 0.7:
                warning = ProcessWarning(
                    batch=batch,
                    warning_time=now,
                    warning_type='temp_anomaly',
                    level='warning',
                    detected_stage=inferred_stage,
                    temperature=temp,
                    damper_opening=damper,
                    smoke_stage=smoke_stage or '',
                    message=f'温度偏低：当前{inferred_stage}阶段窑温仅{temp}℃，'
                            f'正常范围{low}-{high}℃，可能存在欠火风险。',
                )
                warnings.append(warning)
            elif temp > high * 1.15:
                warning = ProcessWarning(
                    batch=batch,
                    warning_time=now,
                    warning_type='temp_anomaly',
                    level='critical',
                    detected_stage=inferred_stage,
                    temperature=temp,
                    damper_opening=damper,
                    smoke_stage=smoke_stage or '',
                    message=f'温度偏高：当前{inferred_stage}阶段窑温达{temp}℃，'
                            f'超出正常范围{low}-{high}℃，存在过火风险！',
                )
                warnings.append(warning)

    if damper is not None and inferred_stage:
        low, high = STAGE_DAMPER_RANGES.get(inferred_stage, (0, 100))
        if damper > high * 1.3 and inferred_stage in ['carbonization', 'refining']:
            warning = ProcessWarning(
                batch=batch,
                warning_time=now,
                warning_type='damper_anomaly',
                level='warning',
                detected_stage=inferred_stage,
                temperature=temp,
                damper_opening=damper,
                smoke_stage=smoke_stage or '',
                message=f'风门开度过大：当前{inferred_stage}阶段风门开度{damper}%，'
                        f'建议范围{low}-{high}%，过大会导致进氧过多、温度难以控制。',
            )
            warnings.append(warning)
        elif damper < low * 0.5 and inferred_stage in ['drying', 'precarbonization']:
            warning = ProcessWarning(
                batch=batch,
                warning_time=now,
                warning_type='damper_anomaly',
                level='info',
                detected_stage=inferred_stage,
                temperature=temp,
                damper_opening=damper,
                smoke_stage=smoke_stage or '',
                message=f'风门开度偏小：当前{inferred_stage}阶段风门开度{damper}%，'
                        f'建议范围{low}-{high}%，过小可能导致排烟不畅。',
            )
            warnings.append(warning)

    if temp is not None and damper is not None and inferred_stage:
        if inferred_stage == 'carbonization' and temp > 600 and damper > 60:
            warning = ProcessWarning(
                batch=batch,
                warning_time=now,
                warning_type='combo_anomaly',
                level='critical',
                detected_stage=inferred_stage,
                temperature=temp,
                damper_opening=damper,
                smoke_stage=smoke_stage or '',
                message=f'组合异常：炭化期高温({temp}℃)配合大风门({damper}%)，'
                        f'进氧量过大极易导致过火灰化，请立即减小风门开度！',
            )
            warnings.append(warning)
        elif inferred_stage == 'drying' and temp < 100 and damper < 30:
            warning = ProcessWarning(
                batch=batch,
                warning_time=now,
                warning_type='combo_anomaly',
                level='warning',
                detected_stage=inferred_stage,
                temperature=temp,
                damper_opening=damper,
                smoke_stage=smoke_stage or '',
                message=f'组合异常：干燥期低温({temp}℃)配合小风门({damper}%)，'
                        f'排烟不畅可能延长干燥时间，建议适当开大风门。',
            )
            warnings.append(warning)

    if smoke_stage and smoke_stage in ['abnormal_heavy_smoke', 'abnormal_no_smoke_early', 'abnormal_black_smoke']:
        level = 'critical' if smoke_stage == 'abnormal_black_smoke' else 'warning'
        msg_map = {
            'abnormal_heavy_smoke': '异常浓烟：可能温度不足导致炭化不良（欠火风险），请检查风门和温度。',
            'abnormal_no_smoke_early': '过早无烟：可能温度过高导致过火，炭料有灰化风险，请降温检查。',
            'abnormal_black_smoke': '异常黑烟：燃烧不完全或焦油堆积，存在过火和安全隐患，请立即处理！',
        }
        warning = ProcessWarning(
            batch=batch,
            warning_time=now,
            warning_type='smoke_anomaly',
            level=level,
            detected_stage=inferred_stage or '',
            temperature=temp,
            damper_opening=damper,
            smoke_stage=smoke_stage,
            message=msg_map[smoke_stage],
        )
        warnings.append(warning)

    return warnings


def save_warnings(batch):
    warnings = generate_warnings(batch)
    for w in warnings:
        w.save()
    return warnings


def _infer_stage_from_temp(temp):
    if temp is None:
        return None
    for stage in ['drying', 'precarbonization', 'carbonization', 'refining']:
        low, high = STAGE_TEMP_RANGES[stage]
        if low <= temp <= high:
            return stage
    if temp > 900:
        return 'refining'
    return 'drying'
