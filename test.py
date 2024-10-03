from django.urls import get_script_prefix, resolve
import os
from dataclasses import asdict

from django.db.models import Case, IntegerField, When
from rest_framework import serializers

import logging
import operator
import os
from functools import reduce

from mvp.models import (
    DataProviderConnection,
    Organization,
    Repository,
    RepositoryCommit,
    RepositoryCommitStatusChoices,
)
from django.conf import settings
from django.db.models import Q
from mvp.apis import GitHubApiConfig, AzureDevOpsApiConfig
from mvp.integrations import (
    get_git_provider_integration,
    AzureDevOpsIntegration,
    GitHubIntegration,
)
from mvp.tasks import DownloadRepositoriesTask
from mvp.utils import run_command_subprocess
