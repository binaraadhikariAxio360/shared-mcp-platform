# PractiCare Complete System Architecture & End-to-End Audit Report

**Date:** October 14, 2026  
**Auditor:** Principal Software Architect, Security & QA Automation Engineer  
**Target:** `apps/practicare/` (FastAPI / PostgreSQL / Next.js / Gemini LangGraph)  
**Repository Root:** `D:\Axio360\shared-mcp-moc`

---

## Executive Summary

A comprehensive architectural and functional audit of the PractiCare clinical management platform was conducted across all domains:
- Identity, Authentication, and Multi-Tenant RBAC
- Company Registration, Tenant Isolation, and Practice Provisioning
- Staff Invitations, Approval Lifecycle, and Shift Self-Service
- Manual Frontend CRUD Operations to PostgreSQL Database Persistence
- Dashboard Metrics and Zero-Data Baseline Protection
- LangGraph Autonomous Clinical AI Agent (Gemini 3.1 Flash-Lite + Deterministic Mode)
- Tool Gateway Security, Authorization, and Human-in-the-Loop (HITL) Approvals

All 7 core domains were verified through automated end-to-end testing, direct PostgreSQL query inspection, and live Gemini tool-calling invocations.

---

## 1. Domain-by-Domain Traceability & Architecture Audit

| Subsystem | Frontend Component | API Endpoint | Service / Handler | Database Table & Isolation | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **Authentication & Session** | `src/app/page.tsx` (Login Modal) | `POST /api/v1/auth/login` | `main.py::auth_login` | `practicare_users` (`tenant_id`, `email` unique) | **VERIFIED** |
| **Company Registration** | `src/app/page.tsx` (Register Company) | `POST /api/v1/auth/register-company` | `main.py::auth_register_company` | `practices`, `practicare_users`, `staff` | **VERIFIED** |
| **Staff Invitations** | `src/app/page.tsx` (Company Settings) | `POST /api/v1/company/invitations` | `main.py::create_staff_invitation` | `staff_invitations` (`tenant_id`, `code` unique) | **VERIFIED** |
| **Staff Join & Validation** | `src/app/page.tsx` (Invitation Join) | `POST /api/v1/auth/join` | `main.py::auth_join_company` | `practicare_users` (`PENDING` membership) | **VERIFIED** |
| **Membership Approval** | `src/app/page.tsx` (Pending Approvals) | `POST /api/v1/company/pending-members/{id}/action` | `main.py::action_pending_member` | `practicare_users.membership_status`, `staff` | **VERIFIED** |
| **Staff & Shift Management** | `src/app/page.tsx` (Staff Tab) | `POST /api/v1/staff/me/shift`, `PUT /api/v1/staff/{id}/shift` | `main.py::set_my_shift`, `set_staff_shift` | `staff` (`on_shift` vs `is_active`) | **VERIFIED** |
| **Clinical Tasks** | `src/app/page.tsx` (Tasks Tab) | `GET, POST, PUT, DELETE /api/v1/tasks` | `main.py` task endpoints | `tasks` (`tenant_id`, `practice_id`, `room_id`, `assigned_staff_id`) | **VERIFIED** |
| **Checklists** | `src/app/page.tsx` (Checklists Tab) | `GET, POST, PUT, DELETE /api/v1/checklists` | `main.py` checklist endpoints | `checklists` (`tenant_id`, `assigned_staff_id`) | **VERIFIED** |
| **Inventory & Supplies** | `src/app/page.tsx` (Inventory Tab) | `GET, POST, PUT, DELETE /api/v1/inventory` | `main.py` inventory endpoints | `inventory_items` (`tenant_id`, `min_threshold`) | **VERIFIED** |
| **Exam Rooms** | `src/app/page.tsx` (Rooms Tab) | `GET, POST, PUT, DELETE /api/v1/rooms` | `main.py` room endpoints | `rooms` (`tenant_id`, `room_number`, `status`) | **VERIFIED** |
| **Dashboard Analytics** | `src/app/page.tsx` (Dashboard Grid) | `GET /api/v1/dashboard/summary` | `main.py::get_dashboard_summary` | Aggregate SQL queries strictly scoped to `tenant_id` | **VERIFIED** |
| **AI Agent Chat** | `src/app/page.tsx` (AI Assistant) | `POST /api/v1/ai/chat` | `main.py::ai_chat_endpoint` -> `agent.py::run` | `ai_conversations`, `ai_messages` | **VERIFIED** |
| **AI Conversations** | `src/app/page.tsx` (Chat Drawer) | `GET, POST, PUT, DELETE /api/v1/ai/conversations` | `main.py` conversation routes | `ai_conversations` (`tenant_id`, `user_id` composite index) | **VERIFIED** |

---

## 2. Security & Multi-Tenancy Architecture

### 2.1 Cryptographic Identity & Session Validation
- All protected endpoints depend on `get_request_context` (`main.py:64-148`).
- When a `Bearer <token>` is provided, the token is cryptographically verified using HMAC-SHA256 (`security.py`).
- The user account is queried from `practicare_users` by `sub` (user ID) and compared against `tenant_id` in the token claims.
- **Header Spoofing Resistance:** Verified server-side identity completely overrides any client-supplied `x-tenant-id`, `x-user-role`, or `x-user-id` headers.

### 2.2 Account & Membership Gating
- `is_active == False`: Rejected with `HTTP 403 Forbidden` ("Account is inactive. Access disabled.").
- `membership_status == 'PENDING'`: Rejected with `HTTP 403 Forbidden` ("Account membership is pending Owner approval.").
- `membership_status == 'REJECTED'`: Rejected with `HTTP 403 Forbidden` ("Account membership request was rejected by clinic Owner.").

### 2.3 RBAC Permission Matrix
- **CLINIC_OWNER**: Unrestricted administrative access across tasks, rooms, checklists, staff profiles, account status overrides, and destructive actions.
- **ATTENDING_PHYSICIAN**: Clinical operations, task creation, room management, checklist completion, own shift self-service. Cannot delete checklists or deactivate accounts.
- **NURSE_STAFF**: Floor operations, checklist completion, task status updates, own shift self-service. Read-only access to staff directory. Cannot create tasks or delete checklists.
- **INVENTORY_MANAGER**: Stock intake, supply threshold management, room inventory inspections. Cannot create tasks or delete checklists.
- **CLINICAL_AUDITOR**: Compliance reporting. Receives anonymized aggregate data with zero employee PII. Forbidden from viewing individual rooms or modifying clinical state.

---

## 3. Data Integrity & Hardcoding Audit

An in-depth code scan was performed on `apps/practicare/frontend/src/app/page.tsx` to detect hardcoded constants, mock fallbacks, or faked API responses.

### Findings:
1. **No Fake Task or Room Data in Production State:** All state variables (`tasks`, `checklists`, `inventory`, `rooms`, `staff`, `summary`) are populated directly by asynchronous `fetch()` requests against `/api/v1/...`.
2. **Empty State Banners:** When a new practice is registered, the frontend checks:
   `summary && summary.total_rooms === 0 && summary.tasks_total === 0 && summary.low_stock_count === 0`
   and displays the dedicated Empty Practice Onboarding Banner, ensuring zero demo data leaks into newly created tenants.
3. **Demo Personas are Client-Side Quick-Select Only:** `DEMO_PROFILES` are explicitly labelled for 1-click persona switching during evaluation, and authenticate via `/api/v1/auth/login` rather than bypassing backend verification.
