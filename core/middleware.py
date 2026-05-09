from django.conf import settings


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        csp_form_action = getattr(settings, "CSP_FORM_ACTION", ("'self'",))
        csp_frame_src = getattr(settings, "CSP_FRAME_SRC", ("'self'",))
        csp_media_src = getattr(settings, "CSP_MEDIA_SRC", ("'self'",))

        csp = [
            f"default-src {' '.join(settings.CSP_DEFAULT_SRC)}",
            f"style-src {' '.join(settings.CSP_STYLE_SRC)}",
            f"script-src {' '.join(settings.CSP_SCRIPT_SRC)}",
            f"font-src {' '.join(settings.CSP_FONT_SRC)}",
            f"img-src {' '.join(settings.CSP_IMG_SRC)}",
            f"connect-src {' '.join(settings.CSP_CONNECT_SRC)}",
            f"frame-src {' '.join(csp_frame_src)}",
            f"media-src {' '.join(csp_media_src)}",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            f"form-action {' '.join(csp_form_action)}",
        ]

        response.setdefault("Content-Security-Policy", "; ".join(csp))
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("Referrer-Policy", "same-origin")
        response.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")

        if hasattr(request, "user") and request.user.is_authenticated and response.get("Content-Type", "").startswith("text/html"):
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"

        return response
