# Copyright 2013-2017 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test ResourcePool objects."""

from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from maasserver.enum import NODE_PERMISSION
from maasserver.models.resourcepool import (
    DEFAULT_RESOURCEPOOL_DESCRIPTION,
    DEFAULT_RESOURCEPOOL_NAME,
    ResourcePool,
)
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from maasserver.utils.orm import reload_object


class TestResourcePoolManager(MAASServerTestCase):
    """Tests for `ResourcePool` manager."""

    def test_get_default_resource_pool_returns_default_pool(self):
        pool = ResourcePool.objects.get_default_resource_pool()
        self.assertEqual(pool.id, 0)
        self.assertEqual(pool.name, DEFAULT_RESOURCEPOOL_NAME)
        self.assertEqual(pool.description, DEFAULT_RESOURCEPOOL_DESCRIPTION)
        self.assertIsNotNone(pool.created)
        self.assertIsNotNone(pool.updated)

    def test_get_default_resource_pool_ignores_other_pools(self):
        factory.make_ResourcePool()
        self.assertEqual(
            ResourcePool.objects.get_default_resource_pool().name,
            DEFAULT_RESOURCEPOOL_NAME)


class TestResourcePool(MAASServerTestCase):

    def test_init(self):
        name = factory.make_name('name')
        description = factory.make_name('description')
        pool = ResourcePool(name=name, description=description)
        pool.save()
        pool = reload_object(pool)
        self.assertEqual(pool.name, name)
        self.assertEqual(pool.description, description)

    def test_is_default_true(self):
        self.assertTrue(
            ResourcePool.objects.get_default_resource_pool().is_default())

    def test_is_default_false(self):
        self.assertFalse(factory.make_ResourcePool().is_default())

    def test_delete(self):
        pool = factory.make_ResourcePool()
        pool.delete()
        self.assertIsNone(reload_object(pool))

    def test_delete_default_fails(self):
        pool = ResourcePool.objects.get_default_resource_pool()
        self.assertRaises(ValidationError, pool.delete)

    def test_delete_pool_with_machines_fails(self):
        pool = ResourcePool.objects.get_default_resource_pool()
        factory.make_Node(pool=pool)
        self.assertRaises(ValidationError, pool.delete)


class TestResourcePoolManagerGetResourcePoolOr404(MAASServerTestCase):

    def test__user_view_returns_resource_pool(self):
        user = factory.make_User()
        pool = factory.make_ResourcePool()
        self.assertEqual(
            pool,
            ResourcePool.objects.get_resource_pool_or_404(
                pool.id, user, NODE_PERMISSION.VIEW))

    def test__user_edit_raises_PermissionError(self):
        user = factory.make_User()
        pool = factory.make_ResourcePool()
        self.assertRaises(
            PermissionDenied,
            ResourcePool.objects.get_resource_pool_or_404,
            pool.id, user, NODE_PERMISSION.EDIT)

    def test__user_admin_raises_PermissionError(self):
        user = factory.make_User()
        pool = factory.make_ResourcePool()
        self.assertRaises(
            PermissionDenied,
            ResourcePool.objects.get_resource_pool_or_404,
            pool.id, user, NODE_PERMISSION.ADMIN)

    def test__admin_view_returns_resource_pool(self):
        admin = factory.make_admin()
        pool = factory.make_ResourcePool()
        self.assertEqual(
            pool,
            ResourcePool.objects.get_resource_pool_or_404(
                pool.id, admin, NODE_PERMISSION.VIEW))

    def test__admin_edit_returns_resource_pool(self):
        admin = factory.make_admin()
        pool = factory.make_ResourcePool()
        self.assertEqual(
            pool,
            ResourcePool.objects.get_resource_pool_or_404(
                pool.id, admin, NODE_PERMISSION.EDIT))

    def test__admin_admin_returns_pool(self):
        admin = factory.make_admin()
        pool = factory.make_ResourcePool()
        self.assertEqual(
            pool,
            ResourcePool.objects.get_resource_pool_or_404(
                pool.id, admin, NODE_PERMISSION.ADMIN))
