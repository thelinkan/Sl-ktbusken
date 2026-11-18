"""Keep the benchmarks out of the default run; they run with ``-m slow``."""

import pytest


def pytest_collection_modifyitems(config, items):
    if "slow" in (config.option.markexpr or ""):
        return
    skip = pytest.mark.skip(reason="prestandamätning: kör med -m slow")
    for item in items:
        if "benchmarks" in item.nodeid.replace("\\", "/").split("/"):
            item.add_marker(skip)
