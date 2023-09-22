import pytest
from OpenSSL import crypto

@pytest.fixture
def tls_config() -> tuple[bytes, bytes]:
    # create a key pair
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 1024)

    # create a self-signed cert
    cert = crypto.X509()
    cert.get_subject().O = "Canonical"
    cert.get_subject().OU = "Anbox Cloud"
    cert.get_subject().CN = "anbox-cloud.io"
    cert.set_serial_number(1000)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(key)
    cert.sign(key, "sha1")
    return crypto.dump_privatekey(crypto.FILETYPE_PEM, key), crypto.dump_certificate(
        crypto.FILETYPE_PEM, cert
    )

@pytest.fixture
def lxd_secret(tls_config):
    return {
        "type": "lxd",
        "name": "juju",
        "region": "default",
        "endpoint": "https://1.2.3.4:8443",
        "identityendpoint": "",
        "storageendpoint": "",
        "credential": {
            "authtype": "certificate",
            "attrs": {
                "client-cert": tls_config[1].decode("utf-8"),
                "client-key":  tls_config[0].decode("utf-8"),
                "server-cert": "-----BEGIN CERTIFICATE-----\nMIIB/jCCAYSgAwIBAgIRAOK8FTN83SBIlyz1hVjLAukwCgYIKoZIzj0EAwMwMjEc\nMBoGA1UEChMTbGludXhjb250YWluZXJzLm9yZzESMBAGA1UEAwwJcm9vdEBqdWp1\nMB4XDTIzMDkxNDA5NTQxNVoXDTMzMDkxMTA5NTQxNVowMjEcMBoGA1UEChMTbGlu\ndXhjb250YWluZXJzLm9yZzESMBAGA1UEAwwJcm9vdEBqdWp1MHYwEAYHKoZIzj0C\nAQYFK4EEACIDYgAEciWQqXqACauT4rPZNpwsW1fX7S9wItrUO6oiC3M/byQ1/Aoa\nLeNKGm78e4lqmHNl1gaugheP+6xMH/4GvqOPSqOBMKMpZqOYQaTcb7Yo/lQkWJYS\nJkSF5ZmN7SFrN/Kco14wXDAOBgNVHQ8BAf8EBAMCBaAwEwYDVR0lBAwwCgYIKwYB\nBQUHAwEwDAYDVR0TAQH/BAIwADAnBgNVHREEIDAeggRqdWp1hwR/AAABhxAAAAAA\nAAAAAAAAAAAAAAABMAoGCCqGSM49BAMDA2gAMGUCMQCMeyH1wxJg3xK8drrC8/q5\nJChelKfH5JNydgXhrsjkqYPZg49JDTF354My+JqaCIkCMHs6CXNBE1oP4gt9QxzF\nrOwhteFjSKVcKXMHYFC7SoBjIHFFIMD4i4juNw0W0TzqeA==\n-----END CERTIFICATE-----\n",
            },
            "redacted": [],
        },
        "cacertificates": [],
        "skiptlsverify": False,
        "iscontrollercloud": True,
    }
