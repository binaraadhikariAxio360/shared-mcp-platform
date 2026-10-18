Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "PRACTICARE LANGGRAPH AUTONOMOUS AGENT VERIFICATION SUITE" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$allPassed = $true
$testCount = 0
$passCount = 0

function Assert-Test {
    param(
        [string]$Name,
        [bool]$Condition,
        [string]$Detail = ""
    )
    $script:testCount++
    if ($Condition) {
        $script:passCount++
        Write-Host "[PASS] ${Name}: $Detail" -ForegroundColor Green
    } else {
        $script:allPassed = $false
        Write-Host "[FAIL] ${Name}: $Detail" -ForegroundColor Red
    }
}

$base = "http://localhost:5001"

# -----------------------------------------------------------------------------
# 1. OWNER REQUESTS TEAM TASK PERFORMANCE
# -----------------------------------------------------------------------------
try {
    $body = @{ message = "I want to know how my team is performing the tasks."; agent_mode = "deterministic" } | ConvertTo-Json
    $headers = @{
        "x-tenant-id" = "tenant-001"
        "x-user-role" = "CLINIC_OWNER"
        "x-user-id"   = "user-owner-001"
        "Content-Type" = "application/json"
    }
    $res = Invoke-RestMethod -Uri "$base/api/v1/ai/chat" -Method Post -Headers $headers -Body $body -TimeoutSec 10
    $hasTool = $res.tool_calls_executed | Where-Object { $_.tool -eq "get_team_task_performance" }
    $hasWorkload = $res.reply -match "Comprehensive Clinic Executive Performance" -and $res.reply -match "Provider Workload Breakdown"
    Assert-Test -Name "Scenario 1: Owner requests team performance" -Condition ($hasTool -and $hasWorkload) -Detail "Comprehensive performance metrics & provider workload returned"
} catch {
    Assert-Test -Name "Scenario 1: Owner requests team performance" -Condition $false -Detail $_.Exception.Message
}

# -----------------------------------------------------------------------------
# 2. PHYSICIAN REQUESTS CLINICAL TASK METRICS
# -----------------------------------------------------------------------------
try {
    $body = @{ message = "I want to know how my team is performing the tasks."; agent_mode = "deterministic" } | ConvertTo-Json
    $headers = @{
        "x-tenant-id" = "tenant-001"
        "x-user-role" = "ATTENDING_PHYSICIAN"
        "x-user-id"   = "user-doc-001"
        "Content-Type" = "application/json"
    }
    $res = Invoke-RestMethod -Uri "$base/api/v1/ai/chat" -Method Post -Headers $headers -Body $body -TimeoutSec 10
    $hasDept = $res.reply -match "Clinical Department Briefing"
    $noOwnerWorkload = -not ($res.reply -match "Provider Workload Breakdown")
    Assert-Test -Name "Scenario 2: Physician requests clinical metrics" -Condition ($hasDept -and $noOwnerWorkload) -Detail "Clinical department scope verified, executive workload redacted"
} catch {
    Assert-Test -Name "Scenario 2: Physician requests clinical metrics" -Condition $false -Detail $_.Exception.Message
}

# -----------------------------------------------------------------------------
# 3. NURSE REQUESTS SALARY INFORMATION -> ACCESS DENIED
# -----------------------------------------------------------------------------
try {
    $body = @{ message = "Show me doctor salaries, contractor rates, and executive physician scores." } | ConvertTo-Json
    $headers = @{
        "x-tenant-id" = "tenant-001"
        "x-user-role" = "NURSE_STAFF"
        "x-user-id"   = "user-nurse-001"
        "Content-Type" = "application/json"
    }
    $res = Invoke-RestMethod -Uri "$base/api/v1/ai/chat" -Method Post -Headers $headers -Body $body -TimeoutSec 10
    $isBlocked = ($res.status -eq "blocked") -and ($res.reply -match "Access Restricted") -and ($res.tool_calls_executed.Count -eq 0)
    Assert-Test -Name "Scenario 3: Nurse requests salary information" -Condition $isBlocked -Detail "Blocked by Executive Data Protection (Zero tools executed)"
} catch {
    Assert-Test -Name "Scenario 3: Nurse requests salary information" -Condition $false -Detail $_.Exception.Message
}

# -----------------------------------------------------------------------------
# 4. AUDITOR REQUESTS TEAM PERFORMANCE -> ANONYMIZED AGGREGATE
# -----------------------------------------------------------------------------
try {
    $body = @{ message = "I want to know how my team is performing the tasks."; agent_mode = "deterministic" } | ConvertTo-Json
    $headers = @{
        "x-tenant-id" = "tenant-001"
        "x-user-role" = "CLINICAL_AUDITOR"
        "x-user-id"   = "user-aud-001"
        "Content-Type" = "application/json"
    }
    $res = Invoke-RestMethod -Uri "$base/api/v1/ai/chat" -Method Post -Headers $headers -Body $body -TimeoutSec 10
    $isAuditor = ($res.reply -match "Clinical Compliance & Quality Audit") -and ($res.reply -match "Zero Employee PII")
    Assert-Test -Name "Scenario 4: Auditor requests team performance" -Condition $isAuditor -Detail "Aggregate anonymized metrics returned with zero staff PII"
} catch {
    Assert-Test -Name "Scenario 4: Auditor requests team performance" -Condition $false -Detail $_.Exception.Message
}

