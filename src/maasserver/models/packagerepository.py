# Copyright 2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""PackageRepository objects."""

__all__ = [
    "PackageRepository",
    ]

from django.contrib.postgres.fields import ArrayField
from django.db.models import (
    BooleanField,
    CharField,
    Manager,
    QuerySet,
    TextField,
    URLField,
)
from maasserver import DefaultMeta
from maasserver.models.cleansave import CleanSave
from maasserver.models.timestampedmodel import TimestampedModel
from maasserver.utils.orm import MAASQueriesMixin


class PackageRepositoryQueriesMixin(MAASQueriesMixin):

    def get_specifiers_q(self, specifiers, separator=':', **kwargs):
        # This dict is used by the constraints code to identify objects
        # with particular properties. Please note that changing the keys here
        # can impact backward compatibility, so use caution.
        specifier_types = {
            None: self._add_default_query,
            'id': "__id",
            'name': "__name",
        }
        return super(PackageRepositoryQueriesMixin, self).get_specifiers_q(
            specifiers, specifier_types=specifier_types, separator=separator,
            **kwargs)


class PackageRepositoryQuerySet(QuerySet, PackageRepositoryQueriesMixin):
    """Custom QuerySet which mixes in some additional queries specific to
    this object. This needs to be a mixin because an identical method is needed
    on both the Manager and all QuerySets which result from calling the
    manager.
    """


class PackageRepositoryManager(Manager, PackageRepositoryQueriesMixin):
    """Manager for `PackageRepository` class."""

    def get_queryset(self):
        return PackageRepositoryQuerySet(self.model, using=self._db)

    def get_object_or_404(self, specifiers):
        """Fetch a `PackageRepository` by its id. Raise exceptions if no
        `PackageRepository` with its id exists, or if the provided user does
        not have the required permission on this `PackageRepository`.

        :param specifiers: The interface specifier.
        :type specifiers: str
        :raises: django.http.Http404_,
            :class:`maasserver.exceptions.PermissionDenied`.

        .. _django.http.Http404: https://
           docs.djangoproject.com/en/dev/topics/http/views/
           #the-http404-exception
        """
        return self.get_object_by_specifiers_or_raise(specifiers)


class PackageRepository(CleanSave, TimestampedModel):
    """A `PackageRepository`."""

    MAIN_ARCHES = ['amd64', 'i386']
    PORTS_ARCHES = ['armhf', 'arm64', 'powerpc', 'ppc64el']

    class Meta(DefaultMeta):
        """Needed for South to recognize this model."""

    objects = PackageRepositoryManager()

    name = CharField(max_length=41, unique=True, default='')

    description = TextField(blank=True, default='')

    url = URLField(blank=False, help_text="The URL of the PackageRepository.")

    distributions = ArrayField(
        TextField(), blank=True, null=True, default=list)

    disabled_pockets = ArrayField(
        TextField(), blank=True, null=True, default=list)

    components = ArrayField(TextField(), blank=True, null=True, default=list)

    arches = ArrayField(TextField(), blank=True, null=True, default=list)

    key = TextField(blank=True, default='')

    default = BooleanField(default=False)

    enabled = BooleanField(default=True)

    def __str__(self):
        return "%s (%s)" % (self.id, self.name)

    @classmethod
    def get_main_archive(cls):
        repo = cls.objects.filter(
            arches__overlap=PackageRepository.MAIN_ARCHES,
            enabled=True,
            default=True).first()
        if repo is None:
            return "http://archive.ubuntu.com/ubuntu"
        else:
            return repo.url

    @classmethod
    def get_ports_archive(cls):
        repo = cls.objects.filter(
            arches__overlap=PackageRepository.PORTS_ARCHES,
            enabled=True,
            default=True).first()
        if repo is None:
            return "http://ports.ubuntu.com/ubuntu-ports"
        else:
            return repo.url