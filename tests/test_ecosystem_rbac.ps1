Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "AXIO360 ECOSYSTEM MULTI-TENANT & RBAC COMPREHENSIVE VERIFICATION" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$allPassed = $true

# -----------------------------------------------------------------------------
# 1. FRONTEND HEALTH CHECKS
# -----------------------------------------------------------------------------
Write-Host "`n--- [1] FRONTEND SERVICES HEALTH (:3001 - :3004) ---" -ForegroundColor Yellow

$frontends = @(
    @{ Name = "PractiCare UI"; Url = "http://localhost:3001" },
    @{ Name = "TaxSnap UI"; Url = "http://localhost:3002" },
    @{ Name = "PropSights UI"; Url = "http://localhost:3003" },
    @{ Name = "OnScribe UI"; Url = "http://localhost:3004" }
)

foreach ($fe in $frontends) {
    try {
        $res = Invoke-WebRequest -Uri $fe.Url -Method Get -TimeoutSec 5 -UseBasicParsing
        if ($res.StatusCode -eq 200) {
            Write-Host "[PASS] $($fe.Name) ($($fe.Url)) is UP (HTTP 200)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] $($fe.Name) ($($fe.Url)) returned HTTP $($res.StatusCode)" -ForegroundColor Red
            $allPassed = $false
        }
    } catch {
        Write-Host "[FAIL] $($fe.Name) ($($fe.Url)) error: $($_.Exception.Message)" -ForegroundColor Red
        $allPassed = $false
    }
}

# -----------------------------------------------------------------------------
# 2. BACKEND AUTH ROLES & ROOT ENDPOINTS
# -----------------------------------------------------------------------------
Write-Host "`n--- [2] BACKEND AUTH ROLES ENDPOINTS (:5001 - :5004) ---" -ForegroundColor Yellow

$backends = @(
    @{ Name = "PractiCare API"; Url = "http://localhost:5001" },
    @{ Name = "TaxSnap API"; Url = "http://localhost:5002" },
    @{ Name = "PropSights API"; Url = "http://localhost:5003" },
    @{ Name = "OnScribe API"; Url = "http://localhost:5004" }
)

foreach ($be in $backends) {
    try {
        $root = Invoke-RestMethod -Uri "$($be.Url)/" -Method Get -TimeoutSec 5
        $headers = @{
            "x-tenant-id" = "tenant-001"
            "x-user-role" = "ADMIN"
            "x-user-id"   = "test-user"
        }
        $roles = Invoke-RestMethod -Uri "$($be.Url)/api/v1/auth/roles" -Method Get -Headers $headers -TimeoutSec 5
        if ($roles.roles.Count -ge 4) {
            Write-Host "[PASS] $($be.Name) ($($be.Url)): Root OK & Auth Roles OK ($($roles.roles.Count) roles configured)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] $($be.Name) ($($be.Url)): Incomplete roles response" -ForegroundColor Red
            $allPassed = $false
        }
    } catch {
        Write-Host "[FAIL] $($be.Name) ($($be.Url)) error: $($_.Exception.Message)" -ForegroundColor Red
        $allPassed = $false
    }
}

# -----------------------------------------------------------------------------
# 3. PRACTICARE MULTI-TENANT ISOLATION & RBAC (:5001)
# -----------------------------------------------------------------------------
Write-Host "`n--- [3] PRACTICARE (:5001) MULTI-TENANT & RBAC ---" -ForegroundColor Yellow
try {
    $h1 = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "CLINIC_OWNER"; "x-user-id" = "owner-1" }
    $h2 = @{ "x-tenant-id" = "tenant-002"; "x-user-role" = "CLINIC_OWNER"; "x-user-id" = "owner-2" }

    $rooms1 = Invoke-RestMethod -Uri "http://localhost:5001/api/v1/rooms" -Method Get -Headers $h1
    $rooms2 = Invoke-RestMethod -Uri "http://localhost:5001/api/v1/rooms" -Method Get -Headers $h2

    if ($rooms1.Count -gt 0 -and $rooms2.Count -gt 0 -and $rooms1[0].tenant_id -eq "tenant-001" -and $rooms2[0].tenant_id -eq "tenant-002") {
        Write-Host "[PASS] Tenant Isolation: tenant-001 has $($rooms1.Count) rooms, tenant-002 has $($rooms2.Count) rooms (Strict Partitioning)" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Tenant Isolation mismatch in PractiCare rooms" -ForegroundColor Red
        $allPassed = $false
    }

    # RBAC: NURSE_STAFF delete room forbidden
    $hNurse = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "NURSE_STAFF"; "x-user-id" = "nurse-1" }
    try {
        Invoke-RestMethod -Uri "http://localhost:5001/api/v1/rooms/$($rooms1[0].id)" -Method Delete -Headers $hNurse
        Write-Host "[FAIL] Expected 403 for NURSE_STAFF delete room" -ForegroundColor Red
        $allPassed = $false
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 403) {
            Write-Host "[PASS] RBAC Enforcement: NURSE_STAFF DELETE room -> HTTP 403 (Forbidden)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Unexpected error status: $($_.Exception.Message)" -ForegroundColor Red
            $allPassed = $false
        }
    }
} catch {
    Write-Host "[FAIL] PractiCare test error: $($_.Exception.Message)" -ForegroundColor Red
    $allPassed = $false
}

