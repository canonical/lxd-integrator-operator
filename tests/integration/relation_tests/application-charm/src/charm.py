#!/usr/bin/env python3

import json
import logging
import tempfile

import ops
from charms.tls_certificates_interface.v3.tls_certificates import (
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_private_key,
)
from ops.framework import StoredState
from ops.model import WaitingStatus
from pylxd import Client

logger = logging.getLogger(__name__)


class ApplicationCharm(ops.CharmBase):
    """Application charm that connects to database charms."""

    _state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        self._state.set_default(cert=None, key=None, lxd_nodes=[])
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.client_relation_joined, self._on_client_relation_joined)
        self.framework.observe(self.on.client_relation_changed, self._on_client_relation_changed)

    @property
    def public_ip(self) -> str:
        """Public address of the unit."""
        return self.model.get_binding("juju-info").network.ingress_address.exploded

    @property
    def private_ip(self) -> str:
        """Private address of the unit."""
        return self.model.get_binding("juju-info").network.bind_address.exploded

    def _on_start(self, _):
        self.unit.status = ops.ActiveStatus()

    def _on_client_relation_joined(self, event):
        self._state.cert, self._state.key = self._generate_selfsigned_cert(
            self.public_ip, self.public_ip, self.private_ip
        )
        relation_data = event.relation.data[self.unit]
        relation_data["client_certificates"] = json.dumps([self._state.cert.decode("utf-8")])

    def _on_client_relation_changed(self, event):
        data = event.relation.data[event.unit]
        self._state.lxd_nodes = json.loads(data.get("nodes", "[]"))
        if not self._state.lxd_nodes:
            event.defer()
            self.unit.status = WaitingStatus("Waiting for node info")
            return
        with tempfile.NamedTemporaryFile(delete=False) as cert, tempfile.NamedTemporaryFile(
            delete=False
        ) as key:
            cert.write(self._state.cert)
            cert.close()
            key.write(self._state.key)
            key.close()
            self.framework.breakpoint("tester")
            for node in self._state.lxd_nodes:
                trusted_clients_fp = node.get("trusted_certs_fp", [])
                if not trusted_clients_fp:
                    event.defer()
                    logging.info("client not authenticated yet")
                    return
                client = Client(
                    endpoint=node["endpoint"], verify=False, cert=(cert.name, key.name)
                )
                assert client.trusted, f"Client not trusted {client}"
                logger.info(f"Successfully connected to {node['endpoint']}")
        self.unit.status = ops.ActiveStatus()

    def _generate_selfsigned_cert(self, hostname, public_ip, private_ip) -> tuple[bytes, bytes]:
        if not hostname:
            raise Exception("A hostname is required")

        if not public_ip:
            raise Exception("A public IP is required")

        if not private_ip:
            raise Exception("A private IP is required")

        ca_key = generate_private_key(key_size=4096)
        ca_cert = generate_ca(ca_key, hostname)

        key = generate_private_key(key_size=4096)
        csr = generate_csr(
            private_key=key,
            subject=hostname,
            sans_dns=[public_ip, private_ip, hostname],
            sans_ip=[public_ip, private_ip],
        )
        cert = generate_certificate(csr=csr, ca=ca_cert, ca_key=ca_key)
        return cert, key


if __name__ == "__main__":
    ops.main(ApplicationCharm)
