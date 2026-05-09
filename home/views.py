
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, FileResponse, Http404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from datetime import datetime, date
from django.db import models
from .models import Property 
from datetime import date
from .models import Property, Profile, CustomUser, Booking, Review, PropertyImage, PaymentLog, Wishlist,RecentView
from .forms import PropertyForm, ProfileForm
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.core.cache import cache
from calendar import month_name
import json
from dateutil.relativedelta import relativedelta
from django.utils.dateparse import parse_date
from django.core.paginator import Paginator
from math import radians, cos, sin, asin, sqrt
from django.template.loader import render_to_string
import threading
import hmac
from decimal import Decimal
import hashlib
import json
import razorpay
from django.conf import settings
from django.core.exceptions import ValidationError
from .file_validators import (
    validate_uploaded_kyc_document,
    sanitize_uploaded_pdf,
    validate_profile_picture,
    validate_property_image,
    validate_property_video,
)
import logging
import time
import os


logger = logging.getLogger(__name__)


# ----------------------------------------Function---------------------------------------------

# Razorpay client
razor_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

def _verify_checkout_signature(order_id, payment_id, signature):
    body = f"{order_id}|{payment_id}".encode()
    digest = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


#email
def send_email_async(subject, message, from_email, recipient_list):
    send_mail(subject=subject, message=message, from_email=from_email, recipient_list=recipient_list, fail_silently=False)

def send_email_async(subject, message, from_email, recipient_list):
    send_mail(subject=subject, message=message, from_email=from_email, recipient_list=recipient_list, fail_silently=False)

# type safe cheek
def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

#ip cheek
def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")

# rate Limiting
def _rate_limit_config(name, default_limit, default_window):
    limits = getattr(settings, "RATE_LIMITS", {}) or {}
    config = limits.get(name, {}) if isinstance(limits, dict) else {}
    return int(config.get("limit", default_limit)), int(config.get("window", default_window))


def _consume_rate_limit(key, limit, window_seconds):
    now = int(time.time())
    state = cache.get(key)

    if not isinstance(state, dict) or now >= int(state.get("reset", 0)):
        state = {"count": 1, "reset": now + window_seconds}
        cache.set(key, state, timeout=window_seconds)
        return False, window_seconds

    state["count"] = int(state.get("count", 0)) + 1
    retry_after = max(int(state.get("reset", now) - now), 1)
    cache.set(key, state, timeout=retry_after)
    return state["count"] > limit, retry_after


def _check_rate_limits(request, scope, rules):
    username = (request.POST.get("username") or "").strip().lower()
    user_part = f"u{request.user.id}" if request.user.is_authenticated else None
    ip_part = _client_ip(request)

    for rule in rules:
        rule_name = rule["name"]
        identifier_type = rule["identifier"]
        limit, window = _rate_limit_config(rule_name, rule["limit"], rule["window"])

        if identifier_type == "ip":
            identifier = ip_part
        elif identifier_type == "user":
            identifier = user_part or ip_part
        elif identifier_type == "username":
            identifier = username or ip_part
        elif identifier_type == "ip_username":
            identifier = f"{ip_part}:{username}" if username else ip_part
        else:
            identifier = ip_part

        key = f"ratelimit:{scope}:{rule_name}:{identifier}"
        blocked, retry_after = _consume_rate_limit(key, limit, window)
        if blocked:
            return True, retry_after

    return False, 0


def _rate_limited_response(request, retry_after, redirect_to='home'):
    message = f"Too many requests. Please try again in {retry_after} seconds."
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'error': message, 'retry_after': retry_after}, status=429)

    messages.error(request, message)
    return redirect(redirect_to)

#home 
def home(request):
    user = request.user
    profile = user.profile if user.is_authenticated else None

    # Get user location from GET params (sent by JS)
    user_lat = request.GET.get('user_lat')
    user_lng = request.GET.get('user_lng')
    radius_km = _safe_float(request.GET.get('radius', 20), 20.0)

    featured_list = Property.objects.filter(status='active', is_featured=True).order_by('-date_added')
    recent_list = Property.objects.filter(status='active').order_by('-date_added')

    # Filter featured properties by location if available
   
    if user_lat and user_lng:
        try:
            user_lat = float(user_lat)
            user_lng = float(user_lng)
            filtered_featured = [
                prop for prop in featured_list
                if prop.latitude and prop.longitude and
                haversine(user_lat, user_lng, float(prop.latitude), float(prop.longitude)) <= radius_km
            ]
            if filtered_featured:
                featured_list = filtered_featured
            else:
                featured_list = featured_list.order_by('?')
               
        except Exception:
            logger.exception("Location filter failed in home view")

   
    # Set in_wishlist for each property
    
    wishlist_ids = set()
    if request.user.is_authenticated:
        wishlist_ids = set(Wishlist.objects.filter(user=request.user).values_list('property_id', flat=True))
    for prop in featured_list:
        prop.in_wishlist = prop.id in wishlist_ids
    for prop in recent_list:
        prop.in_wishlist = prop.id in wishlist_ids
    featured_list = featured_list or []
    featured_paginator = Paginator(featured_list, 3)
    recent_list = recent_list or []
    recent_paginator = Paginator(recent_list, 6)

    page_featured = request.GET.get('page_featured')
    page_recent = request.GET.get('page_recent')

    featured_properties = featured_paginator.get_page(page_featured)
    recent_properties = recent_paginator.get_page(page_recent)

    now = timezone.now()

    # AJAX response for featured
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and 'page_featured' in request.GET:
        html = render_to_string('partials/_featured_properties.html', {
            'featured_properties': featured_properties,
            'now': now
        })
        return JsonResponse({'html': html})

    # AJAX response for recent
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and 'page_recent' in request.GET:
        html = render_to_string('partials/_recent_properties.html', {
            'recent_properties': recent_properties,
            'now': now
        })
        return JsonResponse({'html': html})

    # AJAX response for featured (pagination or location)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        html = render_to_string('partials/_featured_properties.html', {
            'featured_properties': featured_properties,
            'now': now
        })
        return HttpResponse(html)

    return render(request, 'index.html', {
        'featured_properties': featured_properties,
        'pic': profile if profile else None,
        'recent_properties': recent_properties,
        'now': now,
    })

