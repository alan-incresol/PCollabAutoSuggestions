from __future__ import annotations

from dataclasses import dataclass

from config import Settings


@dataclass(frozen=True)
class EntitySpec:
    id: str
    label: str
    collection: str
    lucene_index: str
    vector_index: str
    requires_org_opu_id: bool
    vector_paths: tuple[str, ...]
    lexical_paths: tuple[tuple[str, bool], ...]
    label_path: str
    detail_paths: tuple[tuple[str, str], ...]
    projection: dict[str, int]


def entity_spec(entity_type: str, settings: Settings) -> EntitySpec:
    if entity_type == "vendor":
        return EntitySpec(
            id="vendor",
            label="Vendor",
            collection=settings.vendor_collection,
            lucene_index=settings.vendor_lucene_index,
            vector_index=settings.vendor_vector_index,
            requires_org_opu_id=False,
            vector_paths=("vendorDetails.basicDetails.companyName",),
            lexical_paths=(
                ("vendorDetails.basicDetails.companyName", True),
                ("vendorCode", False),
                ("erpVendorCode", False),
            ),
            label_path="vendorDetails.basicDetails.companyName",
            detail_paths=(
                ("Vendor code", "vendorCode"),
                ("ERP code", "erpVendorCode"),
                ("GSTIN", "vendorDetails.companyOverviewDetails.gstin"),
            ),
            projection={
                "vendorCode": 1,
                "erpVendorCode": 1,
                "orgId": 1,
                "orgOpuId": 1,
                "vendorDetails.basicDetails.companyName": 1,
                "vendorDetails.companyOverviewDetails.gstin": 1,
            },
        )
    if entity_type == "material":
        return EntitySpec(
            id="material",
            label="Material",
            collection=settings.material_collection,
            lucene_index=settings.material_lucene_index,
            vector_index=settings.material_vector_index,
            requires_org_opu_id=True,
            vector_paths=("materialData.materialDetails.discription",),
            lexical_paths=(
                ("materialData.materialDetails.discription", True),
                ("material", False),
            ),
            label_path="materialData.materialDetails.discription",
            detail_paths=(
                ("Material", "material"),
                ("HSN", "materialData.materialDetails.hsn"),
            ),
            projection={
                "material": 1,
                "orgId": 1,
                "orgOpuId": 1,
                "materialData.materialDetails.discription": 1,
                "materialData.materialDetails.hsn": 1,
            },
        )
    raise ValueError(f"Unknown entityType: {entity_type!r}")
