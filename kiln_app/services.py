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


def get_expected_recipe_stage(batch):
    if not batch.recipe:
        return None
    stages = batch.recipe.stages.order_by('stage_order')
    if not stages.exists():
        return None

    elapsed = batch.recipe_elapsed_minutes
    if elapsed is None:
        return None

    cumulative_minutes = 0
    for stage in stages:
        cumulative_minutes += stage.duration_minutes
        if elapsed <= cumulative_minutes:
            return stage
    return stages.last()


SMOKE_COLOR_MAP = {
    'drying': 'white',
    'precarbonization': 'yellow',
    'carbonization': 'green',
    'refining': 'light',
    'cooling': 'none',
}

SMOKE_STAGE_MAP = {
    'white': '干燥期（白烟）',
    'yellow': '预炭化（黄烟）',
    'green': '炭化期（青烟）',
    'light': '精炼期（淡烟/无烟）',
    'none': '冷却期',
    'black': '异常黑烟',
}


def check_recipe_deviations(batch):
    deviations = []
    if not batch.recipe:
        return deviations

    expected_stage = get_expected_recipe_stage(batch)
    if not expected_stage:
        return deviations

    now = timezone.now()
    latest_temp = batch.temperature_records.order_by('-record_time').first()
    latest_damper = batch.damper_records.order_by('-record_time').first()
    latest_smoke = batch.smokestage_set.order_by('-record_time').first()

    if latest_temp:
        temp = float(latest_temp.temperature)
        temp_min = float(expected_stage.temp_min)
        temp_max = float(expected_stage.temp_max)
        temp_target = float(expected_stage.temp_target) if expected_stage.temp_target else (temp_min + temp_max) / 2

        temp_deviation = temp - temp_target
        temp_deviation_percent = abs(temp_deviation) / temp_target * 100 if temp_target > 0 else 0

        if temp < temp_min:
            level = 'severe' if temp < temp_min * 0.7 else 'moderate' if temp < temp_min * 0.9 else 'slight'
            deviations.append({
                'type': 'temperature',
                'level': level,
                'standard_value': temp_min,
                'actual_value': temp,
                'deviation_value': temp - temp_min,
                'deviation_percent': temp_deviation_percent,
                'description': f'温度偏低：当前{temp}℃，标准最低{temp_min}℃，偏低{round(temp_min - temp, 1)}℃',
                'stage': expected_stage,
            })
        elif temp > temp_max:
            level = 'severe' if temp > temp_max * 1.3 else 'moderate' if temp > temp_max * 1.15 else 'slight'
            deviations.append({
                'type': 'temperature',
                'level': level,
                'standard_value': temp_max,
                'actual_value': temp,
                'deviation_value': temp - temp_max,
                'deviation_percent': temp_deviation_percent,
                'description': f'温度偏高：当前{temp}℃，标准最高{temp_max}℃，偏高{round(temp - temp_max, 1)}℃',
                'stage': expected_stage,
            })

    if latest_damper:
        damper = latest_damper.damper_opening
        damper_min = expected_stage.damper_min
        damper_max = expected_stage.damper_max
        damper_target = expected_stage.damper_target if expected_stage.damper_target else (damper_min + damper_max) // 2

        damper_deviation = damper - damper_target
        damper_deviation_percent = abs(damper_deviation) / damper_target * 100 if damper_target > 0 else 0

        if damper < damper_min:
            level = 'severe' if damper < damper_min * 0.5 else 'moderate' if damper < damper_min * 0.7 else 'slight'
            deviations.append({
                'type': 'damper',
                'level': level,
                'standard_value': damper_min,
                'actual_value': damper,
                'deviation_value': damper - damper_min,
                'deviation_percent': damper_deviation_percent,
                'description': f'风门开度过小：当前{damper}%，标准最小{damper_min}%',
                'stage': expected_stage,
            })
        elif damper > damper_max:
            level = 'severe' if damper > damper_max * 1.5 else 'moderate' if damper > damper_max * 1.3 else 'slight'
            deviations.append({
                'type': 'damper',
                'level': level,
                'standard_value': damper_max,
                'actual_value': damper,
                'deviation_value': damper - damper_max,
                'deviation_percent': damper_deviation_percent,
                'description': f'风门开度过大：当前{damper}%，标准最大{damper_max}%',
                'stage': expected_stage,
            })

    if latest_smoke and expected_stage.smoke_color:
        smoke_stage = latest_smoke.stage
        expected_smoke = expected_stage.smoke_color

        actual_smoke_color = None
        if 'drying' in smoke_stage or 'white' in smoke_stage:
            actual_smoke_color = 'white'
        elif 'precarbonization' in smoke_stage or 'yellow' in smoke_stage:
            actual_smoke_color = 'yellow'
        elif 'carbonization' in smoke_stage or 'green' in smoke_stage:
            actual_smoke_color = 'green'
        elif 'refining' in smoke_stage or 'light' in smoke_stage or '淡' in smoke_stage:
            actual_smoke_color = 'light'
        elif 'cooling' in smoke_stage or 'none' in smoke_stage or '无烟' in smoke_stage:
            actual_smoke_color = 'none'
        elif 'black' in smoke_stage or '黑烟' in smoke_stage:
            actual_smoke_color = 'black'

        if actual_smoke_color and actual_smoke_color != expected_smoke:
            if actual_smoke_color == 'black':
                level = 'severe'
            else:
                level = 'moderate'
            deviations.append({
                'type': 'smoke',
                'level': level,
                'standard_value': 0,
                'actual_value': 0,
                'deviation_value': 0,
                'deviation_percent': 0,
                'description': f'烟色偏差：预期{SMOKE_STAGE_MAP.get(expected_smoke, expected_smoke)}，实际{latest_smoke.get_stage_display()}',
                'stage': expected_stage,
            })

    return deviations


