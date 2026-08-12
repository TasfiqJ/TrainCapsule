from __future__ import annotations

from scripts.gates.generate_sbom import build_sbom


def test_sbom_is_deterministic_cyclonedx_and_contains_installed_project() -> None:
    first = build_sbom()
    assert first == build_sbom()
    assert first["bomFormat"] == "CycloneDX"
    assert first["specVersion"] == "1.5"
    components = first["components"]
    assert isinstance(components, list) and components
    assert all(str(component["purl"]).startswith("pkg:pypi/") for component in components)
    names = {str(component["name"]).lower() for component in components}
    assert "traincapsule-ai-factory" in names
