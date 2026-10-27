"""Isolated tests: never connect to the configured application database or media service."""
from .settings import *  # noqa: F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
DEBUG = True
SECURE_SSL_REDIRECT = False
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
