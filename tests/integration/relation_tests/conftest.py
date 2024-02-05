from pathlib import Path

import yaml

APPLICATION_APP_NAME = "lxd-tester"
TEST_APP_CHARM_PATH = "tests/integration/relation_tests/application-charm"
CHARM_NAME = yaml.safe_load(Path("metadata.yaml").read_text())["name"]
APP_NAMES = [APPLICATION_APP_NAME, CHARM_NAME]
