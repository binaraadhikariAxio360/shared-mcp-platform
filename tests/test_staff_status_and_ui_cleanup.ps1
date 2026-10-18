# ==============================================================================
# PRACTICARE - UI CLEANUP & STAFF ACCOUNT STATUS VERIFICATION SUITE
# ==============================================================================

$apiBase = "http://localhost:5001"
$uiBase = "http://localhost:3001"
$ErrorActionPreference = "Stop"

function Assert-Condition {
    param($condition, $message)
    if ($condition) {
        Write-Host "  [PASS] $message" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] $message" -ForegroundColor Red
        throw "Assertion failed: $message"
    }
}

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "TEST 1: FRONTEND UI RENDERING & HEADER BUTTON VERIFICATION" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 1.1 Verify Next.js frontend is accessible
$uiResp = Invoke-WebRequest -Uri "$uiBase/" -UseBasicParsing
Assert-Condition ($uiResp.StatusCode -eq 200) "PractiCare Frontend UI renders with HTTP 200"

# 1.2 Inspect frontend source code to confirm removal of global Sync button and redundant header actions
$pageSrc = Get-Content -Path "apps/practicare/frontend/src/app/page.tsx" -Raw
$headerMatch = [regex]::Match($pageSrc, '(?s)<header.*?</header>')
Assert-Condition ($headerMatch.Success) "Found page header in template"
$headerContent = $headerMatch.Value

Assert-Condition ($headerContent -notmatch 'Sync') "Global 'Sync' button is removed from page header"
Assert-Condition ($headerContent -notmatch 'New Task') "Redundant page-header 'New Task' button is removed"
Assert-Condition ($headerContent -notmatch 'New Checklist') "Redundant page-header 'New Checklist' button is removed"
Assert-Condition ($headerContent -notmatch 'Add Supply Item') "Redundant page-header 'Add Supply Item' button is removed"
Assert-Condition ($headerContent -notmatch 'Add Room') "Redundant page-header 'Add Room' button is removed"
Assert-Condition ($headerContent -match 'AI Agent') "Global 'AI Agent' button is preserved in page header"

# 1.3 Verify internal section action buttons remain intact inside main view
Assert-Condition ($pageSrc -match '<span>Add Task</span>') "Internal 'Add Task' button inside Clinical Tasks section is preserved"
Assert-Condition ($pageSrc -match '<span>Add Checklist</span>') "Internal 'Add Checklist' button inside Checklists section is preserved"
Assert-Condition ($pageSrc -match '<span>Add Supply Item</span>') "Internal 'Add Supply Item' button inside Supplies section is preserved"
Assert-Condition ($pageSrc -match '<span>Add Room</span>') "Internal 'Add Room' button inside Rooms section is preserved"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "TEST 2: STAFF LISTING & STATUS FIELDS (IS_ACTIVE & ON_SHIFT)" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 2.1 Authenticate as Clinic Owner (tenant-001)
$loginOwner = Invoke-RestMethod -Uri "$apiBase/api/v1/auth/login" -Method Post -ContentType "application/json" -Body '{"email":"owner@vanguardclinic.com","password":"password123"}'
$ownerToken = $loginOwner.access_token
Assert-Condition ($ownerToken -match "^pcsess\.") "Authenticated as Clinic Owner"

# 2.2 Authenticate as Attending Physician (tenant-001)
$loginDoc = Invoke-RestMethod -Uri "$apiBase/api/v1/auth/login" -Method Post -ContentType "application/json" -Body '{"email":"doctor@vanguardclinic.com","password":"password123"}'
$docToken = $loginDoc.access_token
Assert-Condition ($docToken -match "^pcsess\.") "Authenticated as Attending Physician"

# 2.3 Fetch staff list and verify both fields are present
$staffList = Invoke-RestMethod -Uri "$apiBase/api/v1/staff" -Headers @{ "Authorization" = "Bearer $ownerToken" }
Assert-Condition ($staffList.Count -ge 4) "Staff list retrieved: $($staffList.Count) members found"

