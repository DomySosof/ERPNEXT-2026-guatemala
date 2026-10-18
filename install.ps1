#Requires -Version 5.1
<#
  install.ps1 - ERPNext v16 sobre Docker para Windows (PowerShell)
  Nada se instala en tu maquina: todo vive en contenedores y volumenes Docker.
  Es el equivalente para PowerShell de install.sh (mismos comandos y flags).

  Uso:                .\install.ps1  ->  asistente web  ->  .\install.ps1 contabilidad

  Comandos:
     install (por defecto)  Instala / reanuda la instalacion completa
     up / start             Levanta el stack
     stop                   Detiene los contenedores (conserva datos)
     restart                Reinicia el stack
     status                 Estado de los servicios
     logs [servicio]        Ver logs (por defecto: backend)
     shell [servicio]       Abrir una terminal dentro de un contenedor
     console                Consola de Python de Frappe (sitio activo)
     contabilidad           Configura la contabilidad guatemalteca (ejecutalo
                            DESPUES de crear tu empresa con el asistente web)
     reports [anio]         Genera los estados financieros y los libros contables
     backup                 Respalda base de datos + archivos
     restore <archivo>      Restaura un respaldo .sql.gz
     update                 Actualiza a la version indicada en .env
     destroy                ELIMINA contenedores + volumenes (borra todo)
     env                    Muestra la configuracion activa
     help                   Esta ayuda

  Flags:
     --no-pull              No descargar imagenes
     --yes / -y             No preguntar nada
#>

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# Evita que la salida de stderr de comandos nativos se trate como error fatal.
$PSNativeCommandUseErrorActionPreference = $false

# ------------------------------------------------------------------ basicos --
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }
# No se cambia el directorio de trabajo: todas las rutas del proyecto se arman
# absolutas, y asi 'restore <ruta relativa>' se resuelve desde donde lo lanzas.

$EnvFile      = Join-Path $ScriptDir '.env'
$EnvExample   = Join-Path $ScriptDir '.env.example'
$ComposeFile  = Join-Path $ScriptDir 'docker-compose.yml'
$ScriptsDir   = Join-Path $ScriptDir 'scripts'
$SENTINEL     = 'ERP_ACCOUNTING_SETUP_OK'

$script:BackendId = $null

# ---------------------------------------------------------- salida en color --
function Write-Log  { param([string]$m) Write-Host '[>] '  -NoNewline -ForegroundColor Cyan;   Write-Host $m }
function Write-Ok   { param([string]$m) Write-Host '[OK] ' -NoNewline -ForegroundColor Green;  Write-Host $m }
function Write-Warn { param([string]$m) Write-Host '[!] '  -NoNewline -ForegroundColor Yellow; Write-Host $m }
function Write-Err  { param([string]$m) Write-Host '[x] '  -NoNewline -ForegroundColor Red;    Write-Host $m }
function Write-Hr   { Write-Host ('-' * 72) -ForegroundColor DarkGray }
function Die        { param([string]$m) Write-Err $m; exit 1 }

# ------------------------------------------------------------- argumentos ---
$Command   = 'install'
$Pull      = $true
$AssumeYes = $false
$Extra     = @()

foreach ($a in @($args)) {
  if ($a -eq '--no-pull') {
    $Pull = $false
  } elseif ($a -eq '-y' -or $a -eq '--yes') {
    $AssumeYes = $true
  } elseif ($a -eq '-h' -or $a -eq '--help') {
    $Command = 'help'
  } elseif ($a -like '-*') {
    Die "Opcion desconocida: $a  (usa .\install.ps1 help)"
  } else {
    if ($Command -eq 'install' -and $Extra.Count -eq 0 -and $a -ne 'install') {
      $Command = $a
    } else {
      $Extra += $a
    }
  }
}
$Command = $Command.ToLower()

