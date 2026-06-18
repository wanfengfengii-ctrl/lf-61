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
]