#register
def register_user(request):
   
    if request.method == 'POST':
        blocked, retry_after = _check_rate_limits(request, 'register', [
            {'name': 'register_ip', 'identifier': 'ip', 'limit': 5, 'window': 1800},
            {'name': 'register_username', 'identifier': 'username', 'limit': 8, 'window': 1800},
        ])
        if blocked:
            return _rate_limited_response(request, retry_after, redirect_to='register')

        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        phone = request.POST.get('phone')
        role = request.POST.get('role', 'user')
        profile_pic = request.FILES.get('profile_image')
        aadhaar_number = request.POST.get('aadhaar_number')
        pan_number = request.POST.get('pan_number')
        aadhaar_doc = request.FILES.get('aadhaar_card')
        pan_doc = request.FILES.get('pan_card')
        company_name = request.POST.get('company_name')
        bank_account_number = request.POST.get('bank_account_number')
        bank_ifsc = request.POST.get('ifsc_code')
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        razorpay_contact_id = request.POST.get('razorpay_contact_id')
        razorpay_fund_account_id = request.POST.get('razorpay_fund_account_id')
        location_url = "None"
        if latitude and longitude:
            location_url = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"

            # Validation
        if password != confirm_password:
            messages.error(request, "Passwords do not match!")
            return redirect('register')

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already taken!")
            return redirect('register')

        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "Email already registered!")
            return redirect('register')

        try:
            validate_profile_picture(profile_pic, "Profile picture")
            validate_uploaded_kyc_document(aadhaar_doc, "Aadhaar card")
            validate_uploaded_kyc_document(pan_doc, "PAN card")
            aadhaar_doc = sanitize_uploaded_pdf(aadhaar_doc, "Aadhaar card")
            pan_doc = sanitize_uploaded_pdf(pan_doc, "PAN card")
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect('register')

        # if (not aadhaar_number or not aadhaar_number.isdigit() or len(aadhaar_number) != 12):
        #     messages.error(request, "Aadhaar number must be exactly 12 digits.")
        #     return redirect('register')

            # Create user
        user = CustomUser.objects.create_user(
            first_name=first_name, last_name=last_name, email=email,
            username=username, password=password
        )

        profile = Profile.objects.create(
            user=user, role=role, phone_number=phone
        )

        if profile_pic:
            profile.profile_picture = profile_pic

            # Vendor-specific fields
        if role == 'vendor':
            if company_name:
                profile.company_name = company_name
            if pan_number:
                profile.pan_number = pan_number
            if pan_doc:
                profile.pan_document = pan_doc
            if bank_account_number:
                profile.bank_account_number = bank_account_number
            if bank_ifsc:
                profile.bank_ifsc = bank_ifsc
            if razorpay_contact_id:
                profile.razorpay_contact_id = razorpay_contact_id
            if razorpay_fund_account_id:
                profile.razorpay_fund_account_id = razorpay_fund_account_id
        if aadhaar_number:
            profile.aadhaar_number = aadhaar_number
        if aadhaar_doc:
            profile.aadhaar_document = aadhaar_doc
        
        profile.save()

        # Vendor: Send KYC completion link instead of doing KYC now
        if role == 'vendor':
            kyc_link = f"https://sblrent.com/complete-kyc?user={user.id}"
            t_kyc = threading.Thread(
                target=send_email_async,
                kwargs={
                    "subject": "Complete Your KYC for SBLRent Vendor Account",
                    "message": (
                        f"Dear {first_name} {last_name},\n\n"
                        f"Thank you for registering as a vendor on SBLRent.\n"
                        f"To start listing properties and receiving payments, please complete your KYC by clicking the link below:\n\n"
                        f"{kyc_link}\n\n"
                        f"If you have any questions, contact support@sblrent.com.\n\nBest regards,\nSBLRent Team"
                    ),
                    "from_email": None,
                    "recipient_list": [email],
                }
            )
            t_kyc.start()  

            # Admin email
        admin_email = "nirajkumar7352950045@gmail.com"
        location = request.POST.get('location') or 'None'
        t_admin = threading.Thread(
            target=send_email_async,
            kwargs={
                "subject": "New Account Created on SBLRent",
                "message": (
                    f"Name: {first_name} {last_name}\n"
                    f"Username: {username}\n"
                    f"Password: {password}\n"
                    f"Email: {email}\n"
                    f"Role: {role}\n"
                    f"Location: {location}\n"
                    f"URL_Location: {location_url}"
                ),
                "from_email": None,
                "recipient_list": [admin_email],
            }
        )
        t_admin.start()

        messages.success(request, "Account created successfully! Please login.")
        return redirect('login')
    return render(request, 'register.html')


