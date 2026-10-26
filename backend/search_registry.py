"""
Map MongoDB collection name → Atlas Search index name + autocomplete field paths.

Atlas index names should match how indexes are defined in Atlas (often same as JSON
stems under search-indexes/). Adjust collection keys if your DB uses different names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# PurRequisitions / pr.json
FIELD_PATHS_PR: dict[str, str] = {
    "prNum": "prNum",
    "poNum": "poData.poNum",
    "rfqId": "poData.rfqId",
    "materialCode": "requisitionDetails.itemDetails.materialCode",
    "materialDesc": "requisitionDetails.itemDetails.materialDesc",
    "prType": "requisitionDetails.prDetails.prType",
    "requisitionType": "requisitionDetails.prDetails.requisitionType",
}

# PurchaseOrders (or equivalent) / po.json
FIELD_PATHS_PO: dict[str, str] = {
    "poNum": "poNum",
    "prNum": "prNum",
    "rfqId": "rfqId",
    "vendorCode": "vendorCode",
    "status": "status",
    "matrNo": "orderDetails.itemDetails.matrNo",
    "matrDesc": "orderDetails.itemDetails.matrDesc",
    "deliveryPlantName": "orderDetails.poDetails.deliveryPlantName",
}

# RFQ / rfq_data.json
FIELD_PATHS_RFQ: dict[str, str] = {
    "rfqId": "rfqId",
    "materialCode": "rfqData.materialDetails.materialCode",
    "materialDesc": "rfqData.materialDetails.materialDesc",
    "prNum": "rfqData.materialDetails.prNum",
    "email": "rfqData.rfqDetails.email",
    "responsible": "rfqData.rfqDetails.responsible",
    "rfqDesc": "rfqData.rfqDetails.rfqDesc",
    "rfqName": "rfqData.rfqDetails.rfqName",
    "selectVendorCompanyName": "rfqData.selectVendors.companyName",
    "selectVendorCode": "rfqData.selectVendors.vendorCode",
    "submittedVendorCode": "submittedVendors.vendorCode",
    "submittedVendorName": "submittedVendors.vendorName",
}

# Material master / material_master.json
FIELD_PATHS_MATERIAL_MASTER: dict[str, str] = {
    "material": "material",
    "discription": "materialData.materialDetails.discription",
    "hsn": "materialData.materialDetails.hsn",
    "matGroup": "materialData.materialDetails.matGroup",
    "matType": "materialData.materialDetails.matType",
    "plantCode": "materialData.plants.plantCode",
    "plantDesc": "materialData.plants.plantDesc",
    # Common alias — root `material` is the code-like field in this index
    "materialCode": "material",
}

# Vendor master / vendor_master.json
FIELD_PATHS_VENDOR_MASTER: dict[str, str] = {
    "erpVendorCode": "erpVendorCode",
    "vendorCode": "vendorCode",
    "companyName": "vendorDetails.basicDetails.companyName",
    "contactEmail": "vendorDetails.basicDetails.contactEmail",
    "pointOfContactName": "vendorDetails.basicDetails.pointOfContactName",
    "gstin": "vendorDetails.companyOverviewDetails.gstin",
    "city": "vendorDetails.vendorAddressDetails.city",
}

# Invoices / invoices.json — materialCode aliases to matrNo for cross-collection payloads
FIELD_PATHS_INVOICES: dict[str, str] = {
    "invNum": "invNum",
    "vendorCode": "vendorCode",
    "poNums": "poNums",
    "matrNo": "invoiceDetails.itemDetails.matrNo",
    "matrDesc": "invoiceDetails.itemDetails.matrDesc",
    "hsnSc": "invoiceDetails.itemDetails.hsnSc",
    "invoicePoNum": "invoiceDetails.itemDetails.poNum",
    "customer": "invoiceDetails.basicDetails.customer",
    "materialCode": "invoiceDetails.itemDetails.matrNo",
    "materialDesc": "invoiceDetails.itemDetails.matrDesc",
}


@dataclass(frozen=True)
class CollectionConfig:
    index_name: str
    field_paths: dict[str, str]
    requires_org_opu_id: bool = True


# collection_name -> search config
_INVOICES_CFG = CollectionConfig("invoices", FIELD_PATHS_INVOICES)

COLLECTION_REGISTRY: dict[str, CollectionConfig] = {
    "PurRequisitions": CollectionConfig("pr", FIELD_PATHS_PR),
    "OmOrgPurOrders": CollectionConfig("po", FIELD_PATHS_PO),
    "PurchaseOrders": CollectionConfig("po", FIELD_PATHS_PO),
    "RfqData": CollectionConfig("rfq_data", FIELD_PATHS_RFQ),
    "MaterialMaster": CollectionConfig("material-master", FIELD_PATHS_MATERIAL_MASTER),
    "OmOrgVendorDetails": CollectionConfig(
        "vendor-master", FIELD_PATHS_VENDOR_MASTER, requires_org_opu_id=False
    ),
    "OmOrgPurInvoices": _INVOICES_CFG,
    "Invoices": _INVOICES_CFG,
}

_ACRONYM_REPLACEMENTS = {
    "Pr": "PR",
    "Po": "PO",
    "Rfq": "RFQ",
    "Erp": "ERP",
    "Hsn": "HSN",
    "Gstin": "GSTIN",
    "Opu": "OPU",
    "Inv": "INV",
}

_FIELD_LABEL_OVERRIDES = {
    "discription": "Description",
    "matrNo": "Material Number",
    "matrDesc": "Material Description",
}


def field_label(field_id: str) -> str:
    if field_id in _FIELD_LABEL_OVERRIDES:
        return _FIELD_LABEL_OVERRIDES[field_id]
    words = re.sub(r"([A-Z])", r" \1", field_id).strip().split()
    titled = " ".join(word.capitalize() for word in words)
    for old, new in _ACRONYM_REPLACEMENTS.items():
        titled = titled.replace(old, new)
    return titled


def resolve_collection_name(name: str) -> str:
    stripped = name.strip()
    if stripped in COLLECTION_REGISTRY:
        return stripped
    canonical = {key.lower(): key for key in COLLECTION_REGISTRY}.get(stripped.lower())
    if canonical:
        return canonical
    raise ValueError(
        f"Unknown collectionName: {stripped!r}. "
        f"Known collections: {list_known_collections()}"
    )


def get_collection_config(collection_name: str) -> dict[str, object]:
    coll = resolve_collection_name(collection_name)
    config = COLLECTION_REGISTRY[coll]
    fields = [
        {"id": field_id, "label": field_label(field_id), "path": path}
        for field_id, path in sorted(config.field_paths.items())
    ]
    return {
        "collectionName": coll,
        "searchIndexName": config.index_name,
        "requiresOrgOpuId": config.requires_org_opu_id,
        "fields": fields,
    }


def list_known_collections() -> list[str]:
    return sorted(COLLECTION_REGISTRY.keys())
