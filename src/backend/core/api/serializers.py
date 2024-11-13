"""Client serializers for the Meet core app."""

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from core import models, utils


class UserSerializer(serializers.ModelSerializer):
    """Serialize users."""

    class Meta:
        model = models.User
        fields = ["id", "email", "full_name", "short_name"]
        read_only_fields = ["id", "email", "full_name", "short_name"]


class ResourceAccessSerializerMixin:
    """
    A serializer mixin to share controlling that the logged-in user submitting a room access object
    is administrator on the targeted room.
    """

    # pylint: disable=too-many-boolean-expressions
    def validate(self, data):
        """
        Check access rights specific to writing (create/update)
        """
        request = self.context.get("request", None)
        user = getattr(request, "user", None)
        if (
            # Update
            self.instance
            and (
                data["role"] == models.RoleChoices.OWNER
                and not self.instance.resource.is_owner(user)
                or self.instance.role == models.RoleChoices.OWNER
                and not self.instance.user == user
            )
        ) or (
            # Create
            not self.instance
            and data.get("role") == models.RoleChoices.OWNER
            and not data["resource"].is_owner(user)
        ):
            raise PermissionDenied(
                "Only owners of a room can assign other users as owners."
            )
        return data

    def validate_resource(self, resource):
        """The logged-in user must be administrator of the resource."""
        request = self.context.get("request", None)
        user = getattr(request, "user", None)

        if not (user and user.is_authenticated and resource.is_administrator(user)):
            raise PermissionDenied(
                _("You must be administrator or owner of a room to add accesses to it.")
            )

        return resource


class ResourceAccessSerializer(
    ResourceAccessSerializerMixin, serializers.ModelSerializer
):
    """Serialize Room to User accesses for the API."""

    class Meta:
        model = models.ResourceAccess
        fields = ["id", "user", "resource", "role"]
        read_only_fields = ["id"]

    def update(self, instance, validated_data):
        """Make "user" and "resource" fields readonly but only on update."""
        validated_data.pop("resource", None)
        validated_data.pop("user", None)
        return super().update(instance, validated_data)


class NestedResourceAccessSerializer(ResourceAccessSerializer):
    """Serialize Room accesses for the API with full nested user."""

    user = UserSerializer(read_only=True)


class ListRoomSerializer(serializers.ModelSerializer):
    """Serialize Room model for a list API endpoint."""

    class Meta:
        model = models.Room
        fields = ["id", "name", "slug", "is_public"]
        read_only_fields = ["id", "slug"]


class RoomSerializer(serializers.ModelSerializer):
    """Serialize Room model for the API."""

    class Meta:
        model = models.Room
        fields = ["id", "name", "slug", "configuration", "is_public"]
        read_only_fields = ["id", "slug"]

    def to_representation(self, instance):
        """
        Add users only for administrator users.
        Add LiveKit credentials for public instance or related users/groups
        """
        output = super().to_representation(instance)
        request = self.context.get("request")

        if not request:
            return output

        role = instance.get_role(request.user)
        is_admin = models.RoleChoices.check_administrator_role(role)

        if role is not None:
            access_serializer = NestedResourceAccessSerializer(
                instance.accesses.select_related("resource", "user").all(),
                context=self.context,
                many=True,
            )
            output["accesses"] = access_serializer.data

        if not is_admin:
            del output["configuration"]

        if role is not None or instance.is_public:
            slug = f"{instance.id!s}"
            username = request.query_params.get("username", None)

            output["livekit"] = {
                "url": settings.LIVEKIT_CONFIGURATION["url"],
                "room": slug,
                "token": utils.generate_token(
                    room=slug, user=request.user, username=username
                ),
            }

        output["is_administrable"] = is_admin

        return output


class RecordingSerializer(serializers.ModelSerializer):
    """Serialize Recording for the API."""

    room = ListRoomSerializer(read_only=True)

    class Meta:
        model = models.Recording
        fields = ["id", "room", "created_at", "updated_at", "status"]
        read_only_fields = fields


class StartRecordingSerializer(serializers.Serializer):
    """Validate start recording requests."""

    mode = serializers.ChoiceField(
        choices=models.RecordingModeChoices.choices,
        required=True,
        error_messages={
            "required": "Recording mode is required.",
            "invalid_choice": "Invalid recording mode. Choose between "
            "screen_recording or transcript.",
        },
    )

    def create(self, validated_data):
        """Not implemented as this is a validation-only serializer."""
        raise NotImplementedError("StartRecordingSerializer is validation-only")

    def update(self, instance, validated_data):
        """Not implemented as this is a validation-only serializer."""
        raise NotImplementedError("StartRecordingSerializer is validation-only")