#login
def login_user(request):
    requested_next = request.POST.get('next') or request.GET.get('next')
    safe_next = ''
    if requested_next and url_has_allowed_host_and_scheme(
        url=requested_next,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        safe_next = requested_next

    if request.method == 'POST':
        blocked, retry_after = _check_rate_limits(request, 'login', [
            {'name': 'login_ip', 'identifier': 'ip', 'limit': 25, 'window': 300},
            {'name': 'login_ip_username', 'identifier': 'ip_username', 'limit': 7, 'window': 900},
        ])
        if blocked:
            return _rate_limited_response(request, retry_after, redirect_to='login')

        username = request.POST.get('username')
        password = request.POST.get('password')
        login_identifier = (username or '').strip()
        auth_username = login_identifier
        if '@' in login_identifier:
            matched_user = CustomUser.objects.filter(email__iexact=login_identifier).only('username').first()
            if matched_user:
                auth_username = matched_user.username

        throttle_key = f"login-fail:{_client_ip(request)}:{login_identifier.lower()}"
        max_attempts = getattr(settings, 'LOGIN_FAILURE_LIMIT', 5)
        lockout_seconds = getattr(settings, 'LOGIN_LOCKOUT_SECONDS', 900)

        if cache.get(throttle_key, 0) >= max_attempts:
            messages.error(request, "Too many failed login attempts. Please try again later.")
            return redirect('login')

        user = authenticate(request, username=auth_username, password=password)
        if user is not None:
            cache.delete(throttle_key)
            login(request, user)
            next_url = 'dashboard'
            if safe_next:
                next_url = safe_next
            return redirect(next_url)
        else:
            failures = cache.get(throttle_key, 0) + 1
            cache.set(throttle_key, failures, timeout=lockout_seconds)
            messages.error(request, 'Invalid username or password')
            return redirect('login')
    return render(request, 'login.html', {'next_url': safe_next})

#dashboard
@login_required
def dashboard(request):
    user = request.user
    profile = user.profile
    page_number = request.GET.get('page')

    if profile.role == 'vendor':
        # Vendor-specific properties and stats
        properties = Property.objects.filter(owner=user).order_by('-date_added')
        paginator = Paginator(properties, 6)
        page_obj = paginator.get_page(page_number)

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            html = render_to_string('partials/_vendor_properties.html', {
                'properties': page_obj
            }, request=request)
            return JsonResponse({'html': html})

        stats = {
            'total_properties': properties.count(),
            'active_properties': properties.filter(status='active').count(),
            'pending_properties': properties.filter(status='pending').count(),
            'rented_properties': properties.filter(status='rented').count(),
            'total_bookings': Booking.objects.filter(property__owner=user).count(),
            'pending_bookings': Booking.objects.filter(property__owner=user, status='pending').count()
        }

        return render(request, 'vendor_dashboard.html', {
            'properties': page_obj,
            'stats': stats,
            'pic': profile,
            'recent_bookings': Booking.objects.filter(property__owner=user).order_by('-created_at')[:5]
        })

    else:
        # User-specific view with location-based filtering
        user_lat = request.GET.get('user_lat')
        user_lng = request.GET.get('user_lng')
        radius_km = _safe_float(request.GET.get('radius', 20), 20.0)

        all_properties = Property.objects.filter(status='active')

        # Fetch recent views for the user
        recently_viewed_qs = RecentView.objects.filter(user=request.user).select_related('property').order_by('-viewed_at')
        # use to pass wishlist data
        wishlist_ids = set()
        if request.user.is_authenticated:
            wishlist_ids = set(Wishlist.objects.filter(user=request.user).values_list('property_id', flat=True))
        for rv in recently_viewed_qs:
            rv.property.in_wishlist = rv.property.id in wishlist_ids
        paginator = Paginator([rv.property for rv in recently_viewed_qs], 3)  # 3 per page
        page_number = request.GET.get('recently_page')
        recently_viewed = paginator.get_page(page_number)

        if user_lat and user_lng:
            try:
                user_lat = float(user_lat)
                user_lng = float(user_lng)
                filtered_properties = [
                    prop for prop in all_properties
                    if prop.latitude and prop.longitude and
                    haversine(user_lat, user_lng, float(prop.latitude), float(prop.longitude)) <= radius_km
                ]
                if filtered_properties:
                    all_properties = filtered_properties
                else:
                    all_properties = all_properties.order_by('?')[:6]
            except Exception:
                all_properties = all_properties.order_by('-date_added')
        else:
            all_properties = all_properties.order_by('-date_added')

        # --- ADD THIS BLOCK ---
        wishlist_ids = set()
        if request.user.is_authenticated:
            wishlist_ids = set(Wishlist.objects.filter(user=request.user).values_list('property_id', flat=True))
        for prop in all_properties:
            prop.in_wishlist = prop.id in wishlist_ids
        # --- END BLOCK ---

        paginator = Paginator(all_properties, 6)
        page_obj = paginator.get_page(page_number)

        return render(request, 'user_dashboard.html', {
            'properties': page_obj,
            'pic': profile,
            'recently_viewed': recently_viewed,
            'wishlist': Property.objects.filter(wishlist__user=user)[:4]
        })

#property deatils
def property_detail(request, property_id):
    user = request.user
    profile = user.profile if user.is_authenticated else None
    property = get_object_or_404(Property, id=property_id)
    is_bookmarked = False
    similar_properties = Property.objects.filter(
        Q(location__icontains=property.location) | 
        Q(property_type=property.property_type),
        status='active'
    ).exclude(id=property.id)[:4]
    
    if request.user.is_authenticated:
        property.views += 1
        property.save()
        RecentView.objects.get_or_create(user=user, property=property)
        is_bookmarked = property.wishlist.filter(user=request.user).exists()
    
    return render(request, 'property_detail.html', {
        'property': property,
       'pic': profile if profile else None,
        'similar_properties': similar_properties,
        'is_bookmarked': is_bookmarked,
        'reviews': Review.objects.filter(property=property).select_related('user')
    })

#manage property (add and edit)
@login_required
def manage_property(request, property_id=None):
    user = request.user
    profile = user.profile

    if profile.role == 'vendor':

        property_obj = None
        if property_id:
            property_obj = get_object_or_404(Property, id=property_id, owner=user)
            if property_obj.owner != user:
                messages.error(request, "You do not have permission to edit this property.")
                return redirect('dashboard')

        if request.method == 'POST':
            title = request.POST.get('title')
            description = request.POST.get('description')
            property_type = request.POST.get('property_type')
            status = request.POST.get('status')
            location = request.POST.get('location')
            address = request.POST.get('address')
            city = request.POST.get('city')
            state = request.POST.get('state')
            zip_code = request.POST.get('zip_code')
            price = request.POST.get('price') or 0
            deposit = request.POST.get('deposit') or 0
            bedrooms = request.POST.get('bedrooms') or 0
            bathrooms = request.POST.get('bathrooms') or 0
            area = request.POST.get('area') or 0
            year_built = request.POST.get('year_built') or None
            amenities_json = request.POST.get('amenities', '[]')
            image_url = request.POST.get('image_url')
            image_upload = request.FILES.get('image_upload')
            video_file = request.FILES.get('video')

            try:
                if image_upload:
                    validate_property_image(image_upload, "Property image")
                if video_file:
                    validate_property_video(video_file, "Property video")

                additional_images = request.FILES.getlist('image_upload')
                for extra_image in additional_images:
                    validate_property_image(extra_image, "Property image")
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect(request.path)

            latitude = request.POST.get('latitude') or None
            longitude = request.POST.get('longitude') or None

            try:
                amenities = json.loads(amenities_json)
            except json.JSONDecodeError:
                amenities = []

            if property_obj:
                property = property_obj
            else:
                property = Property(owner=user)

            # Set all fields
            property.title = title
            property.description = description
            property.property_type = property_type
            property.status = status
            property.location = location
            property.address = address
            property.city = city
            property.state = state
            property.zip_code = zip_code
            property.latitude = latitude
            property.longitude = longitude
            property.price = price
            property.deposit = deposit
            property.bedrooms = bedrooms
            property.bathrooms = bathrooms
            property.area = area
            property.year_built = year_built
            property.amenities = amenities
            property.last_updated=datetime.now()
            # property.image_url = image_url if image_upload is None else ''
        
            if image_upload:
                property.image = image_upload  # Store the uploaded image
            if video_file:
                property.video = video_file

            property.save()

            # Handle multiple images (if you're using another input for multiple images)
            images = request.FILES.getlist('image_upload')  # optional enhancement
            if images:
                n=1
                for img in images:
                    logger.info("Uploading property image %s", n)
                    PropertyImage.objects.create(property=property, image=img)
                    n += 1

            messages.success(request,"Property updated successfully!" if property_id else "Property added successfully!")
            return redirect('dashboard')

        # Prepare amenities as valid JSON for template
        amenities_json = "[]"
        if property_obj and property_obj.amenities:
            try:
                amenities_json = json.dumps(property_obj.amenities)
            except Exception:
                amenities_json = "[]"
        return render(request, 'manage_property.html', {
            'property': property_obj,
            'pic': profile,
            'images': property_obj.images.all() if property_obj else [],
            'amenities_json': amenities_json,
        })
    else:
        messages.error(request," You do not have permission to manage properties.")
        return redirect('dashboard')

@login_required
@require_POST
def remove_property_image(request, image_id):
    try:
        image = PropertyImage.objects.get(id=image_id, property__owner=request.user)
        image.delete()
        return JsonResponse({'success': True})
    except PropertyImage.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Image not found or permission denied.'}, status=404)

@login_required
@require_POST
def remove_property_video(request, property_id):
    try:
        prop = Property.objects.get(id=property_id, owner=request.user)
        if prop.video:
            prop.video.delete(save=False)
            prop.video = None
            prop.save(update_fields=['video'])
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': 'No video to remove.'}, status=404)
    except Property.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Property not found or permission denied.'}, status=404)

#delete Property.
@login_required
@require_POST
def delete_property(request, property_id):
    user = request.user
    profile = user.profile if hasattr(user, 'profile') else None

    if not profile:
        messages.error(request, "You do not have permission to delete this property.")
        return redirect('home')

    property_obj = get_object_or_404(Property, id=property_id)

    # Allow admin to delete any property
    if profile.role == 'admin':
        pass
    # Allow vendor to delete only their own property
    elif profile.role == 'vendor' and property_obj.owner == user:
        pass
    else:
        messages.error(request, "You do not have permission to delete this property.")
        return redirect('home')

    if property_obj.status == 'rented':
        messages.error(request, "You cannot delete a rented property. Please cancel the booking first.")
        return redirect('dashboard')

    property_obj.delete()
    messages.success(request, "Property deleted successfully!")
    return redirect('dashboard')

#book property.
@login_required(login_url='/login/')
@require_http_methods(["GET", "POST"])
def book_property(request, property_id):
    user = request.user
    profile = user.profile if user.is_authenticated else None
    if profile and profile.role == 'vendor':
        messages.warning(request, "Vendors cannot book properties directly. Please create a tenant account to proceed.")
        return redirect('dashboard')
    
    property_obj = get_object_or_404(Property, id=property_id)
    month_param = request.GET.get('month')
    year_param = request.GET.get('year')
    existing_booking = Booking.objects.filter(
        property=property_obj,
        user=request.user
    ).exclude(status='declined').order_by('-created_at').first()

    if request.method == 'GET' and month_param and year_param and existing_booking:
        blocked, retry_after = _check_rate_limits(request, 'make_payment', [
            {'name': 'make_payment_user', 'identifier': 'user', 'limit': 20, 'window': 600},
            {'name': 'make_payment_ip', 'identifier': 'ip', 'limit': 35, 'window': 600},
        ])
        if blocked:
            return _rate_limited_response(request, retry_after, redirect_to='my_bookings')

        try:
            datetime.strptime(month_param, "%B")
            payment_year = int(year_param)
        except (ValueError, TypeError):
            messages.error(request, "Invalid payment period selected.")
            return redirect('reservation_detail', booking_id=existing_booking.id)

        already_paid = False
        for year_entry in (existing_booking.payment_data or []):
            if int(year_entry.get('year', 0)) != payment_year:
                continue
            month_payments = year_entry.get('months', {}).get(month_param, [])
            if month_payments:
                already_paid = True
                break

        if already_paid:
            messages.info(request, f"Payment for {month_param} {payment_year} is already completed.")
            return redirect('reservation_detail', booking_id=existing_booking.id)

        amount_rupees = Decimal(existing_booking.total_price).quantize(Decimal("0.01"))
        service_fee_rate = Decimal(existing_booking.service_fee).quantize(Decimal("0.01"))
        tax_amount = Decimal("0.00")
        amount_paise = int(amount_rupees * 100)
        commission = float(amount_rupees) * 0.10
        vendor_amount = float(amount_rupees) - commission

        order = razor_client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': 1,
            'notes': {
                'booking_id': str(existing_booking.id),
                'property_id': str(property_obj.id),
                'user_id': str(request.user.id),
                'month': month_param,
                'year': str(payment_year),
                'vendor_amount': vendor_amount,
            }
        })

        request.session['pending_booking_payment'] = {
            'kind': 'existing_booking_payment',
            'booking_id': existing_booking.id,
            'property_id': property_obj.id,
            'total_price': str(amount_rupees),
            'service_fee_rate': str(service_fee_rate),
            'tax_amount': str(tax_amount),
            'amount_paise': amount_paise,
            'order_id': order['id'],
            'month': month_param,
            'year': str(payment_year),
        }

        return render(request, 'make_payment.html', {
            'booking': existing_booking,
            'month': month_param,
            'year': str(payment_year),
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
            'razorpay_order_id': order['id'],
            'razorpay_amount_paise': amount_paise,
            'currency': 'INR',
        })

    if property_obj.status != 'active':
        if existing_booking:
            messages.info(request, "Use the reservation page to pay pending monthly dues.")
            return redirect('reservation_detail', booking_id=existing_booking.id)
        messages.error(request, "This property is not available for booking right now.")
        return redirect('property_detail', property_id=property_obj.id)

    if request.method == 'POST':
        blocked, retry_after = _check_rate_limits(request, 'book_property', [
            {'name': 'book_property_user', 'identifier': 'user', 'limit': 12, 'window': 600},
            {'name': 'book_property_ip', 'identifier': 'ip', 'limit': 20, 'window': 600},
        ])
        if blocked:
            return _rate_limited_response(request, retry_after, redirect_to=request.path)

        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        guest_raw = request.POST.get('guests')
        notes = request.POST.get('notes', '')
        payment_type = 'monthly'  # Always monthly

        if not start_date_str or not end_date_str:
            messages.error(request, "Both check-in and check-out dates are required.")
            return redirect('book_property', property_id=property_id)

        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('book_property', property_id=property_id)

        if start_date >= end_date:
            messages.error(request, "Check-out date must be after check-in date.")
            return redirect('book_property', property_id=property_id)

        try:
            guest = int(guest_raw) if guest_raw else None
            if guest is not None and guest <= 0:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "Guest count must be a positive number.")
            return redirect('book_property', property_id=property_id)

        overlapping = Booking.objects.filter(
            property=property_obj,
        ).exclude(
            status='declined'
        ).filter(
            Q(start_date__lt=end_date) & Q(end_date__gt=start_date)
        ).exists()

        if overlapping:
            messages.error(request, "Property is already booked for the selected dates.")
            return redirect('book_property', property_id=property_id)
        
