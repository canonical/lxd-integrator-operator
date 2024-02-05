#!/usr/bin/env python3
#
# (c) 2020 Canonical Ltd. All rights reserved
#

"""Interfaces exposed by the LXD-Integrator Charm."""

import io
import json
import logging
import os
import ssl
from http import client as httpclient

from OpenSSL.crypto import FILETYPE_PEM, load_certificate
from ops.charm import CharmBase, RelationChangedEvent, RelationJoinedEvent
from ops.framework import Object, StoredState

BASE_PATH = os.getenv("JUJU_CHARM_DIR")
CLIENT_CERT_PATH = "{}/client.crt".format(BASE_PATH)
CLIENT_KEY_PATH = "{}/client.key".format(BASE_PATH)
SERVER_CERT_PATH = "{}/server.crt".format(BASE_PATH)

logger = logging.getLogger(__name__)


class Lxd(Object):
    """LXD interface for connection to LXD APIs."""

    state = StoredState()

    def __init__(self, charm: CharmBase, relation_name: str):
        super().__init__(charm, relation_name)

        self.state.set_default(
            endpoint=None,
            server_name=None,
            client_cert=None,
            client_key=None,
            server_cert=None,
        )
        self._relation_name = relation_name

        self.framework.observe(charm.on[relation_name].relation_changed, self._on_relation_changed)
        self.framework.observe(charm.on[relation_name].relation_joined, self._on_relation_joined)

    @property
    def is_joined(self):
        """Property to know if the relation has been joined."""
        return self.framework.model.get_relation(self._relation_name) is not None

    @property
    def is_ready(self) -> bool:
        """Property to know if the relation is ready."""
        return all(
            [
                self.state.endpoint,
                self.state.client_cert,
                self.state.client_key,
                self.state.server_cert,
            ]
        )

    def _new_connection(self) -> httpclient.HTTPSConnection:
        """Return a http.client.HTTPSConnection configured with the proper endpoint and certificates."""
        self._write_certs_to_filesystem()
        sslcontext = ssl.create_default_context(
            purpose=ssl.Purpose.CLIENT_AUTH, cafile=SERVER_CERT_PATH
        )
        sslcontext.load_cert_chain(certfile=CLIENT_CERT_PATH, keyfile=CLIENT_KEY_PATH)
        # Depending on how it was initialized, the LXD server cert can be configured
        # with 127.0.0.1 as its CN, failing the verification
        sslcontext.check_hostname = False
        endpoint = self.state.endpoint.replace("https://", "").replace("http://", "")
        return httpclient.HTTPSConnection(endpoint, context=sslcontext, timeout=5)

    def set_credentials(
        self, endpoint: str, client_cert: str, client_key: str, server_cert: str
    ) -> None:
        """Set credentials for the given LXD cluster."""
        self.state.endpoint = endpoint
        self.state.client_cert = client_cert
        self.state.client_key = client_key
        self.state.server_cert = server_cert

        # Check that the credentials are trusted to LXD
        conn = self._new_connection()
        conn.request("GET", "/1.0")
        raw_res = conn.getresponse().read().decode("utf-8")
        resp = json.loads(raw_res)["metadata"]
        conn.close()
        if resp["auth"] != "trusted":
            raise RuntimeError("invalid credentials: not trusted")
        self.state.server_name = resp["environment"]["server_name"]
        logger.info("credentials configured")

    def _on_relation_joined(self, event: RelationJoinedEvent):
        if not self.is_ready:
            event.defer()
            return

        data = self.framework.model.get_relation(self._relation_name).data[self.model.unit]
        data["nodes"] = json.dumps(
            [
                {
                    "endpoint": self.state.endpoint,
                    "name": self.state.server_name,
                    "trusted_certs_fp": [],
                }
            ]
        )
        data["version"] = "1.0"

    def _clean_certs_from_filesystem(self):
        """Remove previously saved certificates from filesystem."""
        if os.path.exists(CLIENT_CERT_PATH):
            os.remove(CLIENT_CERT_PATH)

        if os.path.exists(CLIENT_KEY_PATH):
            os.remove(CLIENT_KEY_PATH)

        if os.path.exists(SERVER_CERT_PATH):
            os.remove(SERVER_CERT_PATH)

    def _write_certs_to_filesystem(self):
        if not os.path.exists(CLIENT_CERT_PATH):
            with open(os.open(CLIENT_CERT_PATH, os.O_CREAT | os.O_WRONLY, 0o600), "w") as f:
                f.write(self.state.client_cert)

        if not os.path.exists(CLIENT_KEY_PATH):
            with open(os.open(CLIENT_KEY_PATH, os.O_CREAT | os.O_WRONLY, 0o600), "w") as f:
                f.write(self.state.client_key)

        if not os.path.exists(SERVER_CERT_PATH):
            with open(os.open(SERVER_CERT_PATH, os.O_CREAT | os.O_WRONLY, 0o600), "w") as f:
                f.write(self.state.server_cert)

    def _unregister_cert(self, cert: str) -> None:
        if not self.is_ready:
            raise RuntimeError("credentials not configured")

        conn = self._new_connection()

        fp = self._cert_fingerprint(cert)
        logger.info("removing certificate {} from trust store".format(fp))
        conn.request("DELETE", "/1.0/certificates/{}".format(fp))
        response = conn.getresponse()
        data = response.read().decode("utf-8")
        conn.close()

        if response.getcode() != 202:
            logger.error(data)

    def _cert_fingerprint(self, cert):
        if isinstance(cert, str):
            cert = load_certificate(FILETYPE_PEM, cert)
        return cert.digest("sha256").decode("utf-8").replace(":", "").lower()

    def _register_cert(self, cert: str) -> None:
        if not self.is_ready:
            raise RuntimeError("credentials not configured")

        buff = io.StringIO(cert)
        content = ""
        line = buff.readline()
        while line and "-----BEGIN CERTIFICATE-----" not in line:
            line = buff.readline()
        line = buff.readline()
        while line and "-----END CERTIFICATE-----" not in line:
            content += line.rstrip("\r\n")
            line = buff.readline()

        x509_cert = load_certificate(FILETYPE_PEM, cert)
        name = x509_cert.get_subject().CN
        fp = self._cert_fingerprint(x509_cert)

        logger.info("adding certificate {} to trust store".format(fp))

        payload = json.dumps({"type": "client", "certificate": content, "name": name})
        headers = {"Content-Type": "application/json"}

        conn = self._new_connection()
        conn.request("POST", "/1.0/certificates", headers=headers, body=payload)
        response = conn.getresponse()
        data = response.read().decode("utf-8")
        conn.close()
        self._clean_certs_from_filesystem()
        if 200 <= response.getcode() < 300:
            return

        if "Certificate already in trust store" in data:
            logger.warning("certificate already provisioned. Skipping provision")
        else:
            logger.error(data)

    def _on_relation_changed(self, event: RelationChangedEvent):
        if not self.is_ready:
            event.defer()
            return

        received = event.relation.data[event.unit]
        local_data = event.relation.data[self.model.unit]

        trusted_certs_fp = received.get("trusted_certs_fp", [])
        if isinstance(trusted_certs_fp, str):
            trusted_certs_fp = json.loads(trusted_certs_fp)
        registered_certs = set(trusted_certs_fp)

        client_certs = received.get("client_certificates", [])
        if isinstance(client_certs, str):
            client_certs = json.loads(client_certs)
        client_certificates = set(client_certs)

        # Un-register removed certificates
        removed_certs = registered_certs - client_certificates
        for cert in removed_certs:
            self._unregister_cert(cert)

        # Register new certs
        nodes = json.loads(local_data.get("nodes", "[]"))
        current_node = next(node for node in nodes if node["endpoint"] == self.state.endpoint)

        trusted_fps = set(
            json.loads(current_node["trusted_certs_fp"])
            if isinstance(current_node["trusted_certs_fp"], str)
            else current_node["trusted_certs_fp"]
        )
        new_certs = client_certificates - registered_certs
        for cert in new_certs:
            self._register_cert(cert)
            fp = self._cert_fingerprint(cert)
            trusted_fps.add(fp)

        current_node["trusted_certs_fp"] = list(trusted_fps)
        local_data["nodes"] = json.dumps([current_node])
        self._clean_certs_from_filesystem()
