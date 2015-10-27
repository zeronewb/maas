# Copyright 2015 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""VLAN form."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = [
    "VLANForm",
]

from django.core.exceptions import ValidationError
from maasserver.forms import MAASModelForm
from maasserver.models.vlan import VLAN


class VLANForm(MAASModelForm):
    """VLAN creation/edition form."""

    class Meta:
        model = VLAN
        fields = (
            'name',
            'vid',
            )

    def __init__(self, *args, **kwargs):
        self.fabric = kwargs.pop('fabric', None)
        super(VLANForm, self).__init__(*args, **kwargs)
        instance = kwargs.get('instance')
        if instance is None and self.fabric is None:
            raise ValueError("Form requires either a instance or a fabric.")

    def clean(self):
        cleaned_data = super(VLANForm, self).clean()
        if self.instance.id is not None and self.instance.is_fabric_default():
            raise ValidationError(
                "Cannot modify the default VLAN for a fabric.")
        return cleaned_data

    def save(self):
        """Persist the interface into the database."""
        interface = super(VLANForm, self).save(commit=False)
        if self.fabric is not None:
            interface.fabric = self.fabric
        interface.save()
        return interface