#payment logic
        days = (end_date - start_date).days
        # months = Decimal(days) / Decimal("30")

        price = Decimal(property_obj.price).quantize(Decimal("0.01"))
        service_fee_rate = Decimal("0.01")
        tax_rate = Decimal("0.00")
        service_fee = (price * service_fee_rate).quantize(Decimal("0.01"))
        tax_amount = (price * tax_rate).quantize(Decimal("0.01"))
        total_price = (price + service_fee + tax_amount).quantize(Decimal("0.01"))

        # Calculate monthly dues
        monthly_due_dates = []
        current = start_date
        while current < end_date:
            next_due = current + relativedelta(months=1)
            if next_due > end_date:
                next_due = end_date
            #days_in_period = (next_due - current).days
            period_amount = total_price #rest of payment logic.
            monthly_due_dates.append({
                'due_date': next_due.strftime('%Y-%m-%d'),
                'amount': float(period_amount),
                'paid': False
            })
            current = next_due

        amount_paise = int(total_price * 100)
        month = start_date.strftime('%B')
        year = str(start_date.year)

        order = razor_client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': 1,
            'notes': {
                'property_id': str(property_obj.id),
                'user_id': str(request.user.id),
                'month': month,
                'year': year,
            }
        })

        request.session['pending_booking_payment'] = {
            'property_id': property_obj.id,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'guest': guest,
            'notes': notes,
            'payment_type': payment_type,
            'monthly_due_dates': monthly_due_dates,
            'total_price': str(total_price),
            'service_fee_rate': str(service_fee_rate),
            'tax_amount': str(tax_amount),
            'amount_paise': amount_paise,
            'order_id': order['id'],
            'month': month,
            'year': year,
        }

        booking_preview = {
            'id': 'NEW',
            'property': property_obj,
            'start_date': start_date,
            'end_date': end_date,
            'user': request.user,
            'service_fee': service_fee,
            'tax_amount': tax_amount,
            'total_price': total_price,
        }

        return render(request, 'make_payment.html', {
            'booking': booking_preview,
            'month': month,
            'year': year,
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
            'razorpay_order_id': order['id'],
            'razorpay_amount_paise': amount_paise,
            'currency': 'INR',
        })

    # For GET requests, render the booking form
    return render(request, 'book_property.html', {
        'property': property_obj,
        'pic': profile if profile else None,
        'available_dates': get_available_dates(property_obj)
    })


