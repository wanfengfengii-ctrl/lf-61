from django.urls import path
from . import views

app_name = 'kiln_app'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    path('kilns/', views.kiln_list, name='kiln_list'),
    path('kilns/create/', views.kiln_create, name='kiln_create'),
    path('kilns/<int:pk>/edit/', views.kiln_edit, name='kiln_edit'),
    path('kilns/<int:pk>/delete/', views.kiln_delete, name='kiln_delete'),

    path('batches/', views.batch_list, name='batch_list'),
    path('batches/create/', views.batch_create, name='batch_create'),
    path('batches/<int:pk>/edit/', views.batch_edit, name='batch_edit'),
    path('batches/<int:pk>/delete/', views.batch_delete, name='batch_delete'),
    path('batches/<int:pk>/', views.batch_detail, name='batch_detail'),

    path('batches/<int:batch_pk>/temperature/create/', views.temperature_create, name='temperature_create'),
    path('temperature/<int:pk>/edit/', views.temperature_edit, name='temperature_edit'),
    path('temperature/<int:pk>/delete/', views.temperature_delete, name='temperature_delete'),

    path('batches/<int:batch_pk>/damper/create/', views.damper_create, name='damper_create'),
    path('damper/<int:pk>/edit/', views.damper_edit, name='damper_edit'),
    path('damper/<int:pk>/delete/', views.damper_delete, name='damper_delete'),

    path('batches/<int:batch_pk>/smoke/create/', views.smoke_create, name='smoke_create'),
    path('smoke/<int:pk>/edit/', views.smoke_edit, name='smoke_edit'),
    path('smoke/<int:pk>/delete/', views.smoke_delete, name='smoke_delete'),

    path('batches/<int:batch_pk>/rating/create/', views.rating_create, name='rating_create'),
    path('batches/<int:batch_pk>/rating/edit/', views.rating_edit, name='rating_edit'),

    path('batches/<int:pk>/review/', views.batch_review, name='batch_review'),
    path('analysis/', views.batch_analysis, name='batch_analysis'),
    path('export/csv/', views.batch_export_csv, name='batch_export_csv'),

    path('yield-comparison/', views.yield_comparison, name='yield_comparison'),

    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/create/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:pk>/edit/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', views.supplier_delete, name='supplier_delete'),

    path('materials/', views.material_batch_list, name='material_batch_list'),
    path('materials/create/', views.material_batch_create, name='material_batch_create'),
    path('materials/<int:pk>/edit/', views.material_batch_edit, name='material_batch_edit'),
    path('materials/<int:pk>/delete/', views.material_batch_delete, name='material_batch_delete'),
    path('materials/<int:pk>/', views.material_batch_detail, name='material_batch_detail'),

    path('materials/<int:material_pk>/moisture/create/', views.moisture_test_create, name='moisture_test_create'),
    path('moisture/<int:pk>/edit/', views.moisture_test_edit, name='moisture_test_edit'),
    path('moisture/<int:pk>/delete/', views.moisture_test_delete, name='moisture_test_delete'),

    path('stock-ledger/', views.stock_ledger, name='stock_ledger'),

    path('issues/', views.material_issue_list, name='material_issue_list'),
    path('issues/create/', views.material_issue_create, name='material_issue_create'),
    path('issues/<int:pk>/edit/', views.material_issue_edit, name='material_issue_edit'),
    path('issues/<int:pk>/delete/', views.material_issue_delete, name='material_issue_delete'),

    path('losses/', views.material_loss_list, name='material_loss_list'),
    path('losses/create/', views.material_loss_create, name='material_loss_create'),
    path('losses/<int:pk>/edit/', views.material_loss_edit, name='material_loss_edit'),
    path('losses/<int:pk>/delete/', views.material_loss_delete, name='material_loss_delete'),

    path('warnings/', views.stock_warning_list, name='stock_warning_list'),
    path('warnings/<int:pk>/resolve/', views.stock_warning_resolve, name='stock_warning_resolve'),

    path('batches/<int:pk>/traceability/', views.batch_traceability, name='batch_traceability'),
    path('material-impact/', views.material_impact_analysis, name='material_impact_analysis'),
    path('material-usage-report/', views.material_usage_report, name='material_usage_report'),
    path('export/material-csv/', views.export_material_csv, name='export_material_csv'),

    # 采购计划
    path('purchase-plans/', views.purchase_plan_list, name='purchase_plan_list'),
    path('purchase-plans/create/', views.purchase_plan_create, name='purchase_plan_create'),
    path('purchase-plans/<int:pk>/edit/', views.purchase_plan_edit, name='purchase_plan_edit'),
    path('purchase-plans/<int:pk>/delete/', views.purchase_plan_delete, name='purchase_plan_delete'),
    path('purchase-plans/<int:pk>/', views.purchase_plan_detail, name='purchase_plan_detail'),
    path('purchase-plans/<int:pk>/approve/', views.purchase_plan_approve, name='purchase_plan_approve'),

    # 采购订单
    path('purchase-orders/', views.purchase_order_list, name='purchase_order_list'),
    path('purchase-orders/create/', views.purchase_order_create, name='purchase_order_create'),
    path('purchase-orders/<int:pk>/edit/', views.purchase_order_edit, name='purchase_order_edit'),
    path('purchase-orders/<int:pk>/delete/', views.purchase_order_delete, name='purchase_order_delete'),
    path('purchase-orders/<int:pk>/', views.purchase_order_detail, name='purchase_order_detail'),

    # 到货验收
    path('purchase-arrivals/', views.purchase_arrival_list, name='purchase_arrival_list'),
    path('purchase-arrivals/create/', views.purchase_arrival_create, name='purchase_arrival_create'),
    path('purchase-arrivals/<int:pk>/edit/', views.purchase_arrival_edit, name='purchase_arrival_edit'),
    path('purchase-arrivals/<int:pk>/delete/', views.purchase_arrival_delete, name='purchase_arrival_delete'),
    path('purchase-arrivals/<int:pk>/', views.purchase_arrival_detail, name='purchase_arrival_detail'),

    # 费用分摊
    path('cost-splits/', views.cost_split_list, name='cost_split_list'),
    path('cost-splits/create/', views.cost_split_create, name='cost_split_create'),
    path('cost-splits/<int:pk>/edit/', views.cost_split_edit, name='cost_split_edit'),
    path('cost-splits/<int:pk>/delete/', views.cost_split_delete, name='cost_split_delete'),

    # 批次成本
    path('batch-costs/', views.batch_cost_list, name='batch_cost_list'),
    path('batch-costs/create/', views.batch_cost_create, name='batch_cost_create'),
    path('batch-costs/<int:pk>/edit/', views.batch_cost_edit, name='batch_cost_edit'),
    path('batch-costs/<int:pk>/delete/', views.batch_cost_delete, name='batch_cost_delete'),
    path('batch-costs/<int:pk>/', views.batch_cost_detail, name='batch_cost_detail'),
    path('batch-costs/<int:cost_pk>/items/add/', views.batch_cost_item_add, name='batch_cost_item_add'),
    path('batch-cost-items/<int:pk>/delete/', views.batch_cost_item_delete, name='batch_cost_item_delete'),

    # 成本预警
    path('cost-warnings/', views.cost_warning_list, name='cost_warning_list'),
    path('cost-warnings/<int:pk>/resolve/', views.cost_warning_resolve, name='cost_warning_resolve'),
    path('cost-warning-dashboard/', views.cost_warning_dashboard, name='cost_warning_dashboard'),

    # 供应商价格
    path('supplier-price-comparison/', views.supplier_price_comparison, name='supplier_price_comparison'),
    path('supplier-price-history/', views.supplier_price_history_list, name='supplier_price_history_list'),
    path('supplier-price-history/create/', views.supplier_price_history_create, name='supplier_price_history_create'),
    path('supplier-price-history/<int:pk>/edit/', views.supplier_price_history_edit, name='supplier_price_history_edit'),
    path('supplier-price-history/<int:pk>/delete/', views.supplier_price_history_delete, name='supplier_price_history_delete'),

    # 成本分析
    path('cost-analysis/', views.cost_analysis, name='cost_analysis'),
    path('batch-profit-analysis/', views.batch_profit_analysis, name='batch_profit_analysis'),
    path('purchase-progress/', views.purchase_progress, name='purchase_progress'),

    # 报表导出
    path('export/purchase-csv/', views.export_purchase_csv, name='export_purchase_csv'),
    path('export/cost-csv/', views.export_cost_csv, name='export_cost_csv'),
    path('export/price-comparison-csv/', views.export_price_comparison_csv, name='export_price_comparison_csv'),
]
