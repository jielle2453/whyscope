# Synthesises one narration WAV per beat with Windows SAPI (System.Speech). Output: public/audio/narr-XX.wav
# Usage: powershell -File audio/make_narration.ps1 [-Voice "Microsoft Zira Desktop"] [-Rate -1]
param([string]$Voice = "Microsoft Zira Desktop", [int]$Rate = -1)
Add-Type -AssemblyName System.Speech
$root = Split-Path -Parent $PSScriptRoot
$scenes = Get-Content (Join-Path $root "scenes.json") -Raw | ConvertFrom-Json
$out = Join-Path $root "public/audio"
New-Item -ItemType Directory -Force $out | Out-Null
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $s.SelectVoice($Voice) } catch { Write-Host "voice $Voice not found, using default" }
$s.Rate = $Rate
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(44100, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($b in $scenes.beats) {
  $f = Join-Path $out ("narr-{0:D2}.wav" -f $b.id)
  $s.SetOutputToWaveFile($f, $fmt)
  $s.Speak($b.narration)
  $s.SetOutputToNull()
}
$s.Dispose()
Write-Host "narration written to $out"
