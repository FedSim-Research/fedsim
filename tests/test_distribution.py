from importlib.metadata import distribution


def test_installed_package_retains_declared_license_documents():
    package = distribution("fedsim-research")
    declared = package.metadata.get_all("License-File") or []
    assert "LICENSE" in declared
    assert "THIRD_PARTY_NOTICES.md" in declared
    files = package.files or []
    license_file = next(path for path in files if str(path).endswith("/licenses/LICENSE"))
    notices_file = next(
        path for path in files if str(path).endswith("/licenses/THIRD_PARTY_NOTICES.md")
    )
    assert "Apache License" in license_file.read_text(encoding="utf-8")
    assert "Flower Labs GmbH" in notices_file.read_text(encoding="utf-8")
