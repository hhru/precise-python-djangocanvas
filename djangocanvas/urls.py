from django.conf.urls import patterns, url

from djangocanvas.views import *

urlpatterns = patterns(
    '',
    url(r'^authorize_application.html$', authorize_application, name='authorize_application'),
    url(r'^deauthorize_application.html$', deauthorize_application, name='deauthorize_application'))
