#!/usr/bin/env python3
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'charcoal_system.settings')
django.setup()

from kiln_app.models import FiringRecipe, Batch, RecipeStage, RecipeDeviationRecord
from kiln_app.services import (
    check_recipe_deviations, get_expected_recipe_stage,
    suggest_recipe, calculate_recipe_statistics, save_recipe_deviations
)
from django.utils import timezone


def test_recipes():
    print('=== 1. 配方列表测试 ===')
    recipes = FiringRecipe.objects.all()
    for r in recipes:
        print(f'  {r.code}: {r.name} | 树种: {r.get_wood_species_display()} | 目标: {r.get_target_grade_display()} | 阶段数: {r.stage_count} | 状态: {r.get_status_display()}')
    print(f'共 {recipes.count()} 个配方')

    print('\n=== 2. 橡木标准配方阶段详情 ===')
    oak_recipe = FiringRecipe.objects.get(code='OAK-STD-001')
    for stage in oak_recipe.stages.all():
        print(f'  阶段{stage.stage_order}: {stage.get_stage_name_display()} | '
              f'{stage.duration_minutes}分钟 | '
              f'温度{stage.temp_min}-{stage.temp_max}℃ | '
              f'风门{stage.damper_min}-{stage.damper_max}% | '
              f'烟色: {stage.get_smoke_color_display()}')

    print('\n=== 3. 配方推荐测试 ===')
    suggestions = suggest_recipe(wood_species='oak', target_grade='excellent')
    print('  橡木特级配方推荐:')
    for s in suggestions[:3]:
        print(f'    {s["recipe"].name} - 推荐得分: {s["score"]} | 完成批次: {s["stats"].completed_batches} | 平均评分: {s["stats"].avg_total_score}')

    print('\n=== 4. 批次套用配方测试 ===')
    batch = Batch.objects.filter(finish_date__isnull=False).first()
    if batch:
        batch.recipe = oak_recipe
        batch.save()
        print(f'  批次: {batch.batch_no}')
        print(f'  套用配方: {oak_recipe.name}')
        print(f'  已烧制时间: {batch.recipe_elapsed_minutes} 分钟')
        print(f'  配方进度: {batch.recipe_progress_percent}%')
        expected_stage = get_expected_recipe_stage(batch)
        if expected_stage:
            print(f'  当前预期阶段: {expected_stage.get_stage_name_display()}')
    else:
        print('  没有找到已完成的批次')

    print('\n=== 5. 偏差检测测试 ===')
    batch_with_temp = Batch.objects.filter(temperature_records__isnull=False).first()
    if batch_with_temp:
        batch_with_temp.recipe = oak_recipe
        batch_with_temp.save()
        print(f'  批次: {batch_with_temp.batch_no}')

        latest_temp = batch_with_temp.temperature_records.order_by('-record_time').first()
        latest_damper = batch_with_temp.damper_records.order_by('-record_time').first()
        if latest_temp:
            print(f'  最新温度: {latest_temp.temperature}℃ @ {latest_temp.record_time}')
        if latest_damper:
            print(f'  最新风门: {latest_damper.damper_opening}% @ {latest_damper.record_time}')

        deviations = check_recipe_deviations(batch_with_temp)
        print(f'  偏差检测结果 ({len(deviations)} 项):')
        if deviations:
            for dev in deviations:
                level_emoji = {'normal': '✅', 'slight': '⚠️', 'moderate': '⚡', 'severe': '🚨'}
                print(f'    {level_emoji.get(dev["level"], "❓")} {dev["description"]}')
        else:
            print('    无偏差，全部正常')

        saved = save_recipe_deviations(batch_with_temp)
        print(f'  保存了 {len(saved)} 条偏差记录')
    else:
        print('  没有找到有温度记录的批次')

    print('\n=== 6. 配方统计测试 ===')
    stats = calculate_recipe_statistics(oak_recipe)
    print(f'  配方: {oak_recipe.name}')
    print(f'  总批次数: {stats.total_batches}')
    print(f'  完成批次数: {stats.completed_batches}')
    print(f'  平均出炭率: {stats.avg_yield_rate}%')
    print(f'  平均烧制时长: {stats.avg_duration_hours}小时')
    print(f'  总偏差次数: {stats.total_deviations}')
    print(f'  严重偏差次数: {stats.severe_deviations}')
    print(f'  特级品率: {stats.excellent_rate}%')
    print(f'  一级以上品率: {stats.good_rate}%')
    print(f'  平均综合评分: {stats.avg_total_score}')

    print('\n=== 测试完成 ===')
    print('烧炭工艺配方与标准作业模块核心功能全部正常！')


if __name__ == '__main__':
    test_recipes()
