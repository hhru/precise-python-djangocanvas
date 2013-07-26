# -*- coding: utf-8 -*-
from django.http import HttpResponse, QueryDict
from django.conf import settings

from views import authorize_application
from utils import authorization_denied_view, get_post_authorization_redirect_url
from models import SocialUser
from exceptions import SocialAuthDenied, SocialAuthRequired
from providers import VkontakteAuthProvider, FacebookAuthProvider
from djangocanvas.settings import FANDJANGO_CACHE_SIGNED_REQUEST

DEFAULT_P3P_POLICY = 'IDC DSP COR ADM DEVi TAIi PSA PSD IVAi IVDi CONi HIS OUR IND CNT'
P3P_POLICY = getattr(settings, 'VK_P3P_POLICY', DEFAULT_P3P_POLICY)

SOCIAL_AUTH_PROVIDERS = {
    'vkontakte': VkontakteAuthProvider,
    'facebook': FacebookAuthProvider
}


class SocialAuthMiddleware(object):

    def process_request(self, request):
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
            request.GET = request.POST
            request.POST = QueryDict('')
            request.method = 'GET'

        request.social_user = self.get_social_user(request)
        if request.social_user is not None:
            return

        request.auth_provider = self.get_social_auth_provider(request.get_host())
        if request.auth_provider is None:
            return
        try:
            request.social_user = request.auth_provider.authenticate(request)
        except SocialAuthRequired:
            return authorize_application(
                request=request,
                redirect_uri=get_post_authorization_redirect_url(request)
            )
        except SocialAuthDenied:
            return authorization_denied_view(request)

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

    def get_social_auth_provider(self, host):
        if ':' in host:
            domain, __ = host.split(':', 2)
        else:
            domain = host
        social_network = settings.SOCIAL_NETWORK_DOMAINS.get(domain)
        provider = SOCIAL_AUTH_PROVIDERS.get(social_network)
        if provider is None:
            return None
        else:
            return provider()

    def get_social_user(self, request):
        social_user_id = request.session.get('_social_auth_user_id', None)
        if social_user_id is None:
            return
        try:
            return SocialUser.objects.get(id=social_user_id)
        except SocialUser.DoesNotExist:
            return


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
