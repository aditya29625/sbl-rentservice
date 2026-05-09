from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    # Core URLs
    path('', views.home, name='home'),
    path('home/', views.home, name='home'),
    path('login/', views.login_user, name='login'),
    path('register/', views.register_user, name='register'),  
    path('logout/', views.logout_user, name='logout'),
    
    # Dashboard and Profile URLs
    path('dashboard/', views.dashboard, name='dashboard'),
    path('kyc-document/<str:doc_type>/', views.download_kyc_document, name='download_kyc_document'),
    # path('profile/', views.manage_profile, name='manage_profile'),
    path('properties/', views.property_list, name='property_list'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('my-wishlist/', views.my_wishlist, name='my_wishlist'),
    path('remove-property-image/<int:image_id>/', views.remove_property_image, name='remove_property_image'),
    path('remove-property-video/<int:property_id>/', views.remove_property_video, name='remove_property_video'),

    
    # Property URLs
    path('properties/', views.property_list, name='property_list'),
    path('property/<int:property_id>/', views.property_detail, name='property_detail'),
    path('property/add/', views.manage_property, name='add_property'),
    path('property/edit/<int:property_id>/', views.manage_property, name='edit_property'),
    path('property/delete/<int:property_id>/', views.delete_property, name='delete_property'),
    
    # Booking URLs
    path('book/<int:property_id>/', views.book_property, name='book_property'),
    path('booking/<int:booking_id>/', views.booking_confirmation, name='booking_confirmation'),
    path('reservation/<int:booking_id>/', views.reservation_details, name='reservation_detail'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    # path('vendor/bookings/', views.vendor_booking_requests, name='vendor_booking_requests'),
    # path('vendor/bookings/<int:booking_id>/approve/', views.approve_booking, name='approve_booking'),
    # path('vendor/bookings/<int:booking_id>/decline/', views.decline_booking, name='decline_booking'),
    path("payments/verify/", views.payment_verify, name="payment_verify"),
    path('cancel-booking/<int:booking_id>/', views.cancel_booking, name='cancel_booking'),
    path('reservation/<int:booking_id>/', views.reservation_details, name='reservation_details'),
    
    # Wishlist URLs
    path('wishlist/toggle/<int:property_id>/', views.toggle_wishlist, name='toggle_wishlist'),
    path('my-wishlist/', views.my_wishlist, name='my_wishlist'),
    path('properties/', views.property_list, name='property_list'),
    path('my-wishlist/', views.my_wishlist, name='my_wishlist'),
    path('wishlist/toggle/<int:property_id>/', views.toggle_wishlist, name='toggle_wishlist'),
    
    # Authentication URLs (password reset)
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(
             template_name='accounts/password_reset.html'
         ), 
         name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='accounts/password_reset_done.html'
         ), 
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='accounts/password_reset_confirm.html'
         ), 
         name='password_reset_confirm'),
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='accounts/password_reset_complete.html'
         ), 
         name='password_reset_complete'),
]

if settings.DEBUG and hasattr(settings, 'MEDIA_ROOT') and str(settings.MEDIA_URL).startswith('/'):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)