$staffMember1 = $staffList | Where-Object { $_.id -eq "stf-02" } # Marcus Chen, RN
Assert-Condition ($null -ne $staffMember1.is_active) "Staff member has 'is_active' account status field"
Assert-Condition ($null -ne $staffMember1.on_shift) "Staff member has 'on_shift' shift status field"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "TEST 3: CLINIC OWNER CAN DEACTIVATE & ACTIVATE STAFF ACCOUNT" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 3.1 Clinic Owner deactivates stf-02
$deactResp = Invoke-RestMethod -Uri "$apiBase/api/v1/staff/stf-02/status" -Method Put -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $ownerToken" } -Body '{"is_active": false}'
Assert-Condition ($deactResp.is_active -eq $false) "Clinic Owner successfully deactivated staff 'stf-02' (Marcus Chen)"
# Requirement 9: Do not automatically change On Shift / Off Duty when account status changes
Assert-Condition ($deactResp.on_shift -eq $true) "Shift status (on_shift) remained True after account deactivation"

# 3.2 Inactive staff cannot be assigned to new tasks (Requirement 10)
$taskBody = @{
    title = "Urgent triage vitals round"
    priority = "High"
    status = "Pending"
    due_date = "2026-10-15 14:00"
    assigned_staff_id = "stf-02"
} | ConvertTo-Json

$assignFailed = $false
try {
    Invoke-RestMethod -Uri "$apiBase/api/v1/tasks" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $ownerToken" } -Body $taskBody
} catch {
    $assignFailed = $true
    Assert-Condition ($_.Exception.Response.StatusCode.value__ -eq 400) "Assignment to inactive staff blocked with HTTP 400"
}
Assert-Condition ($assignFailed -eq $true) "Verified inactive staff member cannot be selected for new task assignments"

# 3.3 Clinic Owner reactivates stf-02
$reactResp = Invoke-RestMethod -Uri "$apiBase/api/v1/staff/stf-02/status" -Method Put -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $ownerToken" } -Body '{"is_active": true}'
Assert-Condition ($reactResp.is_active -eq $true) "Clinic Owner successfully reactivated staff 'stf-02'"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "TEST 4: RBAC AUTHORIZATION - NON-OWNER CANNOT MODIFY ACCOUNT STATUS" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 4.1 Attending Physician tries to deactivate staff -> 403 Forbidden
$rbacFailed = $false
try {
    Invoke-RestMethod -Uri "$apiBase/api/v1/staff/stf-02/status" -Method Put -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $docToken" } -Body '{"is_active": false}'
} catch {
    $rbacFailed = $true
    Assert-Condition ($_.Exception.Response.StatusCode.value__ -eq 403) "Non-owner modification blocked with HTTP 403 Forbidden"
}
Assert-Condition ($rbacFailed -eq $true) "Verified non-owner role cannot modify staff account status"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "TEST 5: TENANT ISOLATION - CROSS-TENANT MODIFICATION DENIED" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 5.1 Tenant-001 Owner tries to modify Tenant-002 staff ('stf-m01') -> 403 Forbidden
$crossTenantFailed = $false
try {
    Invoke-RestMethod -Uri "$apiBase/api/v1/staff/stf-m01/status" -Method Put -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $ownerToken" } -Body '{"is_active": false}'
} catch {
    $crossTenantFailed = $true
    Assert-Condition ($_.Exception.Response.StatusCode.value__ -eq 403) "Cross-tenant staff modification blocked with HTTP 403 Forbidden"
}
Assert-Condition ($crossTenantFailed -eq $true) "Cross-tenant account status modification securely rejected"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "TEST 6: AVOID LOCKING OUT THE LAST ACTIVE CLINIC OWNER" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 6.1 Attempt to deactivate the owner account
$targetOwnerUser = $loginOwner.user.id
$lockoutPrevented = $false
try {
    Invoke-RestMethod -Uri "$apiBase/api/v1/users/$targetOwnerUser/status" -Method Put -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $ownerToken" } -Body '{"is_active": false}'
} catch {
    $lockoutPrevented = $true
    Assert-Condition ($_.Exception.Response.StatusCode.value__ -eq 400) "Deactivating last active Clinic Owner blocked with HTTP 400"
}
Assert-Condition ($lockoutPrevented -eq $true) "Verified last active Clinic Owner lockout prevention"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "TEST 7: DEACTIVATED USER BLOCKED FROM AUTH & PROTECTED ENDPOINTS" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 7.1 Deactivate nurse user account
$nurseLogin = Invoke-RestMethod -Uri "$apiBase/api/v1/auth/login" -Method Post -ContentType "application/json" -Body '{"email":"nurse@vanguardclinic.com","password":"password123"}'
$nurseToken = $nurseLogin.access_token
$nurseId = $nurseLogin.user.id

