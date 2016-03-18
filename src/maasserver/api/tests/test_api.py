# Copyright 2012-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test maasserver API."""

__all__ = []

import http.client
import json

from django.conf import settings
from django.core.urlresolvers import reverse
from maasserver.api import (
    machines as machines_module,
    nodes as nodes_module,
)
from maasserver.api.nodes import store_node_power_parameters
from maasserver.exceptions import (
    ClusterUnavailable,
    MAASAPIBadRequest,
)
from maasserver.forms_settings import INVALID_SETTING_MSG_TEMPLATE
from maasserver.models import (
    Config,
    SSHKey,
)
from maasserver.models.user import get_auth_tokens
from maasserver.testing import get_data
from maasserver.testing.api import APITestCase
from maasserver.testing.factory import factory
from maasserver.testing.oauthclient import OAuthAuthenticatedClient
from maasserver.testing.testcase import (
    MAASServerTestCase,
    MAASTransactionServerTestCase,
)
from maasserver.utils.converters import json_load_bytes
from maasserver.utils.orm import get_one
from maastesting.matchers import MockCalledOnceWith
from mock import Mock
from testtools.matchers import (
    Contains,
    Equals,
    MatchesListwise,
)


class TestAuthentication(MAASServerTestCase):
    """Tests for `maasserver.api.auth`."""

    def test_invalid_oauth_request(self):
        # An OAuth-signed request that does not validate is an error.
        user = factory.make_User()
        client = OAuthAuthenticatedClient(user)
        get_auth_tokens(user).delete()  # Delete the user's API keys.
        response = client.post(reverse('nodes_handler'), {'op': 'start'})
        observed = response.status_code, response.content
        expected = (
            Equals(http.client.UNAUTHORIZED),
            Contains(b"Invalid access token:"),
            )
        self.assertThat(observed, MatchesListwise(expected))


class TestXSSBugs(MAASServerTestCase):
    """Tests for making sure we don't allow cross-site scripting bugs."""

    def test_invalid_signature_response_is_textplain(self):
        response = self.client.get(
            reverse('nodes_handler'),
            {'op': '<script>alert(document.domain)</script>'})
        self.assertIn("text/plain", response.get("Content-Type"))
        self.assertNotIn("text/html", response.get("Content-Type"))


class TestStoreNodeParameters(MAASServerTestCase):
    """Tests for `store_node_power_parameters`."""

    def setUp(self):
        super(TestStoreNodeParameters, self).setUp()
        self.node = factory.make_Node()
        self.save = self.patch(self.node, "save")
        self.request = Mock()

    def test_no_connected_rack_controllers(self):
        # When get_power_types returns empty dictionary.
        mock_get_power_types = self.patch(nodes_module, "get_power_types")
        mock_get_power_types.return_value = {}
        power_type = factory.pick_power_type()
        self.request.POST = {"power_type": power_type}
        error = self.assertRaises(
            ClusterUnavailable, store_node_power_parameters,
            self.node, self.request)
        self.assertEquals(
            "No rack controllers connected to validate the power_type.",
            str(error))
        self.assertThat(
            mock_get_power_types, MockCalledOnceWith(ignore_errors=True))

    def test_power_type_not_given(self):
        # When power_type is not specified, nothing happens.
        self.request.POST = {}
        self.node.power_type = ''
        store_node_power_parameters(self.node, self.request)
        self.assertEqual('', self.node.power_type)
        self.assertEqual({}, self.node.power_parameters)
        self.save.assert_has_calls([])

    def test_power_type_set_but_no_parameters(self):
        # When power_type is valid, it is set. However, if power_parameters is
        # not specified, the node's power_parameters is left alone, and the
        # node is saved.
        power_type = factory.pick_power_type()
        self.request.POST = {"power_type": power_type}
        store_node_power_parameters(self.node, self.request)
        self.assertEqual(power_type, self.node.power_type)
        self.assertEqual({}, self.node.power_parameters)
        self.save.assert_called_once_with()

    def test_power_type_set_with_parameters(self):
        # When power_type is valid, and power_parameters is valid JSON, both
        # fields are set on the node, and the node is saved.
        power_type = factory.pick_power_type()
        power_parameters = {"foo": [1, 2, 3]}
        self.request.POST = {
            "power_type": power_type,
            "power_parameters": json.dumps(power_parameters),
            }
        store_node_power_parameters(self.node, self.request)
        self.assertEqual(power_type, self.node.power_type)
        self.assertEqual(power_parameters, self.node.power_parameters)
        self.save.assert_called_once_with()

    def test_power_type_set_with_invalid_parameters(self):
        # When power_type is valid, but power_parameters is invalid JSON, the
        # node is not saved, and an exception is raised.
        power_type = factory.pick_power_type()
        self.request.POST = {
            "power_type": power_type,
            "power_parameters": "Not JSON.",
            }
        self.assertRaises(
            MAASAPIBadRequest, store_node_power_parameters,
            self.node, self.request)
        self.save.assert_has_calls([])

    def test_invalid_power_type(self):
        # When power_type is invalid, the node is not saved, and an exception
        # is raised.
        self.request.POST = {"power_type": factory.make_name("bogus")}
        self.assertRaises(
            MAASAPIBadRequest, store_node_power_parameters,
            self.node, self.request)
        self.save.assert_has_calls([])

    def test_unknown_power_type(self):
        # Sometimes a node doesn't know its power type, and will declare its
        # powertype as ''; store_node_power_parameters will store that
        # appropriately.
        power_type = ''
        self.request.POST = {
            "power_type": '',
            }
        store_node_power_parameters(self.node, self.request)
        self.assertEqual(power_type, self.node.power_type)
        self.save.assert_called_once_with()


