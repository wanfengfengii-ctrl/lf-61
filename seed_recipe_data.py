#!/usr/bin/env python3
import os
import django
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'charcoal_system.settings')
django.setup()

from django.utils import timezone
from kiln_app.models import FiringRecipe, RecipeStage, RecipeStatistics
from kiln_app.services import calculate_recipe_statistics


def seed_recipes():
    recipes_data = [
        {
            'code': 'OAK-STD-001',
            'name': '橡木标准烧制配方',
            'wood_species': 'oak',
            'kiln_type': '立式炭窑',
            'target_grade': 'good',
            'target_yield_rate': 22.5,
            'total_duration_hours': 72.0,
            'ignition_duration_minutes': 45,
            'status': 'active',
            'version': '1.2',
            'description': '适用于橡木原料的标准烧制工艺，成品一级品率约70%',
            'created_by': '张师傅',
            'stages': [
                {'stage_order': 1, 'stage_name': 'ignition', 'duration_minutes': 180,
                 'temp_min': 0, 'temp_max': 150, 'temp_target': 100,
                 'damper_min': 60, 'damper_max': 100, 'damper_target': 80,
                 'smoke_color': 'white', 'operation_points': '点火后保持大风门，充分排烟，注意观察火焰颜色'},
                {'stage_order': 2, 'stage_name': 'drying', 'duration_minutes': 720,
                 'temp_min': 100, 'temp_max': 200, 'temp_target': 150,
                 'damper_min': 50, 'damper_max': 80, 'damper_target': 65,
                 'smoke_color': 'white', 'operation_points': '缓慢升温，充分干燥木材，避免开裂'},
                {'stage_order': 3, 'stage_name': 'precarbonization', 'duration_minutes': 600,
                 'temp_min': 200, 'temp_max': 400, 'temp_target': 300,
                 'damper_min': 30, 'damper_max': 60, 'damper_target': 45,
                 'smoke_color': 'yellow', 'operation_points': '进入预炭化阶段，黄烟开始排出，逐步关小风门'},
                {'stage_order': 4, 'stage_name': 'carbonization', 'duration_minutes': 900,
                 'temp_min': 400, 'temp_max': 700, 'temp_target': 550,
                 'damper_min': 15, 'damper_max': 40, 'damper_target': 25,
                 'smoke_color': 'green', 'operation_points': '炭化主期，青烟缭绕，稳定温度，控制进氧量'},
                {'stage_order': 5, 'stage_name': 'refining', 'duration_minutes': 480,
                 'temp_min': 700, 'temp_max': 850, 'temp_target': 780,
                 'damper_min': 5, 'damper_max': 20, 'damper_target': 10,
                 'smoke_color': 'light', 'operation_points': '精炼期，淡烟或无烟，提高炭品质，注意防止过火'},
                {'stage_order': 6, 'stage_name': 'cooling', 'duration_minutes': 1440,
                 'temp_min': 50, 'temp_max': 300, 'temp_target': 100,
                 'damper_min': 0, 'damper_max': 10, 'damper_target': 0,
                 'smoke_color': 'none', 'operation_points': '封窑冷却，确保完全熄灭后再出窑'},
            ]
        },
        {
            'code': 'OAK-PREMIUM-001',
            'name': '橡木特级品精制配方',
            'wood_species': 'oak',
            'kiln_type': '立式炭窑',
            'target_grade': 'excellent',
            'target_yield_rate': 18.0,
            'total_duration_hours': 96.0,
            'ignition_duration_minutes': 60,
            'status': 'active',
            'version': '2.0',
            'description': '高端橡木炭配方，长时间慢烧，特级品率高',
            'created_by': '李师傅',
            'stages': [
                {'stage_order': 1, 'stage_name': 'ignition', 'duration_minutes': 240,
                 'temp_min': 0, 'temp_max': 120, 'temp_target': 80,
                 'damper_min': 70, 'damper_max': 100, 'damper_target': 85,
                 'smoke_color': 'white', 'operation_points': '文火慢点火，均匀受热'},
                {'stage_order': 2, 'stage_name': 'drying', 'duration_minutes': 1080,
                 'temp_min': 80, 'temp_max': 180, 'temp_target': 130,
                 'damper_min': 55, 'damper_max': 75, 'damper_target': 60,
                 'smoke_color': 'white', 'operation_points': '充分干燥，去除水分'},
                {'stage_order': 3, 'stage_name': 'precarbonization', 'duration_minutes': 720,
                 'temp_min': 180, 'temp_max': 380, 'temp_target': 280,
                 'damper_min': 35, 'damper_max': 55, 'damper_target': 40,
                 'smoke_color': 'yellow', 'operation_points': '缓慢升温预炭化'},
                {'stage_order': 4, 'stage_name': 'carbonization', 'duration_minutes': 1200,
                 'temp_min': 380, 'temp_max': 650, 'temp_target': 520,
                 'damper_min': 20, 'damper_max': 35, 'damper_target': 25,
                 'smoke_color': 'green', 'operation_points': '长时间炭化，确保炭化均匀'},
                {'stage_order': 5, 'stage_name': 'refining', 'duration_minutes': 720,
                 'temp_min': 650, 'temp_max': 800, 'temp_target': 720,
                 'damper_min': 8, 'damper_max': 18, 'damper_target': 12,
                 'smoke_color': 'light', 'operation_points': '高温精炼，提升品质'},
                {'stage_order': 6, 'stage_name': 'cooling', 'duration_minutes': 1800,
                 'temp_min': 30, 'temp_max': 250, 'temp_target': 80,
                 'damper_min': 0, 'damper_max': 5, 'damper_target': 0,
                 'smoke_color': 'none', 'operation_points': '缓慢冷却，防止开裂'},
            ]
        },
        {
            'code': 'PINE-FAST-001',
            'name': '松木快速烧制配方',
            'wood_species': 'pine',
            'kiln_type': '卧式炭窑',
            'target_grade': 'medium',
            'target_yield_rate': 25.0,
            'total_duration_hours': 48.0,
            'ignition_duration_minutes': 30,
            'status': 'active',
            'version': '1.0',
            'description': '松木快速烧制工艺，产量高，适合工业用炭',
            'created_by': '王师傅',
            'stages': [
                {'stage_order': 1, 'stage_name': 'ignition', 'duration_minutes': 120,
                 'temp_min': 0, 'temp_max': 180, 'temp_target': 120,
                 'damper_min': 70, 'damper_max': 100, 'damper_target': 90,
                 'smoke_color': 'white', 'operation_points': '快速点火升温'},
                {'stage_order': 2, 'stage_name': 'drying', 'duration_minutes': 360,
                 'temp_min': 120, 'temp_max': 220, 'temp_target': 180,
                 'damper_min': 50, 'damper_max': 80, 'damper_target': 65,
                 'smoke_color': 'white', 'operation_points': '快速干燥'},
                {'stage_order': 3, 'stage_name': 'precarbonization', 'duration_minutes': 360,
                 'temp_min': 220, 'temp_max': 420, 'temp_target': 320,
                 'damper_min': 35, 'damper_max': 55, 'damper_target': 45,
                 'smoke_color': 'yellow', 'operation_points': '快速预炭化'},
                {'stage_order': 4, 'stage_name': 'carbonization', 'duration_minutes': 540,
                 'temp_min': 420, 'temp_max': 680, 'temp_target': 550,
                 'damper_min': 20, 'damper_max': 40, 'damper_target': 30,
                 'smoke_color': 'green', 'operation_points': '高温快速炭化'},
                {'stage_order': 5, 'stage_name': 'refining', 'duration_minutes': 240,
                 'temp_min': 680, 'temp_max': 800, 'temp_target': 750,
                 'damper_min': 10, 'damper_max': 25, 'damper_target': 15,
                 'smoke_color': 'light', 'operation_points': '短时间精炼'},
                {'stage_order': 6, 'stage_name': 'cooling', 'duration_minutes': 720,
                 'temp_min': 50, 'temp_max': 300, 'temp_target': 120,
                 'damper_min': 0, 'damper_max': 15, 'damper_target': 5,
                 'smoke_color': 'none', 'operation_points': '快速冷却出窑'},
            ]
        },
        {
            'code': 'BAMBOO-ECO-001',
            'name': '竹炭环保烧制配方',
            'wood_species': 'bamboo',
            'kiln_type': '立式炭窑',
            'target_grade': 'good',
            'target_yield_rate': 20.0,
            'total_duration_hours': 60.0,
            'ignition_duration_minutes': 40,
            'status': 'draft',
            'version': '0.9',
            'description': '竹炭烧制配方，吸附性能好，正在测试中',
            'created_by': '赵师傅',
            'stages': [
                {'stage_order': 1, 'stage_name': 'ignition', 'duration_minutes': 150,
                 'temp_min': 0, 'temp_max': 130, 'temp_target': 90,
                 'damper_min': 65, 'damper_max': 95, 'damper_target': 80,
                 'smoke_color': 'white', 'operation_points': '文火点燃竹料'},
                {'stage_order': 2, 'stage_name': 'drying', 'duration_minutes': 540,
                 'temp_min': 90, 'temp_max': 190, 'temp_target': 140,
                 'damper_min': 50, 'damper_max': 75, 'damper_target': 60,
                 'smoke_color': 'white', 'operation_points': '充分干燥竹材水分'},
                {'stage_order': 3, 'stage_name': 'precarbonization', 'duration_minutes': 480,
                 'temp_min': 190, 'temp_max': 380, 'temp_target': 280,
                 'damper_min': 30, 'damper_max': 55, 'damper_target': 40,
                 'smoke_color': 'yellow', 'operation_points': '预炭化阶段'},
                {'stage_order': 4, 'stage_name': 'carbonization', 'duration_minutes': 720,
                 'temp_min': 380, 'temp_max': 650, 'temp_target': 500,
                 'damper_min': 15, 'damper_max': 35, 'damper_target': 25,
                 'smoke_color': 'green', 'operation_points': '炭化竹材，形成多孔结构'},
                {'stage_order': 5, 'stage_name': 'refining', 'duration_minutes': 360,
                 'temp_min': 650, 'temp_max': 780, 'temp_target': 720,
                 'damper_min': 5, 'damper_max': 15, 'damper_target': 10,
                 'smoke_color': 'light', 'operation_points': '活化精炼，增强吸附性'},
                {'stage_order': 6, 'stage_name': 'cooling', 'duration_minutes': 1350,
                 'temp_min': 40, 'temp_max': 280, 'temp_target': 100,
                 'damper_min': 0, 'damper_max': 8, 'damper_target': 0,
                 'smoke_color': 'none', 'operation_points': '密封冷却，保护竹炭结构'},
            ]
        },
        {
            'code': 'MIXED-STANDARD-001',
            'name': '杂木通用标准配方',
            'wood_species': 'mixed',
            'kiln_type': '通用炭窑',
            'target_grade': 'medium',
            'target_yield_rate': 23.0,
            'total_duration_hours': 66.0,
            'ignition_duration_minutes': 35,
            'status': 'active',
            'version': '1.1',
            'description': '适用于各种杂木的通用配方，性价比高',
            'created_by': '张师傅',
            'stages': [
                {'stage_order': 1, 'stage_name': 'ignition', 'duration_minutes': 150,
                 'temp_min': 0, 'temp_max': 160, 'temp_target': 110,
                 'damper_min': 60, 'damper_max': 100, 'damper_target': 85,
                 'smoke_color': 'white', 'operation_points': '点火升温阶段'},
                {'stage_order': 2, 'stage_name': 'drying', 'duration_minutes': 600,
                 'temp_min': 100, 'temp_max': 210, 'temp_target': 160,
                 'damper_min': 45, 'damper_max': 75, 'damper_target': 60,
                 'smoke_color': 'white', 'operation_points': '干燥阶段'},
                {'stage_order': 3, 'stage_name': 'precarbonization', 'duration_minutes': 540,
                 'temp_min': 200, 'temp_max': 400, 'temp_target': 300,
                 'damper_min': 30, 'damper_max': 55, 'damper_target': 40,
                 'smoke_color': 'yellow', 'operation_points': '预炭化阶段'},
                {'stage_order': 4, 'stage_name': 'carbonization', 'duration_minutes': 780,
                 'temp_min': 380, 'temp_max': 680, 'temp_target': 530,
                 'damper_min': 18, 'damper_max': 40, 'damper_target': 28,
                 'smoke_color': 'green', 'operation_points': '主炭化阶段'},
                {'stage_order': 5, 'stage_name': 'refining', 'duration_minutes': 360,
                 'temp_min': 680, 'temp_max': 820, 'temp_target': 750,
                 'damper_min': 8, 'damper_max': 20, 'damper_target': 12,
                 'smoke_color': 'light', 'operation_points': '精炼阶段'},
                {'stage_order': 6, 'stage_name': 'cooling', 'duration_minutes': 1500,
                 'temp_min': 40, 'temp_max': 300, 'temp_target': 100,
                 'damper_min': 0, 'damper_max': 10, 'damper_target': 0,
                 'smoke_color': 'none', 'operation_points': '冷却阶段'},
            ]
        },
    ]

    created_count = 0
    for recipe_data in recipes_data:
        stages_data = recipe_data.pop('stages')
        recipe, created = FiringRecipe.objects.get_or_create(
            code=recipe_data['code'],
            defaults=recipe_data
        )
        if created:
            created_count += 1
            print(f'创建配方: {recipe.code} - {recipe.name}')

            for stage_data in stages_data:
                RecipeStage.objects.create(
                    recipe=recipe,
                    **stage_data
                )
            print(f'  添加 {len(stages_data)} 个工艺阶段')

            calculate_recipe_statistics(recipe)
        else:
            print(f'配方已存在: {recipe.code}')

    print(f'\n总共创建了 {created_count} 个配方')
    print(f'当前配方总数: {FiringRecipe.objects.count()}')
    print(f'启用配方数: {FiringRecipe.objects.filter(status="active").count()}')


if __name__ == '__main__':
    print('开始填充烧制配方数据...\n')
    seed_recipes()
    print('\n配方数据填充完成！')
