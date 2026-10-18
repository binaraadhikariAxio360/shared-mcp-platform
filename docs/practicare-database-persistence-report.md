# PractiCare Database Persistence & Manual CRUD Verification Report

**Date:** October 14, 2026  
**Auditor:** QA Automation & PostgreSQL Database Engineer  
**Database Engine:** PostgreSQL 16 (`moc-postgres-db:5432`, external port `5433`)  
**Database Name:** `practicare_db`

---

## 1. Domain-by-Domain Persistence Verification

Every manual frontend CRUD domain was verified through direct API execution and authoritative PostgreSQL transaction commits:

### 1.1 Tasks Domain
| Operation | HTTP Method & Path | PostgreSQL Table | Commit Verified | Read Back Verified | Tenant Scoped |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **Create Task** | `POST /api/v1/tasks` | `tasks` | Yes | Yes (`SELECT id, title, room_id, assigned_staff_id FROM tasks`) | Yes |
| **List Tasks** | `GET /api/v1/tasks` | `tasks` | N/A (Read) | Yes (`WHERE tenant_id = :tid`) | Yes |
| **Get Task Details** | `GET /api/v1/tasks/{id}` | `tasks` | N/A (Read) | Yes (`WHERE id = :id AND tenant_id = :tid`) | Yes |
| **Update Task (Title/Priority)** | `PUT /api/v1/tasks/{id}` | `tasks` | Yes | Yes (Updated title & priority confirmed) | Yes |
| **Complete Task** | `PUT /api/v1/tasks/{id}` | `tasks` | Yes | Yes (`status = 'Completed'`) | Yes |
| **Delete Task** | `DELETE /api/v1/tasks/{id}` | `tasks` | Yes | Yes (`SELECT count(*) == 0`) | Yes |

### 1.2 Checklists Domain
| Operation | HTTP Method & Path | PostgreSQL Table | Commit Verified | Read Back Verified | Tenant Scoped |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **Create Checklist** | `POST /api/v1/checklists` | `checklists` | Yes | Yes (`SELECT id, title FROM checklists`) | Yes |
| **List Checklists** | `GET /api/v1/checklists` | `checklists` | N/A (Read) | Yes (`WHERE tenant_id = :tid`) | Yes |
| **Toggle Status** | `PUT /api/v1/checklists/{id}` | `checklists` | Yes | Yes (`is_completed = true/false`) | Yes |
| **Update Title/Category** | `PUT /api/v1/checklists/{id}` | `checklists` | Yes | Yes (Updated title confirmed) | Yes |
| **Delete Checklist (Owner Only)** | `DELETE /api/v1/checklists/{id}` | `checklists` | Yes | Yes (Record removed from DB) | Yes |

### 1.3 Inventory & Medical Supplies Domain
| Operation | HTTP Method & Path | PostgreSQL Table | Commit Verified | Read Back Verified | Tenant Scoped |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **Create Inventory Item** | `POST /api/v1/inventory` | `inventory_items` | Yes | Yes (`SELECT id, item_name, current_stock`) | Yes |
| **List Inventory** | `GET /api/v1/inventory` | `inventory_items` | N/A (Read) | Yes (`WHERE tenant_id = :tid`) | Yes |
| **Update Stock Level** | `PUT /api/v1/inventory/{id}` | `inventory_items` | Yes | Yes (`current_stock` updated) | Yes |
| **Delete Inventory Item** | `DELETE /api/v1/inventory/{id}` | `inventory_items` | Yes | Yes (Record removed from DB) | Yes |

### 1.4 Exam Rooms Domain
| Operation | HTTP Method & Path | PostgreSQL Table | Commit Verified | Read Back Verified | Tenant Scoped |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **Create Room** | `POST /api/v1/rooms` | `rooms` | Yes | Yes (`SELECT id, room_number, name`) | Yes |
| **List Rooms** | `GET /api/v1/rooms` | `rooms` | N/A (Read) | Yes (`WHERE tenant_id = :tid`) | Yes |
| **Update Room Status** | `PUT /api/v1/rooms/{id}` | `rooms` | Yes | Yes (`status = 'Occupied'/'Available'`) | Yes |
| **Delete Room** | `DELETE /api/v1/rooms/{id}` | `rooms` | Yes | Yes (Record removed from DB) | Yes |

### 1.5 Staff & Shift Profiles Domain
| Operation | HTTP Method & Path | PostgreSQL Table | Commit Verified | Read Back Verified | Tenant Scoped |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **Get Own Profile** | `GET /api/v1/staff/me` | `staff` + `users` | N/A (Read) | Yes (`user_id` linked profile) | Yes |
| **Get Staff By ID** | `GET /api/v1/staff/{id}` | `staff` | N/A (Read) | Yes (`WHERE id = :id AND tenant_id = :tid`) | Yes |
| **Set Own Shift** | `POST /api/v1/staff/me/shift` | `staff` | Yes | Yes (`on_shift = true/false`) | Yes |
| **Owner Shift Override** | `PUT /api/v1/staff/{id}/shift` | `staff` | Yes | Yes (`on_shift` updated by Owner) | Yes |
| **Account Activation Status** | `PUT /api/v1/users/{id}/status` | `practicare_users` | Yes | Yes (`is_active = true/false`) | Yes |

---

## 2. Test Execution Results

The automated regression test suite `tests/verify_practicare_crud.ps1` was executed directly against the live backend:
- Task Edit (`PUT /api/v1/tasks/{id}`): **PASSED**
- Attending Physician Task Update (`PUT`): **PASSED**
- Checklist Edit (`PUT /api/v1/checklists/{id}`): **PASSED**
- Checklist Delete RBAC (Nurse 403 Forbidden): **PASSED**
- Checklist Delete RBAC (Inventory Manager 403 Forbidden): **PASSED**
- Checklist Delete (Clinic Owner HTTP 204): **PASSED**
- Task Delete RBAC (Nurse 403 Forbidden): **PASSED**
- Task Delete (Clinic Owner HTTP 204): **PASSED**

**Overall CRUD Persistence Pass Rate:** **100% (8/8 Test Assertions Passed)**
