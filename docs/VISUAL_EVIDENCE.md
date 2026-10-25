# Visual Evidence Audit (PNG and PDF Files)

This document provides a comprehensive audit of all 15 non-text evidence files in `dataset/evidence/` (11 PNG images and 4 PDF documents), their source origins, capture timestamps, depicted systems/resources, text-file coverage, and flags for resources that are only observable via visual media.

---

## 1. Visual Evidence Manifest and Coverage Matrix

| File ID | File Path | Format | Source Origin | Captured At | System ID | Primary Resource Linked | Covered by Text File? | Only Observable via Visual/PDF? |
|---|---|---|---|---|---|---|---|---|
| `evidence_04` | `evidence/images/account_admin_console_20260926.png` | PNG | `account_admin_portal` | 2026-09-26T11:00:00Z | `account_service` | `account_5762` | **Yes** (`evidence_01`) | No (Mirrored in observability log) |
| `evidence_09` | `evidence/images/search_index_inspector_20260901.png` | PNG | `search_index_admin` | 2026-09-01T06:00:00Z | `search_service` | `search_428` | **Yes** (`evidence_01`) | No (Mirrored in observability log) |
| `evidence_14` | `evidence/images/connector_management_console_20260807.png` | PNG | `integration_admin` | 2026-08-07T08:00:00Z | `integration_service` | `data_flow_1121` | **Yes** (`evidence_01`) | No (Mirrored in observability log) |
| `evidence_18` | `evidence/documents/account_history_report_20260718.pdf` | PDF | `account_history_service` | 2026-07-18T11:00:00Z | `export_service` | `export_1842` / Statement `NST-2026-0718-1842` | **No** | **YES (Observable via PDF stream)** |
| `evidence_19` | `evidence/images/analytics_profile_view_20260713.png` | PNG | `analytics_platform` | 2026-07-13T10:00:00Z | `analytics_platform` | `analytics_7438` | **Yes** (`evidence_01`) | No (Mirrored in observability log) |
| `evidence_23` | `evidence/images/customer_export_console_20260618.png` | PNG | `export_service` | 2026-06-18T12:00:00Z | `export_service` | `export_1260` | **Yes** (`evidence_01`) | No (Mirrored in observability log) |
| `evidence_27` | `evidence/documents/legal_retention_register_20260529.pdf` | PDF | `legal_retention_service` | 2026-05-29T08:00:00Z | `legal_service` | Disputed orders (`ORD-20264118` to `ORD-20264600`) | **No** | **YES (Observable via PDF stream)** |
| `evidence_28` | `evidence/images/support_ticket_console_20260524.png` | PNG | `support_platform` | 2026-05-24T07:00:00Z | `support_platform` | `support_1034` | **Yes** (`evidence_02`) | No (Mirrored in observability log) |
| `evidence_32` | `evidence/images/backup_restore_console_20260429.png` | PNG | `backup_service` | 2026-04-29T09:00:00Z | `backup_service` | `backup_9287` | **Yes** (`evidence_01`) | No (Mirrored in observability log) |
| `evidence_37` | `evidence/images/security_audit_explorer_20260905.png` | PNG | `security_service` | 2026-09-05T07:00:00Z | `security_service` | `audit_record_003` | **No** | **YES (Observable via Image & PDF `evidence_55`)** |
| `evidence_42` | `evidence/images/deleted_account_reference_20260310.png` | PNG | `identity_service` | 2026-03-10T06:00:00Z | `identity_service` | `tombstone_17` | **No** | **YES (Observable via Image only)** |
| `evidence_46` | `evidence/images/object_storage_browser_20260213.png` | PNG | `object_storage` | 2026-02-13T08:00:00Z | `object_storage` | `object_19` (`delivery_confirmation_19.pdf`) | **No** | **YES (Observable via Image only)** |
| `evidence_55` | `evidence/documents/security_retention_extract.pdf` | PDF | `security_service` | 2026-09-05T06:30:00Z | `security_service` | `audit_record_003` | **No** | **YES (Observable via PDF stream)** |
| `evidence_58` | `evidence/documents/delivery_correction_attachment.pdf` | PDF | `support_platform` | 2026-09-12T07:30:00Z | `support_platform` | `support_001` (ticket `CS-4827`) | **No** | **YES (Observable via PDF stream; cited in case_07)** |
| `evidence_60` | `evidence/images/marketing_profile_console.png` | PNG | `marketing_platform` | 2026-09-16T07:20:00Z | `marketing_platform` | `marketing_001` | **No** | **YES (Observable via Image only)** |

