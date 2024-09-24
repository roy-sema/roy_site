import posthog
from api.permissions import CanEditAttestationPermission
from api.tasks import RecalculateCommitAICompositionTask
from django.conf import settings
from django.shortcuts import get_object_or_404
from mvp.mixins import DecodePublicIdMixin
from mvp.models import (
    Repository,
    RepositoryCodeAttestation,
    RepositoryCommit,
    RepositoryFile,
    RepositoryFileChunk,
    RepositoryPullRequest,
)
from mvp.serializers import RepositoryCodeAttestationSerializer
from mvp.utils import start_new_thread
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet


class AttestationViewSet(DecodePublicIdMixin, ModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, CanEditAttestationPermission]
    serializer_class = RepositoryCodeAttestationSerializer
    queryset = RepositoryCodeAttestation.objects.all()
    http_method_names = ["post"]

    def create(self, request, *args, **kwargs):
        repository_id = self.decode_id(kwargs["pk_encoded"])
        repository = get_object_or_404(
            Repository, pk=repository_id, organization=request.current_organization
        )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        data["repository"] = repository
        data["attested_by"] = request.user

        try:
            attestation = RepositoryCodeAttestation.objects.get(
                repository=repository, code_hash=data["code_hash"]
            )
            serializer.instance = attestation
            serializer.partial = kwargs.pop("partial", False)
            status_code = status.HTTP_200_OK
        except RepositoryCodeAttestation.DoesNotExist:
            status_code = status.HTTP_201_CREATED

        attestation = serializer.save()

        self.update_chunks(serializer.instance)

        return Response(serializer.data, status=status_code)

    def update_chunks(self, attestation):
        organization = attestation.repository.organization
        chunks = (
            RepositoryFileChunk.objects.filter(
                file__commit__repository__organization=organization,
                code_hash=attestation.code_hash,
            )
            .prefetch_related("file", "file__commit")
            .all()
        )

        previous_label = chunks[0].get_label() if chunks else None
        event = (
            "attest_agree" if attestation.label == previous_label else "attest_override"
        )
        posthog.capture(
            attestation.attested_by.email,
            event=event,
            properties={
                "code_hash": attestation.code_hash,
                "previous_label": previous_label,
                "attest_label": attestation.label,
            },
        )

        file_ids = set()
        commits = set()
        for chunk in chunks:
            file_ids.add(chunk.file.pk)
            commits.add(chunk.file.commit)

        chunks.update(attestation=attestation)

        # Update attested date for files and commits.
        RepositoryFile.objects.filter(id__in=file_ids).update(
            last_attested_at=attestation.updated_at
        )

        commit_ids = [commit.pk for commit in commits]
        RepositoryCommit.objects.filter(id__in=commit_ids).update(
            last_attested_at=attestation.updated_at
        )

        commit_shas = [commit.sha for commit in commits]
        RepositoryPullRequest.objects.filter(head_commit_sha__in=commit_shas).update(
            last_attested_at=attestation.updated_at
        )

        # In production there's a cron process that will execute this task.
        if settings.DEBUG or settings.TESTING:
            self.recalculate_ai_composition(list(commits))

    @start_new_thread
    def recalculate_ai_composition(self, commits):
        RecalculateCommitAICompositionTask().run(commits)
