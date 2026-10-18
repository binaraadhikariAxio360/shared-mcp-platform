# ==============================================================================
# PRACTICARE AI AGENT PHASE 2 - DOCTOR REQUIREMENTS & INTENT-AWARE TEST SUITE
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
Write-Host "PRACTICARE PHASE 2 - 10 DOCTOR SCENARIOS AND INTENT VERIFICATION" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 1. Authenticate as Clinic Owner (Dr. Sarah Chen / Vanguard Clinic)
$loginT1 = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/login" -Method Post -ContentType "application/json" -Body '{"email":"owner@vanguardclinic.com","password":"password123"}'
$tokenT1 = $loginT1.access_token
Assert-Condition ($tokenT1 -match "^pcsess\.") "Authenticated as Tenant 01 Owner with session token"

# 2. Create isolated test conversation
$conv = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenT1" } -Body '{"title":"Phase 2 Doctor Requirements Test"}'
$convId = $conv.id
Assert-Condition ($convId -match "^conv-") "Created isolated AI test conversation: $convId"

# Helper function to execute chat
function Send-DoctorPrompt {
    param($promptText, $agentMode = "deterministic")
    $body = @{
        conversation_id = $convId
        message = $promptText
        agent_mode = $agentMode
    } | ConvertTo-Json
    return Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/chat" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenT1" } -Body $body
}

# ------------------------------------------------------------------------------
# SCENARIO 1: Create a task for John.
# ------------------------------------------------------------------------------
Write-Host "`n-----------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Scenario 1: Create a task for John." -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------------" -ForegroundColor Yellow
$res1 = Send-DoctorPrompt "Create a task for John."
$reply1 = $res1.reply
$tools1 = $res1.tool_calls_executed
Write-Host "Tools executed: $(($tools1 | ForEach-Object { $_.tool }) -join ', ')" -ForegroundColor DarkGray
Write-Host "Reply preview: $($reply1.Substring(0, [Math]::Min(120, $reply1.Length)))..." -ForegroundColor DarkGray

Assert-Condition ($tools1.Count -ge 1) "Scenario 1 executed authorized tool"
Assert-Condition ($tools1 | Where-Object { $_.tool -eq "create_clinical_task" }) "Selected and executed create_clinical_task"
Assert-Condition ($reply1 -match "Clinical Task Scheduled|Task Scheduled") "Response is an action confirmation"
Assert-Condition ($reply1 -notmatch "Executive Task Performance Report" -and $reply1 -notmatch "Operations Intelligence") "Did not generate unsolicited executive report"
Assert-Condition ($reply1 -match "John Reynolds" -or $reply1 -match "stf-05") "Assigned to resolved staff member John"

# ------------------------------------------------------------------------------
# SCENARIO 2: Show my pending tasks.
# ------------------------------------------------------------------------------
Write-Host "`n-----------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Scenario 2: Show my pending tasks." -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------------" -ForegroundColor Yellow
$res2 = Send-DoctorPrompt "Show my pending tasks."
$reply2 = $res2.reply
$tools2 = $res2.tool_calls_executed
Write-Host "Tools executed: $(($tools2 | ForEach-Object { $_.tool }) -join ', ')" -ForegroundColor DarkGray
Write-Host "Reply preview: $($reply2.Substring(0, [Math]::Min(120, $reply2.Length)))..." -ForegroundColor DarkGray

Assert-Condition ($tools2 | Where-Object { $_.tool -eq "list_tasks" }) "Selected and executed list_tasks"
Assert-Condition ($reply2 -match "Clinical Tasks" -or $reply2 -match "Pending") "Response returns pending tasks listing"
Assert-Condition ($reply2 -notmatch "Operations Intelligence" -and $reply2 -notmatch "Executive Task Performance") "Did not generate unsolicited executive report"

# ------------------------------------------------------------------------------
# SCENARIO 3: Complete task 15.
# ------------------------------------------------------------------------------
Write-Host "`n-----------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Scenario 3: Complete task 15." -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------------" -ForegroundColor Yellow
$res3 = Send-DoctorPrompt "Complete task 15."
$reply3 = $res3.reply
$tools3 = $res3.tool_calls_executed
Write-Host "Tools executed: $(($tools3 | ForEach-Object { $_.tool }) -join ', ')" -ForegroundColor DarkGray
Write-Host "Reply preview: $($reply3.Substring(0, [Math]::Min(120, $reply3.Length)))..." -ForegroundColor DarkGray

