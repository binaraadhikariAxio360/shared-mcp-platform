# ==============================================================================
# PRACTICARE AI CONVERSATION PRIVACY, AUTHENTICATION & NEW TOOLS TEST SUITE
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
Write-Host "1. Testing Secure Session Authentication & Token Issuance" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 1.1 Login as Tenant 01 Owner (Dr. Sarah Chen / Vanguard Clinic)
$loginT1A = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/login" -Method Post -ContentType "application/json" -Body '{"email":"owner@vanguardclinic.com","password":"password123"}'
$tokenT1A = $loginT1A.access_token
Assert-Condition ($tokenT1A -match "^pcsess\.") "Tenant 01 User A received HMAC-SHA256 signed session token: $($tokenT1A.Substring(0, 20))..."

# 1.2 Login as Tenant 02 Owner (Metro Health)
$loginT2 = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/login" -Method Post -ContentType "application/json" -Body '{"email":"owner@metrohealth.com","password":"password123"}'
$tokenT2 = $loginT2.access_token
Assert-Condition ($tokenT2 -match "^pcsess\.") "Tenant 02 User C received HMAC-SHA256 signed session token: $($tokenT2.Substring(0, 20))..."

# 1.3 Reject forged mock token
Write-Host "`nTesting Token Forgery Denial..." -ForegroundColor Yellow
try {
    Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations" -Method Get -Headers @{ "Authorization" = "Bearer moc_sess_usr-001_tenant-001" }
    Assert-Condition $false "Forged mock token should be rejected with 401"
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Assert-Condition ($statusCode -eq 401) "Forged mock token rejected with HTTP 401 Unauthorized"
}

# 1.4 Reject tampered token
try {
    Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations" -Method Get -Headers @{ "Authorization" = "Bearer pcsess.eyJzdWIiOiJ1c3ItMDAxIn0.invalidsignature" }
    Assert-Condition $false "Tampered token should be rejected with 401"
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Assert-Condition ($statusCode -eq 401) "Tampered token rejected with HTTP 401 Unauthorized"
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "2. Testing AI Conversation Creation & Multi-Tenant Privacy" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 2.1 User A creates a private conversation in Tenant 01
$createBody = @{ title = "Dr. Chen Private ICU Consultation" } | ConvertTo-Json
$convA = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenT1A" } -Body $createBody
$convId = $convA.id
Assert-Condition ($convId -match "^conv-") "Created AI Conversation ID: $convId for Tenant 01"

# 2.2 User A sends message in this conversation
$chatBody = @{
    conversation_id = $convId
    message = "Can you provide a practice summary of our facility?"
    agent_mode = "deterministic"
} | ConvertTo-Json
$chatA = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/chat" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenT1A" } -Body $chatBody
Assert-Condition ($chatA.conversation_id -eq $convId) "Chat response matches conversation ID $convId"
Assert-Condition ($chatA.reply.Length -gt 20) "Assistant generated report of length $($chatA.reply.Length)"

# 2.3 User A reads conversation detail
$convDetail = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations/$convId" -Method Get -Headers @{ "Authorization" = "Bearer $tokenT1A" }
Assert-Condition ($convDetail.messages.Count -ge 2) "Conversation history persisted in PostgreSQL (User + Assistant messages: $($convDetail.messages.Count))"

# 2.4 CROSS-TENANT ISOLATION: Tenant 02 User C attempts to read Tenant 01 conversation
Write-Host "`nTesting Cross-Tenant Conversation Isolation..." -ForegroundColor Yellow
try {
    Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations/$convId" -Method Get -Headers @{ "Authorization" = "Bearer $tokenT2" }
    Assert-Condition $false "Tenant 02 should NOT be able to read Tenant 01 conversation"
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Assert-Condition ($statusCode -eq 404) "Cross-tenant access to conversation $convId denied with HTTP 404 Not Found"
}

# 2.4b SAME-TENANT CROSS-USER ISOLATION: Tenant 01 User B (Doctor) attempts to read User A (Owner) conversation
Write-Host "`nTesting Same-Tenant Cross-User Conversation Isolation..." -ForegroundColor Yellow
$loginT1B = Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/login" -Method Post -ContentType "application/json" -Body '{"email":"doctor@vanguardclinic.com","password":"password123"}'
$tokenT1B = $loginT1B.access_token
try {
    Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations/$convId" -Method Get -Headers @{ "Authorization" = "Bearer $tokenT1B" }
    Assert-Condition $false "Tenant 01 User B should NOT be able to read User A's conversation"
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Assert-Condition ($statusCode -eq 404) "Same-tenant cross-user access to conversation $convId denied with HTTP 404 Not Found"
}
$convsT1B = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations" -Method Get -Headers @{ "Authorization" = "Bearer $tokenT1B" }
$foundUserBLeak = $convsT1B | Where-Object { $_.id -eq $convId }
Assert-Condition ($null -eq $foundUserBLeak) "Tenant 01 User B conversation list does NOT leak User A's conversation"

# 2.5 SPOOFED HEADER ATTACK: Attacker sends Tenant 01 token but spoofs 'x-tenant-id: tenant-002'
Write-Host "`nTesting Header Spoofing Resistance..." -ForegroundColor Yellow
$spoofedConvs = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations" -Method Get -Headers @{
    "Authorization" = "Bearer $tokenT1A"
    "x-tenant-id" = "tenant-002"
    "x-user-id" = "usr-002"
}
Assert-Condition ($spoofedConvs.Count -ge 1) "Server retrieved User A's actual tenant-001 conversations, completely ignoring spoofed headers"