# --------------------------------------------------------------- docker CLI --
$script:DC = @()
try {
  $null = & docker compose version 2>$null
  if ($LASTEXITCODE -eq 0) { $script:DC = @('docker', 'compose') }
} catch { }
if ($script:DC.Count -eq 0) {
  if (Get-Command docker-compose -ErrorAction SilentlyContinue) { $script:DC = @('docker-compose') }
}

function Invoke-Native {
  param([string[]]$Cmd)
  $exe  = $Cmd[0]
  $rest = @()
  if ($Cmd.Count -gt 1) { $rest = @($Cmd[1..($Cmd.Count - 1)]) }
  & $exe @rest
}

# Ejecuta 'docker compose --env-file .env -f docker-compose.yml <args>'
function Invoke-Dc {
  param([string[]]$MoreArgs)
  $cmd = @($script:DC) + @('--env-file', $EnvFile, '-f', $ComposeFile) + $MoreArgs
  Invoke-Native $cmd
}

function Get-BackendId {
  if (-not $script:BackendId) {
    $id = @(Invoke-Dc @('ps', '-q', 'backend') 2>$null)
    if ($id.Count -eq 0 -or -not "$($id[0])".Trim()) {
      Die "No encuentro el contenedor 'backend'. Levanta el stack primero (.\install.ps1 up)."
    }
    $script:BackendId = "$($id[0])".Trim()
  }
  return $script:BackendId
}

function Copy-ToBackend {
  param([string]$LocalPath, [string]$RemotePath)
  Invoke-Native @('docker', 'cp', $LocalPath, "$(Get-BackendId):$RemotePath")
}

function Copy-FromBackend {
  param([string]$RemotePath, [string]$LocalPath)
  Invoke-Native @('docker', 'cp', "$(Get-BackendId):$RemotePath", $LocalPath)
}

function Invoke-Preflight {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Die "Docker no esta instalado. Instalalo desde https://docs.docker.com/engine/install/"
  }
  if ($script:DC.Count -eq 0) {
    Die "No se encontro 'docker compose' ni 'docker-compose'. Instala el plugin Compose v2."
  }
  $null = & docker info 2>&1
  if ($LASTEXITCODE -ne 0) {
    Die "El daemon de Docker no responde. Abre Docker Desktop y espera a 'Engine running'."
  }
  if (-not (Test-Path -LiteralPath $ScriptsDir)) { Die "Falta el directorio '$ScriptsDir'." }
}

# --------------------------------------------------------- lectura de .env --
# Se parsea el archivo a mano (no se ejecuta) para soportar valores con
# espacios, comas y acentos.
function Get-Env {
  param([string]$Key)
  if (-not (Test-Path -LiteralPath $EnvFile)) { return '' }
  $line = $null
  foreach ($l in [System.IO.File]::ReadAllLines($EnvFile)) {
    if ($l -match ('^\s*' + [regex]::Escape($Key) + '=')) { $line = $l }
  }
  if (-not $line) { return '' }
  $v = $line.Substring($line.IndexOf('=') + 1).Trim()
  if ($v.Length -ge 2) {
    if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) {
      $v = $v.Substring(1, $v.Length - 2)
    }
  }
  return $v
}

function Write-EnvFile {
  param([string[]]$Lines)
  $enc = New-Object System.Text.UTF8Encoding($false) # UTF-8 sin BOM
  # Se escribe con finales de linea LF (como el .env original) para que Docker
  # Compose no incluya un '\r' al final de cada valor.
  $text = ($Lines -join "`n") + "`n"
  [System.IO.File]::WriteAllText($EnvFile, $text, $enc)
}

function Set-Env {
  param([string]$Key, [string]$Value)
  $lines = @()
  if (Test-Path -LiteralPath $EnvFile) { $lines = @([System.IO.File]::ReadAllLines($EnvFile)) }
  $found = $false
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match ('^\s*' + [regex]::Escape($Key) + '=')) {
      $lines[$i] = "$Key=$Value"
      $found = $true
    }
  }
  if (-not $found) { $lines += "$Key=$Value" }
  Write-EnvFile $lines
}