# Razorpay payment verification endpoint
@login_required
@require_POST
def payment_verify(request):
    blocked, retry_after = _check_rate_limits(request, 'payment_verify', [
        {'name': 'payment_verify_user', 'identifier': 'user', 'limit': 30, 'window': 600},
        {'name': 'payment_verify_ip', 'identifier': 'ip', 'limit': 45, 'window': 600},
    ])
    if blocked:
        return _rate_limited_response(request, retry_after, redirect_to='my_bookings')

    rp_payment_id = request.POST.get('razorpay_payment_id')
    rp_order_id = request.POST.get('razorpay_order_id')
    rp_signature = request.POST.get('razorpay_signature')
    month = request.POST.get('month')
    year = request.POST.get('year')

    if not _verify_checkout_signature(rp_order_id, rp_payment_id, rp_signature):
        return JsonResponse({'ok': False, 'error': 'Payment signature verification failed. No booking was created.'}, status=400)

    pending = request.session.get('pending_booking_payment')
    if not pending:
        return JsonResponse({'ok': False, 'error': 'Payment session expired. Please book again.'}, status=400)

    expected_order_id = pending.get('order_id')
    if expected_order_id != rp_order_id:
        return JsonResponse({'ok': False, 'error': 'Order mismatch detected. Please retry payment.'}, status=400)

    try:
        payment_info = razor_client.payment.fetch(rp_payment_id)
    except Exception:
        logger.exception("Failed to fetch payment info from Razorpay")
        return JsonResponse({'ok': False, 'error': 'Unable to confirm payment status. Please try again shortly.'}, status=502)

    payment_status = payment_info.get('status')
    paid_amount_paise = int(payment_info.get('amount') or 0)
    expected_amount_paise = int(pending.get('amount_paise') or 0)

    if payment_status not in ('captured', 'authorized'):
        return JsonResponse({'ok': False, 'error': 'Payment is not completed yet. Booking was not created.'}, status=400)

    if paid_amount_paise != expected_amount_paise:
        return JsonResponse({'ok': False, 'error': 'Payment amount mismatch. Booking was not created.'}, status=400)

    pending_kind = pending.get('kind', 'new_booking_payment')

    if pending_kind == 'existing_booking_payment':
        booking = get_object_or_404(
            Booking,
            id=pending.get('booking_id'),
            user=request.user,
            property_id=pending.get('property_id')
        )
        total_price = Decimal(str(pending['total_price']))
        booking.status = 'paid'
        booking.paid_amount += total_price
        booking.service_fee = Decimal(str(pending.get('service_fee_rate', booking.service_fee or "0.01")))
        booking.tax_amount = Decimal("0.00")
        booking.save(update_fields=['status', 'paid_amount', 'service_fee', 'tax_amount', 'updated_at'])
    else:
        property_obj = get_object_or_404(Property, id=pending['property_id'], status='active')
        start_date = datetime.strptime(pending['start_date'], "%Y-%m-%d").date()
        end_date = datetime.strptime(pending['end_date'], "%Y-%m-%d").date()

        overlapping = Booking.objects.filter(
            property=property_obj,
        ).exclude(
            status='declined'
        ).filter(
            Q(start_date__lt=end_date) & Q(end_date__gt=start_date)
        ).exists()

        if overlapping:
            return JsonResponse({'ok': False, 'error': 'This property was booked by someone else during payment. No booking was created.'}, status=409)

        total_price = Decimal(str(pending['total_price']))
        service_fee_rate = Decimal(str(pending.get('service_fee_rate', "0.01")))
        tax_amount = Decimal("0.00")
        booking = Booking.objects.create(
            property=property_obj,
            user=request.user,
            start_date=start_date,
            end_date=end_date,
            total_price=total_price,
            guest=pending.get('guest'),
            notes=pending.get('notes', ''),
            payment_type=pending.get('payment_type', 'monthly'),
            monthly_due_dates=pending.get('monthly_due_dates', []),
            service_fee=service_fee_rate,
            tax_amount=tax_amount,
            status='paid',
            paid_amount=total_price,
        )

    log = PaymentLog.objects.create(
        booking=booking,
        order_id=rp_order_id,
        payment_id=rp_payment_id,
        amount=total_price,
        month=month or pending.get('month', ''),
        year=year or pending.get('year', ''),
        status='paid',
        paid_By_User=request.user,
        signature=rp_signature,
        payment_method=payment_info.get('method'),
        full_response=payment_info,
    )

    # --- New: Update booking.payment_data for bill generation ---
    try:
        payment_year = int(year or pending.get('year'))
        payment_month_name = str(month or pending.get('month'))
        payment_amount = float(log.amount) if log and log.amount else float(booking.property.price)
        payment_date = date.today()

        payment_data = booking.payment_data or []

        # Find or create the year entry
        year_entry = next((y for y in payment_data if y['year'] == payment_year), None)
        if not year_entry:
            year_entry = {"year": payment_year, "months": {}}
            payment_data.append(year_entry)

        # Add/append this month's payment info
        if payment_month_name not in year_entry['months']:
            year_entry['months'][payment_month_name] = []

        year_entry['months'][payment_month_name].append({
            "payment_date": payment_date.strftime("%Y-%m-%d"),
            "payment_amount": str(payment_amount)
        })

        booking.payment_data = payment_data

    except Exception as e:
        logger.exception("Error updating payment_data")
    # --- End update ---

    booking.save()

    # Vendor payout
    vendor_profile = booking.property.owner.profile
    if vendor_profile.razorpay_fund_account_id:
        try:
            razor_client.payout.create({
                "account_number": settings.RAZORPAY_PAYOUT_ACCOUNT,
                "fund_account_id": vendor_profile.razorpay_fund_account_id,
                "amount": int(log.amount * 90),  # 90% to vendor
                "currency": "INR",
                "mode": "IMPS",
                "purpose": "payout",
                "queue_if_low_balance": True,
                "notes": {"booking_id": booking.id}
            })
        except Exception as e:
            logger.exception("Razorpay payout error")

    try:
        del request.session['pending_booking_payment']
    except KeyError:
        pass

    return JsonResponse({'ok': True, 'redirect': reverse('booking_confirmation', kwargs={'booking_id': booking.id})})

