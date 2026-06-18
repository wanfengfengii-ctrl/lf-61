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
]
