# Windows.Media.Ocr helper — OCRs an image, prints JSON: [{text,x,y,w,h}, ...]
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ocr_win.ps1 <imagepath>
param([Parameter(Mandatory=$true)][string]$ImagePath)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
  function Await($op, $t){ $task=$asTaskGeneric.MakeGenericMethod($t).Invoke($null,@($op)); $task.Wait(); $task.Result }
  [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
  [Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
  [Windows.Storage.StorageFile,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
  $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path $ImagePath).Path)) ([Windows.Storage.StorageFile])
  $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
  if ($null -eq $engine) { Write-Output '[]'; exit 0 }
  $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  $out = New-Object System.Collections.ArrayList
  foreach($line in $result.Lines){
    foreach($word in $line.Words){
      $r = $word.BoundingRect
      [void]$out.Add([pscustomobject]@{ text=$word.Text; x=[math]::Round($r.X,1); y=[math]::Round($r.Y,1); w=[math]::Round($r.Width,1); h=[math]::Round($r.Height,1) })
    }
  }
  $out | ConvertTo-Json -Compress
} catch {
  Write-Output ('{"error":"' + ($_.Exception.Message -replace '"','''') + '"}')
}
