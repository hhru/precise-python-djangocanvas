#coding: utf-8
from datetime import datetime, timedelta
from urlparse import parse_qs

from django.db import models

from djangocanvas.settings import FACEBOOK_APPLICATION_ID, FACEBOOK_APPLICATION_SECRET_KEY

from djangocanvas.api.facepy import GraphAPI


class Facebook:
    """
    Facebook instances hold information on the current user and
    his/her signed request.
    """

    user = None
    """A ``User`` instance."""

    signed_request = None
    """A ``SignedRequest`` instance."""


class OAuthToken(models.Model):
    """
    Instances of the OAuthToken class are credentials used to query
    the Facebook API on behalf of a user.
    """

    token = models.TextField(verbose_name=u'Token')
    """A string describing the OAuth token itself."""

    issued_at = models.DateTimeField(verbose_name=u'Issued at')
    """A ``datetime`` object describing when the token was issued."""

    expires_at = models.DateTimeField(verbose_name=u'Expires at', null=True, blank=True)
    """A ``datetime`` object describing when the token expires (or ``None`` if it doesn't)"""

    @property
    def expired(self):
        """Determine whether the OAuth token has expired."""
        return self.expires_at < datetime.now() if self.expires_at else False

    @property
    def extended(self):
        """Determine whether the OAuth token has been extended."""
        if self.expires_at:
            return self.expires_at - self.issued_at > timedelta(days=30)
        else:
            return False

    def extend(self):
        """Extend the OAuth token."""
        graph = GraphAPI()

        response = graph.get(
            'oauth/access_token',
            client_id=FACEBOOK_APPLICATION_ID,
            client_secret=FACEBOOK_APPLICATION_SECRET_KEY,
            grant_type='fb_exchange_token',
            fb_exchange_token=self.token)

        components = parse_qs(response)

        self.token = components['access_token'][0]
        self.expires_at = datetime.now() + timedelta(seconds=int(components['expires'][0]))

        self.save()

    class Meta:
        verbose_name = 'OAuth token'
        verbose_name_plural = 'OAuth tokens'


class SocialUser(models.Model):
    social_id = models.BigIntegerField(verbose_name=u'Идентификатор в социальной сети', unique=True)
    provider = models.CharField(verbose_name=u'Социальная сеть', max_length=50)
    first_name = models.CharField(verbose_name=u'Имя', max_length=255, blank=True, null=True)
    last_name = models.CharField(verbose_name=u'Фамилия', max_length=255, blank=True, null=True)
    authorized = models.BooleanField(verbose_name=u'Авторизован', default=True)
    oauth_token = models.OneToOneField(u'OAuthtoken', blank=True, null=True,
                                       related_name='social_user')

    def __unicode__(self):
        return '%s, %s' % (self.social_id, self.provider)

    class Meta:
        verbose_name = u'Пользователь социальной сети'
        verbose_name_plural = u'Пользователи социальной сети'
