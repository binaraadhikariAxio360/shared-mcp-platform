# ==============================================================================
# PRACTICARE MULTI-TENANT REGISTRATION & INVITATION SYSTEM TEST SUITE
# ==============================================================================

$baseUrl = "http://localhost:5001"
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
Write-Host "PRACTICARE MULTI-TENANT & INVITATION ONBOARDING VERIFICATION" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

$uniqueSuffix = [System.Guid]::NewGuid().ToString().Substring(0, 6)

# ------------------------------------------------------------------------------
# 1. OWNER REGISTRATION: PATH A (CREATE NEW COMPANY)
# ------------------------------------------------------------------------------
Write-Host "`n[Test 1] Register Owner A with new company 'Apex Medical'..." -ForegroundColor Yellow
$ownerABody = @{
    name = "Dr. Alice Smith"
    email = "alice.$uniqueSuffix@apexmedical.org"
    password = "password123"
    company_name = "Apex Medical $uniqueSuffix"
} | ConvertTo-Json

$regA = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/register-company" -Method Post -ContentType "application/json" -Body $ownerABody
Assert-Condition ($regA.user.role -eq "CLINIC_OWNER") "User role is CLINIC_OWNER"
Assert-Condition ($regA.user.membership_status -eq "APPROVED") "Owner membership is automatically APPROVED"
Assert-Condition ($regA.user.tenant_id -match "^tenant-") "Server generated unique Tenant ID: $($regA.user.tenant_id)"
Assert-Condition ($regA.access_token -match "^pcsess\.") "Received valid session token for Owner A"

$tokenOwnerA = $regA.access_token
$tenantA = $regA.user.tenant_id

# ------------------------------------------------------------------------------
# 2. SEPARATE TENANT CREATION FOR SAME COMPANY NAME (NO ACCIDENTAL MERGING)
# ------------------------------------------------------------------------------
Write-Host "`n[Test 2] Register Owner B with IDENTICAL company name (must create separate tenant)..." -ForegroundColor Yellow
$ownerBBody = @{
    name = "Dr. Bob Jones"
    email = "bob.$uniqueSuffix@apexmedical.org"
    password = "password123"
    company_name = "Apex Medical $uniqueSuffix" # Exact same company name
} | ConvertTo-Json

$regB = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/register-company" -Method Post -ContentType "application/json" -Body $ownerBBody
$tenantB = $regB.user.tenant_id
$tokenOwnerB = $regB.access_token

Assert-Condition ($tenantB -ne $tenantA) "Different owners with identical company names get isolated tenants ($tenantA vs $tenantB)"

# ------------------------------------------------------------------------------
# 3. COMPANY SETTINGS (OWNER-ONLY)
# ------------------------------------------------------------------------------
Write-Host "`n[Test 3] Fetch Company Settings as Owner A..." -ForegroundColor Yellow
$settingsA = Invoke-RestMethod -Uri "$baseUrl/api/v1/company/settings" -Method Get -Headers @{ "Authorization" = "Bearer $tokenOwnerA" }
Assert-Condition ($settingsA.tenant_id -eq $tenantA) "Company Settings returns correct tenant ID"
Assert-Condition ($settingsA.total_staff_count -ge 1) "Initial total staff count includes Owner record"
Assert-Condition ($settingsA.active_invitations_count -eq 0) "Active invitations count starts at 0"
Assert-Condition ($settingsA.pending_requests_count -eq 0) "Pending requests count starts at 0"

# ------------------------------------------------------------------------------
# 4. OWNER GENERATES SECURE INVITATION CODE
# ------------------------------------------------------------------------------
Write-Host "`n[Test 4] Owner A creates an invitation code for a PHYSICIAN..." -ForegroundColor Yellow
$invReq = @{
    role = "PHYSICIAN"
    max_uses = 1
    expires_in_days = 7
} | ConvertTo-Json

$invA = Invoke-RestMethod -Uri "$baseUrl/api/v1/company/invitations" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenOwnerA" } -Body $invReq
$codeA = $invA.code
Assert-Condition ($codeA -match "^INV-[A-Z0-9]{4}-[A-Z0-9]{4}$") "Generated secure code format: $codeA"
Assert-Condition ($invA.role -eq "PHYSICIAN") "Invitation role is PHYSICIAN"
Assert-Condition ($invA.is_active -eq $true) "Invitation is active"

