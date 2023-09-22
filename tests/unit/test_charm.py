import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from charm import LxdIntegratorCharm
from ops import ActiveStatus, BlockedStatus
from ops.testing import Harness


@pytest.fixture
def harness(request):
    harness = Harness(LxdIntegratorCharm)
    request.addfinalizer(harness.cleanup)
    harness.begin()
    yield harness


@pytest.fixture
def lxd_response():
    return {
        "metadata": {
            "auth": "trusted",
            "environment": {"server_name": "lxd_test"},
        }
    }


def test_on_install_blocks_if_not_trusted(harness: Harness):
    harness.charm.on.install.emit()
    assert harness.model.unit.status == BlockedStatus(
        "Missing credentials access; grant with: juju trust"
    )


def test_get_credentials_from_config(harness: Harness, tls_config, lxd_secret, lxd_response):
    with harness.hooks_disabled():
        harness.update_config(
            {
                "lxd_endpoint": lxd_secret["endpoint"],
                "lxd_client_cert": tls_config[1].decode("utf-8"),
                "lxd_client_key": tls_config[0].decode("utf-8"),
                "lxd_server_cert": lxd_secret["credential"]["attrs"]["server-cert"],
            }
        )
    with patch("charm.Lxd._new_connection") as mocked_con:
        f = BytesIO(json.dumps(lxd_response).encode("utf-8"))
        mocked_response = MagicMock()
        mocked_response.getresponse.return_value = f
        mocked_con.return_value = mocked_response
        harness.charm.on.install.emit()
        assert harness.model.unit.status == ActiveStatus("")


def test_success_on_trust(harness: Harness, lxd_secret, lxd_response):
    with patch("charm.subprocess.run") as mock_cmd, patch(
        "charm.Lxd._new_connection"
    ) as mocked_con:
        f = BytesIO(json.dumps(lxd_response).encode("utf-8"))
        mocked_response = MagicMock()
        mocked_response.getresponse.return_value = f
        mocked_con.return_value = mocked_response
        mock_cmd.return_value = MagicMock(stdout=json.dumps(lxd_secret).encode("utf-8"))
        harness.charm.on.config_changed.emit()
        assert harness.model.unit.status == ActiveStatus("")


def test_publish_unit_data_on_relation_join(harness: Harness, lxd_secret, lxd_response):
    with harness.hooks_disabled():
        id = harness.add_relation("api", harness.model.app.name)
        with patch("charm.subprocess.run") as mock_cmd, patch(
            "charm.Lxd._new_connection"
        ) as mocked_con:
            f = BytesIO(json.dumps(lxd_response).encode("utf-8"))
            mocked_response = MagicMock()
            mocked_response.getresponse.return_value = f
            mocked_con.return_value = mocked_response
            mock_cmd.return_value = MagicMock(stdout=json.dumps(lxd_secret).encode("utf-8"))
            harness.charm.on.install.emit()
    harness.charm.on.api_relation_joined.emit(harness.model.get_relation("api", id))
    data = harness.get_relation_data(id, harness.model.unit)
    assert "nodes" in data
    assert "version" in data


def test_registers_cert_on_relation_change(harness: Harness, lxd_secret, lxd_response, tls_config):
    relation_data = {
        "nodes": json.dumps(
            [{"endpoint": "https://1.2.3.4:8443", "name": "lxd_test", "trusted_certs_fp": "[]"}]
        ),
        "version": "1.0",
    }
    with harness.hooks_disabled():
        id = harness.add_relation("api", "app")
        harness.update_relation_data(id, harness.model.unit.name, relation_data)
        with patch("charm.subprocess.run") as mock_cmd, patch(
            "charm.Lxd._new_connection"
        ) as mocked_con:
            f = BytesIO(json.dumps(lxd_response).encode("utf-8"))
            mocked_response = MagicMock()
            mocked_response.getresponse.return_value = f
            mocked_con.return_value = mocked_response
            mock_cmd.return_value = MagicMock(stdout=json.dumps(lxd_secret).encode("utf-8"))
            harness.charm.on.install.emit()
            harness.add_relation_unit(id, "app/0")
    with patch("charm.Lxd._register_cert") as new_cert:
        app_relation_data = {
            "trusted_certs_fp": "[]",
            "client_certificates": f"[{json.dumps(tls_config[1].decode('utf-8'))}]",
        }
        harness.update_relation_data(id, "app/0", app_relation_data)
        assert new_cert.call_count == 1
