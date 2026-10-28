# SAPI WAV of the spoken question, used as Chrome's fake microphone in record.ts
param([string]$Text = "why do cats eyes glow at night", [string]$Out = "audio/question.wav")
Add-Type -AssemblyName System.Speech
$root = Split-Path -Parent $PSScriptRoot
$f = Join-Path $root $Out
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice("Microsoft Zira Desktop"); $s.Rate = 0
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($f, $fmt); $s.Speak($Text); $s.SetOutputToNull(); $s.Dispose()
