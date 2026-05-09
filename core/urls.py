"""
URL configuration for Hello project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
# add manually
from django.urls import path , include
from django.http import HttpResponse, FileResponse

#To change the title of admin pannel. # add manually
# admin.site.site_header = "Niraj's SuperUser Pannel"
# admin.site.site_title = "Niraj's Admin Portal"
# admin. site.index_title = "Welcome to SuperUser Pannel"
 

from django.conf import settings
from django.conf.urls.static import static


def sitemap_xml(request):
    return FileResponse(
        open(settings.BASE_DIR / "sitemap.xml", "rb"),
        content_type="application/xml",
    )

urlpatterns = [
    # ... your existing URLs
    path("sitemap.xml", sitemap_xml, name="sitemap_xml"),
    path("nilamadmin/", admin.site.urls),
    path('', include('home.urls'))
    
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)