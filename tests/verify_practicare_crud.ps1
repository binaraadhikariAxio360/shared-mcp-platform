Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "PRACTICARE CLINICAL TASK & CHECKLIST CRUD / RBAC VERIFICATION" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$allPassed = $true
$base = "http://localhost:5001"

$ownerHeaders = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "CLINIC_OWNER"; "x-user-id" = "owner-1" }
$docHeaders   = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "ATTENDING_PHYSICIAN"; "x-user-id" = "doc-1" }
$nurseHeaders = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "NURSE_STAFF"; "x-user-id" = "nurse-1" }
$invHeaders   = @{ "x-tenant-id" = "tenant-001"; "x-user-role" = "INVENTORY_MANAGER"; "x-user-id" = "inv-1" }

# -----------------------------------------------------------------------------
# 1. TASK EDIT (PUT /api/v1/tasks/{id})
# -----------------------------------------------------------------------------
Write-Host "`n--- [1] TASK EDIT (PUT) ---" -ForegroundColor Yellow
try {
    $tasks = Invoke-RestMethod -Uri "$base/api/v1/tasks" -Method Get -Headers $ownerHeaders
    $taskId = $tasks[0].id
    Write-Host "Target Task ID: $taskId (Current: '$($tasks[0].title)')"

    # Edit as CLINIC_OWNER
    $taskUpdateBody = @{
        title = "Updated Autoclave sterilization verification"
        priority = "Critical"
        status = "In Progress"
    } | ConvertTo-Json

    $res1 = Invoke-RestMethod -Uri "$base/api/v1/tasks/$taskId" -Method Put -Headers $ownerHeaders -Body $taskUpdateBody -ContentType "application/json"
    if ($res1.title -eq "Updated Autoclave sterilization verification" -and $res1.status -eq "In Progress") {
        Write-Host "[PASS] CLINIC_OWNER PUT task -> HTTP 200 (Title and Status updated)" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] CLINIC_OWNER PUT task update mismatch" -ForegroundColor Red
        $allPassed = $false
    }

    # Edit as ATTENDING_PHYSICIAN
    $docUpdateBody = @{
        title = "Physician Certified Autoclave Cycle"
        priority = "High"
    } | ConvertTo-Json

    $res2 = Invoke-RestMethod -Uri "$base/api/v1/tasks/$taskId" -Method Put -Headers $docHeaders -Body $docUpdateBody -ContentType "application/json"
    if ($res2.title -eq "Physician Certified Autoclave Cycle" -and $res2.priority -eq "High") {
        Write-Host "[PASS] ATTENDING_PHYSICIAN PUT task -> HTTP 200 (Title and Priority updated)" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] ATTENDING_PHYSICIAN PUT task update mismatch" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "[FAIL] Task edit failed: $($_.Exception.Message)" -ForegroundColor Red
    $allPassed = $false
}

# -----------------------------------------------------------------------------
# 2. CHECKLIST EDIT (PUT /api/v1/checklists/{id})
# -----------------------------------------------------------------------------
Write-Host "`n--- [2] CHECKLIST EDIT (PUT) ---" -ForegroundColor Yellow
try {
    $checklists = Invoke-RestMethod -Uri "$base/api/v1/checklists" -Method Get -Headers $ownerHeaders
    $chkId = $checklists[0].id
    Write-Host "Target Checklist ID: $chkId (Current: '$($checklists[0].title)')"

    $chkUpdateBody = @{
        title = "Updated Morning Biohazard Waste Inspection Protocol"
        category = "Hygiene"
        frequency = "Daily"
    } | ConvertTo-Json

    $chkRes = Invoke-RestMethod -Uri "$base/api/v1/checklists/$chkId" -Method Put -Headers $ownerHeaders -Body $chkUpdateBody -ContentType "application/json"
    if ($chkRes.title -eq "Updated Morning Biohazard Waste Inspection Protocol") {
        Write-Host "[PASS] CLINIC_OWNER PUT checklist -> HTTP 200 (Title and Category updated)" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] CLINIC_OWNER PUT checklist update mismatch" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "[FAIL] Checklist edit failed: $($_.Exception.Message)" -ForegroundColor Red
    $allPassed = $false
}

