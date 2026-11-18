# Offline Windows SAPI TTS (System.Speech): one 16 kHz mono 16-bit wav per line of a TSV "key<TAB>voice<TAB>rate<TAB>text".
# Usage: powershell -ExecutionPolicy Bypass -File tts_sapi.ps1 <list.tsv> <out_dir>
param([string]$List, [string]$OutDir)
Add-Type -AssemblyName System.Speech
New-Item -ItemType Directory -Force $OutDir | Out-Null
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$n = 0
foreach ($line in [System.IO.File]::ReadAllLines($List, [System.Text.Encoding]::UTF8)) {
    $p = $line.Split("`t")
    if ($p.Length -lt 4) { continue }
    $wav = Join-Path $OutDir ($p[0] + ".wav")
    if (Test-Path $wav) { continue }
    $s.SelectVoice($p[1])
    $s.Rate = [int]$p[2]
    $s.SetOutputToWaveFile($wav, $fmt)
    $s.Speak($p[3])
    $n++
}
$s.SetOutputToNull()
Write-Output "synthesized $n"
