# Any Karaoke

Turn any mp3 file into a karaoke track. The extractor splits the song into a backing track
and a vocal track, transcribes the vocals with whisperX and writes word aligned lyrics. The
player then plays both tracks with independent volume sliders while scrolling the lyrics.

## Install

This project uses [uv](https://docs.astral.sh/uv/) and needs Python 3.10 or newer.

```
uv sync
```

That installs the player only. The extraction pipeline (torch, demucs, whisperX) is several
gigabytes and lives in an optional extra:

```
uv sync --extra extract
```

The `ffmpeg` CLI must be on your PATH. whisperX decodes audio by shelling out to it.

### CUDA

The default PyPI torch wheels are CPU only on Windows, so torch, torchaudio and torchvision are
pulled from the PyTorch cu128 index instead (see `[tool.uv.sources]` in `pyproject.toml`). CUDA
12.8 is the first version that supports Blackwell (sm_120) cards. To target a different CUDA
version, change the index URL and re-run `uv lock`.

Check that the GPU is picked up:

```
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

If it prints a `+cpu` version, transcription will still work but will be very slow.

The Python floor matters. Allowing 3.9 makes the resolver fall back to whisperX 3.3.1, which
declares `torch` and `torchaudio` with no version bounds and resolves to an incompatible pair
(the symptom is `OSError: [WinError 127]` when torchaudio loads).

## Extract a song

```
uv run any-karaoke-extract "path/to/song.mp3" "path/to/karaoke_library"
```

This creates a folder named after the mp3 title tag containing:

| File | Contents |
| --- | --- |
| `music.wav` | Backing track (vocals removed) |
| `vocals.wav` | Isolated vocals |
| `any_karaoke_file.json` | Title, artist, album, duration and timed lyrics |
| `asr_result.json` | Raw whisperX transcription |
| `alignment_result.json` | Forced alignment output |
| `online_lyrics.txt` | Lyrics from api.lyrics.ovh, when found |
| `mp3_lyrics.txt` | Lyrics embedded in the ID3 tags, when present |

Pick a smaller whisperX model with `--whisper-model` (for example `medium` or `small`) if
`large-v3` does not fit in your GPU memory.

Lyric lines come from the whisperX forced alignment, so each line also carries word level
timings under a `words` key.

## Play

```
uv run any-karaoke
```

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Open a karaoke folder |
| `Ctrl+Q` | Quit |

Drag the two sliders to balance the backing track against the vocals. The sliders only appear
while the mouse is inside the window.

## Configuration

`src/any_karaoke/game_config.py` holds the colors, frame rate and model names. Two paths can be
overridden with environment variables so an installed package does not write inside its own
install folder:

| Variable | Purpose |
| --- | --- |
| `ANY_KARAOKE_TEMP` | Scratch folder used by demucs |
| `ANY_KARAOKE_MODELS` | whisperX model download cache |

If the lyrics run slightly ahead of or behind the audio on your machine, adjust
`LYRICS_TIME_OFFSET` in the same file. Positive values show the lyrics earlier.

## Development

```
uv run pytest
uv run black src tests
uv run flake8 src tests
```