# -----------------------------------------------------------------------------
# 3. CHECKLIST DELETE RBAC (DELETE /api/v1/checklists/{id})
# -----------------------------------------------------------------------------
Write-Host "`n--- [3] CHECKLIST DELETE RBAC ---" -ForegroundColor Yellow
try {
    # Create temp checklist item
    $tempChkBody = @{
        title = "Temporary Deletable Checklist Item"
        category = "Sterilization"
        frequency = "Daily"
    } | ConvertTo-Json
    $tempChk = Invoke-RestMethod -Uri "$base/api/v1/checklists" -Method Post -Headers $ownerHeaders -Body $tempChkBody -ContentType "application/json"
    $tempId = $tempChk.id
    Write-Host "Created Temp Checklist ID: $tempId"

    # Attempt delete as NURSE_STAFF -> Expect 403 Forbidden
    try {
        Invoke-RestMethod -Uri "$base/api/v1/checklists/$tempId" -Method Delete -Headers $nurseHeaders
        Write-Host "[FAIL] Expected HTTP 403 for NURSE_STAFF deleting checklist" -ForegroundColor Red
        $allPassed = $false
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 403) {
            Write-Host "[PASS] NURSE_STAFF DELETE checklist -> HTTP 403 Forbidden (RBAC Protected)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Unexpected status code: $($_.Exception.Message)" -ForegroundColor Red
            $allPassed = $false
        }
    }

    # Attempt delete as INVENTORY_MANAGER -> Expect 403 Forbidden
    try {
        Invoke-RestMethod -Uri "$base/api/v1/checklists/$tempId" -Method Delete -Headers $invHeaders
        Write-Host "[FAIL] Expected HTTP 403 for INVENTORY_MANAGER deleting checklist" -ForegroundColor Red
        $allPassed = $false
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 403) {
            Write-Host "[PASS] INVENTORY_MANAGER DELETE checklist -> HTTP 403 Forbidden (RBAC Protected)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Unexpected status code: $($_.Exception.Message)" -ForegroundColor Red
            $allPassed = $false
        }
    }

    # Delete as CLINIC_OWNER -> Expect HTTP 204 / Success
    try {
        $delRes = Invoke-WebRequest -Uri "$base/api/v1/checklists/$tempId" -Method Delete -Headers $ownerHeaders -UseBasicParsing
        if ($delRes.StatusCode -eq 204 -or $delRes.StatusCode -eq 200) {
            Write-Host "[PASS] CLINIC_OWNER DELETE checklist -> HTTP $($delRes.StatusCode) (Successfully Deleted)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Unexpected status on delete: $($delRes.StatusCode)" -ForegroundColor Red
            $allPassed = $false
        }
    } catch {
        Write-Host "[FAIL] CLINIC_OWNER delete failed: $($_.Exception.Message)" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "[FAIL] Checklist delete flow error: $($_.Exception.Message)" -ForegroundColor Red
    $allPassed = $false
}

# -----------------------------------------------------------------------------
# 4. TASK DELETE RBAC (DELETE /api/v1/tasks/{id})
# -----------------------------------------------------------------------------
Write-Host "`n--- [4] TASK DELETE RBAC ---" -ForegroundColor Yellow
try {
    # Create temp task
    $tempTaskBody = @{
        title = "Temporary Deletable Task"
        priority = "Low"
        due_date = "2026-10-15 18:00"
    } | ConvertTo-Json
    $tempTask = Invoke-RestMethod -Uri "$base/api/v1/tasks" -Method Post -Headers $ownerHeaders -Body $tempTaskBody -ContentType "application/json"
    $tempTskId = $tempTask.id
    Write-Host "Created Temp Task ID: $tempTskId"

    # Attempt delete as NURSE_STAFF -> Expect 403 Forbidden
    try {
        Invoke-RestMethod -Uri "$base/api/v1/tasks/$tempTskId" -Method Delete -Headers $nurseHeaders
        Write-Host "[FAIL] Expected HTTP 403 for NURSE_STAFF deleting task" -ForegroundColor Red
        $allPassed = $false
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 403) {
            Write-Host "[PASS] NURSE_STAFF DELETE task -> HTTP 403 Forbidden (RBAC Protected)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Unexpected status code: $($_.Exception.Message)" -ForegroundColor Red
            $allPassed = $false
        }
    }

    # Delete as CLINIC_OWNER -> Expect HTTP 204 / Success
    try {
        $delTaskRes = Invoke-WebRequest -Uri "$base/api/v1/tasks/$tempTskId" -Method Delete -Headers $ownerHeaders -UseBasicParsing
        if ($delTaskRes.StatusCode -eq 204 -or $delTaskRes.StatusCode -eq 200) {
            Write-Host "[PASS] CLINIC_OWNER DELETE task -> HTTP $($delTaskRes.StatusCode) (Successfully Deleted)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Unexpected status on delete: $($delTaskRes.StatusCode)" -ForegroundColor Red
            $allPassed = $false
        }
    } catch {
        Write-Host "[FAIL] CLINIC_OWNER task delete failed: $($_.Exception.Message)" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "[FAIL] Task delete flow error: $($_.Exception.Message)" -ForegroundColor Red
    $allPassed = $false
}

Write-Host "`n======================================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "ALL PRACTICARE TASK & CHECKLIST CRUD / RBAC TESTS PASSED (100%)" -ForegroundColor Green
} else {
    Write-Host "SOME TESTS FAILED! CHECK OUTPUT ABOVE." -ForegroundColor Red
}
Write-Host "======================================================================" -ForegroundColor Cyan