def save_recipe_deviations(batch):
    deviations_data = check_recipe_deviations(batch)
    saved_deviations = []

    from .models import RecipeDeviationRecord
    for dev_data in deviations_data:
        deviation = RecipeDeviationRecord.objects.create(
            batch=batch,
            recipe_stage=dev_data.get('stage'),
            deviation_type=dev_data['type'],
            deviation_level=dev_data['level'],
            standard_value=dev_data['standard_value'],
            actual_value=dev_data['actual_value'],
            deviation_value=dev_data['deviation_value'],
            deviation_percent=round(dev_data['deviation_percent'], 2),
            description=dev_data['description'],
        )
        saved_deviations.append(deviation)

    return saved_deviations


def calculate_recipe_statistics(recipe):
    from .models import RecipeStatistics, KilnRating
    from django.db.models import Avg, Count

    batches = recipe.batches.all()
    completed_batches = batches.filter(finish_date__isnull=False)

    stats, created = RecipeStatistics.objects.get_or_create(recipe=recipe)

    stats.total_batches = batches.count()
    stats.completed_batches = completed_batches.count()

    yield_rates = []
    durations = []
    for b in completed_batches:
        if b.yield_rate:
            yield_rates.append(b.yield_rate)
        if b.duration_hours:
            durations.append(b.duration_hours)

    if yield_rates:
        stats.avg_yield_rate = round(sum(yield_rates) / len(yield_rates), 2)
    if durations:
        stats.avg_duration_hours = round(sum(durations) / len(durations), 2)

    from .models import RecipeDeviationRecord
    all_deviations = RecipeDeviationRecord.objects.filter(batch__recipe=recipe)
    stats.total_deviations = all_deviations.count()
    stats.severe_deviations = all_deviations.filter(deviation_level='severe').count()

    rated_batches = completed_batches.filter(rating__isnull=False)
    if rated_batches.exists():
        total_rated = rated_batches.count()
        excellent_count = rated_batches.filter(rating__grade='excellent').count()
        good_count = rated_batches.filter(rating__grade='good').count()

        stats.excellent_rate = round(excellent_count / total_rated * 100, 2) if total_rated > 0 else 0
        stats.good_rate = round((excellent_count + good_count) / total_rated * 100, 2) if total_rated > 0 else 0

        avg_score = KilnRating.objects.filter(batch__recipe=recipe).aggregate(
            avg_score=Avg('total_score')
        )['avg_score']
        if avg_score is not None:
            stats.avg_total_score = round(float(avg_score), 2)

    stats.save()
    return stats


def get_recipe_comparison_data(recipe_ids=None):
    from .models import FiringRecipe, RecipeStatistics

    recipes = FiringRecipe.objects.all()
    if recipe_ids:
        recipes = recipes.filter(id__in=recipe_ids)

    comparison_data = []
    for recipe in recipes:
        try:
            stats = recipe.statistics
        except RecipeStatistics.DoesNotExist:
            stats = calculate_recipe_statistics(recipe)

        comparison_data.append({
            'recipe': recipe,
            'stats': stats,
            'target_grade': recipe.get_target_grade_display(),
            'wood_species': recipe.get_wood_species_display(),
        })

    return comparison_data


def suggest_recipe(wood_species=None, kiln_type=None, target_grade=None):
    from .models import FiringRecipe, RecipeStatistics

    recipes = FiringRecipe.objects.filter(status='active')

    if wood_species:
        recipes = recipes.filter(wood_species=wood_species)
    if kiln_type:
        recipes = recipes.filter(kiln_type__icontains=kiln_type)
    if target_grade:
        recipes = recipes.filter(target_grade=target_grade)

    results = []
    for recipe in recipes:
        try:
            stats = recipe.statistics
        except RecipeStatistics.DoesNotExist:
            stats = calculate_recipe_statistics(recipe)

        score = 0
        if stats.completed_batches > 0:
            score += stats.completed_batches * 2
        if stats.avg_total_score:
            score += float(stats.avg_total_score) * 0.5
        if stats.severe_deviations > 0 and stats.total_deviations > 0:
            score -= (stats.severe_deviations / stats.total_deviations) * 20

        results.append({
            'recipe': recipe,
            'stats': stats,
            'score': round(score, 2),
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results