function Set-EnvIfEmpty {
  param([string]$Key, [string]$Value)
  if (-not (Get-Env $Key)) { Set-Env $Key $Value }
}

function New-Secret {
  $bytes = New-Object byte[] 48
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  $s = [Convert]::ToBase64String($bytes) -replace '[^A-Za-z0-9]', ''
  return $s.Substring(0, [Math]::Min(20, $s.Length))
}

function Ensure-Env {
  if (-not (Test-Path -LiteralPath $EnvFile)) {
    if (-not (Test-Path -LiteralPath $EnvExample)) { Die "Falta $EnvExample" }
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Write-Ok 'Creado .env a partir de .env.example'
  }
  Set-EnvIfEmpty 'SITE_ADMIN_PASSWORD'   (New-Secret)
  Set-EnvIfEmpty 'DB_ROOT_PASSWORD'      (New-Secret)
  Set-EnvIfEmpty 'ERPNEXT_VERSION'       'v16.51.1'
  Set-EnvIfEmpty 'SITE_NAME'             'frontend'
  Set-EnvIfEmpty 'HTTP_PORT'             '8080'
  Set-EnvIfEmpty 'COUNTRY'               'Guatemala'
  Set-EnvIfEmpty 'CURRENCY'              'GTQ'
  Set-EnvIfEmpty 'FISCAL_YEARS'          (Get-Date -Format 'yyyy')
  Set-EnvIfEmpty 'ERP_PERPETUAL_INVENTORY' '0'
  Set-EnvIfEmpty 'ERP_MINIMAL_CHART'     '1'
}

function Get-EnvOr {
  param([string]$Key, [string]$Default = '')
  $v = Get-Env $Key
  if ([string]::IsNullOrEmpty($v)) { return $Default }
  return $v
}

function Load-Config {
  $script:SITE_NAME           = Get-EnvOr 'SITE_NAME' 'frontend'
  $script:HTTP_PORT           = Get-EnvOr 'HTTP_PORT' '8080'
  $script:ERPNEXT_VERSION     = Get-EnvOr 'ERPNEXT_VERSION' 'v16.51.1'
  $script:SITE_ADMIN_PASSWORD = Get-Env 'SITE_ADMIN_PASSWORD'
  $script:COMPANY_NAME        = Get-Env 'COMPANY_NAME'
  $script:COMPANY_ABBR        = Get-Env 'COMPANY_ABBR'
  $script:PERPETUAL_INVENTORY = Get-EnvOr 'ERP_PERPETUAL_INVENTORY' '0'
  $script:MINIMAL_CHART       = Get-EnvOr 'ERP_MINIMAL_CHART' '1'
  $script:COUNTRY             = Get-Env 'COUNTRY'
  $script:CURRENCY            = Get-Env 'CURRENCY'
  $script:FISCAL_YEAR_START_MONTH = Get-EnvOr 'FISCAL_YEAR_START_MONTH' '1'
  $script:FISCAL_YEARS        = Get-Env 'FISCAL_YEARS'
  $script:LD_FOLIO_INICIO     = Get-Env 'LD_FOLIO_INICIO'
}

