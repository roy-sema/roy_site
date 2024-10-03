from django.urls import get_script_prefix, resolve
import os
from dataclasses import asdict

from django.db.models import Case, IntegerField, When
from rest_framework import serializers
