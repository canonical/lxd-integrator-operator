#!/usr/bin/env python3
#
# (c) 2020 Canonical Ltd. All rights reserved
#

"""Charmed machine operator for integration with LXD."""

import json
import logging
import subprocess

from interface import Lxd
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus

logger = logging.getLogger(__name__)


class LxdIntegratorCharm(CharmBase):
    """Charmed Operator to connect to an LXD cloud using juju credentials."""

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        self.client = Lxd(self, "api")

    def _on_install(self, event):
        if not self._check_credentials():
            return

    def _on_config_changed(self, event):
        if not self._check_credentials():
            return

    def _check_credentials(self):
        if self.client.is_ready:
            return

        try:
            result = subprocess.run(
                ["credential-get", "--format=json"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            creds = json.loads(result.stdout.decode("utf8"))
            endpoint = creds["endpoint"]
            client_cert = creds["credential"]["attrs"]["client-cert"]
            client_key = creds["credential"]["attrs"]["client-key"]
            server_cert = creds["credential"]["attrs"]["server-cert"]
            if endpoint and client_cert and client_key and server_cert:
                self.client.set_credentials(endpoint, client_cert, client_key, server_cert)
                self.model.unit.status = ActiveStatus()
                return True
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse JSON from credentials-get: {}".format(e.msg))
        except FileNotFoundError:
            pass
        except subprocess.CalledProcessError as e:
            if "permission denied" not in e.stderr.decode("utf8"):
                raise

        endpoint = self.model.config["lxd_endpoint"]
        client_cert = self.model.config["lxd_client_cert"]
        client_key = self.model.config["lxd_client_key"]
        server_cert = self.model.config["lxd_server_cert"]
        if endpoint and client_cert and client_key and server_cert:
            self.client.set_credentials(endpoint, client_cert, client_key, server_cert)
            self.model.unit.status = ActiveStatus()
            return True

        self.model.unit.status = BlockedStatus(
            "Missing credentials access; grant with: juju trust"
        )
        return False


if __name__ == "__main__":
    main(LxdIntegratorCharm)
