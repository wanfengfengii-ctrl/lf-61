import os
import sys
import random
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'charcoal_system.settings')
import django
django.setup()

from django.utils import timezone
from kiln_app.models import (
    Kiln, Batch, TemperatureRecord, DamperRecord,
    SmokeStage, KilnRating
)


def seed_database():
    print('=' * 60)
    print('开始初始化测试数据...')
    print('=' * 60)

    Kiln.objects.all().delete()
    Batch.objects.all().delete()
    TemperatureRecord.objects.all().delete()
    DamperRecord.objects.all().delete()
    SmokeStage.objects.all().delete()
    KilnRating.objects.all().delete()

    print('\n1. 创建炭窑档案...')
    kilns_data = [
        {'name': '1号窑', 'location': '东区一号车间', 'capacity': 5000, 'status': 'active'},
        {'name': '2号窑', 'location': '东区一号车间', 'capacity': 5000, 'status': 'active'},
        {'name': '3号窑', 'location': '东区二号车间', 'capacity': 8000, 'status': 'idle'},
        {'name': '4号窑', 'location': '西区车间', 'capacity': 6000, 'status': 'maintenance'},
    ]
    kilns = []
    for kd in kilns_data:
        kiln = Kiln.objects.create(
            name=kd['name'],
            location=kd['location'],
            capacity=kd['capacity'],
            build_date=datetime(2022, 3, 15).date(),
            status=kd['status'],
            description=f'{kd["name"]}是传统土窑改造升级而来，配备自动化测温系统。'
        )
        kilns.append(kiln)
        print(f'   ✓ 创建: {kiln.name} - {kiln.get_status_display()}')

    print('\n2. 创建烧炭批次...')
    material_types = ['oak', 'pine', 'bamboo', 'fruitwood', 'mixed']
    operators = ['张师傅', '李师傅', '王师傅', '赵师傅']

    batches = []

    for i in range(5):
        kiln = kilns[i % 2]
        base_date = timezone.now() - timedelta(days=30 - i * 6)
        ignition = base_date - timedelta(hours=random.randint(40, 72))
        finish = base_date
        material_w = round(random.uniform(3500, 4800), 1)
        rate = random.uniform(0.15, 0.28)
        charcoal_w = round(material_w * rate, 1)

        batch = Batch.objects.create(
            batch_no=f'B{2024}{12:02d}{i+1:03d}',
            kiln=kiln,
            material_type=material_types[i % len(material_types)],
            material_weight=material_w,
            charcoal_weight=charcoal_w,
            ignition_date=ignition,
            finish_date=finish,
            operator=operators[i % len(operators)],
            notes=f'第{i+1}批次测试数据，采用传统升温工艺。'
        )
        batches.append(batch)
        print(f'   ✓ 批次 {batch.batch_no} | 窑:{batch.kiln.name} | 成炭率:{batch.yield_rate}%')

    ongoing_batch = Batch.objects.create(
        batch_no='B202412099',
        kiln=kilns[1],
        material_type='oak',
        material_weight=4500,
        ignition_date=timezone.now() - timedelta(hours=12),
        operator='张师傅',
        notes='正在烧制中，实时记录数据...'
    )
    batches.append(ongoing_batch)
    print(f'   ✓ 批次 {ongoing_batch.batch_no} | (进行中)')

    print('\n3. 创建温度记录...')
    temp_profile = [
        (0, 5, 25), (2, 6, 80), (4, 8, 120), (6, 10, 180),
        (8, 12, 260), (10, 14, 340), (14, 16, 420), (18, 20, 500),
        (22, 24, 560), (26, 28, 600), (30, 32, 640), (34, 36, 650),
        (38, 40, 640), (42, 44, 580), (46, 48, 450),
    ]

    for batch in batches[:5]:
        duration = (batch.finish_date - batch.ignition_date).total_seconds() / 3600
        num_points = int(duration / 3) + 1
        for j in range(num_points):
            hours = j * 3
            if hours > duration:
                hours = duration
            rec_time = batch.ignition_date + timedelta(hours=hours)
            if hours < 5:
                temp = round(random.uniform(25, 180), 1)
            elif hours < 12:
                temp = round(random.uniform(180, 400), 1)
            elif hours < 25:
                temp = round(random.uniform(400, 600), 1)
            elif hours < 40:
                temp = round(random.uniform(550, 680), 1)
            else:
                temp = round(random.uniform(300, 600), 1)
            TemperatureRecord.objects.create(
                batch=batch,
                record_time=rec_time,
                temperature=temp,
                position='窑中心' if j % 3 == 0 else ('上层' if j % 3 == 1 else '下层')
            )
        print(f'   ✓ 批次 {batch.batch_no}: {num_points} 条温度记录')

    for j in range(5):
        hours = j * 2.5
        rec_time = ongoing_batch.ignition_date + timedelta(hours=hours)
        temp = round(random.uniform(25, 180), 1)
        TemperatureRecord.objects.create(
            batch=ongoing_batch,
            record_time=rec_time,
            temperature=temp,
            position='窑中心'
        )
    print(f'   ✓ 批次 {ongoing_batch.batch_no}: {5} 条温度记录（进行中）')

    print('\n4. 创建风门记录...')
    damper_profile = [
        (0, 100), (4, 80), (8, 70), (12, 60), (18, 50),
        (24, 45), (30, 40), (36, 35), (42, 30), (46, 20),
    ]

    for batch in batches[:5]:
        duration = (batch.finish_date - batch.ignition_date).total_seconds() / 3600
        for hours, opening in damper_profile:
            if hours <= duration:
                rec_time = batch.ignition_date + timedelta(hours=hours)
                DamperRecord.objects.create(
                    batch=batch,
                    record_time=rec_time,
                    damper_opening=opening,
                    damper_name='主风门',
                    reason=f'阶段调整：第{hours}小时'
                )
        print(f'   ✓ 批次 {batch.batch_no}: {len(damper_profile)} 条风门记录')

    for hours, opening in [(0, 100), (3, 85), (6, 75), (9, 65)]:
        rec_time = ongoing_batch.ignition_date + timedelta(hours=hours)
        DamperRecord.objects.create(
            batch=ongoing_batch,
            record_time=rec_time,
            damper_opening=opening,
            damper_name='主风门'
        )
    print(f'   ✓ 批次 {ongoing_batch.batch_no}: {4} 条风门记录（进行中）')

    print('\n5. 创建烟色阶段记录...')
    smoke_stages = [
        ('drying', 0, 8),
        ('precarbonization', 8, 18),
        ('carbonization', 18, 36),
        ('abnormal_heavy_smoke', 32, None),
        ('refining', 36, 46),
        ('cooling', 46, None),
    ]

    for batch in batches[:5]:
        duration = (batch.finish_date - batch.ignition_date).total_seconds() / 3600
        for stage, start_h, end_h in smoke_stages:
            actual_start = min(start_h, duration)
            rec_time = batch.ignition_date + timedelta(hours=actual_start)
            density = random.randint(3, 8)
            if 'abnormal' in stage:
                density = random.randint(8, 10)
            SmokeStage.objects.create(
                batch=batch,
                record_time=rec_time,
                stage=stage,
                smoke_density=density,
                notes=f'进入{stage}阶段'
            )
        print(f'   ✓ 批次 {batch.batch_no}: {len(smoke_stages)} 条烟色记录（含异常）')

    for stage, start_h, _ in [('drying', 0), ('precarbonization', 9)]:
        rec_time = ongoing_batch.ignition_date + timedelta(hours=start_h)
        SmokeStage.objects.create(
            batch=ongoing_batch,
            record_time=rec_time,
            stage=stage,
            smoke_density=random.randint(4, 7)
        )
    print(f'   ✓ 批次 {ongoing_batch.batch_no}: {2} 条烟色记录（进行中）')

    print('\n6. 创建出窑评级...')
    grades = ['excellent', 'good', 'medium', 'good', 'excellent']
    for i, batch in enumerate(batches[:5]):
        grade = grades[i]
        base_scores = {
            'excellent': (85, 100),
            'good': (70, 85),
            'medium': (60, 75),
            'poor': (40, 65),
            'reject': (0, 50),
        }
        low, high = base_scores[grade]
        KilnRating.objects.create(
            batch=batch,
            grade=grade,
            appearance_score=random.randint(low, high),
            hardness_score=random.randint(low, high),
            moisture_score=random.randint(low, high),
            ash_content_score=random.randint(low, high),
            evaluator=operators[(i + 1) % len(operators)],
            evaluation_date=batch.finish_date.date(),
            remarks=f'本批次{grade == "excellent" and "品质极佳" or grade == "good" and "品质优良" or "基本合格"}，各项指标{grade == "excellent" and "均达到特级标准" or grade == "good" and "符合一级标准" or "略有瑕疵但不影响使用"}。'
        )
        rating = batch.rating
        print(f'   ✓ 批次 {batch.batch_no}: {rating.get_grade_display()} | 综合分: {rating.total_score}')

    print('\n' + '=' * 60)
    print('测试数据初始化完成！统计摘要：')
    print(f'   炭窑档案: {Kiln.objects.count()} 条')
    print(f'   烧炭批次: {Batch.objects.count()} 条 (其中 {Batch.objects.filter(finish_date__isnull=True).count()} 条进行中)')
    print(f'   温度记录: {TemperatureRecord.objects.count()} 条')
    print(f'   风门记录: {DamperRecord.objects.count()} 条')
    print(f'   烟色记录: {SmokeStage.objects.count()} 条 (其中异常 {SmokeStage.objects.filter(is_normal=False).count()} 条)')
    print(f'   出窑评级: {KilnRating.objects.count()} 条')
    print('=' * 60)


if __name__ == '__main__':
    seed_database()