# ----------------------------------------------------------- utilidades dc --
function Test-Port {
  param([string]$Port)
  if (-not (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) { return }
  $inUse = $false
  try {
    if (Get-NetTCPConnection -State Listen -LocalPort ([int]$Port) -ErrorAction SilentlyContinue) { $inUse = $true }
  } catch { } # en Windows antiguos el cmdlet puede no existir
  if (-not $inUse) {
    # Fallback por si Get-NetTCPConnection no esta disponible.
    $tcp = netstat -an | Select-String -Pattern (":$Port\s+.*LISTENING")
    if (-not $tcp) { return }
  }

  # Si el puerto lo ocupa nuestro propio stack, no es un problema.
  $proj = Get-EnvOr 'COMPOSE_PROJECT_NAME' 'erpnext'
  $names = @(Invoke-Native @('docker', 'ps', '--filter', "publish=$Port", '--format', '{{.Names}}') 2>$null)
  foreach ($n in $names) {
    if ("$n" -match ('^' + [regex]::Escape($proj) + '-')) { return }
  }

  Write-Warn "El puerto $Port ya esta en uso por otro programa. Cambia HTTP_PORT en .env si algo no funciona."
}

function Wait-ForCreateSite {
  Write-Log "Esperando a que el contenedor 'create-site' termine (puede tardar varios minutos)..."
  $cidOut = @(Invoke-Dc @('ps', '-a', '-q', 'create-site') 2>$null)
  $cid = if ($cidOut.Count -gt 0) { "$($cidOut[0])".Trim() } else { '' }
  if (-not $cid) {
    Write-Warn 'No se encontro el contenedor create-site; continuo.'
    return $true
  }
  for ($i = 0; $i -le 240; $i++) {
    $state = "$(Invoke-Native @('docker', 'inspect', '-f', '{{.State.Status}}:{{.State.ExitCode}}', $cid) 2>$null)".Trim()
    if (-not $state) { $state = 'unknown:1' }
    switch -Wildcard ($state) {
      'exited:0' { Write-Ok 'Sitio listo.'; return $true }
      'exited:*' {
        Write-Err "El contenedor create-site termino con error ($state)."
        Invoke-Dc @('logs', '--tail=80', 'create-site') 2>$null
        return $false
      }
      default {
        if ($i -ge 240) {
          Write-Err 'Timeout esperando la creacion del sitio (20 min).'
          Invoke-Dc @('logs', '--tail=80', 'create-site') 2>$null
          return $false
        }
        Start-Sleep -Seconds 5
      }
    }
  }
  return $false
}

function Test-SiteReady {
  $apps = Invoke-Dc @('exec', '-T', 'backend', 'bench', '--site', $script:SITE_NAME, 'list-apps') 2>$null
  return ("$apps" -match 'erpnext')
}

# Ejecuta un script Python dentro del contenedor, en el contexto del sitio.
# El script se copia al contenedor (evita problemas de codificacion de stdin en
# Windows) y se ejecuta con el interprete Python del virtualenv del contenedor.
function Invoke-InSite {
  param(
    [Parameter(Mandatory = $true)][string]$ScriptPath,
    [hashtable]$EnvVars = @{},
    [string]$Sentinel = $SENTINEL
  )
  $leaf   = Split-Path -Leaf $ScriptPath
  $remote = "/tmp/$leaf"

  Copy-ToBackend -LocalPath $ScriptPath -RemotePath $remote | Out-Null

  $exec = @('exec', '-T')
  foreach ($k in $EnvVars.Keys) { $exec += @('-e', "$k=$($EnvVars[$k])") }
  $exec += @('-w', '/home/frappe/frappe-bench', '-e', 'FRAPPE_STREAM_LOGGING=1', 'backend', 'bash', '-c')
  $exec += "if [ -x env/bin/python ]; then exec env/bin/python $remote '$($script:SITE_NAME)'; else exec python3 $remote '$($script:SITE_NAME)'; fi"

  $out = Invoke-Dc $exec 2>&1 | Out-String
  $rc  = $LASTEXITCODE

  Invoke-Dc @('exec', '-T', 'backend', 'rm', '-f', $remote) 2>$null | Out-Null

  if ($rc -eq 0 -and ($out -match [regex]::Escape($Sentinel))) {
    return $out
  }

  Write-Err "No se pudo ejecutar $ScriptPath dentro del contenedor."
  Write-Host '----- salida del contenedor -----' -ForegroundColor DarkGray
  Write-Host $out
  throw "Fallo al ejecutar $leaf dentro del contenedor."
}

# --------------------------------------------------------------- comandos ---
function Cmd-Install {
  Invoke-Preflight
  Ensure-Env
  Load-Config
  Test-Port $script:HTTP_PORT

  Write-Hr
  Write-Host " ERPNext $($script:ERPNEXT_VERSION) . Docker" -ForegroundColor White
  Write-Host " Sitio        : $($script:SITE_NAME)"
  Write-Host " URL          : http://localhost:$($script:HTTP_PORT)"
  Write-Host ' Usuario      : Administrator'
  Write-Host " Pais/moneda  : $($script:COUNTRY) . $($script:CURRENCY)"
  Write-Hr

  if ($Pull) {
    Write-Log 'Descargando imagenes (esto solo pasa la primera vez)...'
    Invoke-Dc @('pull', '--quiet') 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Warn 'No se pudieron precargar todas las imagenes; continuare.' }
  }

  Write-Log 'Levantando los servicios...'
  Invoke-Dc @('up', '-d')
  if ($LASTEXITCODE -ne 0) { Die 'No se pudieron levantar los servicios.' }

  if (-not (Wait-ForCreateSite)) { Die 'Fallo la creacion del sitio.' }

  Write-Log 'Verificando que el sitio responda...'
  $i = 0
  while (-not (Test-SiteReady)) {
    $i++
    if ($i -gt 60) { Die "El sitio no responde con la app 'erpnext'. Revisa: .\install.ps1 logs backend" }
    Start-Sleep -Seconds 5
  }
  Write-Ok 'Sitio operativo.'

  Write-Hr
  Write-Ok 'Instalacion terminada. El sitio quedo limpio (sin empresas ni datos de prueba).'
  Write-Host ''
  Write-Host ' Siguientes 2 pasos:' -ForegroundColor White
  Write-Host ''
  Write-Host ' 1) Crea tu empresa con el asistente web' -ForegroundColor White
  Write-Host "    Abre http://localhost:$($script:HTTP_PORT) y entra como Administrator"
  Write-Host "    Contrasena: $($script:SITE_ADMIN_PASSWORD)"
  Write-Host '    El asistente te pedira los datos de TU empresa. Usa:'
  Write-Host "      . Pais            : $($script:COUNTRY)"
  Write-Host "      . Moneda          : $($script:CURRENCY)"
  Write-Host '      . Plan de cuentas : Guatemala - Cuentas'
  Write-Host ''
  Write-Host ' 2) Prepara la contabilidad guatemalteca' -ForegroundColor White
  Write-Host '    Cuando termines el asistente, vuelve aqui y ejecuta:'
  Write-Host '      .\install.ps1 contabilidad' -ForegroundColor White
  Write-Host '    Crea los reportes y los libros (Libro Diario y Libro Mayor), corrige el'
  Write-Host '    catalogo de Guatemala y deja listos los ejercicios fiscales.'
  Write-Host ''
  Write-Host ' Para generar los estados en archivos: .\install.ps1 reports' -ForegroundColor DarkGray
  Write-Hr
}

