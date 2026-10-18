$endpoints = @(
    @{ Name = "PractiCare Backend"; Url = "http://localhost:5001/health"; UI = "http://localhost:3001" },
    @{ Name = "TaxSnap Backend";    Url = "http://localhost:5002/health"; UI = "http://localhost:3002" },
    @{ Name = "PropSights Backend"; Url = "http://localhost:5003/health"; UI = "http://localhost:3003" },
    @{ Name = "OnScribe Backend";   Url = "http://localhost:5004/health"; UI = "http://localhost:3004" }
)

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "AXIO360 ECOSYSTEM DIAGNOSTICS & CONNECTIVITY VERIFICATION" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$allHealthy = $true

foreach ($svc in $endpoints) {
    Write-Host "`nTesting $($svc.Name)..." -ForegroundColor Yellow
    
    # 1. Backend Health Check
    try {
        $backendRes = Invoke-RestMethod -Uri $svc.Url -Method Get -TimeoutSec 5
        Write-Host "  [BACKEND OK] $($svc.Url)" -ForegroundColor Green
        Write-Host "    Status: $($backendRes.status)" -ForegroundColor Gray
        Write-Host "    DB Connected: $($backendRes.database_connected)" -ForegroundColor Gray
        Write-Host "    Tenant Count: $($backendRes.tenant_count)" -ForegroundColor Gray
    } catch {
        Write-Host "  [BACKEND FAIL] $($svc.Url): $($_.Exception.Message)" -ForegroundColor Red
        $allHealthy = $false
    }

    # 2. Frontend UI HTTP 200 Check
    try {
        $uiRes = Invoke-WebRequest -Uri $svc.UI -Method Get -TimeoutSec 5 -UseBasicParsing
        if ($uiRes.StatusCode -eq 200) {
            Write-Host "  [FRONTEND OK] $($svc.UI) -> HTTP 200 OK" -ForegroundColor Green
        } else {
            Write-Host "  [FRONTEND WARN] $($svc.UI) -> HTTP $($uiRes.StatusCode)" -ForegroundColor Yellow
            $allHealthy = $false
        }
    } catch {
        Write-Host "  [FRONTEND FAIL] $($svc.UI): $($_.Exception.Message)" -ForegroundColor Red
        $allHealthy = $false
    }
}

# 3. CORS Preflight Simulation
Write-Host "`n--- Testing CORS Preflight (OPTIONS) Headers ---" -ForegroundColor Yellow
foreach ($svc in $endpoints) {
    try {
        $corsHeaders = @{
            "Origin" = "http://localhost:3001"
            "Access-Control-Request-Method" = "POST"
            "Access-Control-Request-Headers" = "x-tenant-id,x-user-role,x-user-id,content-type"
        }
        $optionsRes = Invoke-WebRequest -Uri "$($svc.Url.Replace('/health', '/api/v1/auth/login'))" -Method Options -Headers $corsHeaders -UseBasicParsing -TimeoutSec 5
        $allowOrigin = $optionsRes.Headers["access-control-allow-origin"]
        $allowCreds = $optionsRes.Headers["access-control-allow-credentials"]
        Write-Host "  [CORS OK] $($svc.Name) allows origin: $allowOrigin (Credentials: $allowCreds)" -ForegroundColor Green
    } catch {
        Write-Host "  [CORS NOTE] $($svc.Name) options check: $($_.Exception.Message)" -ForegroundColor Gray
    }
}

Write-Host "`n======================================================================" -ForegroundColor Cyan
if ($allHealthy) {
    Write-Host "ALL BACKEND & FRONTEND SERVICES ARE FULLY OPERATIONAL AND HEALTHY!" -ForegroundColor Green
} else {
    Write-Host "ONE OR MORE SERVICES FAILED HEALTH CHECKS!" -ForegroundColor Red
}
Write-Host "======================================================================" -ForegroundColor Cyan