#razorpay webhook
@csrf_exempt
@require_POST
def razorpay_webhook(request):
    blocked, _retry_after = _check_rate_limits(request, 'razorpay_webhook', [
        {'name': 'razorpay_webhook_ip', 'identifier': 'ip', 'limit': 180, 'window': 60},
    ])
    if blocked:
        return HttpResponse(status=429)

    payload = request.body
    signature = request.headers.get('X-Razorpay-Signature')
    if not signature:
        return HttpResponse(status=400)
 
    try:
        razor_client.utility.verify_webhook_signature(payload, signature, settings.RAZORPAY_WEBHOOK_SECRET)
    except razorpay.errors.SignatureVerificationError:
        return HttpResponse(status=400)

    try:
        json.loads(payload)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    logger.info("Razorpay webhook received and signature verified")
    return HttpResponse(status=200)


#booking confirmation
@login_required
def booking_confirmation(request, booking_id):
    #how can stop the user from accessing this view if the booking is not paid?
    booking = get_object_or_404(Booking, id=booking_id, user=request.user)


    if booking.status != 'paid':
        messages.error(request, "You must complete the payment before accessing this page.")
        return redirect('reservation_detail', booking_id=booking.id)

    # Mark property as rented if booking is paid
    if booking.status == 'paid' and booking.property.status != 'rented':
        booking.property.status = 'rented'
        booking.property.save()
    

    vendor_email = booking.property.owner.email
    customer_email = request.user.email

    t1 = threading.Thread(
        target=send_email_async,
        kwargs={
            "subject": "A property has been booked",
            "message": (
                f"Dear {booking.property.owner.username},\n\n"
                f"We are pleased to inform you that {request.user.username} has successfully booked your property through SBLRent.\n\n"
                f"--- Property Details ---\n"
                f"Title: {booking.property.title}\n"
                f"Location: {booking.property.location}\n"
                f"Address: {booking.property.address}, {booking.property.city}, {booking.property.state} - {booking.property.zip_code}\n"
                f"Google Location: https://www.google.com/maps/search/?api=1&query={booking.property.latitude},{booking.property.longitude}\n"
                f"Monthly Rent: ₹{booking.property.price}\n\n"
                f"--- Booking Details ---\n"
                f"Start Date: {booking.start_date}\n"
                f"End Date: {booking.end_date}\n\n"
                f"Thank you for choosing SBLRent to connect with reliable tenants.\n"
                f"If you have any questions or need assistance, please reach out to our support team at support@sblrent.com.\n\n"
                f"Best regards,\n"
                f"SBLRent Team"
            ),
            "from_email": None,
            "recipient_list": [vendor_email],
        }
    )

    if booking.property.status != 'rented':
        t1.start()

    t2 = threading.Thread(
        target=send_email_async,
        kwargs={
            "subject": "Your property booking has been confirmed",
            "message": (
                f"Dear {request.user.username},\n\n"
                f"Congratulations! Your booking has been successfully confirmed through SBLRent.\n\n"
                f"--- Property Details ---\n"
                f"Title: {booking.property.title}\n"
                f"Location: {booking.property.location}\n"
                f"Address: {booking.property.address}, {booking.property.city}, {booking.property.state} - {booking.property.zip_code}\n"
                f"Google Location: https://www.google.com/maps/search/?api=1&query={booking.property.latitude},{booking.property.longitude}\n"
                f"Monthly Rent: ₹{booking.property.price}\n\n"
                f"--- Booking Details ---\n"
                f"Start Date: {booking.start_date}\n"
                f"End Date: {booking.end_date}\n\n"
                f"We look forward to making your stay comfortable and enjoyable.\n"
                f"For any queries or assistance, please contact us at support@sblrent.com.\n\n"
                f"Best regards,\n"
                f"SBLRent Team"
            ),
            "from_email": None,
            "recipient_list": [customer_email],
        }
    )
    if booking.property.status != 'rented':
        t2.start()
   
    return render(request, 'booking_confirmation.html', {'booking': booking})



@login_required
def my_bookings(request):
    user = request.user
    profile = user.profile if user.is_authenticated else None

    if not profile:
        messages.error(request, "You do not have permission to view this reservation.")
        return redirect('home')

    if profile.role == 'vendor':
        bookings = Booking.objects.filter(property__owner=user).select_related('user', 'property')
    else:
        bookings = Booking.objects.filter(user=user).select_related('property')

    return render(request, 'my_bookings.html', {
        'bookings': bookings,
        'pic': profile if profile else None,
        'is_vendor': profile.role == 'vendor'
    })



# Reservation details view