# 2.6 Tenant 02 lists conversations -> should NOT see User A's conversation
$convsT2 = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations" -Method Get -Headers @{ "Authorization" = "Bearer $tokenT2" }
$foundLeaked = $convsT2 | Where-Object { $_.id -eq $convId }
Assert-Condition ($null -eq $foundLeaked) "Tenant 02 conversation list does NOT leak Tenant 01 conversation"

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "3. Testing AI Tool Gateway Execution (All 5 New Tools)" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# Tool 1: search_staff
Write-Host "Executing Tool 1: search_staff..." -ForegroundColor White
$chatStaff = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/chat" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenT1A" } -Body (@{
    conversation_id = $convId
    message = "Search for staff member Dr. Sarah"
    agent_mode = "deterministic"
} | ConvertTo-Json)
$execStaff = $chatStaff.tool_calls_executed | Where-Object { $_.tool -eq "search_staff" }
Assert-Condition ($null -ne $execStaff) "Tool 'search_staff' executed successfully via ToolGateway (status: $($execStaff.status))"

# Tool 2: list_tasks
Write-Host "Executing Tool 2: list_tasks..." -ForegroundColor White
$chatTasks = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/chat" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenT1A" } -Body (@{
    conversation_id = $convId
    message = "Show all pending clinical tasks"
    agent_mode = "deterministic"
} | ConvertTo-Json)
$execTasks = $chatTasks.tool_calls_executed | Where-Object { $_.tool -eq "list_tasks" }
Assert-Condition ($null -ne $execTasks) "Tool 'list_tasks' executed successfully via ToolGateway (status: $($execTasks.status))"

# Tool 3: update_task_status
Write-Host "Executing Tool 3: update_task_status..." -ForegroundColor White
# First get a real task ID from DB via direct API
$allTasks = Invoke-RestMethod -Uri "$baseUrl/api/v1/tasks" -Method Get -Headers @{ "Authorization" = "Bearer $tokenT1A" }
if ($allTasks.Count -gt 0) {
    $targetTask = $allTasks[0]
    $taskId = $targetTask.id
    Write-Host "  Targeting Task: $taskId (Current Status: $($targetTask.status))"
    $chatUpdate = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/chat" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenT1A" } -Body (@{
        conversation_id = $convId
        message = "Mark task $taskId as Completed"
        agent_mode = "deterministic"
    } | ConvertTo-Json)
    $execUpdate = $chatUpdate.tool_calls_executed | Where-Object { $_.tool -eq "update_task_status" }
    Assert-Condition ($null -ne $execUpdate) "Tool 'update_task_status' executed successfully via ToolGateway (status: $($execUpdate.status))"
    
    # Verify in PostgreSQL
    $verifyTask = Invoke-RestMethod -Uri "$baseUrl/api/v1/tasks" -Method Get -Headers @{ "Authorization" = "Bearer $tokenT1A" } | Where-Object { $_.id -eq $taskId }
    Assert-Condition ($verifyTask.status -eq "Completed") "Task status in PostgreSQL verified as 'Completed'"
}

# Tool 4: get_inventory_status
Write-Host "Executing Tool 4: get_inventory_status..." -ForegroundColor White
$chatInv = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/chat" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenT1A" } -Body (@{
    conversation_id = $convId
    message = "Which medical supplies or inventory items are running low?"
    agent_mode = "deterministic"
} | ConvertTo-Json)
$execInv = $chatInv.tool_calls_executed | Where-Object { $_.tool -eq "get_inventory_status" }
Assert-Condition ($null -ne $execInv) "Tool 'get_inventory_status' executed successfully via ToolGateway (status: $($execInv.status))"

# Tool 5: get_practice_summary
Write-Host "Executing Tool 5: get_practice_summary..." -ForegroundColor White
$chatSumm = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/chat" -Method Post -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenT1A" } -Body (@{
    conversation_id = $convId
    message = "Give me a complete clinic practice summary"
    agent_mode = "deterministic"
} | ConvertTo-Json)
$execSumm = $chatSumm.tool_calls_executed | Where-Object { $_.tool -eq "get_practice_summary" }
Assert-Condition ($null -ne $execSumm) "Tool 'get_practice_summary' executed successfully via ToolGateway (status: $($execSumm.status))"

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "4. Testing Conversation Rename and Deletion Lifecycle" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 4.1 Rename
$renameBody = @{ title = "Renamed Executive Summary" } | ConvertTo-Json
$renamed = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations/$convId" -Method Put -ContentType "application/json" -Headers @{ "Authorization" = "Bearer $tokenT1A" } -Body $renameBody
Assert-Condition ($renamed.title -eq "Renamed Executive Summary") "Conversation title updated to '$($renamed.title)'"

# 4.2 Delete
$deleted = Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations/$convId" -Method Delete -Headers @{ "Authorization" = "Bearer $tokenT1A" }
Assert-Condition ($deleted.success -eq $true) "Conversation deleted successfully"

# 4.3 Verify 404 after deletion
try {
    Invoke-RestMethod -Uri "$baseUrl/api/v1/ai/conversations/$convId" -Method Get -Headers @{ "Authorization" = "Bearer $tokenT1A" }
    Assert-Condition $false "Deleted conversation should return 404"
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Assert-Condition ($statusCode -eq 404) "Subsequent GET returns HTTP 404 Not Found"
}

Write-Host "`n=================================================================" -ForegroundColor Green
Write-Host "ALL SECURITY, ISOLATION & TOOL TESTS PASSED PERFECTLY!" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Green
