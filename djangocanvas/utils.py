import re
from datetime import timedelta
from urlparse import urlparse
from functools import wraps
from urllib import quote_plus

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db.models.loading import get_model
from django.utils.importlib import import_module

from djangocanvas.settings import FACEBOOK_APPLICATION_CANVAS_URL
from djangocanvas.settings import FACEBOOK_APPLICATION_DOMAIN
from djangocanvas.settings import FACEBOOK_APPLICATION_NAMESPACE
from djangocanvas.settings import DISABLED_PATHS
from djangocanvas.settings import ENABLED_PATHS
from djangocanvas.settings import AUTHORIZATION_DENIED_VIEW
from djangocanvas.settings import VK_APP_ID, VK_APP_SECRET, FACEBOOK_APPLICATION_ID, \
    FACEBOOK_APPLICATION_SECRET_KEY
from djangocanvas.api import vkontakte
from djangocanvas.api.facepy import GraphAPI, get_application_access_token


def is_disabled_path(path):
    """
    Determine whether or not the path matches one or more paths
    in the DISABLED_PATHS setting.

    :param path: A string describing the path to be matched.
    """
    for disabled_path in DISABLED_PATHS:
        match = re.search(disabled_path, path[1:])
        if match:
            return True
    return False


def is_enabled_path(path):
    """
    Determine whether or not the path matches one or more paths
    in the ENABLED_PATHS setting.

    :param path: A string describing the path to be matched.
    """
    for enabled_path in ENABLED_PATHS:
        match = re.search(enabled_path, path[1:])
        if match:
            return True
    return False


def cached_property(**kwargs):
    """Cache the return value of a property."""
    def decorator(function):
        @wraps(function)
        def wrapper(self):
            key = 'fandjango.%(model)s.%(property)s_%(pk)s' % {
                'model': self.__class__.__name__,
                'pk': self.pk,
                'property': function.__name__
            }

            cached_value = cache.get(key)

            delta = timedelta(**kwargs)

            if cached_value is None:
                value = function(self)
                cache.set(key, value, delta.days * 86400 + delta.seconds)
            else:
                value = cached_value

            return value
        return wrapper
    return decorator


def authorization_denied_view(request):
    """Proxy for the view referenced in ``FANDJANGO_AUTHORIZATION_DENIED_VIEW``."""
    authorization_denied_module_name = AUTHORIZATION_DENIED_VIEW.rsplit('.', 1)[0]
    authorization_denied_view_name = AUTHORIZATION_DENIED_VIEW.split('.')[-1]

    authorization_denied_module = import_module(authorization_denied_module_name)
    authorization_denied_view = getattr(authorization_denied_module, authorization_denied_view_name)

    return authorization_denied_view(request)


def get_post_authorization_redirect_url(request):
    """Determine the URL users should be redirected to upon authorization the application."""
    path = request.get_full_path()

    if FACEBOOK_APPLICATION_CANVAS_URL:
        path = path.replace(urlparse(FACEBOOK_APPLICATION_CANVAS_URL).path, '')

    redirect_uri = 'http://%(domain)s/%(namespace)s%(path)s' % {
        'domain': FACEBOOK_APPLICATION_DOMAIN,
        'namespace': FACEBOOK_APPLICATION_NAMESPACE,
        'path': path
    }

    return redirect_uri


def send_notification(user, message):
    if user.provider == 'vkontakte':
        vkapi = vkontakte.API(api_id=VK_APP_ID,
                              api_secret=VK_APP_SECRET)
        vkapi.get('secure.sendNotification', client_secret=VK_APP_SECRET, uid=user.social_id, message=message)
    else:
        token = get_application_access_token(FACEBOOK_APPLICATION_ID, FACEBOOK_APPLICATION_SECRET_KEY)
        graph = GraphAPI(token)
        graph.post(
            '/{social_id}/notifications?access_token={token}&template={message}'
            .format(social_id=user.social_id, token=token, message=quote_plus(message.encode('utf-8')))
        )


def get_social_user_model():
    try:
        app_label, model_name = settings.AUTH_SOCIAL_USER_MODEL.split('.')
    except ValueError:
        raise ImproperlyConfigured("AUTH_SOCIAL_USER_MODEL must be of the form 'app_label.model_name'")
    user_model = get_model(app_label, model_name)
    if user_model is None:
        raise ImproperlyConfigured("AUTH_SOCIAL_USER_MODEL refers to model '{0}' that has not been installed"
                                   .format(settings.AUTH_SOCIAL_USER_MODEL))
    return user_model
