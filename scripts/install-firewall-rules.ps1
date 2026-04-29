$ErrorActionPreference = "Stop"

$rules = @(
  @{ Name = "Animus Link Launcher 8997"; Port = 8997 },
  @{ Name = "Animus Link Bridge 8998"; Port = 8998 }
)

foreach ($rule in $rules) {
  Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
  New-NetFirewallRule `
    -DisplayName $rule.Name `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $rule.Port | Out-Null
  Write-Host "Allowed TCP port $($rule.Port) as '$($rule.Name)'"
}
