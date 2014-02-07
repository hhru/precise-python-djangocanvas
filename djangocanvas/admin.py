from django.contrib import admin
from models import OAuthToken, SocialUser


class SocialUserAdmin(admin.ModelAdmin):
    list_display = ['social_id', 'provider', 'authorized', 'first_name', 'last_name']


class OAuthTokenAdmin(admin.ModelAdmin):
    list_display = ['social_user', 'issued_at', 'expires_at', 'expired']

# admin.site.register(SocialUser, SocialUserAdmin)
admin.site.register(OAuthToken, OAuthTokenAdmin)
