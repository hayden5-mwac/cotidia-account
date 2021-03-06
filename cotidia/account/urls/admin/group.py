from django.urls import path
from django.conf.urls import url

from cotidia.admin.views.generic import DynamicListView
from cotidia.account.views.admin.group import (
    GroupCreate,
    GroupDetail,
    GroupUpdate,
    GroupDelete,
)
from cotidia.account.serializers.group import GroupAdminSerializer


ure = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

urlpatterns = [
    path(
        "",
        DynamicListView.as_view(),
        {
            "model": "group",
            "app_label": "auth",
            "serializer_class": GroupAdminSerializer,
            "template_type": "padded",
            "add_view": True,
        },
        name="group-list",
    ),
    url(r"^add/$", GroupCreate.as_view(), name="group-add"),
    url(r"^(?P<pk>[\d]+)$", GroupDetail.as_view(), name="group-detail"),
    url(r"^(?P<pk>[\d]+)/update$", GroupUpdate.as_view(), name="group-update"),
    url(r"^(?P<pk>[\d]+)/delete$", GroupDelete.as_view(), name="group-delete"),
]
