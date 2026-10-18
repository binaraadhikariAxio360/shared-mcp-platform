$headers = @{
    "x-tenant-id" = "tenant-001"
    "x-user-role" = "CLINIC_OWNER"
    "x-user-id"   = "user-owner-001"
    "Content-Type" = "application/json"
}

Write-Host "Sending prompt with Marcus..."
$body1 = @{ message = "Post-op Sterilization & Restock,102,2026-10-15,High,Marcus" } | ConvertTo-Json
$r1 = Invoke-RestMethod -Uri "http://localhost:5001/api/v1/ai/chat" -Method Post -Headers $headers -Body $body1 -TimeoutSec 90
Write-Host "--- RESPONSE 1 ---"
Write-Host "REPLY: $($r1.reply)"
Write-Host "TOOLS: $(($r1.tool_calls_executed | ForEach-Object { "$($_.tool)($($_.status))" }) -join ', ')"