# ------------------------------------------------------------------------------
# 5. PUBLIC INVITATION VALIDATION
# ------------------------------------------------------------------------------
Write-Host "`n[Test 5] Public validation of invitation code..." -ForegroundColor Yellow
$valReq = @{ code = $codeA } | ConvertTo-Json
$valRes = Invoke-RestMethod -Uri "$baseUrl/api/v1/invitations/validate" -Method Post -ContentType "application/json" -Body $valReq
Assert-Condition ($valRes.valid -eq $true) "Invitation is reported as valid"
Assert-Condition ($valRes.company_name -eq "Apex Medical $uniqueSuffix") "Validation reveals company name: $($valRes.company_name)"
Assert-Condition ($valRes.role -eq "PHYSICIAN") "Validation reveals designated role: $($valRes.role)"

# Bad code test
$badValReq = @{ code = "INV-FAKE-CODE" } | ConvertTo-Json
$badValRes = Invoke-RestMethod -Uri "$baseUrl/api/v1/invitations/validate" -Method Post -ContentType "application/json" -Body $badValReq
Assert-Condition ($badValRes.valid -eq $false) "Bogus invitation code is invalid"

# ------------------------------------------------------------------------------
# 6. STAFF JOINS WITH INVITATION (PATH B) -> PENDING APPROVAL
# ------------------------------------------------------------------------------
Write-Host "`n[Test 6] Staff member joins company using invitation code..." -ForegroundColor Yellow
$staffJoinBody = @{
    name = "Dr. Gregory House"
    email = "house.$uniqueSuffix@apexmedical.org"
    password = "password123"
    invitation_code = $codeA
} | ConvertTo-Json

$joinRes = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/join" -Method Post -ContentType "application/json" -Body $staffJoinBody
Assert-Condition ($joinRes.membership_status -eq "PENDING") "Registered staff status is PENDING"
Assert-Condition ($joinRes.requires_approval -eq $true) "Requires owner approval"
Assert-Condition ($joinRes.tenant_id -eq $tenantA) "Staff user is linked to Tenant A"
$staffAId = $joinRes.user_id

# ------------------------------------------------------------------------------
# 7. PENDING STAFF LOGIN IS BLOCKED (HTTP 403)
# ------------------------------------------------------------------------------
Write-Host "`n[Test 7] Verify pending staff cannot log in until approved..." -ForegroundColor Yellow
$staffLoginBlocked = $false
try {
    $loginAttempt = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/login" -Method Post -ContentType "application/json" -Body (@{ email = "house.$uniqueSuffix@apexmedical.org"; password = "password123" } | ConvertTo-Json)
} catch {
    if ($_.Exception.Response.StatusCode -eq 403) {
        $staffLoginBlocked = $true
    }
}
Assert-Condition ($staffLoginBlocked -eq $true) "Pending staff login blocked with HTTP 403"

# ------------------------------------------------------------------------------
# 8. OWNER REVIEWS PENDING REQUESTS & TENANT ISOLATION
# ------------------------------------------------------------------------------
Write-Host "`n[Test 8] Owner A reviews pending requests..." -ForegroundColor Yellow
$pendingListA = Invoke-RestMethod -Uri "$baseUrl/api/v1/company/pending-members" -Method Get -Headers @{ "Authorization" = "Bearer $tokenOwnerA" }
Assert-Condition ($pendingListA.Count -ge 1) "Owner A has pending member(s)"
$pendingMember = $pendingListA | Where-Object { $_.user_id -eq $staffAId }
Assert-Condition ($pendingMember.name -eq "Dr. Gregory House") "Pending member Dr. Gregory House visible to Owner A"

Write-Host "`n[Test 8b] Tenant isolation: Owner B cannot see Owner A's pending requests..." -ForegroundColor Yellow
$pendingListB = Invoke-RestMethod -Uri "$baseUrl/api/v1/company/pending-members" -Method Get -Headers @{ "Authorization" = "Bearer $tokenOwnerB" }
$leakInB = $pendingListB | Where-Object { $_.user_id -eq $staffAId }
Assert-Condition ($leakInB -eq $null) "Owner B does NOT see Tenant A's applicant (Zero cross-tenant leak)"

# ------------------------------------------------------------------------------
# 9. OWNER APPROVES PENDING STAFF MEMBER
# ------------------------------------------------------------------------------
Write-Host "`n[Test 9] Owner A approves Dr. Gregory House..." -ForegroundColor Yellow
$approveReq = @{ action = "APPROVE" } | ConvertTo-Json
$approveRes = Invoke-RestMethod -Uri "$baseUrl/api/v1/company/pending-members/$staffAId/action" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenOwnerA" } -Body $approveReq

Assert-Condition ($approveRes.membership_status -eq "APPROVED") "Membership status updated to APPROVED"
Assert-Condition ($approveRes.staff_record_id -ne $null) "Staff record automatically created/linked: $($approveRes.staff_record_id)"

# Verify approved staff is now visible in Owner A's staff list
$staffListA = Invoke-RestMethod -Uri "$baseUrl/api/v1/staff" -Method Get -Headers @{ "Authorization" = "Bearer $tokenOwnerA" }
$foundStaff = $staffListA | Where-Object { $_.name -eq "Dr. Gregory House" }
Assert-Condition ($foundStaff -ne $null) "Dr. Gregory House is visible in PractiCare Staff Directory for Tenant A"

# ------------------------------------------------------------------------------
# 10. APPROVED STAFF CAN NOW LOG IN & PERFORM CLINICAL TASKS
# ------------------------------------------------------------------------------
Write-Host "`n[Test 10] Approved staff logs in successfully..." -ForegroundColor Yellow
$staffLogin = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/login" -Method Post -ContentType "application/json" -Body (@{ email = "house.$uniqueSuffix@apexmedical.org"; password = "password123" } | ConvertTo-Json)
$tokenStaff = $staffLogin.access_token
Assert-Condition ($tokenStaff -match "^pcsess\.") "Staff received active session token"
Assert-Condition ($staffLogin.user.membership_status -eq "APPROVED") "Staff user object reflects APPROVED"

# ------------------------------------------------------------------------------
# 11. INVITATION USAGE LIMIT ENFORCEMENT
# ------------------------------------------------------------------------------
Write-Host "`n[Test 11] Verify exhausted invitation code cannot be reused..." -ForegroundColor Yellow
$exhaustedJoinBlocked = $false
try {
    $joinAttempt2 = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/join" -Method Post -ContentType "application/json" -Body (@{
        name = "Dr. James Wilson"
        email = "wilson.$uniqueSuffix@apexmedical.org"
        password = "password123"
        invitation_code = $codeA # Already reached max_uses = 1
    } | ConvertTo-Json)
} catch {
    if ($_.Exception.Response.StatusCode -eq 400) {
        $exhaustedJoinBlocked = $true
    }
}
Assert-Condition ($exhaustedJoinBlocked -eq $true) "Re-using exhausted invitation code rejected with HTTP 400"

# ------------------------------------------------------------------------------
# 12. INVITATION REVOCATION
# ------------------------------------------------------------------------------
Write-Host "`n[Test 12] Owner A creates and revokes an invitation code..." -ForegroundColor Yellow
$invRevokeReq = @{ role = "NURSE"; max_uses = 5; expires_in_days = 3 } | ConvertTo-Json
$invToRevoke = Invoke-RestMethod -Uri "$baseUrl/api/v1/company/invitations" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenOwnerA" } -Body $invRevokeReq
$codeRevoke = $invToRevoke.code
$invId = $invToRevoke.id

$delRes = Invoke-RestMethod -Uri "$baseUrl/api/v1/company/invitations/$invId" -Method Delete -Headers @{ "Authorization" = "Bearer $tokenOwnerA" }
Assert-Condition ($delRes.message -match "revoked") "Invitation revoked successfully"

# Join attempt with revoked code
$revokedJoinBlocked = $false
try {
    Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/join" -Method Post -ContentType "application/json" -Body (@{
        name = "Nurse Jackie"
        email = "jackie.$uniqueSuffix@apexmedical.org"
        password = "password123"
        invitation_code = $codeRevoke
    } | ConvertTo-Json)
} catch {
    if ($_.Exception.Response.StatusCode -eq 400) {
        $revokedJoinBlocked = $true
    }
}
Assert-Condition ($revokedJoinBlocked -eq $true) "Revoked invitation code rejected with HTTP 400"

# ------------------------------------------------------------------------------
# 13. USER AI CHAT PRIVACY & ISOLATION
# ------------------------------------------------------------------------------
Write-Host "`n[Test 13] Verify user-level AI chat isolation between Owner and Staff..." -ForegroundColor Yellow
# Owner A creates an AI conversation
$ownerConv = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenOwnerA" } -Body '{"title":"Owner Private Executive Strategy"}'
$ownerConvId = $ownerConv.id

# Staff A lists conversations -> Owner A's conversation must NOT be in staff list
$staffConvs = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations" -Method Get -Headers @{ "Authorization" = "Bearer $tokenStaff" }
$leakedConv = $staffConvs | Where-Object { $_.id -eq $ownerConvId }
Assert-Condition ($leakedConv -eq $null) "Staff member cannot see Owner's private AI conversations"

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "ALL MULTI-TENANT & INVITATION ONBOARDING TESTS PASSED (13/13)" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan
