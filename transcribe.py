"""
Yerel Turkce transkripsiyon pipeline'i.

Adimlar:
  1) FFmpeg  -> videodan 16kHz mono WAV cikartir (bir kere, sonra cache'lenir)
  2) Silero VAD -> faster-whisper'in icine gomulu vad_filter=True olarak calisir,
     sessizlik/gurultu bolgelerini atlar (halusinasyonu onler)
  3) Faster-Whisper (large-v3, int8) -> WAV'i transkript eder
  4) Merge -> segmentler .txt olarak birlestirilir

Kaldigi yerden devam etme (resume):
  Her video icin segmentler _progress/<video>.segments.jsonl dosyasina
  segment segment (satir satir) ANINDA yazilir ve flush edilir. Script
  kapatilirsa / kesilirse, bir sonraki calistirmada bu dosyanin son satirindan
  itibaren (clip_timestamps ile) transkripsiyon KALDIGI SANIYEDEN devam eder,
  baştan baslamaz.
"""

import argparse
import json
import sys
import time
import wave
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

VIDEO_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
    ".m4v", ".webm", ".ts", ".mts", ".m2ts",
}


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def fmt_time(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def find_videos(input_dir: Path) -> list[Path]:
    files = [
        p for p in sorted(input_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    ]
    return files


def safe_stem(video_path: Path, input_dir: Path) -> str:
    rel = video_path.relative_to(input_dir).with_suffix("")
    return str(rel).replace("\\", "__").replace("/", "__")


class VideoState:
    def __init__(self, progress_dir: Path, key: str):
        self.state_path = progress_dir / f"{key}.json"
        self.segments_path = progress_dir / f"{key}.segments.jsonl"
        self.data = self._load()

    def _load(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "status": "pending",
            "audio_path": None,
            "duration_sec": None,
            "updated_at": None,
            "error": None,
        }

    def save(self) -> None:
        self.data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)

    def last_end_sec(self) -> float:
        if not self.segments_path.exists():
            return 0.0
        last = None
        with self.segments_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = line
        if not last:
            return 0.0
        try:
            return float(json.loads(last)["end"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return 0.0

    def append_segment(self, start: float, end: float, text: str) -> None:
        with self.segments_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"start": start, "end": end, "text": text}, ensure_ascii=False) + "\n")
            f.flush()

    def build_txt(self, out_path: Path) -> None:
        parts = []
        if self.segments_path.exists():
            with self.segments_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts.append(json.loads(line)["text"].strip())
        text = " ".join(p for p in parts if p)
        out_path.write_text(text, encoding="utf-8")


def get_ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
        if exe:
            return exe
        raise RuntimeError(
            "ffmpeg bulunamadi. 'pip install imageio-ffmpeg' calistigindan emin ol "
            "ya da ffmpeg'i sistem PATH'ine ekle."
        )