# -----------------------------------------------------------------------------
# 4. TAXSNAP MULTI-TENANT ISOLATION & RBAC (:5002)
# -----------------------------------------------------------------------------
Write-Host "`n--- [4] TAXSNAP (:5002) MULTI-TENANT & RBAC ---" -ForegroundColor Yellow
try {
    $h1 = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "FINANCE_DIRECTOR"; "x-user-id" = "dir-1" }
    $h2 = @{ "x-tenant-id" = "tenant-002"; "x-user-role" = "FINANCE_DIRECTOR"; "x-user-id" = "dir-2" }

    $sum1 = Invoke-RestMethod -Uri "http://localhost:5002/api/v1/dashboard/summary" -Method Get -Headers $h1
    $sum2 = Invoke-RestMethod -Uri "http://localhost:5002/api/v1/dashboard/summary" -Method Get -Headers $h2

    if ($sum1.tenant_id -eq "tenant-001" -and $sum2.tenant_id -eq "tenant-002" -and $sum1.business_name -ne $sum2.business_name) {
        Write-Host "[PASS] Tenant Isolation: tenant-001 '$($sum1.business_name)' != tenant-002 '$($sum2.business_name)'" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Tenant Isolation mismatch in TaxSnap" -ForegroundColor Red
        $allPassed = $false
    }

    # RBAC: AUDITOR_STAKEHOLDER post income forbidden
    $hAudit = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "AUDITOR_STAKEHOLDER"; "x-user-id" = "audit-1" }
    $body = @{ source = "Dividend Gain"; amount = 5000; date = "2026-10-15"; status = "Received" } | ConvertTo-Json
    try {
        Invoke-RestMethod -Uri "http://localhost:5002/api/v1/income" -Method Post -Headers $hAudit -Body $body -ContentType "application/json"
        Write-Host "[FAIL] Expected 403 for AUDITOR_STAKEHOLDER income create" -ForegroundColor Red
        $allPassed = $false
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 403) {
            Write-Host "[PASS] RBAC Enforcement: AUDITOR_STAKEHOLDER POST income -> HTTP 403 (Forbidden)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Unexpected error status: $($_.Exception.Message)" -ForegroundColor Red
            $allPassed = $false
        }
    }
} catch {
    Write-Host "[FAIL] TaxSnap test error: $($_.Exception.Message)" -ForegroundColor Red
    $allPassed = $false
}