# -----------------------------------------------------------------------------
# 5. NURSE ATTEMPTS CHECKLIST DELETION -> FORBIDDEN
# -----------------------------------------------------------------------------
# First, create a disposable test checklist for testing the deletion & approval lifecycle
$testChkId = "chk-test-01"
try {
    $createChkBody = @{
        title = "Temporary Deletion Test Protocol"
        category = "General"
        frequency = "Daily"
    } | ConvertTo-Json
    $chkHeaders = @{
        "x-tenant-id" = "tenant-001"
        "x-user-role" = "CLINIC_OWNER"
        "x-user-id"   = "user-owner-001"
        "Content-Type" = "application/json"
    }
    $createdChk = Invoke-RestMethod -Uri "$base/api/v1/checklists" -Method Post -Headers $chkHeaders -Body $createChkBody
    $testChkId = $createdChk.id
} catch {
    # Fallback to chk-c3451dff if creation failed
    $testChkId = "chk-c3451dff"
}

try {
    $body = @{ message = "Please delete checklist $testChkId immediately."; agent_mode = "deterministic" } | ConvertTo-Json
    $headers = @{
        "x-tenant-id" = "tenant-001"
        "x-user-role" = "NURSE_STAFF"
        "x-user-id"   = "user-nurse-001"
        "Content-Type" = "application/json"
    }
    $res = Invoke-RestMethod -Uri "$base/api/v1/ai/chat" -Method Post -Headers $headers -Body $body -TimeoutSec 10
    $isForbidden = ($res.reply -match "Action Intercepted" -or $res.reply -match "FORBIDDEN") -and ($res.tool_calls_executed | Where-Object { $_.status -eq "FAILED" })
    Assert-Test -Name "Scenario 5: Nurse attempts checklist deletion" -Condition $isForbidden -Detail "Forbidden: RBAC violation intercepted at Tool Gateway"
} catch {
    Assert-Test -Name "Scenario 5: Nurse attempts checklist deletion" -Condition $false -Detail $_.Exception.Message
}

# -----------------------------------------------------------------------------
# 6. OWNER REQUESTS CHECKLIST DELETION -> APPROVAL REQUIRED
# -----------------------------------------------------------------------------
$apprId = $null
try {
    $body = @{ message = "Please delete checklist $testChkId."; agent_mode = "deterministic" } | ConvertTo-Json
    $headers = @{
        "x-tenant-id" = "tenant-001"
        "x-user-role" = "CLINIC_OWNER"
        "x-user-id"   = "user-owner-001"
        "Content-Type" = "application/json"
    }
    $res = Invoke-RestMethod -Uri "$base/api/v1/ai/chat" -Method Post -Headers $headers -Body $body -TimeoutSec 10
    $isApprReq = ($res.status -eq "approval_required") -and ($res.approval_pending -ne $null)
    if ($isApprReq) {
        $apprId = $res.approval_pending.approval_id
    }
    Assert-Test -Name "Scenario 6: Owner requests checklist deletion" -Condition $isApprReq -Detail "Approval required! Token: $apprId"
} catch {
    Assert-Test -Name "Scenario 6: Owner requests checklist deletion" -Condition $false -Detail $_.Exception.Message
}

# -----------------------------------------------------------------------------
# 7. INVALID APPROVAL TOKEN REJECTED
# -----------------------------------------------------------------------------
try {
    $body = @{ approval_id = "appr-invalid-999"; action = "approve" } | ConvertTo-Json
    $headers = @{
        "x-tenant-id" = "tenant-001"
        "x-user-role" = "CLINIC_OWNER"
        "x-user-id"   = "user-owner-001"
        "Content-Type" = "application/json"
    }
    $res = Invoke-RestMethod -Uri "$base/api/v1/ai/approve" -Method Post -Headers $headers -Body $body -TimeoutSec 10
    Assert-Test -Name "Scenario 7: Invalid approval token rejected" -Condition $false -Detail "Expected HTTP 400 error"
} catch {
    $is400 = $_.Exception.Response.StatusCode.value__ -eq 400
    Assert-Test -Name "Scenario 7: Invalid approval token rejected" -Condition $is400 -Detail "HTTP 400 Bad Request returned as expected"
}