def extract_audio(ffmpeg_exe: str, video_path: Path, wav_path: Path) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-acodec", "pcm_s16le",
        str(wav_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not wav_path.exists():
        raise RuntimeError(f"ffmpeg ses cikartma hatasi:\n{proc.stderr[-2000:]}")


def wav_duration_sec(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def load_model(model_name: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    attempts = []
    if device == "cuda":
        attempts.append(("cuda", compute_type))
        attempts.append(("cuda", "int8"))
    attempts.append(("cpu", "int8"))

    last_err = None
    tried = set()
    for dev, ctype in attempts:
        if (dev, ctype) in tried:
            continue
        tried.add((dev, ctype))
        try:
            log(f"Model yukleniyor: {model_name} (device={dev}, compute_type={ctype})")
            model = WhisperModel(model_name, device=dev, compute_type=ctype)
            if dev == "cpu" and device == "cuda":
                log("UYARI: CUDA baslatilamadi, CPU'ya dusuldu. Transkripsiyon COK daha "
                    "yavas olacak. NVIDIA surucusunu guncelleyip tekrar dene "
                    "(RTX 5060 icin en guncel Game Ready / Studio surucusu gerekir).")
            return model, dev, ctype
        except Exception as e:  # noqa: BLE001
            last_err = e
            log(f"  -> basarisiz ({dev}/{ctype}): {e}")
    raise RuntimeError(f"Model hicbir konfigurasyonla yuklenemedi: {last_err}")


def process_video(
    video_path: Path,
    input_dir: Path,
    output_dir: Path,
    audio_dir: Path,
    progress_dir: Path,
    model,
    language: str,
    keep_wav: bool,
) -> None:
    key = safe_stem(video_path, input_dir)
    state = VideoState(progress_dir, key)
    out_txt = output_dir / f"{key}.txt"

    if state.data["status"] == "done" and out_txt.exists():
        log(f"[ATLA] zaten tamamlanmis: {video_path.name}")
        return

    log(f"[BASLA] {video_path.name}")

    wav_path = audio_dir / f"{key}.wav"
    if state.data.get("audio_path") and Path(state.data["audio_path"]).exists():
        wav_path = Path(state.data["audio_path"])
    elif not wav_path.exists():
        log(f"  ses cikartiliyor (ffmpeg) -> {wav_path.name}")
        ffmpeg_exe = get_ffmpeg_exe()
        extract_audio(ffmpeg_exe, video_path, wav_path)

    duration = state.data.get("duration_sec")
    if not duration:
        duration = wav_duration_sec(wav_path)
    state.data.update({
        "status": "transcribing",
        "audio_path": str(wav_path),
        "duration_sec": duration,
    })
    state.save()

    last_end = state.last_end_sec()
    if duration and last_end >= duration - 0.5:
        log("  segmentler zaten tamam, birlestiriliyor...")
    else:
        if last_end > 0:
            log(f"  onceki calistirmadan devam: {fmt_time(last_end)} / {fmt_time(duration)}")
            clip_timestamps = f"{last_end},{duration}"
        else:
            clip_timestamps = None

        segments, info = model.transcribe(
            str(wav_path),
            language=language,
            task="transcribe",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            beam_size=5,
            condition_on_previous_text=True,
            clip_timestamps=clip_timestamps,
        )

        t0 = time.time()
        n_seg = 0
        try:
            for seg in segments:
                state.append_segment(seg.start, seg.end, seg.text)
                n_seg += 1
                pct = (seg.end / duration * 100) if duration else 0.0
                elapsed = time.time() - t0
                sys.stdout.write(
                    f"\r  {fmt_time(seg.end)}/{fmt_time(duration)} "
                    f"(%{pct:5.1f})  gecen sure: {fmt_time(elapsed)}   "
                )
                sys.stdout.flush()
                if n_seg % 20 == 0:
                    state.data["status"] = "transcribing"
                    state.save()
        except KeyboardInterrupt:
            sys.stdout.write("\n")
            state.save()
            log(f"  [DURDURULDU] {video_path.name} -> ilerleme kaydedildi, "
                f"bir sonraki calistirmada {fmt_time(state.last_end_sec())} noktasindan devam edecek.")
            raise
        sys.stdout.write("\n")

    state.build_txt(out_txt)
    state.data["status"] = "done"
    state.save()

    if keep_wav is False:
        try:
            wav_path.unlink(missing_ok=True)
            state.data["audio_path"] = None
            state.save()
        except OSError:
            pass

    log(f"[TAMAM] {video_path.name} -> {out_txt}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Yerel Turkce video transkripsiyon pipeline'i")
    ap.add_argument("--input-dir", required=True, help="Videolarin oldugu klasor (alt klasorler dahil taranir)")
    ap.add_argument("--output-dir", default=None, help="TXT ciktilarinin yazilacagi klasor (varsayilan: <input-dir>/transcripts)")
    ap.add_argument("--model", default="large-v3", help="Whisper model adi (varsayilan: large-v3)")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="cuda veya cpu")
    ap.add_argument("--compute-type", default="int8_float16", help="ctranslate2 compute_type (varsayilan: int8_float16)")
    ap.add_argument("--language", default="tr", help="Dil kodu (varsayilan: tr)")
    ap.add_argument("--keep-wav", action="store_true", help="Ara WAV dosyalarini silme")
    args = ap.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.is_dir():
        log(f"HATA: giris klasoru bulunamadi: {input_dir}")
        sys.exit(1)

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else input_dir / "transcripts"
    progress_dir = output_dir / "_progress"
    audio_dir = output_dir / "_audio"
    for d in (output_dir, progress_dir, audio_dir):
        d.mkdir(parents=True, exist_ok=True)

    videos = find_videos(input_dir)
    if not videos:
        log(f"'{input_dir}' altinda desteklenen video bulunamadi ({', '.join(sorted(VIDEO_EXTS))}).")
        sys.exit(0)

    log(f"{len(videos)} video bulundu.")
    for v in videos:
        log(f"  - {v.relative_to(input_dir)}")

    model, dev, ctype = load_model(args.model, args.device, args.compute_type)
    log(f"Model hazir (device={dev}, compute_type={ctype}).")

    try:
        for video_path in videos:
            try:
                process_video(
                    video_path=video_path,
                    input_dir=input_dir,
                    output_dir=output_dir,
                    audio_dir=audio_dir,
                    progress_dir=progress_dir,
                    model=model,
                    language=args.language,
                    keep_wav=args.keep_wav,
                )
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"[HATA] {video_path.name}: {e}")
                key = safe_stem(video_path, input_dir)
                state = VideoState(progress_dir, key)
                state.data["status"] = "error"
                state.data["error"] = str(e)
                state.save()
                continue
    except KeyboardInterrupt:
        log("Kullanici tarafindan durduruldu. Tekrar calistirinca kaldigi yerden devam edecek.")
        sys.exit(0)

    log("Tum videolar tamamlandi.")


if __name__ == "__main__":
    main()
