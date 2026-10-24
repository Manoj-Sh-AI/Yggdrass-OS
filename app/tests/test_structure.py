"""Smoke test: the package imports and the three layers exist."""

import importlib

import pytest


def test_package_imports():
    import yggdrass

    assert yggdrass.__version__


@pytest.mark.parametrize("layer", ["interface", "processing", "data"])
def test_layer_exists(layer):
    assert importlib.import_module(f"yggdrass.{layer}")