function Cmd-Up {
  Invoke-Preflight; Ensure-Env; Load-Config
  Invoke-Dc @('up', '-d') | Out-Null
  Write-Ok 'Servicios levantados.'
}

function Cmd-Stop {
  Invoke-Preflight; Ensure-Env
  Invoke-Dc @('stop') | Out-Null
  Write-Ok 'Servicios detenidos (los datos se conservan).'
}

function Cmd-Restart {
  Invoke-Preflight; Ensure-Env
  Invoke-Dc @('restart') | Out-Null
  Write-Ok 'Servicios reiniciados.'
}

function Cmd-Status {
  Invoke-Preflight; Ensure-Env
  Invoke-Dc @('ps')
}

function Cmd-Logs {
  Invoke-Preflight; Ensure-Env
  $svc = if ($Extra.Count -ge 1) { $Extra[0] } else { 'backend' }
  Invoke-Dc @('logs', '-f', '--tail=200', $svc)
}

function Cmd-Shell {
  Invoke-Preflight; Ensure-Env
  $svc = if ($Extra.Count -ge 1) { $Extra[0] } else { 'backend' }
  Write-Log "Abriendo bash en el contenedor '$svc'..."
  Invoke-Dc @('exec', $svc, 'bash')
}

function Cmd-Console {
  Invoke-Preflight; Ensure-Env; Load-Config
  Write-Log "Consola de Frappe del sitio '$($script:SITE_NAME)'. Escribe exit() para salir."
  Invoke-Dc @('exec', 'backend', 'bench', '--site', $script:SITE_NAME, 'console')
}