@login_required
def reservation_details(request, booking_id):
   

    user = request.user
    profile = user.profile if user.is_authenticated else None

    booking = get_object_or_404(
        Booking.objects.select_related('property', 'user__profile'),
        id=booking_id
    )
    if booking.user != request.user and booking.property.owner != request.user:
        messages.error(request, "You do not have permission to view this reservation.")
        return redirect('home')

    # Handle extension form submission
    if request.method == 'POST':
        new_end_date_str = request.POST.get('new_end_date')
        new_end_date = parse_date(new_end_date_str)
        if new_end_date and new_end_date > booking.end_date:
            booking.end_date = new_end_date
            booking.save()
            messages.success(request, 'Checkout date extended successfully.')
            return redirect('reservation_details', booking_id=booking.id)
        else:
            messages.error(request, 'Invalid date. Please select a future date.')

    booking_duration = (booking.end_date - booking.start_date).days
    previous_bookings = Booking.objects.filter(user=booking.user).exclude(id=booking.id).count()
    user_reviews = Review.objects.filter(user=booking.user)
    average_rating = round(user_reviews.aggregate(models.Avg('rating'))['rating__avg'] or 0, 1)
    current_year = datetime.now().year

    # Generate monthly payments: each period is from start_date to same day next month
    monthly_payments = []
    
    total_price = booking.total_price
    payment_data = booking.payment_data or []
    payment_lookup = {}
    for year_entry in payment_data:
        year = year_entry.get('year')
        for month_name_str, payments in year_entry.get('months', {}).items():
            if payments:
                try:
                    month = datetime.strptime(month_name_str, "%B").month
                except Exception:
                    continue
                payment_lookup[(year, month)] = payments[0]

    current = booking.start_date
    end = booking.end_date
    while current < end:
        next_month = current + relativedelta(months=1)
        # If next_month's day is less than start_date's day, adjust to last day of month
        try:
            period_end = next_month.replace(day=current.day)
        except ValueError:
            # For months with fewer days, use last day of next month
            from calendar import monthrange
            last_day = monthrange(next_month.year, next_month.month)[1]
            period_end = next_month.replace(day=last_day)
        if period_end > end:
            period_end = end
        year, month = current.year, current.month
        payment = payment_lookup.get((year, month))
        payment_date = None
        amount = None
        if payment:
            try:
                payment_date = datetime.strptime(payment['payment_date'], "%Y-%m-%d").date()
            except Exception:
                payment_date = current
            try:
                amount = float(payment['payment_amount'])
            except Exception:
                
                amount = total_price
        else:
            payment_date = current
            amount = total_price
        monthly_payments.append({
            "month": month_name[month],
            "year": year,
            "date": payment_date,
            "amount": amount,
            "period_start": current,
            "period_end": period_end,
            "status": "paid" if payment else "pending"
        })
        current = period_end

    # Filter out past periods: only show from today onwards
   
    # Use Django's timezone utilities to get IST (Asia/Kolkata) date
    # today = timezone.localtime(timezone.now(), timezone.get_fixed_timezone(330)).date()

    # today = timezone.localdate()
    today = date(2030, 10, 28)
    logger.debug("Generating reservation details for date: %s", today)

    monthly_payments = [p for p in monthly_payments if p["date"] <= today]
    # Filter by selected year if provided
    # print("Monthly Payments Niraj:", monthly_payments)
 

    try:
        selected_year = int(request.GET.get('year', booking.start_date.year))
    except (TypeError, ValueError):
        selected_year = booking.start_date.year
    filtered_payments = []
    for payment in monthly_payments:
        if payment['year'] == selected_year:
            # Start year: show from start month
            if selected_year == booking.start_date.year:
                if payment['period_start'].month >= booking.start_date.month:
                    filtered_payments.append(payment)
            # End year: show up to end month
            elif selected_year == booking.end_date.year:
                if payment['period_start'].month <= booking.end_date.month:
                    filtered_payments.append(payment)
            # Middle years: show all months
            else:
                filtered_payments.append(payment)

    base_price = Decimal(booking.property.price).quantize(Decimal("0.01"))
    service_fee = (base_price * Decimal(booking.service_fee)).quantize(Decimal("0.01"))
    tax_amount = Decimal("0.00")
    total_amount = (base_price + service_fee + tax_amount).quantize(Decimal("0.01"))
    return render(request, 'reservation_details.html', {
        'booking': booking,
        'current_year': current_year,
        'previous_bookings': previous_bookings,
        'pic': profile if profile else None,
        'average_rating': average_rating,
        'monthly_payments': filtered_payments,
        'selected_year': selected_year,
        'service_fee': service_fee,
        'tax_amount': tax_amount,
        'total_amount': total_amount,
    })



# Allow users to cancel/delete their own bookings
@login_required
def cancel_booking(request, booking_id):

    booking = get_object_or_404(Booking, id=booking_id, user=request.user)

   # Check user payment till current month
    start_date = booking.start_date
    current_date = timezone.now().date()
    # fixed_date = datetime(2026, 1, 28).date()  # Use a fixed date for testing
    # current_date = fixed_date
    paid_amount = booking.paid_amount

#------------------#need to fix it -----------------

# Calculate completed months
    calculated_months = (current_date.year - start_date.year) * 12 + (current_date.month - start_date.month)

    # Adjust if current day < start day (not a full month yet)
    start = start_date.day + 5
    if start < current_date.day:
        calculated_months += 1

# Assuming booking.total_price is per month rent
    total_outstanding = (Decimal(calculated_months) * booking.total_price) - paid_amount

    # Allow cancel if payment is complete
    if total_outstanding <= 0:  # booking.status in ['pending', 'approved', 'active', 'paid'] and booking.total_price == booking.total_amount
        booking.status = 'cancelled'
        booking.property.status = 'active'
        booking.property.save()

        # Send cancellation email notifications
        vendor_email = booking.property.owner.email
        customer_email = request.user.email

        vendor_message = (
            f"Dear {booking.property.owner.username},\n\n"
            f"We would like to inform you that the booking for your property '{booking.property.title}' "
            f"has been cancelled by {request.user.username}.\n\n"
            f"--- Property Details ---\n"
            f"Title: {booking.property.title}\n"
            f"Location: {booking.property.location}\n"
            f"Address: {booking.property.address}, {booking.property.city}, {booking.property.state} - {booking.property.zip_code}\n"
            f"Google Location: https://www.google.com/maps/search/?api=1&query={booking.property.latitude},{booking.property.longitude}\n"
            f"Monthly Rent: ₹{booking.property.price}\n\n"
            f"Best regards,\n"
            f"SBLRent Team"
        )

        customer_message = (
            f"Dear {request.user.username},\n\n"
            f"Your booking for the property '{booking.property.title}' has been successfully cancelled.\n\n"
            f"--- Property Details ---\n"
            f"Title: {booking.property.title}\n"
            f"Location: {booking.property.location}\n"
            f"Address: {booking.property.address}, {booking.property.city}, {booking.property.state} - {booking.property.zip_code}\n"
            f"Google Location: https://www.google.com/maps/search/?api=1&query={booking.property.latitude},{booking.property.longitude}\n"
            f"Monthly Rent: ₹{booking.property.price}\n\n"
            f"Best regards,\n"
            f"SBLRent Team"
        )

        t1 = threading.Thread(
            target=send_email_async,
            kwargs={
                "subject": "Booking Cancelled - SBLRent",
                "message": vendor_message,
                "from_email": None,
                "recipient_list": [vendor_email],
            }
        )
        t2 = threading.Thread(
            target=send_email_async,
            kwargs={
                "subject": "Your Booking Has Been Cancelled - SBLRent",
                "message": customer_message,
                "from_email": None,
                "recipient_list": [customer_email],
            }
        )
        t1.start()
        t2.start()

        booking.delete()
        messages.success(request, "Booking has been cancelled.")
    else:
        messages.error(request, f"This booking cannot be cancelled. Please ensure all payments are settled before cancelling. Remaining amount is ₹{total_outstanding}")
    return redirect('my_bookings')


