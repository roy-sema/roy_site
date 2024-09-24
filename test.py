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

class BaseWebhookView(APIView, ABC):
    RESPONSE_ERROR = "Unexpected error, please try again"
    RESPONSE_SUCCESS = "Webhook received and processed successfully"
    RESPONSE_UNSUPPORTED_ACTION = "Unsupported action"

    parser_classes = [BodySavingJSONParser]

    @abstractmethod
    def get_integration(self) -> GitBaseIntegration:
        pass

    @abstractmethod
    def post(self, request, *args, **kwargs):
        pass

    def dispatch(self, request, *args, **kwargs):
        webhook = None
        if request.method == "POST":
            webhook = self.store_webhook_data(request)

        response = super().dispatch(request, *args, **kwargs)

        if webhook:
            try:
                webhook.response_status_code = response.status_code
                webhook.response_message = response.data
                webhook.save()
            except Exception as error:
                traceback_on_debug()
                capture_exception(error)

        return response

    def store_webhook_data(self, request):
        integration = self.get_integration()
        provider_name = integration.provider.name

        headers = None
        payload = None

        try:
            headers, payload = self.get_webhook_request_data(request)
            file_path = self.write_webhook_request_to_file(
                request,
                provider_name,
                headers,
                payload,
                integration.WEBHOOK_REQUEST_HEADER_ID,
            )
            if not file_path:
                return None

            return WebhookRequest.objects.create(
                provider=integration.provider,
                data_file_path=file_path,
            )
        except Exception as error:
            with push_scope() as scope:
                scope.set_extra("provider", provider_name)
                if headers and payload:
                    scope.set_extra("headers", headers)
                    scope.set_extra("payload", payload)
                traceback_on_debug()
                capture_exception(error)

    def get_webhook_request_data(self, request):
        return dict(request.headers), json.loads(request.body.decode("utf-8"))

    def write_webhook_request_to_file(
        self, request, provider_name, headers, payload, header_request_id="x-request-id"
    ):
        folder = self.make_webhook_request_directory()

        request_id = request.headers.get(header_request_id)
        if not request_id:
            with push_scope() as scope:
                scope.set_extra("provider", provider_name)
                scope.set_extra("headers", headers)
                capture_message(f"Can't fetch header f{header_request_id}")

            request_id = str(uuid.uuid4())

        file_path = os.path.join(
            str(folder),
            f"{slugify(provider_name)}-{slugify(request_id)}.json",
        )
        if os.path.exists(file_path):
            return None

        with open(file_path, "w") as f:
            f.write(json.dumps({"headers": headers, "payload": payload}))

        return file_path

    def make_webhook_request_directory(self):
        now = datetime.now()
        folder = os.path.join(
            settings.WEBHOOK_DATA_DIRECTORY,
            *[str(now.strftime(_format)) for _format in ["%Y", "%m", "%d", "%H"]],
        )

        os.makedirs(folder, exist_ok=True)

        return folder

    @start_new_thread
    def process_pull_request_background(self, request_data, integration):
        ProcessPullRequestTask().run(request_data, integration)