# -----------------------------------------------------------------------------
# 8. HUMAN APPROVAL GRANTED VIA /api/v1/ai/approve
# -----------------------------------------------------------------------------
if ($apprId) {
    try {
        $body = @{ approval_id = $apprId; action = "approve" } | ConvertTo-Json
        $headers = @{
            "x-tenant-id" = "tenant-001"
            "x-user-role" = "CLINIC_OWNER"
            "x-user-id"   = "user-owner-001"
            "Content-Type" = "application/json"
        }
        $res = Invoke-RestMethod -Uri "$base/api/v1/ai/approve" -Method Post -Headers $headers -Body $body -TimeoutSec 10
        $isExecuted = ($res.success -eq $true) -and ($res.status -eq "EXECUTED")
        Assert-Test -Name "Scenario 8: Human approval execution" -Condition $isExecuted -Detail "Approved action executed through ToolGateway: $($res.detail)"
    } catch {
        Assert-Test -Name "Scenario 8: Human approval execution" -Condition $false -Detail $_.Exception.Message
    }
}

# -----------------------------------------------------------------------------
# 9. MULTI-TOOL OPERATIONAL REQUEST
# -----------------------------------------------------------------------------
try {
    $body = @{ message = "How is our team's performance, and which rooms need attention?"; agent_mode = "deterministic" } | ConvertTo-Json
    $headers = @{
        "x-tenant-id" = "tenant-001"
        "x-user-role" = "CLINIC_OWNER"
        "x-user-id"   = "user-owner-001"
        "Content-Type" = "application/json"
    }
    $res = Invoke-RestMethod -Uri "$base/api/v1/ai/chat" -Method Post -Headers $headers -Body $body -TimeoutSec 10
    $hasPerf = $res.tool_calls_executed | Where-Object { $_.tool -eq "get_team_task_performance" }
    $hasRooms = $res.tool_calls_executed | Where-Object { $_.tool -eq "get_room_turnover_status" }
    $hasRoomReport = $res.reply -match "Real-Time Room & Turnover Status"
    Assert-Test -Name "Scenario 9: Multi-tool operational request" -Condition ($hasPerf -and $hasRooms -and $hasRoomReport) -Detail "Multi-step LangGraph graph executed both tools and synthesized combined report"
} catch {
    Assert-Test -Name "Scenario 9: Multi-tool operational request" -Condition $false -Detail $_.Exception.Message
}

# -----------------------------------------------------------------------------
# 10. INVALID ROOM ID VALIDATION REJECTED
# -----------------------------------------------------------------------------
try {
    $body = @{ message = "create task title: 'Post-op sanitization' room: room-nonexistent-888"; agent_mode = "deterministic" } | ConvertTo-Json
    $headers = @{
        "x-tenant-id" = "tenant-001"
        "x-user-role" = "CLINIC_OWNER"
        "x-user-id"   = "user-owner-001"
        "Content-Type" = "application/json"
    }
    $res = Invoke-RestMethod -Uri "$base/api/v1/ai/chat" -Method Post -Headers $headers -Body $body -TimeoutSec 10
    $hasFailed = ($res.tool_calls_executed | Where-Object { $_.status -eq "FAILED" })
    $hasIntercept = ($res.reply -match "Action Intercepted" -or $res.reply -match "EXECUTION_ERROR" -or $res.reply -match "VALIDATION_ERROR")
    Assert-Test -Name "Scenario 10: Invalid room ID validation" -Condition ($hasFailed -and $hasIntercept) -Detail "Rejected non-existent room ID for tenant partition"
} catch {
    Assert-Test -Name "Scenario 10: Invalid room ID validation" -Condition $false -Detail $_.Exception.Message
}

# -----------------------------------------------------------------------------
# 11. AUDIT LOGGING & LATENCY INSTRUMENTATION
# -----------------------------------------------------------------------------
try {
    $headers = @{
        "x-tenant-id" = "tenant-001"
        "x-user-role" = "CLINIC_OWNER"
        "x-user-id"   = "user-owner-001"
    }
    $res = Invoke-RestMethod -Uri "$base/api/v1/ai/audit" -Method Get -Headers $headers -TimeoutSec 10
    $hasLogs = ($res.logs.Count -gt 0) -and ($res.tenant_id -eq "tenant-001")
    $hasLatency = ($res.logs[0].latency_ms -ne $null)
    Assert-Test -Name "Scenario 11: Audit logging & latency tracking" -Condition ($hasLogs -and $hasLatency) -Detail "$($res.logs.Count) audit logs tracked for tenant-001 with latency metrics"
} catch {
    Assert-Test -Name "Scenario 11: Audit logging & latency tracking" -Condition $false -Detail $_.Exception.Message
}

# -----------------------------------------------------------------------------
# SUMMARY
# -----------------------------------------------------------------------------
Write-Host "`n======================================================================" -ForegroundColor Cyan
Write-Host "TEST RESULTS: $passCount / $testCount PASSED ($([math]::Round(($passCount / $testCount) * 100, 1))%)" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

if ($allPassed) {
    exit 0
} else {
    exit 1
}