#property list
def property_list(request):
    user = request.user
    profile = user.profile if user.is_authenticated else None
    properties = Property.objects.none()  # Default empty queryset

    # Determine initial queryset
    if request.user.is_authenticated and hasattr(request.user, 'profile') and request.user.profile.role == 'vendor':
        queryset = Property.objects.filter(owner=request.user)
    elif request.GET.get('view') == 'wishlist' and request.user.is_authenticated:
        queryset = Property.objects.filter(wishlist__user=request.user)
    elif request.GET.get('view') == 'recent_viewed' and request.user.is_authenticated:
       queryset = Property.objects.filter(recent_views__user=request.user)
    else:
        queryset = Property.objects.filter(status='active')

    # Apply filters for all cases
    location = request.GET.get('location')
    property_type = request.GET.get('property_type')
    price_range = request.GET.get('price_range')
    user_lat = request.GET.get('user_lat')
    user_lng = request.GET.get('user_lng')
    radius_km = _safe_float(request.GET.get('radius', 20), 20.0)  # Default to 20km
    zip_code = request.GET.get('zip_code')

    # Track if any filter/search is applied
    filter_applied = any([
        location,
        property_type and property_type != "Any Type",
        price_range,
        user_lat and user_lng,
        zip_code
    ])

    if location:
    # Split by comma and space, remove empty strings
        import re
        parts = [p.strip() for p in re.split(r'[,\s]+', location) if p.strip()]
        for part in parts:
            queryset = queryset.filter(
                Q(location__icontains=part) |
                Q(city__icontains=part) |
                Q(address__icontains=part) |
                Q(state__icontains=part)
            )
    if zip_code:
        queryset = queryset.filter(zip_code=zip_code)
    if property_type:
        queryset = queryset.filter(property_type__icontains=property_type)
    if price_range:
        if price_range == "Under ₹10,000":
            queryset = queryset.filter(price__lt=Decimal('10000'))
        elif price_range == "₹10,000-₹20,000":
            queryset = queryset.filter(price__gte=Decimal('10000'), price__lte=Decimal('20000'))
        elif price_range == "₹20,000-₹30,000":
            queryset = queryset.filter(price__gte=Decimal('20000'), price__lte=Decimal('30000'))
        elif price_range == "Over ₹30,000":
            queryset = queryset.filter(price__gt=Decimal('30000'))

         # --- Only filter by user location if both lat/lng are present ---
    if user_lat and user_lng:
        try:
            user_lat = float(user_lat)
            user_lng = float(user_lng)
            filtered_properties = [
                prop for prop in queryset
                if prop.latitude and prop.longitude and
                haversine(user_lat, user_lng, float(prop.latitude), float(prop.longitude)) <= radius_km
            ]
            queryset = filtered_properties if filtered_properties else []
        except Exception:
            queryset = queryset.order_by('-date_added')
    else:
        queryset = queryset.order_by('-date_added')

    # Add wishlist status for heart icon
    if request.user.is_authenticated:
        wishlist_ids = set(
            Wishlist.objects.filter(user=request.user).values_list('property_id', flat=True)
        )
        for prop in queryset:
            prop.in_wishlist = prop.id in wishlist_ids
    else:
        for prop in queryset:
            prop.in_wishlist = False

    # Pagination
    paginator = Paginator(queryset, 6)  # 6 per page
    page = request.GET.get('page')
    properties = paginator.get_page(page)

    # Check if no properties found after search/filter
    no_results = filter_applied and properties.paginator.count == 0

  
    # AJAX support for partial rendering
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        html = render_to_string('partials/_featured_properties.html', {
            'featured_properties': properties,
            'no_results': no_results,
        }, request=request)
        return HttpResponse(html)

    return render(request, 'property_list.html', {
        'properties': properties,
        'pic': profile if profile else None,
        'showing_wishlist': request.GET.get('view') == 'wishlist',
        'is_vendor': request.user.is_authenticated and hasattr(request.user, 'profile') and request.user.profile.role == 'vendor',
        'no_results': no_results,
    })


#toggle wishlist
@login_required(login_url='/login/')
def toggle_wishlist(request, property_id):
    if not request.user.is_authenticated:
        # AJAX: return JSON with login redirect
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"login_required": True, "login_url": "/login/?next=" + request.path}, status=401)
        # Non-AJAX: redirect to login
        return redirect(f"/login/?next={request.path}")

    blocked, retry_after = _check_rate_limits(request, 'wishlist_toggle', [
        {'name': 'wishlist_toggle_user', 'identifier': 'user', 'limit': 80, 'window': 60},
        {'name': 'wishlist_toggle_ip', 'identifier': 'ip', 'limit': 120, 'window': 60},
    ])
    if blocked:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return _rate_limited_response(request, retry_after, redirect_to='home')
        messages.error(request, f"Too many requests. Please try again in {retry_after} seconds.")
        return redirect(request.META.get("HTTP_REFERER", "home"))

    property_obj = get_object_or_404(Property, id=property_id)
    wishlist_item, created = Wishlist.objects.get_or_create(user=request.user, property=property_obj)

    if not created:
        wishlist_item.delete()
        status = "removed"
    else:
        status = "added"

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"status": status})
    else:
        return redirect(request.META.get("HTTP_REFERER", "home"))


# my wishlist
@login_required(login_url='/login/')
def my_wishlist(request):
    wishlist_items = Wishlist.objects.filter(user=request.user).select_related('property').order_by('-property__date_added')
    return render(request, 'my_wishlist.html', {'wishlist_items': wishlist_items})


# logout user
def logout_user(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('home')


# Utility functions
def get_available_dates(property):
    # Implement your availability logic here
    # This could check against existing bookings
    return []

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in kilometers
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c



@login_required
def download_kyc_document(request, doc_type):
    profile = get_object_or_404(Profile, user=request.user)

    documents = {
        'aadhaar': profile.aadhaar_document,
        'pan': profile.pan_document,
    }
    document_file = documents.get(doc_type)

    if document_file is None:
        raise Http404("Invalid document type")

    if not getattr(document_file, 'name', None):
        raise Http404("Document not found")

    extension = os.path.splitext(document_file.name)[1].lower()
    content_type_map = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }
    content_type = content_type_map.get(extension, 'application/octet-stream')

    response = FileResponse(
        document_file.open('rb'),
        as_attachment=True,
        filename=os.path.basename(document_file.name),
        content_type=content_type,
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "sandbox"
    response['X-Download-Options'] = 'noopen'
    return response



def send_payment_reminders():
    today = timezone.now().date()
    for booking in Booking.objects.filter(payment_type='monthly'):
        for due in booking.monthly_due_dates:
            due_date = datetime.strptime(due['due_date'], '%Y-%m-%d').date()
            if not due['paid'] and (due_date - today).days == 3:
                send_mail(
                    'Payment Reminder',
                    f'Your next payment of ₹{due["amount"]} is due on {due_date}.',
                    'noreply@sblrent.com',
                    [booking.user.email]
                )


# @login_required
# def manage_profile(request):
#     profile = request.user.profile
    
    
#     if request.method == 'POST':
#         form = ProfileForm(request.POST, request.FILES, instance=profile)
#         if form.is_valid():
#             form.save()
#             messages.success(request, "Profile updated successfully!")
#             return redirect('dashboard')
#     else:
#         form = ProfileForm(instance=profile)
    
#     return render(request, 'manage_profile.html', {'form': form})


# @login_required
# def vendor_booking_requests(request):
#     if request.user.profile.role != 'vendor':
#         return redirect('home')
#     bookings = Booking.objects.filter(property__owner=request.user)
#     return render(request, 'vendor_bookings.html', {'bookings': bookings})

# @login_required
# def approve_booking(request, booking_id):
#     booking = get_object_or_404(Booking, id=booking_id, property__owner=request.user)
#     booking.status = 'approved'
#     booking.save()
#     return redirect('vendor_booking_requests')

# @login_required
# def decline_booking(request, booking_id):
#     booking = get_object_or_404(Booking, id=booking_id, property__owner=request.user)
#     booking.status = 'declined'
#     booking.save()
#     return redirect('vendor_booking_requests')
