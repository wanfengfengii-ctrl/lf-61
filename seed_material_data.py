import os
import django
import random
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'charcoal_system.settings')
django.setup()

from django.utils import timezone
from django.db.models import Sum
from kiln_app.models import (
    Supplier, RawMaterialBatch, MoistureTest,
    MaterialIssue, MaterialLoss, Batch
)

suppliers_data = [
    {'name': '东北林场木材有限公司', 'contact_person': '王经理', 'phone': '13800138001',
     'address': '黑龙江省哈尔滨市道里区林场路1号', 'wood_species': '橡木、松木',
     'supply_capacity': 50000, 'status': 'active', 'credit_rating': 95},
    {'name': '云南竹林开发集团', 'contact_person': '李主任', 'phone': '13800138002',
     'address': '云南省昆明市盘龙区竹业园区', 'wood_species': '竹材、杉木',
     'supply_capacity': 30000, 'status': 'active', 'credit_rating': 88},
    {'name': '山东果木种植基地', 'contact_person': '张场长', 'phone': '13800138003',
     'address': '山东省烟台市栖霞市果园区', 'wood_species': '苹果木、梨木',
     'supply_capacity': 20000, 'status': 'active', 'credit_rating': 92},
    {'name': '福建杂木收购站', 'contact_person': '陈老板', 'phone': '13800138004',
     'address': '福建省龙岩市新罗区木材市场', 'wood_species': '杂木、桦木',
     'supply_capacity': 15000, 'status': 'inactive', 'credit_rating': 75},
]

print('=' * 60)
print('开始填充原料管理模块测试数据')
print('=' * 60)

print('\n1. 创建供应商档案...')
suppliers = []
for data in suppliers_data:
    supplier, created = Supplier.objects.get_or_create(
        name=data['name'],
        defaults=data
    )
    suppliers.append(supplier)
    status = '✓ 创建' if created else '→ 已存在'
    print(f'  {status} {supplier.name}')

print('\n2. 创建原料批次...')
wood_species = ['oak', 'pine', 'bamboo', 'fruitwood', 'birch', 'fir', 'mixed']
quality_grades = ['excellent', 'good', 'good', 'medium', 'medium', 'good']
today = timezone.now().date()

for i in range(1, 11):
    supplier = random.choice(suppliers)
    species = random.choice(wood_species)
    days_ago = random.randint(0, 120)
    arrival_date = today - timedelta(days=days_ago)
    weight = round(random.uniform(500, 3000), 2)
    moisture = round(random.uniform(8, 35), 2)
    grade = quality_grades[i % len(quality_grades)]
    piece_count = random.randint(50, 300)

    batch_no = f'YL{today.year}{i:04d}'
    material, created = RawMaterialBatch.objects.get_or_create(
        batch_no=batch_no,
        defaults={
            'supplier': supplier,
            'wood_species': species,
            'arrival_date': arrival_date,
            'total_weight': weight,
            'moisture_content': moisture,
            'piece_count': piece_count,
            'average_diameter': round(random.uniform(10, 30), 1),
            'average_length': round(random.uniform(100, 300), 1),
            'storage_location': f'仓库{chr(65 + i % 5)}-{i % 10}',
            'quality_grade': grade,
            'inspection_notes': f'本批次木材品质{grade}，外观整齐，无明显虫蛀。',
            'inspector': '质检员李工',
            'inspection_date': arrival_date,
            'unit_price': round(random.uniform(1.5, 4.0), 2),
            'expected_shelf_life': 90,
        }
    )
    status = '✓ 创建' if created else '→ 已存在'
    print(f'  {status} {material.batch_no} | {material.get_wood_species_display()} | {material.total_weight}kg | 含水率{material.moisture_content}%')

    if created:
        for j in range(random.randint(1, 4)):
            test_days = random.randint(0, min(days_ago, 60))
            MoistureTest.objects.create(
                material_batch=material,
                test_date=timezone.now() - timedelta(days=test_days, hours=random.randint(0, 23)),
                moisture_content=round(random.uniform(max(5, moisture - 5), min(40, moisture + 5)), 2),
                test_method=random.choice(['快速水分测定仪', '烘干法', '电阻法']),
                sample_location=random.choice(['上层', '中层', '下层', '随机取样']),
                tester='质检员李工',
            )

print('\n3. 创建领料出库记录...')
batches = Batch.objects.all()
materials = RawMaterialBatch.objects.all()
operators = ['张师傅', '李师傅', '王师傅', '赵师傅']

for i in range(1, 16):
    material = random.choice(materials)
    batch = random.choice(batches) if batches else None
    max_weight = material.remaining_weight * 0.8
    if max_weight < 100:
        continue

    weight = round(random.uniform(100, max_weight), 2)
    issue_date = material.arrival_date + timedelta(days=random.randint(1, 30))

    issue, created = MaterialIssue.objects.get_or_create(
        issue_no=f'LL{today.year}{i:04d}',
        defaults={
            'material_batch': material,
            'batch': batch,
            'weight': weight,
            'issue_date': timezone.make_aware(timezone.datetime.combine(issue_date, timezone.datetime.min.time())),
            'requester': random.choice(operators),
            'stock_keeper': '仓管员小刘',
            'status': 'completed',
            'notes': f'用于{batch.batch_no if batch else "日常"}批次烧炭生产',
        }
    )
    if created:
        print(f'  ✓ 创建 {issue.issue_no} | 领用 {issue.weight}kg | 原料 {issue.material_batch.batch_no} | 用于 {batch.batch_no if batch else "未指定"}')

print('\n4. 创建损耗记录...')
loss_types = ['natural', 'spoilage', 'damage', 'other']
for i in range(1, 6):
    material = random.choice(materials)
    max_weight = material.remaining_weight * 0.1
    if max_weight < 10:
        continue

    weight = round(random.uniform(10, max_weight), 2)
    loss_date = material.arrival_date + timedelta(days=random.randint(10, 60))

    loss, created = MaterialLoss.objects.get_or_create(
        loss_no=f'SH{today.year}{i:04d}',
        defaults={
            'material_batch': material,
            'loss_type': random.choice(loss_types),
            'weight': weight,
            'loss_date': loss_date,
            'discovered_by': '仓管员小刘',
            'description': '库存盘点时发现部分木材受潮变质，已及时清理。',
            'handled': True,
            'handler': '仓库主管',
            'handling_method': '将变质木材清理出库，加强仓库通风管理。',
        }
    )
    if created:
        print(f'  ✓ 创建 {loss.loss_no} | 损耗 {loss.weight}kg | 类型 {loss.get_loss_type_display()} | 原料 {loss.material_batch.batch_no}')

print('\n' + '=' * 60)
print('测试数据填充完成！')
print('=' * 60)
print(f'\n统计信息：')
print(f'  供应商总数: {Supplier.objects.count()}')
print(f'  原料批次总数: {RawMaterialBatch.objects.count()}')
print(f'  含水率检测记录: {MoistureTest.objects.count()}')
print(f'  领料出库记录: {MaterialIssue.objects.count()}')
print(f'  损耗记录: {MaterialLoss.objects.count()}')
print(f'\n  原料总库存: {RawMaterialBatch.objects.aggregate(total=Sum("total_weight"))["total"] or 0}kg')
print(f'  已领用总量: {MaterialIssue.objects.filter(status="completed").aggregate(total=Sum("weight"))["total"] or 0}kg')
print(f'  损耗总量: {MaterialLoss.objects.aggregate(total=Sum("weight"))["total"] or 0}kg')
