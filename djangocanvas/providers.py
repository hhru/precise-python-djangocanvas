# -*- coding: utf-8 -*-
from django.core.exceptions import ImproperlyConfigured

from models import Facebook, OAuthToken, SocialUser
from settings import FACEBOOK_APPLICATION_SECRET_KEY, DISABLED_PATHS, ENABLED_PATHS
from utils import is_disabled_path, is_enabled_path
from api.facepy import SignedRequest, GraphAPI
from api import vkontakte
from forms import VkontakteIframeForm

from exceptions import SocialAuthDenied, SocialAuthRequired


class SocialAuthProvirder(object):
    """
    Base provider class which should handle general events like register/auth user,
    set user is new etc
    """

    def set_user_is_new(self, request):
        request.social_user_is_new = True

    def login(self, request, user):
        request.session['_social_auth_user_id'] = user.pk

    def authenticate(self, request):
        raise NotImplementedError('Method authenticate must be implemented in child classes')


class FacebookAuthProvider(SocialAuthProvirder):
    """Auth provider for Facebook applications."""

    def authenticate(self, request):
        """Process the signed request."""
        if ENABLED_PATHS and DISABLED_PATHS:
            raise ImproperlyConfigured(
                'You may configure either FANDJANGO_ENABLED_PATHS '
                'or FANDJANGO_DISABLED_PATHS, but not both.'
            )

        if DISABLED_PATHS and is_disabled_path(request.path):
            return

        if ENABLED_PATHS and not is_enabled_path(request.path):
            return

        # An error occured during authorization...
        if 'error' in request.GET:
            error = request.GET['error']

            # The user refused to authorize the application...
            if error == 'access_denied':
                raise SocialAuthDenied('Facebook authentication denied')

        # Signed request found in either GET, POST or COOKIES...
        if 'signed_request' in request.REQUEST or 'signed_request' in request.COOKIES:
            request.facebook = Facebook()

            try:
                request.facebook.signed_request = SignedRequest(
                    signed_request=request.REQUEST.get('signed_request') or request.COOKIES.get('signed_request'),
                    application_secret_key=FACEBOOK_APPLICATION_SECRET_KEY)
            except SignedRequest.Error:
                request.facebook = False

            # Valid signed request and user has authorized the application
            if request.facebook and request.facebook.signed_request.user.has_authorized_application:
                # Redirect to Facebook Authorization if the OAuth token has expired
                if request.facebook.signed_request.user.oauth_token.has_expired:
                    raise SocialAuthRequired('User must autharize facebook application')

                # Initialize a User object and its corresponding OAuth token
                try:
                    social_user = SocialUser.objects.get(social_id=request.facebook.signed_request.user.id)
                except SocialUser.DoesNotExist:
                    oauth_token = OAuthToken.objects.create(
                        token=request.facebook.signed_request.user.oauth_token.token,
                        issued_at=request.facebook.signed_request.user.oauth_token.issued_at,
                        expires_at=request.facebook.signed_request.user.oauth_token.expires_at)

                    social_user = SocialUser.objects.create(
                        social_id=request.facebook.signed_request.user.id,
                        provider='facebook',
                        oauth_token=oauth_token)

                    graph = GraphAPI(social_user.oauth_token.token)
                    profile = graph.get('me')

                    social_user.first_name = profile.get('first_name')
                    social_user.last_name = profile.get('last_name')

                    social_user.save()

                    request.social_data = graph
                    self.set_user_is_new(request)

                # Update the user's details and OAuth token
                else:
                    if 'signed_request' in request.REQUEST:
                        social_user.authorized = True

                        if request.facebook.signed_request.user.oauth_token:
                            social_user.oauth_token.token = request.facebook.signed_request.user.oauth_token.token
                            social_user.oauth_token.issued_at = request.facebook.signed_request.user.oauth_token.issued_at
                            social_user.oauth_token.expires_at = request.facebook.signed_request.user.oauth_token.expires_at
                            social_user.oauth_token.save()

                    social_user.save()

                if not social_user.oauth_token.extended:
                    # Attempt to extend the OAuth token, but ignore exceptions raised by
                    # bug #102727766518358 in the Facebook Platform.
                    #
                    # http://developers.facebook.com/bugs/102727766518358/
                    try:
                        social_user.oauth_token.extend()
                    except:
                        pass

                self.login(request, social_user)
                return social_user

            else:
                raise SocialAuthRequired('User must autharize facebook application')

        # ... no signed request found.
        else:
            raise SocialAuthDenied('Facebook authentication failed: no signed request')


class VkontakteAuthProvider(SocialAuthProvirder):

    def authenticate(self, request):

        if 'viewer_id' not in request.GET:
            self.patch_request_with_vkapi(request)
            return

        vk_form = VkontakteIframeForm(request.GET)

        if not vk_form or not vk_form.is_valid():
            raise SocialAuthDenied('Vkontakte authentication denied')

        social_id = vk_form.vk_user_id()

        social_user, created = SocialUser.objects.get_or_create(social_id=social_id,
                                                                provider='vkontakte')
        if created:
            vk_profile = vk_form.profile_api_result()
            if vk_profile:
                social_user.first_name = vk_profile['first_name']
                social_user.last_name = vk_profile['last_name']
                social_user.save()
                request.vk_profile = vk_profile
                self.set_user_is_new(request)

        if social_user:
            social_user.authorized = True
            social_user.save()
            self.login(request, social_user)
            return social_user

            if hasattr(request, 'session'):
                startup_vars = vk_form.cleaned_data
                del startup_vars['api_result']
                request.session['vk_startup_vars'] = startup_vars
                self.patch_request_with_vkapi(request)

        else:
            request.META['VKONTAKTE_LOGIN_ERRORS'] = vk_form.errors

    def patch_request_with_vkapi(self, request):
        """
        Помещает в request.vk_api экземпляр vkontakte.API с настроенной
        авторизацией.
        """
        if hasattr(request, 'session'):
            if 'vk_startup_vars' in request.session:
                token = request.session['vk_startup_vars']['access_token']
                request.social_data = vkontakte.API(token=token)
