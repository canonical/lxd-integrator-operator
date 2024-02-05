import asyncio

import pytest
from conftest import APP_NAMES, APPLICATION_APP_NAME, CHARM_NAME, TEST_APP_CHARM_PATH
from pytest_operator.plugin import OpsTest


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_relation_lxd(ops_test: OpsTest):
    charms = await ops_test.build_charms(".", TEST_APP_CHARM_PATH)
    async with ops_test.fast_forward():
        await asyncio.gather(
            ops_test.model.deploy(
                charms[APPLICATION_APP_NAME],
                application_name=APPLICATION_APP_NAME,
                num_units=1,
            ),
            ops_test.model.deploy(
                charms[CHARM_NAME],
                application_name=CHARM_NAME,
                num_units=1,
                trust=True,
            ),
        )
        await ops_test.model.relate(f"{APPLICATION_APP_NAME}:client", f"{CHARM_NAME}:api")
        await ops_test.model.wait_for_idle(apps=APP_NAMES, status="active", timeout=5000)
