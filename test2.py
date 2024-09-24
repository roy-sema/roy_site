import hashlib

from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from api.models import GenAIFeedback
from api.serializers import GenAIFeedbackSerializer
from mvp.mixins import DecodePublicIdMixin


class GenAIFeedbackViewSet(ModelViewSet, DecodePublicIdMixin):
    permission_classes = [IsAuthenticated & TokenHasReadWriteScope]
    serializer_class = GenAIFeedbackSerializer
    queryset = GenAIFeedback.objects.all()
    http_method_names = ["post"]
