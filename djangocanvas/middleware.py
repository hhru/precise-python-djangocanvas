# -*- coding: utf-8 -*-
from django.conf import settings
from django.http import QueryDict, HttpResponse
from django.core.exceptions import ImproperlyConfigured

from djangocanvas.views import authorize_application
from djangocanvas.models import Facebook, OAuthToken, SocialUser
from djangocanvas.settings import (
    FACEBOOK_APPLICATION_SECRET_KEY, FANDJANGO_CACHE_SIGNED_REQUEST, DISABLED_PATHS, ENABLED_PATHS
)
from djangocanvas.utils import (
    is_disabled_path, is_enabled_path,
    authorization_denied_view, get_post_authorization_redirect_url
)
from djangocanvas.api.facepy import SignedRequest, GraphAPI
from djangocanvas.api import vkontakte
from djangocanvas.forms import VkontakteIframeForm

DEFAULT_P3P_POLICY = 'IDC DSP COR ADM DEVi TAIi PSA PSD IVAi IVDi CONi HIS OUR IND CNT'
P3P_POLICY = getattr(settings, 'VK_P3P_POLICY', DEFAULT_P3P_POLICY)


class FacebookMiddleware():
    """Middleware for Facebook applications."""

    def process_request(self, request):
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
                return authorization_denied_view(request)

        # Signed request found in either GET, POST or COOKIES...
        if 'signed_request' in request.REQUEST or 'signed_request' in request.COOKIES:
            request.facebook = Facebook()

            # If the request method is POST and its body only contains the signed request,
            # chances are it's a request from the Facebook platform and we'll override
            # the request method to HTTP GET to rectify their misinterpretation
            # of the HTTP standard.
            #
            # References:
            # "POST for Canvas" migration at http://developers.facebook.com/docs/canvas/post/
            # "Incorrect use of the HTTP protocol" discussion at http://forum.developers.facebook.net/viewtopic.php?id=93554
            if request.method == 'POST' and 'signed_request' in request.POST:
                request.POST = QueryDict('')
                request.method = 'GET'

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
                    return authorize_application(
                        request=request,
                        redirect_uri=get_post_authorization_redirect_url(request))

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

                request.social_user = social_user

        # ... no signed request found.
        else:
            request.facebook = False

    def process_response(self, request, response):
        """
        Set compact P3P policies and save signed request to cookie.

        P3P is a WC3 standard (see http://www.w3.org/TR/P3P/), and although largely ignored by most
        browsers it is considered by IE before accepting third-party cookies (ie. cookies set by
        documents in iframes). If they are not set correctly, IE will not set these cookies.
        """
        if FANDJANGO_CACHE_SIGNED_REQUEST:
            if 'signed_request' in request.REQUEST:
                response.set_cookie('signed_request', request.REQUEST['signed_request'])
            response['P3P'] = 'CP="IDC CURa ADMa OUR IND PHY ONL COM STA"'
        return response


class VkontakteMiddleware():
    def process_request(self, request):
        if 'viewer_id' not in request.GET:
            self._patch_request_with_vkapi(request)
            return

        vk_form = VkontakteIframeForm(request.GET)

        if not vk_form:
            return

        if not vk_form.is_valid():
            return

        social_id = vk_form.vk_user_id()

        social_user, created = SocialUser.objects.get_or_create(social_id=social_id,
                                                                provider='vkontakte')

        if created:
            vk_profile = vk_form.profile_api_result()
            if vk_profile:
                social_user.first_name = vk_profile['first_name']
                social_user.last_name = vk_profile['last_name']
                social_user.save()

        if social_user:
            social_user.authorized = True
            social_user.save()
            request.social_user = social_user

            if hasattr(request, 'session'):
                startup_vars = vk_form.cleaned_data
                del startup_vars['api_result']
                request.session['vk_startup_vars'] = startup_vars
                self._patch_request_with_vkapi(request)

        else:
            request.META['VKONTAKTE_LOGIN_ERRORS'] = vk_form.errors

    def _patch_request_with_vkapi(self, request):
        """
        Помещает в request.vk_api экземпляр vkontakte.API с настроенной
        авторизацией.
        """
        if hasattr(request, 'session'):
            if 'vk_startup_vars' in request.session:
                token = request.session['vk_startup_vars']['access_token']
                request.social_data = vkontakte.API(token=token)


class IFrameFixMiddleware(object):

    def process_request(self, request):
        """
        Safari and Opera default security policies restrict cookie setting in first request in iframe.
        Solution is to create hidden form to preserve GET variables and REPOST it to current URL.

        Inspired by https://gist.github.com/796811 and https://gist.github.com/1511039.
        """
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        browser_is_safari = 'Safari' in user_agent and 'Chrome' not in user_agent
        browser_is_opera = 'Opera' in user_agent
        first_request = 'sessionid' not in request.COOKIES and 'cookie_fix' not in request.GET
        iframe_auth = 'api_id' in request.GET

        if (browser_is_safari or browser_is_opera) and first_request and iframe_auth:
            html = """<html><body><form name='cookie_fix' method='GET' action='.'>"""
            for item in request.GET:
                html += "<input type='hidden' value='%s' name='%s' />" % (request.GET[item], item)
            html += "<input type='hidden' name='cookie_fix' value='1' />"
            html += "</form>"
            html += '''<script type="text/javascript">document.cookie_fix.submit()</script></html>'''
            return HttpResponse(html)

    def process_response(self, request, response):
        """
        P3P policy for Internet Explorer.
        """
        response["P3P"] = 'CP="%s"' % P3P_POLICY
        return response

