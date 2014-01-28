from django.contrib import admin
from djangocanvas.models import OAuthToken


class SocialUserAdmin(admin.ModelAdmin):
    list_display = ['social_id', 'provider', 'authorized', 'first_name', 'last_name']


class OAuthTokenAdmin(admin.ModelAdmin):
    list_display = ['social_user', 'issued_at', 'expires_at', 'expired']

admin.site.register(OAuthToken, OAuthTokenAdmin)