function Cmd-Env {
  Ensure-Env; Load-Config
  Write-Hr
  "SITE_NAME        = {0}" -f $script:SITE_NAME           | Write-Host
  "HTTP_PORT        = {0}" -f $script:HTTP_PORT           | Write-Host
  "ERPNEXT_VERSION  = {0}" -f $script:ERPNEXT_VERSION     | Write-Host
  "COMPANY_NAME     = {0}" -f ($(if ($script:COMPANY_NAME) { $script:COMPANY_NAME } else { '(se detecta la empresa del sitio)' })) | Write-Host
  "COMPANY_ABBR     = {0}" -f ($(if ($script:COMPANY_ABBR) { $script:COMPANY_ABBR } else { '(no aplica)' })) | Write-Host
  "COUNTRY          = {0}" -f $script:COUNTRY              | Write-Host
  "CURRENCY         = {0}" -f $script:CURRENCY             | Write-Host
  "FISCAL_YEARS     = {0}" -f $script:FISCAL_YEARS        | Write-Host
  "INV. PERPETUO    = {0}" -f $script:PERPETUAL_INVENTORY  | Write-Host
  "PLAN MINIMO      = {0}" -f $script:MINIMAL_CHART        | Write-Host
  "ADMIN_PASSWORD   = {0}" -f $script:SITE_ADMIN_PASSWORD  | Write-Host
  Write-Hr
  Write-Host "Archivo: $EnvFile"
}

function Cmd-Contabilidad {
  Invoke-Preflight; Ensure-Env; Load-Config
  Write-Log 'Configurando la contabilidad guatemalteca (reportes, libros y catalogo)...'
  $env = @{
    ERP_SITE              = $script:SITE_NAME
    ERP_COMPANY           = $script:COMPANY_NAME
    ERP_ABBR              = $script:COMPANY_ABBR
    ERP_COUNTRY           = $script:COUNTRY
    ERP_CURRENCY          = $script:CURRENCY
    ERP_FY_START_MONTH    = $script:FISCAL_YEAR_START_MONTH
    ERP_FISCAL_YEARS      = $script:FISCAL_YEARS
    ERP_PERPETUAL_INVENTORY = $script:PERPETUAL_INVENTORY
    ERP_MINIMAL_CHART     = $script:MINIMAL_CHART
  }
  $out = Invoke-InSite -ScriptPath (Join-Path $ScriptsDir 'setup_accounting.py') -EnvVars $env
  Write-Host $out
  Write-Ok 'Contabilidad lista.'
  Write-Host '   Reportes en: Cuentas > Reportes (barra lateral), y en la tarjeta Financial Statements.' -ForegroundColor DarkGray
}

