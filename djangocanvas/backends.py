# -*- coding: utf-8 -*-
from django.http import QueryDict
from django.core.exceptions import ImproperlyConfigured

import djangocanvas.settings
from djangocanvas.exceptions import FacebookAuthorizationDenied, FacebookAuthorizationError
from djangocanvas.utils import is_disabled_path, is_enabled_path
from djangocanvas.models import Facebook, SocialUser, OAuthToken
from djangocanvas.api.facepy import SignedRequest, GraphAPI
from djangocanvas.api import vkontakte
from djangocanvas.forms import VkontakteIframeForm
from logging import getLogger

logger = getLogger('djangocanvas')


class BaseSocialAuthBackend(object):
    def get_user(self, user_id):
        try:
            return SocialUser.objects.get(pk=user_id)
        except SocialUser.DoesNotExist:
            return None

    def get_social_user(self, social_id):
        try:
            social_user = SocialUser.objects.get_by_natural_key(social_id)
        except SocialUser.DoesNotExist:
            social_user = None
        return social_user

    def _set_user_is_new(self, request):
        request.social_user_is_new = True


class FacebookAuthBackend(BaseSocialAuthBackend):
    def authenticate(self, request):
        """Process the signed request."""
        if djangocanvas.settings.ENABLED_PATHS and djangocanvas.settings.DISABLED_PATHS:
            raise ImproperlyConfigured(
                'You may configure either FANDJANGO_ENABLED_PATHS '
                'or FANDJANGO_DISABLED_PATHS, but not both.'
            )
        if djangocanvas.settings.DISABLED_PATHS and is_disabled_path(request.path):
            return
        if djangocanvas.settings.ENABLED_PATHS and not is_enabled_path(request.path):
            return

        self.has_error(request)

        if 'signed_request' in request.REQUEST or 'signed_request' in request.COOKIES:
            request.facebook = Facebook()
            self.override_incorrect_request(request)
            self.set_signed_request(request)
            if request.facebook and request.facebook.signed_request.user.has_authorized_application:
                return self.get_user_from_signed_request(request)
            else:
                raise FacebookAuthorizationError()

        else:
            request.facebook = False
            return

    def has_error(self, request):
        if 'error' in request.GET:
            logger.warning(u'Facebook authorization error')
            error = request.GET['error']

            if error == 'access_denied':
                logger.warning(u'Facebook user access denied')
                raise FacebookAuthorizationDenied()

    def override_incorrect_request(self, request):
        # If the request method is POST and its body only contains the signed request,
        # chances are it's a request from the Facebook platform and we'll override
        # the request method to HTTP GET to rectify their misinterpretation
        # of the HTTP standard.
        #
        # References:
        # "POST for Canvas" migration at http://developers.facebook.com/docs/canvas/post/
        # "Incorrect use of the HTTP protocol" discussion at
        # http://forum.developers.facebook.net/viewtopic.php?id=93554
        if request.method == 'POST' and 'signed_request' in request.POST:
            request.POST = QueryDict('')
            request.method = 'GET'

    def set_signed_request(self, request):
        try:
            request.facebook.signed_request = SignedRequest(
                signed_request=request.REQUEST.get('signed_request') or request.COOKIES.get('signed_request'),
                application_secret_key=djangocanvas.settings.FACEBOOK_APPLICATION_SECRET_KEY
            )
        except SignedRequest.Error as ex:
            logger.warning(u'Facebook signed request error: {0}'.format(str(ex)))
            request.facebook = False

    def get_user_from_signed_request(self, request):
        if request.facebook.signed_request.user.oauth_token.has_expired:
            raise FacebookAuthorizationError()

        social_id = request.facebook.signed_request.user.id
        social_user = self.get_social_user(social_id)
        if social_user is None:
            logger.info(u'Creating a new user (facebook id = {0})'.format(social_id))
            social_user = self.create_new_facebook_user(request)
        else:
            self.update_facebook_user(social_user, request)

        if not social_user.oauth_token.extended:
            # Attempt to extend the OAuth token, but ignore exceptions raised by
            # bug #102727766518358 in the Facebook Platform.
            #
            # http://developers.facebook.com/bugs/102727766518358/
            try:
                social_user.oauth_token.extend()
            except:
                pass

        return social_user

    def create_new_facebook_user(self, request):
        oauth_token = OAuthToken.create_token(request.facebook.signed_request.user.oauth_token)
        social_id = request.facebook.signed_request.user.id
        graph = GraphAPI(oauth_token.token)
        social_user = SocialUser.create_facebook_user(social_id, oauth_token, graph.get('me'))
        request.social_data = graph
        self._set_user_is_new(request)
        return social_user

    def update_facebook_user(self, social_user, request):
        if 'signed_request' in request.REQUEST:
            social_user.authorized = True
            if request.facebook.signed_request.user.oauth_token:
                social_user.oauth_token.update_token(request.facebook.signed_request.user.oauth_token)

        social_user.save()


class VkontakteAuthBackend(BaseSocialAuthBackend):
    def authenticate(self, request):
        if 'viewer_id' not in request.GET:
            self._patch_request_with_vkapi(request)
            if hasattr(request, 'session') and ('vk_startup_vars' in request.session):
                social_id = request.session['vk_startup_vars'].get('viewer_id')
                return self.get_social_user(social_id)
            return

        vk_form = VkontakteIframeForm(request.GET)

        if not vk_form:
            logger.warning(u'Vkontakte form getting promlem')
            return

        if not vk_form.is_valid():
            logger.warning(u'Vkontakte form is not valid')
            return

        social_id = vk_form.vk_user_id()
        social_user = self.get_social_user(social_id)
        if social_user is None:
            logger.info(u'Creating a new user (vkontakte id = {0})'.format(social_id))
            vk_profile = vk_form.profile_api_result()
            if vk_profile:
                social_user = SocialUser.create_vk_user(vk_profile)
                request.vk_profile = vk_profile
                self._set_user_is_new(request)

        if social_user:
            social_user.authorized = True
            social_user.save()

            if hasattr(request, 'session'):
                startup_vars = vk_form.cleaned_data
                del startup_vars['api_result']
                request.session['vk_startup_vars'] = startup_vars
                self._patch_request_with_vkapi(request)

            return social_user

        else:
            request.META['VKONTAKTE_LOGIN_ERRORS'] = vk_form.errors
            logger.warning(u'Vkontakte login errors' + ': ' + ', '.join(vk_form.errors))

    def _patch_request_with_vkapi(self, request):
        """
        Помещает в request.vk_api экземпляр vkontakte.API с настроенной
        авторизацией.
        """
        if hasattr(request, 'session'):
            if 'vk_startup_vars' in request.session:
                token = request.session['vk_startup_vars']['access_token']
                request.social_data = vkontakte.API(token=token)
