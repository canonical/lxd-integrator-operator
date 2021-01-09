# LXD Integrator

Integrators are special charms that interact with the hosting cloud provider by
using credentials provided by juju via the `juju trust` command.

The LXD Integrator enables charms in the relation to communicate with the host LXD
controller.

## Deployment

```shell script
$ juju deploy lxd-integrator
$ juju trust lxd-integrator
``` 

Then relate the integrator with charms that support the `lxd` relation:
```shell script
$ juju relate lxd-integrator:api my-charm:lxd
```

## Relation
The relation should work no matter the source for LXD, whether it's using the
integrator or not.
Below are details about the information sent on the relation. Any charm implementing
this relation should expect

### Provider side
The provider side of the interface writes information about the available LXD nodes on the relation, and
registers client certificates that it received on the relation to LXD.

### Require side
The require side of the interface sends client certificates to add to LXD and gets information about
available LXD nodes on the relation.

## API
Below is the API that should be used by charms using the LXD interface.
Each section details the information each role should **publish**.
The opposite role would then of course have to read data on the relation coming
from the other side and work with it.

#### Provider
```yaml
'version': '1.0',
'nodes': [
  {
    'endpoint': "https://10.10.10.10:8443",
    'name': 'node-1',
    'trusted_certs_fp': []
  }
]
```
`version` defines the protocol version. Major update brings breaking changes.
`nodes` is a list of active LXD node endpoints. Each node's endpoint should be complete with its
protocol, host and port.
`trusted_certs_fp` is a list of certificate fingerprints that have been added to the LXD trust store

#### Requirer
```yaml
"client_certificates": [
  "-----BEGIN CERTIFICATE-----\nMII...T2zt\n-----END CERTIFICATE-----",
  "-----BEGIN CERTIFICATE-----\nMII...nK0g\n-----END CERTIFICATE-----"
]
```

`client_certificates` is a list of client certificates to register to LXD. When a certificate
has been processed by the `provides` side, it should be available in the
`registered_certificates` list on the relation.