function Cmd-Reports {
  Invoke-Preflight; Ensure-Env; Load-Config
  $year = if ($Extra.Count -ge 1) { $Extra[0] } else { (Get-Date).Year }
  $outdir = Join-Path $ScriptDir 'salidas'
  New-Item -ItemType Directory -Force -Path $outdir | Out-Null

  Write-Log "Generando los estados financieros y los libros contables del ejercicio $year..."
  $env = @{
    EF_SITE         = $script:SITE_NAME
    EF_COMPANY      = $script:COMPANY_NAME
    EF_FISCAL_YEAR  = "$year"
    LD_FOLIO_INICIO = $(if ($script:LD_FOLIO_INICIO) { $script:LD_FOLIO_INICIO } else { '1' })
  }
  $out = Invoke-InSite -ScriptPath (Join-Path $ScriptsDir 'estados_financieros.py') `
    -EnvVars $env -Sentinel 'ERP_FINANCIAL_STATEMENTS_OK'
  $out | Out-File -FilePath (Join-Path $outdir "salida-$year.txt") -Encoding utf8
  Write-Host $out

  Write-Log 'Copiando archivos generados a .\salidas ...'
  Copy-FromBackend -RemotePath '/home/frappe/frappe-bench/sites/_estados_financieros/.' -LocalPath $outdir 2>$null
  if ($LASTEXITCODE -ne 0) { Write-Warn 'No se pudieron copiar los archivos (puede que no se generara ninguno).' }

  Write-Ok "Listo. Revisa: $outdir"
  Get-ChildItem -LiteralPath $outdir -Name
}

function Cmd-Backup {
  Invoke-Preflight; Ensure-Env; Load-Config
  $outdir = Join-Path $ScriptDir 'respaldos'
  New-Item -ItemType Directory -Force -Path $outdir | Out-Null
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

  Write-Log "Respaldando base de datos del sitio '$($script:SITE_NAME)'..."
  Invoke-Dc @('exec', '-T', 'backend', 'bench', '--site', $script:SITE_NAME, 'backup', '--with-files')

  Write-Log 'Copiando respaldos a .\respaldos ...'
  $tmp = Join-Path $outdir '.tmp'
  if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  Copy-FromBackend -RemotePath "/home/frappe/frappe-bench/sites/$($script:SITE_NAME)/private/backups/." -LocalPath $tmp 2>$null

  # nos quedamos con el juego mas reciente
  $sql = Get-ChildItem -LiteralPath $tmp -Filter '*.sql.gz' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($sql) {
    $stem = $sql.Name.Substring(0, $sql.Name.Length - '.sql.gz'.Length)
    Get-ChildItem -LiteralPath $tmp -Filter "$stem.*" | ForEach-Object {
      Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $outdir "$stamp-$($_.Name)") -Force
    }
  }
  Remove-Item -LiteralPath $tmp -Recurse -Force
  Write-Ok "Respaldo en: $outdir"
  Get-ChildItem -LiteralPath $outdir -Name | Select-Object -Last 5
}

function Cmd-Restore {
  Invoke-Preflight; Ensure-Env; Load-Config
  $file = if ($Extra.Count -ge 1) { $Extra[0] } else { '' }
  if (-not $file) { Die 'Uso: .\install.ps1 restore <ruta\al\respaldo.sql.gz>' }
  if (-not (Test-Path -LiteralPath $file)) { Die "No existe el archivo: $file" }

  Write-Warn "Esto SOBRESCRIBE la base de datos del sitio '$($script:SITE_NAME)'."
  if (-not $AssumeYes) {
    $ans = Read-Host 'Continuar? (escribe SI)'
    if ($ans -ne 'SI') { Die 'Cancelado.' }
  }

  $name = Split-Path -Leaf $file
  Copy-ToBackend -LocalPath $file -RemotePath "/tmp/$name" | Out-Null
  Write-Log "Restaurando $name ..."
  Invoke-Dc @('exec', '-T', 'backend', 'bench', '--site', $script:SITE_NAME, '--force', 'restore', "/tmp/$name")
  if ($LASTEXITCODE -ne 0) { Die 'Fallo la restauracion.' }
  Invoke-Dc @('exec', '-T', 'backend', 'bench', '--site', $script:SITE_NAME, 'migrate') | Out-Null
  Invoke-Dc @('exec', '-T', 'backend', 'bench', '--site', $script:SITE_NAME, 'clear-cache') | Out-Null
  Invoke-Dc @('restart', 'backend', 'queue-short', 'queue-long', 'scheduler', 'websocket') | Out-Null
  Write-Ok 'Restauracion completada.'
}

function Cmd-Update {
  Invoke-Preflight; Ensure-Env; Load-Config
  Write-Warn "Actualizar es un cambio de version de la imagen ($($script:ERPNEXT_VERSION)). Haz un respaldo antes."
  if (-not $AssumeYes) {
    $ans = Read-Host 'Continuar? (escribe SI)'
    if ($ans -ne 'SI') { Die 'Cancelado.' }
  }
  Invoke-Dc @('pull')
  Invoke-Dc @('up', '-d') | Out-Null
  Write-Log 'Ejecutando migraciones...'
  while (-not (Test-SiteReady)) { Start-Sleep -Seconds 5 }
  Invoke-Dc @('exec', '-T', 'backend', 'bench', '--site', $script:SITE_NAME, 'migrate')
  if ($LASTEXITCODE -ne 0) { Die 'Fallo la migracion.' }
  Invoke-Dc @('restart', 'backend', 'queue-short', 'queue-long', 'scheduler', 'websocket') | Out-Null
  Write-Ok 'Actualizacion terminada.'
}

function Cmd-Destroy {
  Invoke-Preflight; Ensure-Env
  Write-Warn 'Esto ELIMINA contenedores, volumenes y TODOS los datos de ERPNext.'
  if (-not $AssumeYes) {
    $ans = Read-Host 'Escribe BORRAR para confirmar'
    if ($ans -ne 'BORRAR') { Die 'Cancelado.' }
  }
  Invoke-Dc @('down', '-v', '--remove-orphans') | Out-Null
  Write-Ok 'Todo eliminado. Tu maquina queda limpia (solo quedan estos archivos de texto).'
}

function Cmd-Help {
  $help = @'
install.ps1 - ERPNext v16 sobre Docker para Windows (PowerShell)

Uso:  .\install.ps1              -> asistente web -> .\install.ps1 contabilidad

Comandos:
   install (por defecto)  Instala / reanuda la instalacion completa
   up / start             Levanta el stack
   stop                   Detiene los contenedores (conserva datos)
   restart                Reinicia el stack
   status                 Estado de los servicios
   logs [servicio]        Ver logs (por defecto: backend)
   shell [servicio]       Abrir una terminal dentro de un contenedor
   console                Consola de Python de Frappe (sitio activo)
   contabilidad           Configura la contabilidad guatemalteca
   reports [anio]         Genera los estados financieros y los libros contables
   backup                 Respalda base de datos + archivos
   restore <archivo>      Restaura un respaldo .sql.gz
   update                 Actualiza a la version indicada en .env
   destroy                ELIMINA contenedores + volumenes (borra todo)
   env                    Muestra la configuracion activa
   help                   Esta ayuda

Flags:
   --no-pull              No descargar imagenes
   --yes / -y             No preguntar nada
'@
  Write-Host $help
}

# ------------------------------------------------------------------ main ---
try {
  switch ($Command) {
    'install'                          { Cmd-Install }
    'up'                               { Cmd-Up }
    'start'                            { Cmd-Up }
    'stop'                             { Cmd-Stop }
    'restart'                          { Cmd-Restart }
    'status'                           { Cmd-Status }
    'ps'                               { Cmd-Status }
    'logs'                             { Cmd-Logs }
    'log'                              { Cmd-Logs }
    'shell'                            { Cmd-Shell }
    'bash'                             { Cmd-Shell }
    'console'                          { Cmd-Console }
    'env'                              { Cmd-Env }
    'config'                           { Cmd-Env }
    'contabilidad'                     { Cmd-Contabilidad }
    'accounting'                       { Cmd-Contabilidad }
    'contable'                         { Cmd-Contabilidad }
    'reports'                          { Cmd-Reports }
    'estados'                          { Cmd-Reports }
    'backup'                           { Cmd-Backup }
    'restore'                          { Cmd-Restore }
    'update'                           { Cmd-Update }
    'upgrade'                          { Cmd-Update }
    'destroy'                          { Cmd-Destroy }
    'uninstall'                        { Cmd-Destroy }
    'help'                             { Cmd-Help }
    default                            { Die "Comando desconocido: '$Command'. Usa .\install.ps1 help" }
  }
} catch {
  Write-Err "Fallo: $($_.Exception.Message)"
  Write-Host 'Revisa: .\install.ps1 logs' -ForegroundColor DarkGray
  exit 1
}
