#!/usr/bin/env python3
import os
import django
import random
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'charcoal_system.settings')
django.setup()

from django.utils import timezone
from kiln_app.models import (
    Supplier, PurchasePlan, PurchaseOrder, PurchaseArrival,
    PurchaseCostSplit, BatchCost, BatchCostItem, SupplierPriceHistory,
    RawMaterialBatch, Batch, KilnRating
)


def seed_purchase_data():
    print('=' * 60)
    print('正在生成采购与成本核算模块测试数据...')
    print('=' * 60)

    suppliers = list(Supplier.objects.filter(status='active'))
    if not suppliers:
        print('错误：没有可用的供应商数据，请先运行其他种子脚本。')
        return

    batches = list(Batch.objects.filter(finish_date__isnull=False))
    wood_species = ['oak', 'pine', 'bamboo', 'fruitwood', 'birch', 'fir']
    today = timezone.now().date()
    counter = {'plan': 0, 'order': 0, 'arrival': 0, 'split': 0, 'cost': 0, 'material': 0}

    print(f'\n1. 生成供应商价格历史记录...')
    for supplier in suppliers:
        for i, species in enumerate(random.sample(wood_species, random.randint(2, 4))):
            base_price = random.uniform(1.2, 3.5)
            for j in range(3):
                date = today - timedelta(days=30 * j + random.randint(0, 10))
                price_variation = random.uniform(-0.3, 0.3)
                SupplierPriceHistory.objects.create(
                    supplier=supplier,
                    wood_species=species,
                    price=round(base_price + price_variation, 2),
                    quote_date=date,
                    min_order_qty=random.randint(500, 2000),
                    quality_grade=random.choice(['excellent', 'good', 'medium']),
                    contact_person=supplier.contact_person,
                    notes=f'{dict(RawMaterialBatch.WOOD_SPECIES).get(species, species)}报价记录'
                )
    print(f'   ✓ 已生成 {SupplierPriceHistory.objects.count()} 条价格历史记录')

    print(f'\n2. 生成采购计划...')
    plan_names = ['Q3季度橡木采购计划', '下半年松木储备计划', '竹材补充采购', '果木精选采购', '桦木批量采购']
    for i in range(5):
        supplier = random.choice(suppliers)
        species = random.choice(wood_species)
        weight = random.randint(5000, 20000)
        price = random.uniform(1.5, 3.0)
        status = random.choice(['draft', 'approved', 'partial', 'completed', 'pending'])

        counter['plan'] += 1
        plan = PurchasePlan.objects.create(
            plan_no=f'PLAN{today.strftime("%Y%m%d")}{counter["plan"]:04d}',
            plan_name=plan_names[i],
            wood_species=species,
            total_weight=weight,
            expected_price=round(price, 2),
            required_date=today + timedelta(days=random.randint(7, 60)),
            supplier=supplier,
            status=status,
            applicant='张经理',
            approver='王总' if status in ['approved', 'partial', 'completed'] else '',
            approval_date=today - timedelta(days=random.randint(1, 10)) if status in ['approved', 'partial', 'completed'] else None,
            approval_notes='同意按计划执行' if status in ['approved', 'partial', 'completed'] else '',
            description=f'采购{RawMaterialBatch.WOOD_SPECIES[wood_species.index(species)][1]}用于生产'
        )

        if status in ['approved', 'partial', 'completed']:
            orders_count = random.randint(1, 3)
            for j in range(orders_count):
                order_weight = weight // orders_count if j < orders_count - 1 else weight - (weight // orders_count) * (orders_count - 1)
                order_status = 'completed' if status == 'completed' else random.choice(['confirmed', 'partial', 'completed'])

                counter['order'] += 1
                order = PurchaseOrder.objects.create(
                    order_no=f'PO{today.strftime("%Y%m%d")}{counter["order"]:04d}',
                    purchase_plan=plan,
                    supplier=supplier,
                    wood_species=species,
                    ordered_weight=order_weight,
                    unit_price=round(price + random.uniform(-0.2, 0.2), 2),
                    payment_terms=random.choice(['prepaid', 'delivery', 'credit']),
                    expected_delivery_date=today + timedelta(days=random.randint(3, 15)),
                    status=order_status,
                    order_date=today - timedelta(days=random.randint(5, 20)),
                    contact_person=supplier.contact_person,
                    contact_phone=supplier.phone,
                    buyer='李采购',
                    notes=f'第{j+1}批订单'
                )

                if order_status in ['partial', 'completed']:
                    arrival_count = random.randint(1, 2)
                    for k in range(arrival_count):
                        delivered = order_weight // arrival_count if k < arrival_count - 1 else order_weight - (order_weight // arrival_count) * (arrival_count - 1)
                        accepted = int(delivered * random.uniform(0.95, 1.0))
                        rejected = delivered - accepted

                        counter['arrival'] += 1
                        arrival = PurchaseArrival.objects.create(
                            arrival_no=f'ARR{today.strftime("%Y%m%d")}{counter["arrival"]:04d}',
                            purchase_order=order,
                            arrival_date=timezone.now() - timedelta(days=random.randint(2, 10)),
                            delivered_weight=delivered,
                            accepted_weight=accepted,
                            rejected_weight=rejected,
                            moisture_content=round(random.uniform(18, 35), 2),
                            inspection_result='qualified' if rejected == 0 else 'partial',
                            quality_grade=random.choice(['excellent', 'good', 'medium']),
                            inspector='刘检验',
                            inspection_notes='质量符合要求' if rejected == 0 else '部分不合格，已拒收',
                            supplier_delivery=random.choice(['王司机', '赵师傅', '陈物流']),
                            vehicle_no=f'京A{random.randint(10000, 99999)}',
                            warehouse_keeper='孙仓库',
                            notes=f'第{k+1}次到货'
                        )

                        counter['material'] += 1
                        material_batch = RawMaterialBatch.objects.create(
                            batch_no=f'MAT{today.strftime("%Y%m%d")}{counter["material"]:04d}',
                            supplier=supplier,
                            wood_species=species,
                            arrival_date=arrival.arrival_date.date(),
                            total_weight=accepted,
                            moisture_content=arrival.moisture_content,
                            piece_count=random.randint(100, 500),
                            average_diameter=round(random.uniform(10, 25), 1),
                            average_length=round(random.uniform(100, 300), 1),
                            storage_location=random.choice(['A区', 'B区', 'C区', 'D区']),
                            quality_grade=arrival.quality_grade,
                            inspection_notes=arrival.inspection_notes,
                            inspector=arrival.inspector,
                            inspection_date=arrival.arrival_date.date(),
                            unit_price=order.unit_price,
                            remarks=f'来自采购订单{order.order_no}'
                        )
                        arrival.material_batch = material_batch
                        arrival.save()

                        if random.choice([True, False]):
                            cost_types = [
                                ('transport', '运输费用', random.uniform(100, 500)),
                                ('loading', '装卸费用', random.uniform(50, 200)),
                                ('insurance', '保险费用', random.uniform(20, 100)),
                            ]
                            for ct, desc, amt in random.sample(cost_types, random.randint(1, 3)):
                                counter['split'] += 1
                                PurchaseCostSplit.objects.create(
                                    split_no=f'SPLIT{today.strftime("%Y%m%d")}{counter["split"]:04d}',
                                    purchase_arrival=arrival,
                                    cost_type=ct,
                                    cost_amount=round(amt, 2),
                                    cost_description=desc,
                                    payee=random.choice(['运输公司', '装卸队', '保险公司']),
                                    invoice_no=f'INV{random.randint(10000, 99999)}',
                                    is_allocated=True,
                                    allocated_date=timezone.now(),
                                    operator='李会计',
                                    notes=f'{desc}分摊'
                                )

    print(f'   ✓ 已生成 {PurchasePlan.objects.count()} 个采购计划')
    print(f'   ✓ 已生成 {PurchaseOrder.objects.count()} 个采购订单')
    print(f'   ✓ 已生成 {PurchaseArrival.objects.count()} 个到货验收单')
    print(f'   ✓ 已生成 {PurchaseCostSplit.objects.count()} 条费用分摊记录')
    new_materials = sum(1 for m in RawMaterialBatch.objects.all() if hasattr(m, 'purchase_arrival'))
    print(f'   ✓ 已生成 {new_materials} 个关联原料批次')

    print(f'\n3. 生成批次成本核算数据...')
    cost_batches = [b for b in batches if b.charcoal_weight and not hasattr(b, 'cost')]
    for i, batch in enumerate(cost_batches[:10]):
        material_cost = 0
        material_issues = batch.material_issues.filter(status='completed')
        for issue in material_issues:
            if issue.material_batch.unit_price:
                material_cost += float(issue.weight) * float(issue.material_batch.unit_price)

        labor_cost = random.uniform(200, 800)
        fuel_cost = random.uniform(100, 400)
        electricity_cost = random.uniform(50, 200)
        depreciation_cost = random.uniform(30, 100)
        other_cost = random.uniform(20, 100)
        total_cost = material_cost + labor_cost + fuel_cost + electricity_cost + depreciation_cost + other_cost

        selling_price = random.uniform(8, 15)
        sales_amount = float(batch.charcoal_weight) * selling_price
        profit = sales_amount - total_cost
        profit_rate = (profit / sales_amount * 100) if sales_amount > 0 else 0

        counter['cost'] += 1
        batch_cost = BatchCost.objects.create(
            cost_no=f'COST{today.strftime("%Y%m%d")}{counter["cost"]:04d}',
            batch=batch,
            calculate_date=timezone.now(),
            material_cost=round(material_cost, 2),
            labor_cost=round(labor_cost, 2),
            fuel_cost=round(fuel_cost, 2),
            electricity_cost=round(electricity_cost, 2),
            depreciation_cost=round(depreciation_cost, 2),
            other_cost=round(other_cost, 2),
            selling_price=round(selling_price, 2),
            cost_detail='自动核算成本',
            operator='李会计',
            notes='系统自动生成的成本核算数据'
        )

        cost_items = [
            ('material', '原料成本', material_cost, batch.material_weight, 'kg', batch_cost.material_cost / float(batch.material_weight) if batch.material_weight > 0 else 0),
            ('labor', '人工成本', labor_cost, 8, '工时', labor_cost / 8),
            ('fuel', '燃料成本', fuel_cost, 50, 'kg', fuel_cost / 50),
            ('electricity', '电力成本', electricity_cost, 100, '度', electricity_cost / 100),
        ]
        for ct, name, amt, qty, unit, up in cost_items:
            BatchCostItem.objects.create(
                batch_cost=batch_cost,
                cost_type=ct,
                item_name=name,
                amount=round(amt, 2),
                quantity=qty,
                unit=unit,
                unit_price=round(up, 4),
                description=f'{name}明细'
            )

    print(f'   ✓ 已生成 {BatchCost.objects.count()} 条批次成本核算记录')
    print(f'   ✓ 已生成 {BatchCostItem.objects.count()} 条成本明细记录')

    print(f'\n' + '=' * 60)
    print('采购与成本核算模块测试数据生成完成！')
    print('=' * 60)
    print(f'\n数据摘要：')
    print(f'  供应商价格历史: {SupplierPriceHistory.objects.count()} 条')
    print(f'  采购计划: {PurchasePlan.objects.count()} 个')
    print(f'  采购订单: {PurchaseOrder.objects.count()} 个')
    print(f'  到货验收: {PurchaseArrival.objects.count()} 个')
    print(f'  费用分摊: {PurchaseCostSplit.objects.count()} 条')
    print(f'  批次成本: {BatchCost.objects.count()} 条')
    print(f'  成本明细: {BatchCostItem.objects.count()} 条')


if __name__ == '__main__':
    seed_purchase_data()
