# -*- coding: utf-8 -*-
import djangocanvas.settings

from django.http import HttpResponse
from django.contrib.auth import authenticate, login

from djangocanvas.views import authorize_application
from djangocanvas.exceptions import FacebookAuthorizationDenied, FacebookAuthorizationError

from djangocanvas.utils import (
    authorization_denied_view, get_post_authorization_redirect_url
)

from logging import getLogger


VK_P3P_POLICY = 'IDC DSP COR ADM DEVi TAIi PSA PSD IVAi IVDi CONi HIS OUR IND CNT'
FB_P3P_POLICY = 'IDC CURa ADMa OUR IND PHY ONL COM STA'

logger = getLogger('djangocanvas')


class SocialAuthenticationMiddleware(object):
    def process_request(self, request):
        try:
            user = authenticate(request=request)
        except FacebookAuthorizationDenied:
            return authorization_denied_view(request)
        except FacebookAuthorizationError:
            return authorize_application(
                request=request,
                redirect_uri=get_post_authorization_redirect_url(request)
            )
        if user:
            login(request, user)

    def process_response(self, request, response):
        """
        Save signed request to cookie.
        """
        if djangocanvas.settings.FANDJANGO_CACHE_SIGNED_REQUEST:
            if 'signed_request' in request.REQUEST:
                response.set_cookie('signed_request', request.REQUEST['signed_request'])
        return response


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

        P3P is a WC3 standard (see http://www.w3.org/TR/P3P/), and although largely ignored by most
        browsers it is considered by IE before accepting third-party cookies (ie. cookies set by
        documents in iframes). If they are not set correctly, IE will not set these cookies.
        """
        if hasattr(request, 'facebook') and request.facebook:
            # Set compact P3P policies for Facebook
            P3P_POLICY = FB_P3P_POLICY
        else:
            P3P_POLICY = VK_P3P_POLICY
        response["P3P"] = 'CP="%s"' % P3P_POLICY
        return response
