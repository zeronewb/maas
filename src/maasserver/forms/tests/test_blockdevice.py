# Copyright 2015-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for all forms that are used with `BlockDevice`."""

__all__ = []

import random
import uuid

from maasserver.enum import FILESYSTEM_TYPE
from maasserver.forms import (
    CreatePhysicalBlockDeviceForm,
    FormatBlockDeviceForm,
    UpdateDeployedPhysicalBlockDeviceForm,
    UpdatePhysicalBlockDeviceForm,
    UpdateVirtualBlockDeviceForm,
)
from maasserver.models import Filesystem
from maasserver.models.blockdevice import MIN_BLOCK_DEVICE_SIZE
from maasserver.models.partition import PARTITION_ALIGNMENT_SIZE
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from maasserver.utils.converters import round_size_to_nearest_block
from maasserver.utils.orm import (
    get_one,
    reload_object,
)
from testtools.matchers import MatchesStructure


class TestFormatBlockDeviceForm(MAASServerTestCase):

    def test_requires_fields(self):
        form = FormatBlockDeviceForm(
            block_device=factory.make_BlockDevice(), data={})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertItemsEqual(['fstype'], form.errors.keys())

    def test_is_not_valid_if_block_device_has_partition_table(self):
        fstype = factory.pick_filesystem_type()
        block_device = factory.make_PhysicalBlockDevice()
        factory.make_PartitionTable(block_device=block_device)
        data = {
            'fstype': fstype,
            }
        form = FormatBlockDeviceForm(block_device, data=data)
        self.assertFalse(
            form.is_valid(),
            "Should be invalid because block device has a partition table.")
        self.assertEqual({
            '__all__': [
                "Cannot format block device with a partition table.",
            ]},
            form._errors)

    def test_is_not_valid_if_invalid_format_fstype(self):
        block_device = factory.make_PhysicalBlockDevice()
        data = {
            'fstype': FILESYSTEM_TYPE.LVM_PV,
            }
        form = FormatBlockDeviceForm(block_device, data=data)
        self.assertFalse(
            form.is_valid(),
            "Should be invalid because of an invalid fstype.")
        self.assertEqual({
            'fstype': [
                "Select a valid choice. lvm-pv is not one of the "
                "available choices."
                ],
            }, form._errors)

    def test_is_not_valid_if_invalid_uuid(self):
        fstype = factory.pick_filesystem_type()
        block_device = factory.make_PhysicalBlockDevice()
        data = {
            'fstype': fstype,
            'uuid': factory.make_string(size=32),
            }
        form = FormatBlockDeviceForm(block_device, data=data)
        self.assertFalse(
            form.is_valid(),
            "Should be invalid because of an invalid uuid.")
        self.assertEqual({'uuid': ["Enter a valid value."]}, form._errors)

    def test_is_not_valid_if_invalid_uuid_append_XYZ(self):
        fstype = factory.pick_filesystem_type()
        block_device = factory.make_PhysicalBlockDevice()
        data = {
            'fstype': fstype,
            'uuid': "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaXYZ",
            }
        form = FormatBlockDeviceForm(block_device, data=data)
        self.assertFalse(
            form.is_valid(),
            "Should be invalid because of an invalid uuid.")
        self.assertEqual({'uuid': ["Enter a valid value."]}, form._errors)

    def test_is_not_valid_if_invalid_uuid_prepend_XYZ(self):
        fstype = factory.pick_filesystem_type()
        block_device = factory.make_PhysicalBlockDevice()
        data = {
            'fstype': fstype,
            'uuid': "XYZaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            }
        form = FormatBlockDeviceForm(block_device, data=data)
        self.assertFalse(
            form.is_valid(),
            "Should be invalid because of an invalid uuid.")
        self.assertEqual({'uuid': ["Enter a valid value."]}, form._errors)

    def test_creates_filesystem(self):
        fsuuid = "%s" % uuid.uuid4()
        fstype = factory.pick_filesystem_type()
        block_device = factory.make_PhysicalBlockDevice()
        data = {
            'uuid': fsuuid,
            'fstype': fstype,
            }
        form = FormatBlockDeviceForm(block_device, data=data)
        self.assertTrue(form.is_valid(), form._errors)
        form.save()
        filesystem = get_one(
            Filesystem.objects.filter(block_device=block_device))
        self.assertIsNotNone(filesystem)
        self.assertEqual(fstype, filesystem.fstype)
        self.assertEqual(fsuuid, filesystem.uuid)

    def test_deletes_old_filesystem_and_creates_new_one(self):
        fstype = factory.pick_filesystem_type()
        block_device = factory.make_PhysicalBlockDevice()
        prev_filesystem = factory.make_Filesystem(block_device=block_device)
        data = {
            'fstype': fstype,
            }
        form = FormatBlockDeviceForm(block_device, data=data)
        self.assertTrue(form.is_valid(), form._errors)
        form.save()
        self.assertEqual(
            1,
            Filesystem.objects.filter(block_device=block_device).count(),
            "Should only be one filesystem that exists for block device.")
        self.assertIsNone(reload_object(prev_filesystem))
        filesystem = get_one(
            Filesystem.objects.filter(block_device=block_device))
        self.assertIsNotNone(filesystem)
        self.assertEqual(fstype, filesystem.fstype)


class TestCreatePhysicalBlockDeviceForm(MAASServerTestCase):

    def test_requires_fields(self):
        node = factory.make_Node()
        form = CreatePhysicalBlockDeviceForm(node, data={})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertEqual({
            'name': ['This field is required.'],
            'size': ['This field is required.'],
            'block_size': ['This field is required.'],
            '__all__': [
                'serial/model are required if id_path is not provided.'],
            }, form.errors)

    def test_creates_physical_block_device_with_model_serial(self):
        node = factory.make_Node()
        name = factory.make_name("sd")
        model = factory.make_name("model")
        serial = factory.make_name("serial")
        size = random.randint(
            MIN_BLOCK_DEVICE_SIZE, MIN_BLOCK_DEVICE_SIZE * 10)
        block_size = 4096
        form = CreatePhysicalBlockDeviceForm(node, data={
            'name': name,
            'model': model,
            'serial': serial,
            'size': size,
            'block_size': block_size,
            })
        self.assertTrue(form.is_valid(), form.errors)
        block_device = form.save()
        self.assertThat(block_device, MatchesStructure.byEquality(
            name=name,
            model=model,
            serial=serial,
            size=size,
            block_size=block_size,
            ))

    def test_creates_physical_block_device_with_id_path(self):
        node = factory.make_Node()
        name = factory.make_name("sd")
        id_path = factory.make_absolute_path()
        size = random.randint(
            MIN_BLOCK_DEVICE_SIZE, MIN_BLOCK_DEVICE_SIZE * 10)
        block_size = 4096
        form = CreatePhysicalBlockDeviceForm(node, data={
            'name': name,
            'id_path': id_path,
            'size': size,
            'block_size': block_size,
            })
        self.assertTrue(form.is_valid(), form.errors)
        block_device = form.save()
        self.assertThat(block_device, MatchesStructure.byEquality(
            name=name,
            id_path=id_path,
            size=size,
            block_size=block_size,
            ))


class TestUpdatePhysicalBlockDeviceForm(MAASServerTestCase):

    def test_requires_no_fields(self):
        block_device = factory.make_PhysicalBlockDevice()
        form = UpdatePhysicalBlockDeviceForm(instance=block_device, data={})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertItemsEqual([], form.errors.keys())

    def test_updates_physical_block_device(self):
        block_device = factory.make_PhysicalBlockDevice()
        name = factory.make_name("sd")
        model = factory.make_name("model")
        serial = factory.make_name("serial")
        id_path = factory.make_absolute_path()
        size = random.randint(
            MIN_BLOCK_DEVICE_SIZE, MIN_BLOCK_DEVICE_SIZE * 10)
        block_size = 4096
        form = UpdatePhysicalBlockDeviceForm(instance=block_device, data={
            'name': name,
            'model': model,
            'serial': serial,
            'id_path': id_path,
            'size': size,
            'block_size': block_size,
            })
        self.assertTrue(form.is_valid(), form.errors)
        block_device = form.save()
        self.assertThat(block_device, MatchesStructure.byEquality(
            name=name,
            model=model,
            serial=serial,
            id_path=id_path,
            size=size,
            block_size=block_size,
            ))


class TestUpdateDeployedPhysicalBlockDeviceForm(MAASServerTestCase):

    def test_requires_no_fields(self):
        block_device = factory.make_PhysicalBlockDevice()
        form = UpdateDeployedPhysicalBlockDeviceForm(
            instance=block_device, data={})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertItemsEqual([], form.errors.keys())

    def test_updates_deployed_physical_block_device(self):
        block_device = factory.make_PhysicalBlockDevice()
        name = factory.make_name("sd")
        model = factory.make_name("model")
        serial = factory.make_name("serial")
        id_path = factory.make_absolute_path()
        form = UpdateDeployedPhysicalBlockDeviceForm(
            instance=block_device, data={
                'name': name,
                'model': model,
                'serial': serial,
                'id_path': id_path,
                })
        self.assertTrue(form.is_valid(), form.errors)
        block_device = form.save()
        self.assertThat(block_device, MatchesStructure.byEquality(
            name=name,
            model=model,
            serial=serial,
            id_path=id_path,
            size=block_device.size,
            block_size=block_device.block_size,
            ))


class TestUpdateVirtualBlockDeviceForm(MAASServerTestCase):

    def test_requires_no_fields(self):
        block_device = factory.make_VirtualBlockDevice()
        form = UpdateVirtualBlockDeviceForm(instance=block_device, data={})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertItemsEqual([], form.errors.keys())

    def test_updates_virtual_block_device(self):
        block_device = factory.make_VirtualBlockDevice()
        name = factory.make_name("lv")
        vguuid = "%s" % uuid.uuid4()
        size = random.randint(
            MIN_BLOCK_DEVICE_SIZE, block_device.filesystem_group.get_size())
        form = UpdateVirtualBlockDeviceForm(instance=block_device, data={
            'name': name,
            'uuid': vguuid,
            'size': size,
            })
        self.assertTrue(form.is_valid(), form.errors)
        block_device = form.save()
        expected_size = round_size_to_nearest_block(
            size, PARTITION_ALIGNMENT_SIZE, False)
        self.assertThat(block_device, MatchesStructure.byEquality(
            name=name,
            uuid=vguuid,
            size=expected_size,
            ))