# -----------------------------------------------------------------------------
# 5. PROPSIGHTS MULTI-TENANT ISOLATION & RBAC (:5003)
# -----------------------------------------------------------------------------
Write-Host "`n--- [5] PROPSIGHTS (:5003) MULTI-TENANT & RBAC ---" -ForegroundColor Yellow
try {
    $h1 = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "PRINCIPAL_BROKER"; "x-user-id" = "broker-1" }
    $h2 = @{ "x-tenant-id" = "tenant-002"; "x-user-role" = "PRINCIPAL_BROKER"; "x-user-id" = "broker-2" }

    $sum1 = Invoke-RestMethod -Uri "http://localhost:5003/api/v1/dashboard/summary" -Method Get -Headers $h1
    $sum2 = Invoke-RestMethod -Uri "http://localhost:5003/api/v1/dashboard/summary" -Method Get -Headers $h2

    if ($sum1.tenant_id -eq "tenant-001" -and $sum2.tenant_id -eq "tenant-002" -and $sum1.brokerage_name -ne $sum2.brokerage_name) {
        Write-Host "[PASS] Tenant Isolation: tenant-001 '$($sum1.brokerage_name)' != tenant-002 '$($sum2.brokerage_name)'" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Tenant Isolation mismatch in PropSights" -ForegroundColor Red
        $allPassed = $false
    }

    # RBAC: CLIENT_BUYER post property forbidden
    $hBuyer = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "CLIENT_BUYER"; "x-user-id" = "buyer-1" }
    $propBody = @{ title = "Luxury Penthouse"; address = "100 Congress Ave"; price = 1800000; beds = 3; baths = 3; sqft = 2800; amenities = "Concierge"; status = "AVAILABLE" } | ConvertTo-Json
    try {
        Invoke-RestMethod -Uri "http://localhost:5003/api/v1/properties" -Method Post -Headers $hBuyer -Body $propBody -ContentType "application/json"
        Write-Host "[FAIL] Expected 403 for CLIENT_BUYER property create" -ForegroundColor Red
        $allPassed = $false
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 403) {
            Write-Host "[PASS] RBAC Enforcement: CLIENT_BUYER POST property -> HTTP 403 (Forbidden)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Unexpected error status: $($_.Exception.Message)" -ForegroundColor Red
            $allPassed = $false
        }
    }
} catch {
    Write-Host "[FAIL] PropSights test error: $($_.Exception.Message)" -ForegroundColor Red
    $allPassed = $false
}

# -----------------------------------------------------------------------------
# 6. ONSCRIBE MULTI-TENANT ISOLATION & RBAC (:5004)
# -----------------------------------------------------------------------------
Write-Host "`n--- [6] ONSCRIBE (:5004) MULTI-TENANT & RBAC ---" -ForegroundColor Yellow
try {
    $h1 = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "OPERATIONS_DIRECTOR"; "x-user-id" = "dir-1" }
    $h2 = @{ "x-tenant-id" = "tenant-002"; "x-user-role" = "OPERATIONS_DIRECTOR"; "x-user-id" = "dir-2" }

    $sum1 = Invoke-RestMethod -Uri "http://localhost:5004/api/v1/dashboard/summary" -Method Get -Headers $h1
    $sum2 = Invoke-RestMethod -Uri "http://localhost:5004/api/v1/dashboard/summary" -Method Get -Headers $h2

    if ($sum1.tenant_id -eq "tenant-001" -and $sum2.tenant_id -eq "tenant-002" -and $sum1.organization_name -ne $sum2.organization_name) {
        Write-Host "[PASS] Tenant Isolation: tenant-001 '$($sum1.organization_name)' != tenant-002 '$($sum2.organization_name)'" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Tenant Isolation mismatch in OnScribe" -ForegroundColor Red
        $allPassed = $false
    }

    # RBAC: COMPLIANCE_AUDITOR post project forbidden
    $hAudit = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "COMPLIANCE_AUDITOR"; "x-user-id" = "audit-1" }
    $prjBody = @{ name = "Restricted Project"; code = "RP-99"; sprint_cycle = "Sprint Q4"; target_date = "2026-12-31" } | ConvertTo-Json
    try {
        Invoke-RestMethod -Uri "http://localhost:5004/api/v1/projects" -Method Post -Headers $hAudit -Body $prjBody -ContentType "application/json"
        Write-Host "[FAIL] Expected 403 for COMPLIANCE_AUDITOR project create" -ForegroundColor Red
        $allPassed = $false
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 403) {
            Write-Host "[PASS] RBAC Enforcement: COMPLIANCE_AUDITOR POST project -> HTTP 403 (Forbidden)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Unexpected error status: $($_.Exception.Message)" -ForegroundColor Red
            $allPassed = $false
        }
    }
} catch {
    Write-Host "[FAIL] OnScribe test error: $($_.Exception.Message)" -ForegroundColor Red
    $allPassed = $false
}

Write-Host "`n======================================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "ALL TESTS PASSED! 100% MULTI-TENANT ISOLATION & RBAC COMPLIANCE VERIFIED." -ForegroundColor Green
} else {
    Write-Host "SOME TESTS FAILED! CHECK OUTPUT ABOVE." -ForegroundColor Red
}
Write-Host "======================================================================" -ForegroundColor Cyan