Assert-Condition ($tools3 | Where-Object { $_.tool -eq "update_task_status" }) "Selected and executed update_task_status"
Assert-Condition ($reply3 -match "Task Updated|Task Status Updated") "Response is an action confirmation"
Assert-Condition ($reply3 -match "tsk-15" -and $reply3 -match "Completed") "Task 15 status updated to Completed"
Assert-Condition ($reply3 -notmatch "Operations Intelligence") "Did not generate unsolicited executive report"

# ------------------------------------------------------------------------------
# SCENARIO 4: Explain task 15.
# ------------------------------------------------------------------------------
Write-Host "`n-----------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Scenario 4: Explain task 15." -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------------" -ForegroundColor Yellow
$res4 = Send-DoctorPrompt "Explain task 15."
$reply4 = $res4.reply
$tools4 = $res4.tool_calls_executed
Write-Host "Tools executed: $(($tools4 | ForEach-Object { $_.tool }) -join ', ')" -ForegroundColor DarkGray
Write-Host "Reply preview: $($reply4.Substring(0, [Math]::Min(150, $reply4.Length)))..." -ForegroundColor DarkGray

Assert-Condition ($tools4 | Where-Object { $_.tool -eq "list_tasks" }) "Selected and executed list_tasks"
Assert-Condition ($reply4 -match "Task Investigation" -or $reply4 -match "Review urgent blood chemistry panel") "Retrieved factual task details"
Assert-Condition ($reply4 -match "secondary physician lab verification" -or $reply4 -match "blood chemistry panel") "Explanation quotes documented clinic record notes without inventing reasons"
Assert-Condition ($reply4 -notmatch "Operations Intelligence") "Did not generate unsolicited executive report"

# ------------------------------------------------------------------------------
# SCENARIO 5: How is my team performing?
# ------------------------------------------------------------------------------
Write-Host "`n-----------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Scenario 5: How is my team performing?" -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------------" -ForegroundColor Yellow
$res5 = Send-DoctorPrompt "How is my team performing?"
$reply5 = $res5.reply
$tools5 = $res5.tool_calls_executed
Write-Host "Tools executed: $(($tools5 | ForEach-Object { $_.tool }) -join ', ')" -ForegroundColor DarkGray
Write-Host "Reply preview: $($reply5.Substring(0, [Math]::Min(120, $reply5.Length)))..." -ForegroundColor DarkGray

Assert-Condition ($tools5 | Where-Object { $_.tool -eq "get_team_task_performance" }) "Selected and executed get_team_task_performance"
Assert-Condition ($reply5 -match "Team Performance Summary") "Response is a concise performance summary"
Assert-Condition ($reply5 -match "Completion Rate" -and $reply5 -match "Provider Workload") "Includes core metrics and workload breakdown"

# ------------------------------------------------------------------------------
# SCENARIO 6: Analyse my team's performance.
# ------------------------------------------------------------------------------
Write-Host "`n-----------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Scenario 6: Analyse my team's performance." -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------------" -ForegroundColor Yellow
$res6 = Send-DoctorPrompt "Analyse my team's performance."
$reply6 = $res6.reply
$tools6 = $res6.tool_calls_executed
Write-Host "Tools executed: $(($tools6 | ForEach-Object { $_.tool }) -join ', ')" -ForegroundColor DarkGray
Write-Host "Reply preview: $($reply6.Substring(0, [Math]::Min(120, $reply6.Length)))..." -ForegroundColor DarkGray

Assert-Condition ($tools6 | Where-Object { $_.tool -eq "get_team_task_performance" }) "Selected and executed get_team_task_performance"
Assert-Condition ($reply6 -match "Clinical Operations & Team Performance Analysis") "Response is a detailed analysis"
Assert-Condition ($reply6 -match "Provider Workload Breakdown" -or $reply6 -match "Bottlenecks") "Provides detailed breakdown of workloads and bottlenecks"

# ------------------------------------------------------------------------------
# SCENARIO 7: Generate a monthly task report.
# ------------------------------------------------------------------------------
Write-Host "`n-----------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Scenario 7: Generate a monthly task report." -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------------" -ForegroundColor Yellow
$res7 = Send-DoctorPrompt "Generate a monthly task report."
$reply7 = $res7.reply
$tools7 = $res7.tool_calls_executed
Write-Host "Tools executed: $(($tools7 | ForEach-Object { $_.tool }) -join ', ')" -ForegroundColor DarkGray
Write-Host "Reply preview: $($reply7.Substring(0, [Math]::Min(120, $reply7.Length)))..." -ForegroundColor DarkGray

