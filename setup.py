#!/usr/bin/env python

from setuptools import setup

execfile('djangocanvas/version.py')

readme = open('README.rst').read()

setup(
    name='djangocanvas',
    version=__version__,
    description="Fandjango fork with django-vkontakte-iframe features",
    packages=[
        'djangocanvas',
        'djangocanvas.templatetags'
    ],
    package_data={
        'djangocanvas': [
            'templates/djangocanvas/*',
        ]
    },
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7'
    ]
)
