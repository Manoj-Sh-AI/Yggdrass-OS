param([string]$WebViewVersion = '1.0.4314.35')
$ErrorActionPreference = 'Stop'
$desktopRoot = $PSScriptRoot
$packageRoot = Join-Path $desktopRoot '.packages'
$package = Join-Path $packageRoot "webview2-$WebViewVersion"
$output = Join-Path $desktopRoot 'dist'
New-Item -ItemType Directory -Force -Path $packageRoot, $output | Out-Null
if (!(Test-Path -LiteralPath $package)) {
    $archive = Join-Path $packageRoot "webview2-$WebViewVersion.zip"
    Invoke-WebRequest "https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/$WebViewVersion/microsoft.web.webview2.$WebViewVersion.nupkg" -OutFile $archive
    Expand-Archive -LiteralPath $archive -DestinationPath $package
}
$core = Join-Path $package 'lib/net462/Microsoft.Web.WebView2.Core.dll'
$forms = Join-Path $package 'lib/net462/Microsoft.Web.WebView2.WinForms.dll'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
& node (Join-Path $desktopRoot 'icon.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Desktop icon generation failed.' }
& $compiler /nologo /target:winexe /platform:x64 /optimize+ "/out:$output/Yggdras.exe" "/win32icon:$output/Yggdras.ico" "/win32manifest:$desktopRoot/app.manifest" /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Web.Extensions.dll "/reference:$core" "/reference:$forms" (Join-Path $desktopRoot 'Program.cs')
if ($LASTEXITCODE -ne 0) { throw 'Desktop compilation failed.' }
Copy-Item -LiteralPath $core, $forms -Destination $output -Force
Copy-Item -LiteralPath (Join-Path $package 'runtimes/win-x64/native/WebView2Loader.dll') -Destination $output -Force
Copy-Item -LiteralPath (Join-Path $package 'LICENSE.txt') -Destination (Join-Path $output 'WebView2-LICENSE.txt') -Force
Get-FileHash -LiteralPath (Join-Path $output 'Yggdras.exe') -Algorithm SHA256 | Select-Object Algorithm, Hash
