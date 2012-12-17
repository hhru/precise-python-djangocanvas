Djangocanvas
=========

Fandjango fork with django-vkontakte-iframe features
(In simple terms you can use it to create Facebook and Vkontakte canvas applications)

Usage
-----

1. Add 'djangocanvas' to 'INSTALLED_APPS'

2. Add your app's settings to settings.py::
        
        VK_APP_ID = '1234567'                   # Application ID
        VK_APP_KEY = 'M1gytuHwni'               # Application key
        VK_APP_SECRET = 'MiRFwrDYwcYFCTD18EcY'  # Secure key
        
        FACEBOOK_APPLICATION_ID = '1231231665812571'
        FACEBOOK_APPLICATION_SECRET_KEY = '2134dfsdf68c97e17814113fbdaff31576621'
        FACEBOOK_APPLICATION_NAMESPACE = ''

        'MIDDLEWARE_CLASSES' = {
                ...
                'djangocanvas.middleware.IFrameFixMiddleware',
                'djangocanvas.middleware.VkontakteMiddleware',
                'djangocanvas.middleware.FacebookMiddleware', 
                ...
                'djangocanvas.middleware.SocialAuthenticationMiddleware',
        }

4. Put the following line as the 'First API request' ('Первый запрос к API') 
   option (in your app edit page at vkontakte.ru)::

        method=getProfiles&uids={viewer_id}&format=json&v=3.0&fields=uid,first_name,last_name,nickname,domain,sex,bdate,city,country,timezone,photo,photo_medium,photo_big,photo_rec,has_mobile,rate,contacts,education