class AccountAPITest(APITestCase):

    def test_handler_path(self):
        self.assertEqual(
            '/api/2.0/account/', reverse('account_handler'))

    def test_create_authorisation_token(self):
        # The api operation create_authorisation_token returns a json dict
        # with the consumer_key, the token_key and the token_secret in it.
        response = self.client.post(
            reverse('account_handler'), {'op': 'create_authorisation_token'})
        parsed_result = json_load_bytes(response.content)

        self.assertEqual(
            ['consumer_key', 'token_key', 'token_secret'],
            sorted(parsed_result))
        self.assertIsInstance(parsed_result['consumer_key'], str)
        self.assertIsInstance(parsed_result['token_key'], str)
        self.assertIsInstance(parsed_result['token_secret'], str)

    def test_delete_authorisation_token_not_found(self):
        # If the provided token_key does not exist (for the currently
        # logged-in user), the api returns a 'Not Found' (404) error.
        response = self.client.post(
            reverse('account_handler'),
            {'op': 'delete_authorisation_token', 'token_key': 'no-such-token'})

        self.assertEqual(http.client.NOT_FOUND, response.status_code)

    def test_delete_authorisation_token_bad_request_no_token(self):
        # token_key is a mandatory parameter when calling
        # delete_authorisation_token. It it is not present in the request's
        # parameters, the api returns a 'Bad Request' (400) error.
        response = self.client.post(
            reverse('account_handler'), {'op': 'delete_authorisation_token'})

        self.assertEqual(http.client.BAD_REQUEST, response.status_code)


