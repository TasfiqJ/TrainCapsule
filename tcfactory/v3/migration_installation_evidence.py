"""Deterministic V3-MIG-003 source-installation evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model


class AuthorityTreeBinding(V3Model):
    root: str = Field(min_length=1)
    file_count: int = Field(ge=1)
    tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    installation_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    tree_at_installation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PreservedAuthorityProof(V3Model):
    comparison_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    tree_at_comparison_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    no_post_install_mutation: Literal[True]

    @model_validator(mode="after")
    def require_equal_trees(self) -> PreservedAuthorityProof:
        if self.tree_at_comparison_sha256 != self.current_tree_sha256:
            raise ValueError("preserved authority tree changed after installation")
        return self


class CoverageBinding(V3Model):
    path: Literal[
        "docs/source-of-truth/v3.1-zh-2026-08-12/"
        "SECTION_COVERAGE_V3_TO_V3_1_ZH.json"
    ]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_heading_count: Literal[504]
    mapped_heading_count: Literal[504]
    complete: Literal[True]


class MigrationInstallationEvidence(V3Model):
    schema_version: Literal[1] = 1
    work_item_id: Literal["V3-MIG-003"] = "V3-MIG-003"
    evidence_type: Literal["DETERMINISTIC_SOURCE_INSTALLATION"] = (
        "DETERMINISTIC_SOURCE_INSTALLATION"
    )
    migration_base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    old_authority: AuthorityTreeBinding
    new_authority: AuthorityTreeBinding
    preserved_old_authority: PreservedAuthorityProof
    old_manifest_path: Literal[
        "docs/source-of-truth/v3-2026-08-11/FINAL_MANIFEST_V3.json"
    ]
    old_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    new_manifest_path: Literal[
        "docs/source-of-truth/v3.1-zh-2026-08-12/FINAL_MANIFEST_V3_1_ZH.json"
    ]
    new_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    coverage: CoverageBinding

    @model_validator(mode="after")
    def bind_installation_boundary(self) -> MigrationInstallationEvidence:
        if self.preserved_old_authority.comparison_commit != (
            self.new_authority.installation_commit
        ):
            raise ValueError("old-tree proof is not bound to the new installation commit")
        return self