# Owner deactivates nurse
$userDeact = Invoke-RestMethod -Uri "$apiBase/api/v1/users/$nurseId/status" -Method Put -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $ownerToken" } -Body '{"is_active": false}'
Assert-Condition ($userDeact.is_active -eq $false) "Nurse account deactivated by Clinic Owner"

# 7.2 Inactive nurse attempts to login -> 403 Forbidden
$loginBlocked = $false
try {
    Invoke-RestMethod -Uri "$apiBase/api/v1/auth/login" -Method Post -ContentType "application/json" -Body '{"email":"nurse@vanguardclinic.com","password":"password123"}'
} catch {
    $loginBlocked = $true
    Assert-Condition ($_.Exception.Response.StatusCode.value__ -eq 403) "Inactive user login blocked with HTTP 403 Forbidden"
}
Assert-Condition ($loginBlocked -eq $true) "Verified inactive account cannot authenticate"

# 7.3 Inactive nurse attempts to use existing session token on protected endpoints -> 403 Forbidden
$sessionBlocked = $false
try {
    Invoke-RestMethod -Uri "$apiBase/api/v1/tasks" -Method Get -Headers @{ "Authorization" = "Bearer $nurseToken" }
} catch {
    $sessionBlocked = $true
    Assert-Condition ($_.Exception.Response.StatusCode.value__ -eq 403) "Existing session of inactive user blocked with HTTP 403"
}
Assert-Condition ($sessionBlocked -eq $true) "Verified inactive user's existing session cannot access protected resources"

# 7.4 Inactive nurse attempts to call AI endpoint -> 403 Forbidden
$aiBlocked = $false
try {
    Invoke-RestMethod -Uri "$apiBase/api/v1/ai/conversations" -Method Get -Headers @{ "Authorization" = "Bearer $nurseToken" }
} catch {
    $aiBlocked = $true
    Assert-Condition ($_.Exception.Response.StatusCode.value__ -eq 403) "AI endpoint access by inactive user blocked with HTTP 403"
}
Assert-Condition ($aiBlocked -eq $true) "Verified inactive user cannot access AI endpoints"

# 7.5 Reactivate nurse user account
$userReact = Invoke-RestMethod -Uri "$apiBase/api/v1/users/$nurseId/status" -Method Put -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $ownerToken" } -Body '{"is_active": true}'
Assert-Condition ($userReact.is_active -eq $true) "Nurse account restored to active status"

# Verify nurse can login again
$nurseLoginRestored = Invoke-RestMethod -Uri "$apiBase/api/v1/auth/login" -Method Post -ContentType "application/json" -Body '{"email":"nurse@vanguardclinic.com","password":"password123"}'
Assert-Condition ($nurseLoginRestored.access_token -match "^pcsess\.") "Reactivated user can authenticate normally"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "TEST 8: INDEPENDENT SHIFT STATUS (ON SHIFT / OFF DUTY)" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 8.1 Toggle shift status to Off Duty
$shiftResp = Invoke-RestMethod -Uri "$apiBase/api/v1/staff/stf-01/shift" -Method Put -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $ownerToken" } -Body '{"on_shift": false}'
Assert-Condition ($shiftResp.on_shift -eq $false) "Shift status updated to Off Duty"
Assert-Condition ($shiftResp.is_active -eq $true) "Account status remained Active when shift status changed"

# 8.2 Toggle shift status back to On Shift
$shiftResp2 = Invoke-RestMethod -Uri "$apiBase/api/v1/staff/stf-01/shift" -Method Put -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $ownerToken" } -Body '{"on_shift": true}'
Assert-Condition ($shiftResp2.on_shift -eq $true) "Shift status restored to On Shift"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "TEST 9: AUDIT TRAIL LOGGING OF STATUS CHANGES" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

$auditLogs = Invoke-RestMethod -Uri "$apiBase/api/v1/ai/audit" -Headers @{ "Authorization" = "Bearer $ownerToken" }
$statusAudit = $auditLogs.logs | Where-Object { $_.tool_name -eq "STAFF_ACCOUNT_STATUS_CHANGE" -or $_.tool_name -eq "USER_ACCOUNT_STATUS_CHANGE" }
Assert-Condition ($statusAudit.Count -ge 1) "Audit trail recorded status change events (Count: $($statusAudit.Count))"

Write-Host ""
Write-Host "ALL UI CLEANUP & STAFF ACCOUNT STATUS TESTS PASSED SUCCESSFULLY!" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan
