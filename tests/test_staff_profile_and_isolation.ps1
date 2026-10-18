# ==============================================================================
# PRACTICARE - STAFF PROFILE, SHIFT SELF-SERVICE & TENANT ISOLATION TEST SUITE
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

function Invoke-ApiSafe {
    param($Uri, $Method = "Get", $Headers = @{}, $Body = $null)
    try {
        if ($Body) {
            $resp = Invoke-WebRequest -Uri $Uri -Method $Method -Headers $Headers -ContentType "application/json" -Body $Body -UseBasicParsing
        } else {
            $resp = Invoke-WebRequest -Uri $Uri -Method $Method -Headers $Headers -UseBasicParsing
        }
        return @{
            StatusCode = $resp.StatusCode
            Content = $resp.Content
            Json = if ($resp.Content) { ConvertFrom-Json $resp.Content } else { $null }
            Success = $true
        }
    } catch {
        $ex = $_.Exception
        if ($ex.Response) {
            $stream = $ex.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            $content = $reader.ReadToEnd()
            $json = try { ConvertFrom-Json $content } catch { $null }
            return @{
                StatusCode = [int]$ex.Response.StatusCode
                Content = $content
                Json = $json
                Success = $false
            }
        } else {
            return @{
                StatusCode = 500
                Content = $ex.Message
                Json = $null
                Success = $false
            }
        }
    }
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "PART 1: STAFF PROFILES & DETAILED VERIFIED FIELDS" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 1.1 Authenticate as Clinic Owner
$ownerLogin = Invoke-ApiSafe -Uri "$apiBase/api/v1/auth/login" -Method Post -Body '{"email":"owner@vanguardclinic.com","password":"password123"}'
Assert-Condition ($ownerLogin.StatusCode -eq 200) "Owner login successful"
$ownerToken = $ownerLogin.Json.access_token
$ownerHeaders = @{ "Authorization" = "Bearer $ownerToken" }

# 1.2 Authenticate as Attending Physician
$docLogin = Invoke-ApiSafe -Uri "$apiBase/api/v1/auth/login" -Method Post -Body '{"email":"doctor@vanguardclinic.com","password":"password123"}'
Assert-Condition ($docLogin.StatusCode -eq 200) "Doctor login successful"
$docToken = $docLogin.Json.access_token
$docHeaders = @{ "Authorization" = "Bearer $docToken" }

# 1.3 Staff member fetches their own profile via GET /api/v1/staff/me
$meResp = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/me" -Headers $docHeaders
Assert-Condition ($meResp.StatusCode -eq 200) "Doctor retrieved their own profile via /api/v1/staff/me"
Assert-Condition ($meResp.Json.email -eq "doctor@vanguardclinic.com") "Profile returns verified email address"
Assert-Condition ($meResp.Json.membership_status -eq "APPROVED" -or $meResp.Json.membership_status -eq "OWNER") "Profile returns membership status"
Assert-Condition ($meResp.Json.is_active -eq $true) "Profile reflects account is_active status"
Assert-Condition ($null -ne $meResp.Json.practice_name) "Profile contains affiliated practice name"
$docStaffId = $meResp.Json.id

# 1.4 Owner views authorized staff profile by ID
$staffDetailResp = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/$docStaffId" -Headers $ownerHeaders
Assert-Condition ($staffDetailResp.StatusCode -eq 200) "Owner can view authorized staff profile by ID"
Assert-Condition ($staffDetailResp.Json.id -eq $docStaffId) "Retrieved staff profile matches requested ID"

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "PART 2: SELF-SERVICE SHIFT MANAGEMENT & AUTHORIZATION" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 2.1 Doctor sets own shift status to On Shift (via /api/v1/staff/me/shift)
$shiftOnResp = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/me/shift" -Method Post -Headers $docHeaders -Body '{"on_shift":true}'
Assert-Condition ($shiftOnResp.StatusCode -eq 200) "Doctor self-service: Set On Shift successful"
Assert-Condition ($shiftOnResp.Json.on_shift -eq $true) "Shift status confirmed as true (On Shift)"

# 2.2 Verify shift status persists in database
$verifyShiftResp = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/me" -Headers $docHeaders
Assert-Condition ($verifyShiftResp.Json.on_shift -eq $true) "Shift status persisted in database across requests"

# 2.3 Doctor sets own shift status to Off Duty
$shiftOffResp = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/me/shift" -Method Post -Headers $docHeaders -Body '{"on_shift":false}'
Assert-Condition ($shiftOffResp.StatusCode -eq 200) "Doctor self-service: Set Off Duty successful"
Assert-Condition ($shiftOffResp.Json.on_shift -eq $false) "Shift status confirmed as false (Off Duty)"

# 2.4 Doctor attempts to change another staff member's shift (must be 403 Forbidden)
# Find Owner's staff ID
$ownerMeResp = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/me" -Headers $ownerHeaders
$ownerStaffId = $ownerMeResp.Json.id
$unauthShiftResp = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/$ownerStaffId/shift" -Method Put -Headers $docHeaders -Body '{"on_shift":false}'
Assert-Condition ($unauthShiftResp.StatusCode -eq 403) "Doctor cannot modify another staff member's shift (HTTP 403 Forbidden enforced)"

# 2.5 Owner performs administrative shift override on Doctor
$overrideResp = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/$docStaffId/shift" -Method Put -Headers $ownerHeaders -Body '{"on_shift":true}'
Assert-Condition ($overrideResp.StatusCode -eq 200) "Owner administrative shift override allowed"
Assert-Condition ($overrideResp.Json.on_shift -eq $true) "Shift updated via administrative override"

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "PART 3: OWNER-CONTROLLED ACCOUNT ACTIVATION & SAFETY" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 3.1 Normal staff cannot deactivate other accounts (403 Forbidden)
$staffDeactivateAttempt = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/$ownerStaffId/status" -Method Put -Headers $docHeaders -Body '{"is_active":false}'
Assert-Condition ($staffDeactivateAttempt.StatusCode -eq 403) "Normal staff forbidden from deactivating accounts (HTTP 403 Forbidden)"

# 3.2 Owner cannot deactivate the last active owner (safeguard)
$lastOwnerAttempt = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/$ownerStaffId/status" -Method Put -Headers $ownerHeaders -Body '{"is_active":false}'
Assert-Condition ($lastOwnerAttempt.StatusCode -eq 400) "Safeguard prevents deactivating the last active Clinic Owner (HTTP 400 Bad Request)"

# 3.3 Create a temporary staff member to test deactivation and shift prevention
$randId = (Get-Random -Minimum 1000 -Maximum 9999)
$testEmail = "tempstaff_$randId@vanguardclinic.com"
$testRegister = Invoke-ApiSafe -Uri "$apiBase/api/v1/auth/register-owner" -Method Post -Body (@{
    full_name = "Temp Nurse $randId"
    email = $testEmail
    password = "password123"
    company_name = "Vanguard Comprehensive Health Center"
    role = "NURSE_STAFF"
} | ConvertTo-Json)

if ($testRegister.StatusCode -eq 200) {
    $tempToken = $testRegister.Json.access_token
    $tempHeaders = @{ "Authorization" = "Bearer $tempToken" }
    $tempMe = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/me" -Headers $tempHeaders
    $tempStaffId = $tempMe.Json.id
    
    # Owner deactivates this staff account
    $deactivateResp = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/$tempStaffId/status" -Method Put -Headers $ownerHeaders -Body '{"is_active":false}'
    Assert-Condition ($deactivateResp.StatusCode -eq 200) "Owner can deactivate staff account"
    Assert-Condition ($deactivateResp.Json.is_active -eq $false) "Staff is_active is now false"
    
    # Deactivated account cannot access protected APIs
    $inactiveAccess = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/me" -Headers $tempHeaders
    Assert-Condition ($inactiveAccess.StatusCode -eq 401 -or $inactiveAccess.StatusCode -eq 403) "Deactivated user denied protected API access (HTTP $($inactiveAccess.StatusCode))"
    
    # Inactive staff cannot start a shift (via owner or self)
    $inactiveShift = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/$tempStaffId/shift" -Method Put -Headers $ownerHeaders -Body '{"on_shift":true}'
    Assert-Condition ($inactiveShift.StatusCode -eq 400) "Inactive account blocked from starting a shift (HTTP 400 Bad Request)"
    
    # Reactivate the account
    $reactivateResp = Invoke-ApiSafe -Uri "$apiBase/api/v1/staff/$tempStaffId/status" -Method Put -Headers $ownerHeaders -Body '{"is_active":true}'
    Assert-Condition ($reactivateResp.StatusCode -eq 200) "Owner can reactivate staff account"
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "PART 4: STRICT TENANT ISOLATION & ZERO DEMO LEAKAGE" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 4.1 Register a completely new Company: Tenant Alpha
$randAlpha = (Get-Random -Minimum 10000 -Maximum 99999)
$companyAlphaName = "Apex Cardiology Clinic $randAlpha"
$regAlpha = Invoke-ApiSafe -Uri "$apiBase/api/v1/auth/register-company" -Method Post -Body (@{
    company_name = $companyAlphaName
    owner_name = "Dr. Alice Alpha"
    email = "alice_$randAlpha@apexcardio.com"
    password = "password123"
} | ConvertTo-Json)
Assert-Condition ($regAlpha.StatusCode -eq 200) "Registered Company Alpha ($companyAlphaName)"
$tokenAlpha = $regAlpha.Json.access_token
$tenantAlphaId = if ($regAlpha.Json.tenant_id) { $regAlpha.Json.tenant_id } else { $regAlpha.Json.user.tenant_id }
$headersAlpha = @{ "Authorization" = "Bearer $tokenAlpha" }

# 4.2 Register a second completely new Company: Tenant Beta
$randBeta = (Get-Random -Minimum 10000 -Maximum 99999)
$companyBetaName = "Zenith Pediatrics $randBeta"
$regBeta = Invoke-ApiSafe -Uri "$apiBase/api/v1/auth/register-company" -Method Post -Body (@{
    company_name = $companyBetaName
    owner_name = "Dr. Bob Beta"
    email = "bob_$randBeta@zenithpeds.com"
    password = "password123"
} | ConvertTo-Json)
Assert-Condition ($regBeta.StatusCode -eq 200) "Registered Company Beta ($companyBetaName)"
$tokenBeta = $regBeta.Json.access_token
$tenantBetaId = if ($regBeta.Json.tenant_id) { $regBeta.Json.tenant_id } else { $regBeta.Json.user.tenant_id }
$headersBeta = @{ "Authorization" = "Bearer $tokenBeta" }

Assert-Condition ($tenantAlphaId -and $tenantBetaId -and ($tenantAlphaId -ne $tenantBetaId)) "Tenant Alpha ID ($tenantAlphaId) and Beta ID ($tenantBetaId) are unique"

# 4.3 Verify newly registered Tenant Beta has ZERO demo records
$betaSummary = Invoke-ApiSafe -Uri "$apiBase/api/v1/dashboard/summary" -Headers $headersBeta
Assert-Condition ($betaSummary.StatusCode -eq 200) "Fetched dashboard summary for Tenant Beta"
Assert-Condition ($betaSummary.Json.total_rooms -eq 0) "Tenant Beta starts with 0 rooms (no demo rooms leaked)"
Assert-Condition ($betaSummary.Json.tasks_total -eq 0) "Tenant Beta starts with 0 tasks (no demo tasks leaked)"
Assert-Condition ($betaSummary.Json.checklists_total -eq 0) "Tenant Beta starts with 0 checklists (no demo checklists leaked)"
Assert-Condition ($betaSummary.Json.low_stock_count -eq 0) "Tenant Beta starts with 0 low-stock items"
Assert-Condition ($betaSummary.Json.expiring_soon_count -eq 0) "Tenant Beta starts with 0 expiring items"

# 4.4 Verify operational list endpoints for Tenant Beta return empty arrays
$betaTasks = Invoke-ApiSafe -Uri "$apiBase/api/v1/tasks" -Headers $headersBeta
Assert-Condition ($betaTasks.Json.Count -eq 0) "Tenant Beta /tasks returns empty list"

$betaChecklists = Invoke-ApiSafe -Uri "$apiBase/api/v1/checklists" -Headers $headersBeta
Assert-Condition ($betaChecklists.Json.Count -eq 0) "Tenant Beta /checklists returns empty list"

$betaInventory = Invoke-ApiSafe -Uri "$apiBase/api/v1/inventory" -Headers $headersBeta
Assert-Condition ($betaInventory.Json.Count -eq 0) "Tenant Beta /inventory returns empty list"

$betaRooms = Invoke-ApiSafe -Uri "$apiBase/api/v1/rooms" -Headers $headersBeta
Assert-Condition ($betaRooms.Json.Count -eq 0) "Tenant Beta /rooms returns empty list"

# 4.5 Add operational data ONLY to Tenant Alpha
$createRoomAlpha = Invoke-ApiSafe -Uri "$apiBase/api/v1/rooms" -Method Post -Headers $headersAlpha -Body (@{
    room_number = "A-101"
    name = "Alpha Echo Suite"
    room_type = "Exam"
    status = "Available"
} | ConvertTo-Json)
Assert-Condition ($createRoomAlpha.StatusCode -eq 200 -or $createRoomAlpha.StatusCode -eq 201) "Created room A-101 in Tenant Alpha"
$roomAlphaId = $createRoomAlpha.Json.id

$createTaskAlpha = Invoke-ApiSafe -Uri "$apiBase/api/v1/tasks" -Method Post -Headers $headersAlpha -Body (@{
    title = "Sterilize Probe Alpha"
    priority = "High"
    status = "Pending"
    due_date = "2026-10-20 14:00"
    room_id = $roomAlphaId
} | ConvertTo-Json)
Assert-Condition ($createTaskAlpha.StatusCode -eq 200 -or $createTaskAlpha.StatusCode -eq 201) "Created task in Tenant Alpha"
$taskAlphaId = $createTaskAlpha.Json.id

$createChkAlpha = Invoke-ApiSafe -Uri "$apiBase/api/v1/checklists" -Method Post -Headers $headersAlpha -Body (@{
    title = "Alpha Daily Sterilization"
    category = "Sterilization"
    frequency = "Daily"
    is_completed = $false
} | ConvertTo-Json)
Assert-Condition ($createChkAlpha.StatusCode -eq 200 -or $createChkAlpha.StatusCode -eq 201) "Created checklist in Tenant Alpha"
$chkAlphaId = $createChkAlpha.Json.id

$createInvAlpha = Invoke-ApiSafe -Uri "$apiBase/api/v1/inventory" -Method Post -Headers $headersAlpha -Body (@{
    item_name = "Ultrasound Gel Alpha"
    current_stock = 15
    min_threshold = 20
    unit = "Bottles"
    room_id = $roomAlphaId
} | ConvertTo-Json)
Assert-Condition ($createInvAlpha.StatusCode -eq 200 -or $createInvAlpha.StatusCode -eq 201) "Created inventory item in Tenant Alpha"
$invAlphaId = $createInvAlpha.Json.id

# 4.6 Verify Tenant Beta STILL has ZERO operational records
$betaTasksAfter = Invoke-ApiSafe -Uri "$apiBase/api/v1/tasks" -Headers $headersBeta
Assert-Condition ($betaTasksAfter.Json.Count -eq 0) "Tenant Beta tasks count remains 0 after Alpha created tasks"

$betaRoomsAfter = Invoke-ApiSafe -Uri "$apiBase/api/v1/rooms" -Headers $headersBeta
Assert-Condition ($betaRoomsAfter.Json.Count -eq 0) "Tenant Beta rooms count remains 0 after Alpha created rooms"

# 4.7 Cross-Tenant Single-Item Access Prevention (Direct ID Lookup)
$crossTaskGet = Invoke-ApiSafe -Uri "$apiBase/api/v1/tasks/$taskAlphaId" -Headers $headersBeta
Assert-Condition ($crossTaskGet.StatusCode -eq 404) "Tenant Beta cannot get Tenant Alpha task by ID (HTTP 404)"

$crossRoomGet = Invoke-ApiSafe -Uri "$apiBase/api/v1/rooms/$roomAlphaId" -Headers $headersBeta
Assert-Condition ($crossRoomGet.StatusCode -eq 404) "Tenant Beta cannot get Tenant Alpha room by ID (HTTP 404)"

$crossChkGet = Invoke-ApiSafe -Uri "$apiBase/api/v1/checklists/$chkAlphaId" -Headers $headersBeta
Assert-Condition ($crossChkGet.StatusCode -eq 404) "Tenant Beta cannot get Tenant Alpha checklist by ID (HTTP 404)"

$crossInvGet = Invoke-ApiSafe -Uri "$apiBase/api/v1/inventory/$invAlphaId" -Headers $headersBeta
Assert-Condition ($crossInvGet.StatusCode -eq 404) "Tenant Beta cannot get Tenant Alpha inventory by ID (HTTP 404)"

# 4.8 Cross-Tenant Modification & Deletion Prevention
$crossTaskDelete = Invoke-ApiSafe -Uri "$apiBase/api/v1/tasks/$taskAlphaId" -Method Delete -Headers $headersBeta
Assert-Condition ($crossTaskDelete.StatusCode -eq 404) "Tenant Beta cannot delete Tenant Alpha task (HTTP 404)"

$crossChkDelete = Invoke-ApiSafe -Uri "$apiBase/api/v1/checklists/$chkAlphaId" -Method Delete -Headers $headersBeta
Assert-Condition ($crossChkDelete.StatusCode -eq 404) "Tenant Beta cannot delete Tenant Alpha checklist (HTTP 404)"

# 4.9 Cross-Tenant Foreign Key Boundary Enforcement
# Tenant Beta attempts to create a task pointing to Tenant Alpha's room
$crossFkTask = Invoke-ApiSafe -Uri "$apiBase/api/v1/tasks" -Method Post -Headers $headersBeta -Body (@{
    title = "Malicious Cross-Tenant Task"
    priority = "High"
    status = "Pending"
    due_date = "2026-10-20 14:00"
    room_id = $roomAlphaId
} | ConvertTo-Json)
Assert-Condition ($crossFkTask.StatusCode -eq 400 -or $crossFkTask.StatusCode -eq 404) "Cross-tenant room reference rejected on task creation (HTTP $($crossFkTask.StatusCode))"

# 4.10 AI Tool Cross-Tenant Boundary Verification
$aiChatBeta = Invoke-ApiSafe -Uri "$apiBase/api/v1/ai/chat" -Method Post -Headers $headersBeta -Body (@{
    message = "List all tasks and exam rooms in the practice."
    stream = $false
} | ConvertTo-Json)
Assert-Condition ($aiChatBeta.StatusCode -eq 200) "AI Agent query executed for Tenant Beta"
Assert-Condition ($aiChatBeta.Content -notmatch "Alpha Echo Suite") "AI agent does not leak Tenant Alpha rooms to Tenant Beta"
Assert-Condition ($aiChatBeta.Content -notmatch "Sterilize Probe Alpha") "AI agent does not leak Tenant Alpha tasks to Tenant Beta"

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "PART 5: FRONTEND CODE & COMPONENT STRUCTURE VERIFICATION" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

$frontendCode = Get-Content -Path "apps/practicare/frontend/src/app/page.tsx" -Raw

Assert-Condition ($frontendCode -match "No tasks yet\. Create your first clinical task\.") "Frontend implements empty state for Tasks"
Assert-Condition ($frontendCode -match "No checklists created yet\.") "Frontend implements empty state for Checklists"
Assert-Condition ($frontendCode -match "No inventory items added yet\.") "Frontend implements empty state for Inventory"
Assert-Condition ($frontendCode -match "No exam rooms configured yet\.") "Frontend implements empty state for Rooms"
Assert-Condition ($frontendCode -match "No staff members enrolled yet\.") "Frontend implements empty state for Staff"
Assert-Condition ($frontendCode -match "setSelectedStaffProfile\(s\)") "Staff cards set selectedStaffProfile on click"
Assert-Condition ($frontendCode -match "showStaffProfileModal") "Staff Profile Modal state exists"
Assert-Condition ($frontendCode -match "handleSelfShiftToggle") "Self-service shift handler implemented"
Assert-Condition ($frontendCode -match "Administrative Shift Override") "Visual distinction for Owner Administrative Override"

Write-Host "`n=================================================================" -ForegroundColor Green
Write-Host "ALL TESTS IN TEST SUITE PASSED SUCCESSFULLY (100%)" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Green
