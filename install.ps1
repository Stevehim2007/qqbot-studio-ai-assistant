#requires -Version 5.1
<#
QQ Bot Studio AI Assistant B - Windows installer (PowerShell 5.1+).
Creates a private local config and launcher, and optionally a current-user logon
scheduled task. API keys are never embedded in the launcher/task/command output.
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [string]$InstanceId = "",
    [switch]$ConfigureKey,
    [switch]$InstallService,
    [switch]$Uninstall,
    [switch]$Purge
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$TaskName = "QQBotStudioAIAssistant"

function Stop-WithMessage {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Error $Message
    exit 1
}

function Test-SamePath {
    param([string]$Left, [string]$Right)
    $a = [System.IO.Path]::GetFullPath($Left).TrimEnd([char[]]@('\', '/'))
    $b = [System.IO.Path]::GetFullPath($Right).TrimEnd([char[]]@('\', '/'))
    return [string]::Equals($a, $b, [System.StringComparison]::OrdinalIgnoreCase)
}

function Protect-PrivatePath {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    if (-not (Test-Path -LiteralPath $LiteralPath)) { return }
    try {
        $acl = Get-Acl -LiteralPath $LiteralPath
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($oldRule in @($acl.Access)) {
            [void]$acl.RemoveAccessRule($oldRule)
        }
        $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $rule = New-Object -TypeName System.Security.AccessControl.FileSystemAccessRule -ArgumentList @(
            $identity,
            [System.Security.AccessControl.FileSystemRights]::FullControl,
            [System.Security.AccessControl.AccessControlType]::Allow
        )
        $acl.SetAccessRule($rule)
        Set-Acl -LiteralPath $LiteralPath -AclObject $acl
    }
    catch {
        throw "无法为 '$LiteralPath' 设置仅当前用户访问的 NTFS ACL：$($_.Exception.Message)"
    }
}

function Quote-TaskArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Invoke-PythonChecked {
    param([Parameter(Mandatory = $true)][string[]]$ExtraArgs)
    $allArgs = @()
    $allArgs += $PythonPrefix
    $allArgs += $ExtraArgs
    & $PythonExe @allArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Python 命令执行失败（退出码 $LASTEXITCODE）"
    }
}

function Test-ScheduledTaskExists {
    if (-not (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue)) { return $false }
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    return ($null -ne $task)
}

function Remove-ScheduledTaskIfPresent {
    if (Test-ScheduledTaskExists) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        if (Test-ScheduledTaskExists) {
            Write-Warning "无法删除计划任务 $TaskName，请使用任务计划程序手动检查。"
        }
    }
}

$ScriptDir = $PSScriptRoot
$ScriptPath = Join-Path $ScriptDir "assistant.py"
if (-not (Test-Path -LiteralPath $ScriptPath)) {
    Stop-WithMessage "找不到 assistant.py：$ScriptPath"
}
$StudioHome = if ($env:QQBOT_STUDIO_HOME) { $env:QQBOT_STUDIO_HOME } else { Join-Path $HOME ".local\share\qqbot-studio" }
$DataDir = if ($env:QQBOT_AI_ASSISTANT_HOME) { $env:QQBOT_AI_ASSISTANT_HOME } else { Join-Path $StudioHome "ai-assistant" }
$ConfigPath = if ($env:QQBOT_AI_ASSISTANT_CONFIG) { $env:QQBOT_AI_ASSISTANT_CONFIG } else { Join-Path $DataDir "config.json" }
$BinDir = Join-Path $HOME ".local\bin"
$LauncherPath = Join-Path $BinDir "qqbot-ai-assistant.cmd"

if ($Purge -and -not $Uninstall) { Stop-WithMessage "-Purge 只能与 -Uninstall 一起使用" }
if ($ConfigureKey -and $InstanceId) { Stop-WithMessage "-ConfigureKey 与 -InstanceId 不能同时使用" }

if ($Uninstall) {
    Remove-ScheduledTaskIfPresent
    if (Test-Path -LiteralPath $LauncherPath) {
        Remove-Item -LiteralPath $LauncherPath -Force
    }
    Write-Host "已移除 Windows 登录启动任务（若存在）和启动器：$LauncherPath"
    if ($Purge) {
        $dataFull = [System.IO.Path]::GetFullPath($DataDir)
        $dataTrim = $dataFull.TrimEnd([char[]]@('\', '/'))
        $rootFull = [System.IO.Path]::GetPathRoot($dataFull)
        $homeFull = [System.IO.Path]::GetFullPath($HOME)
        $studioFull = [System.IO.Path]::GetFullPath($StudioHome)
        $scriptFull = [System.IO.Path]::GetFullPath($ScriptDir)
        $unsafe = [string]::IsNullOrWhiteSpace($dataTrim) -or
            (Test-SamePath $dataFull $rootFull) -or
            (Test-SamePath $dataFull $homeFull) -or
            (Test-SamePath $dataFull $studioFull) -or
            (Test-SamePath $dataFull $scriptFull) -or
            $scriptFull.StartsWith($dataTrim + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
        if ($unsafe) { Stop-WithMessage "拒绝删除不安全的数据目录：$DataDir" }
        if (Test-Path -LiteralPath $DataDir) {
            Remove-Item -LiteralPath $DataDir -Recurse -Force
            Write-Host "已删除 B 数据目录：$DataDir"
        }
        if (-not (Test-SamePath $ConfigPath (Join-Path $DataDir "config.json"))) {
            if (Test-Path -LiteralPath $ConfigPath) {
                Write-Host "注意：自定义配置文件未自动删除：$ConfigPath"
            }
        }
    }
    else {
        Write-Host "配置未删除。彻底删除：.\install.ps1 -Uninstall -Purge"
    }
    Write-Host "仓库代码未删除，如不再需要请手动删除：$ScriptDir"
    exit 0
}

# Locate Python 3.10+, preferring python.exe and falling back to the py launcher.
$PythonExe = $null
$PythonPrefix = @()
$pythonCmd = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($pythonCmd) {
    & $pythonCmd.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
    if ($LASTEXITCODE -eq 0) { $PythonExe = $pythonCmd.Source }
}
if (-not $PythonExe) {
    $pyCmd = Get-Command py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pyCmd) {
        & $pyCmd.Source -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
        if ($LASTEXITCODE -eq 0) {
            $PythonExe = $pyCmd.Source
            $PythonPrefix = @("-3")
        }
    }
}
if (-not $PythonExe) { Stop-WithMessage "未找到 Python 3.10+；请安装并确保 python 或 py 在 PATH 中。" }

New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
$initArgs = @(
    $ScriptPath,
    "--config", $ConfigPath,
    "--studio-home", $StudioHome,
    "--init-config",
    "--port", [string]$Port
)
if ($InstanceId) { $initArgs += @("--instance-id", $InstanceId) }
Invoke-PythonChecked -ExtraArgs $initArgs

Protect-PrivatePath -LiteralPath $DataDir
Protect-PrivatePath -LiteralPath $ConfigPath

$pythonInvocation = '"{0}"' -f $PythonExe
if ($PythonPrefix.Count -gt 0) { $pythonInvocation += " " + ($PythonPrefix -join " ") }
$launcherLines = @(
    "@echo off",
    "setlocal",
    "$pythonInvocation `"$ScriptPath`" --config `"$ConfigPath`" --studio-home `"$StudioHome`" %*",
    "exit /b %ERRORLEVEL%"
)
$utf8NoBom = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
[System.IO.File]::WriteAllLines($LauncherPath, [string[]]$launcherLines, $utf8NoBom)

if ($ConfigureKey) {
    Invoke-PythonChecked -ExtraArgs @($ScriptPath, "--config", $ConfigPath, "--studio-home", $StudioHome, "--set-key")
}

if ($InstallService) {
    foreach ($cmdlet in @("New-ScheduledTaskAction", "New-ScheduledTaskTrigger", "New-ScheduledTaskPrincipal", "Register-ScheduledTask", "Start-ScheduledTask")) {
        if (-not (Get-Command $cmdlet -ErrorAction SilentlyContinue)) {
            Stop-WithMessage "当前系统缺少计划任务命令 $cmdlet；配置和启动器已安装，可手动运行 $LauncherPath"
        }
    }
    $taskExe = $PythonExe
    $pythonBase = [System.IO.Path]::GetFileNameWithoutExtension($PythonExe)
    $pythonwName = if ($pythonBase -ieq "py") { "pyw.exe" } else { "pythonw.exe" }
    $pythonwPath = Join-Path ([System.IO.Path]::GetDirectoryName($PythonExe)) $pythonwName
    if (Test-Path -LiteralPath $pythonwPath) { $taskExe = $pythonwPath }
    $taskArguments = @()
    foreach ($prefixPart in $PythonPrefix) { $taskArguments += (Quote-TaskArgument $prefixPart) }
    foreach ($part in @($ScriptPath, "--config", $ConfigPath, "--studio-home", $StudioHome)) {
        $taskArguments += (Quote-TaskArgument $part)
    }
    $action = New-ScheduledTaskAction -Execute $taskExe -Argument ($taskArguments -join " ")
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Description "QQ Bot Studio optional AI Assistant B" -Force | Out-Null
    try {
        Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        Write-Host "Windows 登录启动任务已创建并触发：$TaskName"
    }
    catch {
        Write-Warning "计划任务已创建，但首次启动失败；请检查端口或手动运行 $LauncherPath"
    }
}

Write-Host ""
Write-Host "AI 助手 B 安装完成。"
Write-Host "  启动命令：$LauncherPath"
Write-Host "  访问地址：http://127.0.0.1:$Port/"
Write-Host "  配置文件：$ConfigPath（已设置当前用户 NTFS ACL；API Key 为本地明文存储）"
Write-Host "  固定模型：deepseek-flash"
if ($InstanceId) {
    Write-Host "  Key 来源：显式复用实例 $InstanceId 的 AstrBot 配置（运行时只读）"
}
elseif (-not $ConfigureKey) {
    Write-Host "  下一步：编辑 config.json 的 api_key，或运行："
    Write-Host "  python `"$ScriptPath`" --config `"$ConfigPath`" --set-key"
}
if (-not $InstallService) { Write-Host "  可选 Windows 登录任务：.\install.ps1 -InstallService" }
Write-Host "  卸载：.\install.ps1 -Uninstall   彻底删除配置：.\install.ps1 -Uninstall -Purge"
