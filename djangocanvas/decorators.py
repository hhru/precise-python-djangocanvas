from functools import wraps
from django.http import HttpResponseRedirect
# from django.contrib.auth import authenticate, login
from django.contrib.auth import authenticate

from djangocanvas.utils import authorization_denied_view, get_post_authorization_redirect_url
from djangocanvas.views import authorize_application
from djangocanvas.exceptions import FacebookAuthorizationDenied, FacebookAuthorizationError
from djangocanvas.settings import FACEBOOK_APPLICATION_INITIAL_PERMISSIONS
from djangocanvas.settings import FACEBOOK_AUTHORIZATION_REDIRECT_URL


def facebook_authorization_required(redirect_uri=FACEBOOK_AUTHORIZATION_REDIRECT_URL, permissions=None):
    """
    Require the user to authorize the application.

    :param redirect_uri: A string describing an URL to redirect to after authorization is complete.
                         If ``None``, redirects to the current URL in the Facebook canvas
                         (e.g. ``http://apps.facebook.com/myapp/current/path``). Defaults to
                         ``FACEBOOK_AUTHORIZATION_REDIRECT_URL`` (which, in turn, defaults to ``None``).
    :param permissions: A list of strings describing Facebook permissions.
    """

    def decorator(function):
        @wraps(function)
        def wrapper(request, *args, **kwargs):

            # The user has already authorized the application, but the given view requires
            # permissions besides the defaults listed in ``FACEBOOK_APPLICATION_DEFAULT_PERMISSIONS``.
            #
            # Derive a list of outstanding permissions and prompt the user to grant them.
            if request.facebook and request.facebook.user and permissions:
                outstanding_permissions = [p for p in permissions if p not in request.facebook.user.permissions]

                if outstanding_permissions:
                    return authorize_application(
                        request=request,
                        redirect_uri=redirect_uri or get_post_authorization_redirect_url(request),
                        permissions=outstanding_permissions
                    )

            # The user has not authorized the application yet.
            #
            # Concatenate the default permissions with permissions required for this particular view.
            if not request.facebook or not request.facebook.user:
                return authorize_application(
                    request=request,
                    redirect_uri=redirect_uri or get_post_authorization_redirect_url(request),
                    permissions=(FACEBOOK_APPLICATION_INITIAL_PERMISSIONS or []) + (permissions or [])
                )

            return function(request, *args, **kwargs)
        return wrapper

    if callable(redirect_uri):
        function = redirect_uri
        redirect_uri = None

        return decorator(function)
    else:
        return decorator


def login(request, user):
    SESSION_KEY = '_auth_user_id'
    BACKEND_SESSION_KEY = '_auth_user_backend'
    """
    Persist a user id and a backend in the request. This way a user doesn't
    have to reauthenticate on every request. Note that data set during
    the anonymous session is retained when the user logs in.
    """
    if user is None:
        user = request.user
    # TODO: It would be nice to support different login methods, like signed cookies.
    if SESSION_KEY in request.session:
        if request.session[SESSION_KEY] != user.pk:
            # To avoid reusing another user's session, create a new, empty
            # session if the existing session corresponds to a different
            # authenticated user.
            request.session.flush()
    else:
        request.session.cycle_key()
    request.session[SESSION_KEY] = user.pk
    request.session[BACKEND_SESSION_KEY] = user.backend
    if hasattr(request, 'user'):
        request.user = user
    # user_logged_in.send(sender=user.__class__, request=request, user=user)


def social_login_required(function):
    def wrapper(request, *args, **kwargs):
        if getattr(request.user, 'provider', False):
            return function(request, *args, **kwargs)
        else:
            try:
                user = authenticate(request=request)
            except FacebookAuthorizationDenied:
                return authorization_denied_view(request)
            except FacebookAuthorizationError:
                return authorize_application(request=request,
                                             redirect_uri=get_post_authorization_redirect_url(request))
            if getattr(user, 'provider', False):
                login(request, user)
                return function(request, *args, **kwargs)
            else:
                return HttpResponseRedirect('/')
    return wrapper

        # try:
        #     user = authenticate(request=request)
        # except FacebookAuthorizationDenied:
        #     return authorization_denied_view(request)
        # except FacebookAuthorizationError:
        #     return authorize_application(
        #         request=request,
        #         redirect_uri=get_post_authorization_redirect_url(request)
        #     )
        # login(request, user)
        # if getattr(request, 'social_user', None):
        #     return function(request, *args, **kwargs)
        # else:
        #     return HttpResponseRedirect('/')
