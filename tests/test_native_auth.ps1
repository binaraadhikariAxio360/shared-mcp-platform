# ======================================================================
# Axio360 Ecosystem Native SaaS Authentication & Session Verification
# Tests /api/v1/auth/login, /api/v1/auth/register, /api/v1/auth/me across all 4 apps
# ======================================================================

$apps = @(
    @{ Name = "PractiCare"; Port = 5001; ValidEmail = "owner@vanguardclinic.com"; Password = "password123"; ExpectedRole = "CLINIC_OWNER"; Tenant = "tenant-001" },
    @{ Name = "PractiCare"; Port = 5001; ValidEmail = "owner@metrohealth.com"; Password = "password123"; ExpectedRole = "CLINIC_OWNER"; Tenant = "tenant-002" },
    @{ Name = "TaxSnap";    Port = 5002; ValidEmail = "director@vanguardtax.com"; Password = "password123"; ExpectedRole = "FINANCE_DIRECTOR"; Tenant = "tenant-001" },
    @{ Name = "TaxSnap";    Port = 5002; ValidEmail = "director@horizoncap.com"; Password = "password123"; ExpectedRole = "FINANCE_DIRECTOR"; Tenant = "tenant-002" },
    @{ Name = "PropSights"; Port = 5003; ValidEmail = "broker@austinrealty.com"; Password = "password123"; ExpectedRole = "PRINCIPAL_BROKER"; Tenant = "tenant-001" },
    @{ Name = "PropSights"; Port = 5003; ValidEmail = "broker@lonestarrealty.com"; Password = "password123"; ExpectedRole = "PRINCIPAL_BROKER"; Tenant = "tenant-002" },
    @{ Name = "OnScribe";   Port = 5004; ValidEmail = "director@apexops.com"; Password = "password123"; ExpectedRole = "OPERATIONS_DIRECTOR"; Tenant = "tenant-001" },
    @{ Name = "OnScribe";   Port = 5004; ValidEmail = "director@bluepeakops.com"; Password = "password123"; ExpectedRole = "OPERATIONS_DIRECTOR"; Tenant = "tenant-002" }
)

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "AXIO360 ECOSYSTEM SAAS AUTHENTICATION & SESSION TEST SUITE" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$allPassed = $true

foreach ($app in $apps) {
    $baseUrl = "http://localhost:$($app.Port)"
    Write-Host "`n--- Testing $($app.Name) (Port $($app.Port)) for $($app.ValidEmail) ---" -ForegroundColor Yellow

    # Test 1: Valid Login
    $loginBody = @{
        email = $app.ValidEmail
        password = $app.Password
    } | ConvertTo-Json

    try {
        $loginRes = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/login" -Method Post -Body $loginBody -ContentType "application/json"
        if ($loginRes.access_token -and $loginRes.user.email -eq $app.ValidEmail -and $loginRes.user.tenant_id -eq $app.Tenant) {
            Write-Host "  [PASS] Valid Login: HTTP 200, Token issued, User: $($loginRes.user.name), Role: $($loginRes.user.role), Tenant: $($loginRes.user.tenant_id)" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] Valid Login payload unexpected: $($loginRes | ConvertTo-Json -Compress)" -ForegroundColor Red
            $allPassed = $false
        }
    } catch {
        Write-Host "  [FAIL] Valid Login failed: $_" -ForegroundColor Red
        $allPassed = $false
    }

    # Test 2: Invalid Login (Bad Password -> HTTP 401)
    $badLoginBody = @{
        email = $app.ValidEmail
        password = "wrongpassword"
    } | ConvertTo-Json

    try {
        $badRes = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/login" -Method Post -Body $badLoginBody -ContentType "application/json"
        Write-Host "  [FAIL] Expected HTTP 401 for bad password but received 200" -ForegroundColor Red
        $allPassed = $false
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 401) {
            Write-Host "  [PASS] Invalid Login properly rejected with HTTP 401 Unauthorized" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] Unexpected error status: $($_.Exception.Response.StatusCode)" -ForegroundColor Red
            $allPassed = $false
        }
    }

    # Test 3: /api/v1/auth/me Endpoint
    try {
        $headers = @{
            "x-tenant-id" = $app.Tenant
            "x-user-role" = $app.ExpectedRole
            "x-user-id" = "test-user-id"
        }
        $meRes = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/me" -Method Get -Headers $headers
        if ($meRes.role -eq $app.ExpectedRole -and $meRes.tenant_id -eq $app.Tenant) {
            Write-Host "  [PASS] /auth/me Verified: Active Role $($meRes.role), Tenant: $($meRes.tenant_id)" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] /auth/me payload mismatch: $($meRes | ConvertTo-Json -Compress)" -ForegroundColor Red
            $allPassed = $false
        }
    } catch {
        Write-Host "  [FAIL] /auth/me failed: $_" -ForegroundColor Red
        $allPassed = $false
    }
}

# Test 4: Registration of Fresh Company & Multi-Tenant Partitioning
Write-Host "`n--- Testing Registration Flow & Dynamic Tenant Provisioning ---" -ForegroundColor Yellow
$regApp = @{ Name = "PractiCare"; Port = 5001; Role = "CLINIC_OWNER" }
$randomId = (Get-Random -Minimum 1000 -Maximum 9999)
$newCompany = "Horizon BioHealth Group $randomId"
$newEmail = "director@horizonbio$randomId.com"

$regBody = @{
    email = $newEmail
    password = "password123"
    full_name = "Dr. Marcus Brody"
    company_name = $newCompany
    role = $regApp.Role
} | ConvertTo-Json

try {
    $regRes = Invoke-RestMethod -Uri "http://localhost:$($regApp.Port)/api/v1/auth/register" -Method Post -Body $regBody -ContentType "application/json"
    if ($regRes.access_token -and $regRes.user.email -eq $newEmail -and $regRes.user.tenant_id -match "^tenant-") {
        Write-Host "  [PASS] Registration: New tenant partition '$($regRes.user.tenant_id)' created for '$($regRes.user.company_name)'" -ForegroundColor Green
        
        # Test login with newly created user
        $newLoginBody = @{
            email = $newEmail
            password = "password123"
        } | ConvertTo-Json
        $newLoginRes = Invoke-RestMethod -Uri "http://localhost:$($regApp.Port)/api/v1/auth/login" -Method Post -Body $newLoginBody -ContentType "application/json"
        if ($newLoginRes.user.id -eq $regRes.user.id) {
            Write-Host "  [PASS] Login with freshly registered user verified successfully" -ForegroundColor Green
        }
    } else {
        Write-Host "  [FAIL] Registration response unexpected: $($regRes | ConvertTo-Json -Compress)" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "  [FAIL] Registration test failed: $_" -ForegroundColor Red
    $allPassed = $false
}

Write-Host "`n======================================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "ALL AUTHENTICATION & MULTI-TENANT TESTS PASSED (100% SUCCESS)!" -ForegroundColor Green
} else {
    Write-Host "SOME TESTS FAILED! CHECK OUTPUT ABOVE." -ForegroundColor Red
}
Write-Host "======================================================================" -ForegroundColor Cyan