class TestSSHKeyHandlers(APITestCase):

    def test_sshkeys_handler_path(self):
        self.assertEqual(
            '/api/2.0/account/prefs/sshkeys/', reverse('sshkeys_handler'))

    def test_sshkey_handler_path(self):
        self.assertEqual(
            '/api/2.0/account/prefs/sshkeys/key/',
            reverse('sshkey_handler', args=['key']))

    def test_list_works(self):
        _, keys = factory.make_user_with_keys(user=self.logged_in_user)
        response = self.client.get(reverse('sshkeys_handler'))
        self.assertEqual(http.client.OK, response.status_code, response)
        parsed_result = json_load_bytes(response.content)
        expected_result = [
            dict(
                id=keys[0].id,
                key=keys[0].key,
                resource_uri=reverse('sshkey_handler', args=[keys[0].id]),
                ),
            dict(
                id=keys[1].id,
                key=keys[1].key,
                resource_uri=reverse('sshkey_handler', args=[keys[1].id]),
                ),
            ]
        self.assertEqual(expected_result, parsed_result)

    def test_get_by_id_works(self):
        _, keys = factory.make_user_with_keys(
            n_keys=1, user=self.logged_in_user)
        key = keys[0]
        response = self.client.get(
            reverse('sshkey_handler', args=[key.id]))
        self.assertEqual(http.client.OK, response.status_code, response)
        parsed_result = json_load_bytes(response.content)
        expected = dict(
            id=key.id,
            key=key.key,
            resource_uri=reverse('sshkey_handler', args=[key.id]),
            )
        self.assertEqual(expected, parsed_result)

    def test_delete_by_id_works(self):
        _, keys = factory.make_user_with_keys(
            n_keys=2, user=self.logged_in_user)
        response = self.client.delete(
            reverse('sshkey_handler', args=[keys[0].id]))
        self.assertEqual(
            http.client.NO_CONTENT, response.status_code, response)
        keys_after = SSHKey.objects.filter(user=self.logged_in_user)
        self.assertEqual(1, len(keys_after))
        self.assertEqual(keys[1].id, keys_after[0].id)

    def test_delete_fails_if_not_your_key(self):
        user, keys = factory.make_user_with_keys(n_keys=1)
        response = self.client.delete(
            reverse('sshkey_handler', args=[keys[0].id]))
        self.assertEqual(http.client.FORBIDDEN, response.status_code, response)
        self.assertEqual(1, len(SSHKey.objects.filter(user=user)))

    def test_adding_works(self):
        key_string = get_data('data/test_rsa0.pub')
        response = self.client.post(
            reverse('sshkeys_handler'), data=dict(key=key_string))
        self.assertEqual(http.client.CREATED, response.status_code)
        parsed_response = json_load_bytes(response.content)
        self.assertEqual(key_string, parsed_response["key"])
        added_key = get_one(SSHKey.objects.filter(user=self.logged_in_user))
        self.assertEqual(key_string, added_key.key)

    def test_adding_catches_key_validation_errors(self):
        key_string = factory.make_string()
        response = self.client.post(
            reverse('sshkeys_handler'), data=dict(key=key_string))
        self.assertEqual(
            http.client.BAD_REQUEST, response.status_code, response)
        self.assertIn(b"Invalid", response.content)

    def test_adding_returns_badrequest_when_key_not_in_form(self):
        response = self.client.post(reverse('sshkeys_handler'))
        self.assertEqual(
            http.client.BAD_REQUEST, response.status_code, response)
        self.assertEqual(
            dict(key=["This field is required."]),
            json_load_bytes(response.content))


class MAASAPIAnonTest(MAASServerTestCase):
    # The MAAS' handler is not accessible to anon users.

    def test_anon_get_config_forbidden(self):
        response = self.client.get(
            reverse('maas_handler'),
            {'op': 'get_config'})

        self.assertEqual(http.client.FORBIDDEN, response.status_code)

    def test_anon_set_config_forbidden(self):
        response = self.client.post(
            reverse('maas_handler'),
            {'op': 'set_config'})

        self.assertEqual(http.client.FORBIDDEN, response.status_code)


class MAASAPITest(APITestCase):

    def test_handler_path(self):
        self.assertEqual(
            '/api/2.0/maas/', reverse('maas_handler'))

    def test_simple_user_get_config_forbidden(self):
        response = self.client.get(
            reverse('maas_handler'),
            {'op': 'get_config'})

        self.assertEqual(http.client.FORBIDDEN, response.status_code)

    def test_simple_user_set_config_forbidden(self):
        response = self.client.post(
            reverse('maas_handler'),
            {'op': 'set_config'})

        self.assertEqual(http.client.FORBIDDEN, response.status_code)

    def test_get_config_requires_name_param(self):
        self.become_admin()
        response = self.client.get(
            reverse('maas_handler'),
            {
                'op': 'get_config',
            })

        self.assertEqual(http.client.BAD_REQUEST, response.status_code)
        self.assertEqual(b"No provided name!", response.content)

    def test_get_config_returns_config(self):
        self.become_admin()
        name = 'maas_name'
        value = factory.make_string()
        Config.objects.set_config(name, value)
        response = self.client.get(
            reverse('maas_handler'),
            {
                'op': 'get_config',
                'name': name,
            })

        self.assertEqual(http.client.OK, response.status_code)
        parsed_result = json_load_bytes(response.content)
        self.assertIn('application/json', response['Content-Type'])
        self.assertEqual(value, parsed_result)

    def test_get_config_rejects_unknown_config_item(self):
        self.become_admin()
        name = factory.make_string()
        value = factory.make_string()
        Config.objects.set_config(name, value)
        response = self.client.get(
            reverse('maas_handler'),
            {
                'op': 'get_config',
                'name': name,
            })

        self.assertEqual(
            (
                http.client.BAD_REQUEST,
                {name: [INVALID_SETTING_MSG_TEMPLATE % name]},
            ),
            (response.status_code, json_load_bytes(response.content)))

    def test_set_config_requires_name_param(self):
        self.become_admin()
        response = self.client.post(
            reverse('maas_handler'),
            {
                'op': 'set_config',
                'value': factory.make_string(),
            })

        self.assertEqual(http.client.BAD_REQUEST, response.status_code)
        self.assertEqual(b"No provided name!", response.content)

    def test_set_config_requires_string_name_param(self):
        self.become_admin()
        value = factory.make_string()
        response = self.client.post(
            reverse('maas_handler'),
            {
                'op': 'set_config',
                'name': '',  # Invalid empty name.
                'value': value,
            })

        self.assertEqual(http.client.BAD_REQUEST, response.status_code)
        self.assertEqual(
            b"Invalid name: Please enter a value", response.content)

    def test_set_config_requires_value_param(self):
        self.become_admin()
        response = self.client.post(
            reverse('maas_handler'),
            {
                'op': 'set_config',
                'name': factory.make_string(),
            })

        self.assertEqual(http.client.BAD_REQUEST, response.status_code)
        self.assertEqual(b"No provided value!", response.content)

    def test_admin_set_config(self):
        self.become_admin()
        name = 'maas_name'
        value = factory.make_string()
        response = self.client.post(
            reverse('maas_handler'),
            {
                'op': 'set_config',
                'name': name,
                'value': value,
            })

        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        stored_value = Config.objects.get_config(name)
        self.assertEqual(stored_value, value)

    def test_admin_set_config_rejects_unknown_config_item(self):
        self.become_admin()
        name = factory.make_string()
        value = factory.make_string()
        response = self.client.post(
            reverse('maas_handler'),
            {
                'op': 'set_config',
                'name': name,
                'value': value,
            })

        self.assertEqual(
            (
                http.client.BAD_REQUEST,
                {name: [INVALID_SETTING_MSG_TEMPLATE % name]},
            ),
            (response.status_code, json_load_bytes(response.content)))


class APIErrorsTest(MAASTransactionServerTestCase):

    def test_internal_error_generates_proper_api_response(self):
        error_message = factory.make_string()

        # Monkey patch api.create_node to have it raise a RuntimeError.
        def raise_exception(*args, **kwargs):
            raise RuntimeError(error_message)
        self.patch(machines_module, 'create_machine', raise_exception)
        response = self.client.post(
            reverse('machines_handler'), {'op': 'create'})

        self.assertEqual(
            (
                http.client.INTERNAL_SERVER_ERROR,
                error_message.encode(settings.DEFAULT_CHARSET),
            ),
            (response.status_code, response.content))


def dict_subset(obj, fields):
    """Return a dict of a subset of the fields/values of an object."""
    undefined = object()
    values = (getattr(obj, field, undefined) for field in fields)
    return {
        field: value for field, value in zip(fields, values)
        if value is not undefined
    }
