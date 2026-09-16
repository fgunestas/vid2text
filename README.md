# Yerel Turkce Video Transkripsiyon

Windows + RTX 5060 icin: FFmpeg -> (faster-whisper icine gomulu Silero VAD) -> Faster-Whisper large-v3 (int8) -> birlesik `.txt`.

## Kurulum (bir kere)

1. Bu klasoru Windows makineye kopyala.
2. PowerShell'de klasore gir, calistir:
   ```
   .\setup.ps1
   ```
   Python 3.10+ zaten kurulu oldugu varsayilir. Venv olusturulur, `faster-whisper` ve `imageio-ffmpeg` (icinde hazir ffmpeg ile gelir, ayrica ffmpeg kurmana gerek yok) kurulur.

## Kullanim

```
.\run.ps1 -InputDir "D:\Videolar"
```

- Klasor ve alt klasorlerdeki tum videolari (mp4, mkv, avi, mov, wmv, webm, ts, ...) bulur.
- Her video icin: ses cikartir -> Turkce transkript eder -> `D:\Videolar\transcripts\<video-adi>.txt` olarak yazar.
- Cikti klasorunu degistirmek istersen: `-OutputDir "D:\Metinler"`.
- Ilk calistirmada `large-v3` modeli internetten indirilir (~3 GB, bir kereye mahsus, `~\.cache\huggingface` altinda saklanir).

## Durdur / devam et

- Istedigin an `Ctrl+C` ile durdurabilirsin.
- Tekrar `.\run.ps1 -InputDir "..."` calistirdiginda, her video icin **kaldigi saniyeden** devam eder; tamamlanmis videolari otomatik atlar. Hicbir sey bastan baslamaz.
- Ilerleme durumu `transcripts\_progress\` altinda video basina bir `.json` (durum) ve `.segments.jsonl` (o ana kadar cikan metin parcalari) olarak tutulur. Bu klasoru silme.

## GPU

- `setup.ps1` sonunda `nvidia-smi` ciktisini gosterir; RTX 5060 gorunmuyorsa NVIDIA suruculerini guncelle (https://www.nvidia.com/drivers).
- Script once CUDA (int8_float16) ile denemeye calisir; basarisiz olursa otomatik olarak CPU'ya duser ve bunu ekranda acikca belirtir (CPU'da large-v3 cok yavastir; bu durumda surucu guncellemesi gerekir).
- Elle CPU'ya zorlamak icin: `-Device cpu`.

## Notlar

- VAD adimi ayri bir arac olarak degil, faster-whisper'in `vad_filter=True` secenegiyle (Silero VAD, ONNX, modelin kendi paketinde gelir) calisir; sessiz/gurultulu bolgeleri atlayarak halusinasyonu onler.
- Cikti sadece duz `.txt` (konusmaci ayrimi yok), talebe gore ayarlandi.
- Tamamlanan videolarin ara ses (WAV) dosyalari diskten yer kaplamasin diye otomatik silinir.