Assert-Condition ($tools7 | Where-Object { $_.tool -eq "get_team_task_performance" }) "Selected and executed get_team_task_performance"
Assert-Condition ($reply7 -match "PractiCare Operations Intelligence") "Generated full structured Markdown report on explicit request"
Assert-Condition ($reply7 -match "Provider Workload Breakdown" -and $reply7 -match "Security Context") "Report contains formal sections and governance metadata"

# ------------------------------------------------------------------------------
# SCENARIO 8: Find overdue tasks and suggest priorities.
# ------------------------------------------------------------------------------
Write-Host "`n-----------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Scenario 8: Find overdue tasks and suggest priorities." -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------------" -ForegroundColor Yellow
$res8 = Send-DoctorPrompt "Find overdue tasks and suggest priorities."
$reply8 = $res8.reply
$tools8 = $res8.tool_calls_executed
Write-Host "Tools executed: $(($tools8 | ForEach-Object { $_.tool }) -join ', ')" -ForegroundColor DarkGray
Write-Host "Reply preview: $($reply8.Substring(0, [Math]::Min(120, $reply8.Length)))..." -ForegroundColor DarkGray

Assert-Condition ($tools8 | Where-Object { $_.tool -eq "list_tasks" }) "Selected and executed list_tasks"
Assert-Condition ($reply8 -match "Clinical Tasks" -or $reply8 -match "Priority") "Returns clinical tasks listing"
Assert-Condition ($reply8 -match "Priority Actions" -or $reply8 -match "Prioritize") "Suggests evidence-based clinical priorities"
Assert-Condition ($reply8 -notmatch "Operations Intelligence") "Did not generate unsolicited executive report"

# ------------------------------------------------------------------------------
# SCENARIO 9: Show low-stock inventory items.
# ------------------------------------------------------------------------------
Write-Host "`n-----------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Scenario 9: Show low-stock inventory items." -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------------" -ForegroundColor Yellow
$res9 = Send-DoctorPrompt "Show low-stock inventory items."
$reply9 = $res9.reply
$tools9 = $res9.tool_calls_executed
Write-Host "Tools executed: $(($tools9 | ForEach-Object { $_.tool }) -join ', ')" -ForegroundColor DarkGray
Write-Host "Reply preview: $($reply9.Substring(0, [Math]::Min(120, $reply9.Length)))..." -ForegroundColor DarkGray

Assert-Condition ($tools9 | Where-Object { $_.tool -eq "get_inventory_status" }) "Selected and executed get_inventory_status"
Assert-Condition ($reply9 -match "Medical Supplies & Inventory Status") "Returns inventory status block"
Assert-Condition ($reply9 -match "Low Stock:" -and $reply9 -match "Active Alerts") "Provides itemized stock and active alerts"
Assert-Condition ($reply9 -notmatch "Operations Intelligence") "Did not generate unsolicited executive report"

# ------------------------------------------------------------------------------
# SCENARIO 10: Create a task and assign it to the appropriate staff member.
# ------------------------------------------------------------------------------
Write-Host "`n-----------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Scenario 10: Create a task and assign it to the appropriate staff member." -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------------" -ForegroundColor Yellow
$res10 = Send-DoctorPrompt "Create a task and assign it to the appropriate staff member."
$reply10 = $res10.reply
$tools10 = $res10.tool_calls_executed
Write-Host "Tools executed: $(($tools10 | ForEach-Object { $_.tool }) -join ', ')" -ForegroundColor DarkGray
Write-Host "Reply preview: $($reply10.Substring(0, [Math]::Min(120, $reply10.Length)))..." -ForegroundColor DarkGray

Assert-Condition ($tools10 | Where-Object { $_.tool -eq "create_clinical_task" }) "Selected and executed create_clinical_task"
Assert-Condition ($reply10 -match "Clinical Task Scheduled") "Returns concise action confirmation"
Assert-Condition ($reply10 -notmatch "Unassigned") "Assigned to an active staff member automatically"
Assert-Condition ($reply10 -notmatch "Operations Intelligence") "Did not generate unsolicited executive report"

Write-Host "`n=================================================================" -ForegroundColor Green
Write-Host "ALL 10 DOCTOR SCENARIOS PASSED WITH INTENT-AWARE BEHAVIOR!" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Green
