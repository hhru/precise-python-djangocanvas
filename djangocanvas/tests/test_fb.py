import djangocanvas.settings

from datetime import datetime, timedelta

from django.test import TestCase
from django.test.client import RequestFactory
from django.core.urlresolvers import reverse

from djangocanvas.middleware import FacebookMiddleware
from djangocanvas.models import SocialUser
from djangocanvas.api.facepy import GraphAPI, SignedRequest
from djangocanvas.tests.helpers import set_tests_stubs


TEST_APPLICATION_ID = '508667665812571'
TEST_APPLICATION_SECRET = 'ca52168c97e17814113fbd686e576621'
TEST_SIGNED_REQUEST = u'2q8YtcUJnzYt-82sBA6qDQx2olLWByUGxCGFUsztrYY.eyJhbGdvcml0aG0iOiJITUFDLVNIQTI1NiIsImV4cGlyZXMiOjEzNTU0ODY0MDAsImlzc3VlZF9hdCI6MTM1NTQ4MDc1OCwib2F1dGhfdG9rZW4iOiJBQUFIT29XdUhqRnNCQUJla1FHeTkxSXY5d2taQjVSajA5MjFaQmZ6bml3em9QOHB0RXRCZmpvRE5lS1pDZkRHMFJORmRhZWhtRUhBcVBJT29oVTlpM2tyTUZPR0x3M3dGOWRKTUhmY25yQW5oWkM5bFpBejFvIiwidXNlciI6eyJjb3VudHJ5IjoicnUiLCJsb2NhbGUiOiJydV9SVSIsImFnZSI6eyJtaW4iOjIxfX0sInVzZXJfaWQiOiIxMDAwMDE4NDIxNzA3MDkifQ'

request_factory = RequestFactory()


class FacebookBackendTest(TestCase):
    def setUp(self):
        djangocanvas.settings.FACEBOOK_APPLICATION_SECRET_KEY = TEST_APPLICATION_SECRET
        djangocanvas.settings.FACEBOOK_APPLICATION_ID = TEST_APPLICATION_ID

    def tearDown(self):
        SocialUser.objects.all().delete()

    def test_method_override(self):
        """
        Verify that the request method is overridden
        from POST to GET if it contains a signed request.
        """
        facebook_middleware = FacebookMiddleware()

        request = request_factory.post(
            path=reverse('home'),
            data={
                'signed_request': TEST_SIGNED_REQUEST
            }
        )

        facebook_middleware.process_request(request)

        assert request.method == 'GET'

    def test_authorization_denied(self):
        """
        Verify that the view referred to by AUTHORIZATION_DENIED_VIEW is
        rendered upon refusing to authorize the application.
        """
        response = self.client.get(
            path=reverse('home'),
            data={
                'error': 'access_denied'
            }
        )

        # There's no way to derive the view the response originated from in Django,
        # so verifying its status code will have to suffice.
        assert response.status_code == 403

    @set_tests_stubs()
    def test_application_deauthorization(self):
        """
        Verify that users are marked as deauthorized upon
        deauthorizing the application.
        """
        self.client.post(
            path='/',
            data={
                'signed_request': TEST_SIGNED_REQUEST
            }
        )

        user = SocialUser.objects.get(id=1)
        assert user.authorized is True

        self.client.post(path=reverse('deauthorize_application'),
                         data={'signed_request': TEST_SIGNED_REQUEST})

        user = SocialUser.objects.get(id=1)
        assert user.authorized is False

    def test_signed_request_renewal(self):
        """
        Verify that users are redirected to renew their signed requests
        once they expire.
        """
        signed_request = SignedRequest(TEST_SIGNED_REQUEST, TEST_APPLICATION_SECRET)
        signed_request.user.oauth_token.expires_at = datetime.now() - timedelta(days=1)

        response = self.client.get(
            path='/',
            data={
                'signed_request': signed_request.generate()
            }
        )

        # There's no way to derive the view the response originated from in Django,
        # so verifying its status code will have to suffice.
        assert response.status_code == 401

    @set_tests_stubs()
    def test_registration(self):
        """
        Verify that authorizing the application will register a new user.
        """
        self.client.post(
            path=reverse('home'),
            data={
                'signed_request': TEST_SIGNED_REQUEST
            }
        )

        user = SocialUser.objects.get(id=1)
        graph = GraphAPI(user.oauth_token.token)

        assert user.first_name == graph.get('me')['first_name']
        assert user.last_name == graph.get('me')['last_name']

    @set_tests_stubs()
    def test_extend_oauth_token(self):
        """
        Verify that OAuth access tokens may be extended.
        """
        self.client.post(
            path=reverse('home'),
            data={
                'signed_request': TEST_SIGNED_REQUEST
            }
        )

        user = SocialUser.objects.get(id=1)
        with set_tests_stubs(as_dictionary=False):
            user.oauth_token.extend()

        # Facebook doesn't extend access tokens for test users, so asserting
        # the expiration time will have to suffice.
        assert user.oauth_token.expires_at