---

## 2. True Image-Only Resources (Zero Text/PDF Presence)

The following resources appear EXCLUSIVELY in PNG screenshot evidence, with zero representation in any `.json`, `.sql`, `.log`, `.txt`, or parsed digital PDF document:

1. **`object_19` (`delivery_confirmation_19.pdf`)**
   - **Exact File**: `evidence_46` (`evidence/images/object_storage_browser_20260213.png`)
   - **System**: `object_storage`
   - **Location**: Storage browser table row listing object name `delivery_confirmation_19.pdf`, resource `object_19`, bucket `customer-attachments`.
   - **Subject**: `user_07` (`priya.raman@gmail.com`)
   - **Grep Verification**: Absent from all text/json/sql/log/txt and parsed-PDF output across `dataset/evidence/`. Referenced only in `system_activity.csv` (`activity_4007`).

2. **`marketing_001`**
   - **Exact File**: `evidence_60` (`evidence/images/marketing_profile_console.png`)
   - **System**: `marketing_platform`
   - **Location**: Marketing audience table row showing profile `marketing_001`, subscriber `kwame-mensah@proton.me`, status `ACTIVE`.
   - **Subject**: `user_09` (`kwame-mensah@proton.me`)
   - **Grep Verification**: Absent from all text/json/sql/log/txt and parsed-PDF output across `dataset/evidence/`. Referenced only in `system_activity.csv` (`activity_4008`).

3. **`tombstone_17`**
   - **Exact File**: `evidence_42` (`evidence/images/deleted_account_reference_20260310.png`)
   - **System**: `identity_service`
   - **Location**: Deleted customer reference table row showing tombstone reference `tombstone_17`, user ID `user_17`, timestamp `2026-03-10`.
   - **Subject**: `user_17` (`leonie.g9352@outlook.com`)
   - **Grep Verification**: Absent from all text/json/sql/log/txt and parsed-PDF output across `dataset/evidence/`. Referenced only in `system_activity.csv` (`activity_4011`).

### Non-Image-Only Resources (Parsed via `pdf_parser`)
- **`audit_record_003`**: Fully decoded from digital PDF stream in `evidence_55` (`evidence/documents/security_retention_extract.pdf`).
- **`support_001`**: Fully decoded from digital PDF stream in `evidence_58` (`evidence/documents/delivery_correction_attachment.pdf`).
- **`export_1842`**: Fully decoded from digital PDF stream in `evidence_18` (`evidence/documents/account_history_report_20260718.pdf`).
- **Disputed Orders Register**: Fully decoded from digital PDF stream in `evidence_27` (`evidence/documents/legal_retention_register_20260529.pdf`).

---

## 3. Grounding and Technical Extraction Path

1. **PDF Documents (Zero External OCR Dependency)**:
   - All 4 PDF files (`evidence_18`, `evidence_27`, `evidence_55`, `evidence_58`) are standard digital vector PDFs whose text contents are compressed using Adobe ASCII85 + FlateDecode (`/Filter [ /ASCII85Decode /FlateDecode ]`).
   - The pure-Python parser `code/evidence/pdf_parser.py` decompresses these streams using standard library `base64.a85decode` and `zlib.decompress`, achieving full string recovery without needing Tesseract, Poppler, PyMuPDF, or external vision models.

2. **Console Screenshots (Image Files)**:
   - 6 of the 11 PNG files (`evidence_04`, `evidence_09`, `evidence_14`, `evidence_19`, `evidence_23`, `evidence_28`, `evidence_32`) depict operational UI screens whose underlying events and resource records are simultaneously captured in central observability logs (`evidence_01`, `evidence_02`).
   - The remaining 4 image-only resources (`object_19`, `marketing_001`, `tombstone_17`, `audit_record_003`) are explicitly grounded by `LINK_RESOURCE_IDENTITY` records in `system_activity.csv` (`activity_4000` through `activity_4011`), linking each visual artifact to its subject user, email, and resource identifier.
