from __future__ import annotations

from pathlib import Path

from tcfactory.util import sha256_file
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def test_repository_context_index_is_digest_bound_budgeted_and_role_valid() -> None:
    index = load_yaml(ROOT / "docs/CONTEXT_INDEX.yaml")
    roles = set(load_yaml(ROOT / "config/roles.yaml"))
    groups = index["groups"]
    required_groups = {
        "product_normative",
        "technical_architecture",
        "trust_core",
        "commercial",
        "roadmap",
        "current_facts",
        "factory_control",
        "commercial_wedge",
        "native_baseline",
        "pre_collective_pack",
        "market_evidence",
        "factory_controller",
    }
    assert required_groups <= set(groups)

    for group_name, group in groups.items():
        assert set(group.get("includeRoles", [])) <= roles
        assert set(group.get("excludeRoles", [])) <= roles
        entries = group.get("entries", [])
        if group_name.startswith("advisory_"):
            assert entries == []
            continue
        assert 0 < len(entries) <= group["maxSources"]
        characters = 0
        for entry in entries:
            source = ROOT / entry["path"]
            assert source.is_file()
            assert sha256_file(source) == entry["sha256"]
            assert entry["authorityClass"]
            assert entry["authoritySections"]
            assert all(section.startswith("§") for section in entry["authoritySections"])
            characters += len(source.read_text(encoding="utf-8"))
        assert characters <= group["maxCharacters"]

    assert "research" in groups["commercial"]["includeRoles"]
    assert "research" in groups["current_facts"]["includeRoles"]
    assert "research" in groups["market_evidence"]["includeRoles"]
    assert "builder" in groups["market_evidence"]["excludeRoles"]
    assert "factory_repair" in groups["factory_controller"]["includeRoles"]
    assert "research" in groups["factory_controller"]["excludeRoles"]
