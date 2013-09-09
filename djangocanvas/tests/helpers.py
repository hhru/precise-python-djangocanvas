"""Utility methods for tests."""
import re

from django.utils.functional import wraps

from djangocanvas.tests.test_fb import GraphAPI, SignedRequest


def assert_contains(expected, actual):
    if not re.search(expected, actual):
        raise AssertionError("%s does not contain %s" % (actual, expected))


class set_tests_stubs(object):
    def __init__(self, as_dictionary=True):
        self.old_has_expired = SignedRequest.User.OAuthToken.has_expired
        self.old_graph_get_method = GraphAPI.get
        self.as_dictionary = as_dictionary

    def __enter__(self):
        self.enable()

    def __exit__(self, exc_type, exc_value, traceback):
        self.disable()

    def __call__(self, func):
        @wraps(func)
        def inner(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return inner

    def enable(self):
        SignedRequest.User.OAuthToken.has_expired = _stub_has_expired
        if self.as_dictionary:
            GraphAPI.get = _stub_get_social_user_profile_dictionary
        else:
            GraphAPI.get = _stub_get_social_user_profile_url_parameters

    def disable(self):
        SignedRequest.User.OAuthToken.has_expired = self.old_has_expired
        GraphAPI.get = self.old_graph_get_method


@property
def _stub_has_expired(*args, **kwargs):
    return False


def _stub_get_social_user_profile_dictionary(*args, **kwargs):
    return {'first_name': 'Ivan', 'last_name': 'Ivanov'}


def _stub_get_social_user_profile_url_parameters(*args, **kwargs):
        return 'access_token=15&expires=900'
