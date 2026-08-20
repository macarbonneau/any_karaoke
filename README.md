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

## Extract songs (window)

```
uv run any-karaoke-gui
```

Pick an output folder, add one or more audio files, then press Start. Songs are processed one
after another and the whisperX model is loaded once for the whole queue, which is why batching is
faster than running the CLI per file.

| Control | What it does |
| --- | --- |
| Model | whisperX model. Drop to `medium` or `small` if `large-v3` will not fit in GPU memory |
| Format | `mp3` at 320kbps (default) or lossless `wav` |
| Skip songs already extracted | On by default. Uncheck it to re-extract and overwrite |
| Cancel | Stops after the current step, including part way through separation |
| Play selected | Opens the finished song in the karaoke player |
| Open folder | Reveals the finished song folder in the file manager |

The log pane shows demucs and whisperX output, so model downloads and warnings are visible rather
than hidden.

## Extract songs (command line)

```
uv run any-karaoke-extract "path/to/song.mp3" "path/to/karaoke_library"
```

Options: `--whisper-model` (default `large-v3`) and `--format` (`mp3` or `wav`).

Either way, this creates a folder named after the title tag containing:

| File | Contents |
| --- | --- |
| `music.mp3` | Backing track (vocals removed) |
| `vocals.mp3` | Isolated vocals |
| `any_karaoke_file.json` | Title, artist, album, duration and timed lyrics |
| `asr_result.json` | Raw whisperX transcription |
| `alignment_result.json` | Forced alignment output |
| `online_lyrics.txt` | Lyrics from api.lyrics.ovh, when found |
| `mp3_lyrics.txt` | Lyrics embedded in the ID3 tags, when present |

Stems are written as 320kbps mp3, which is about a fifth of the wav size (roughly 17MB per song
instead of 76MB). Use `--format wav` for lossless output. The player reads either, so libraries
extracted before the switch keep working.

Lyric lines come from the whisperX forced alignment, so each line also carries word level
timings under a `words` key.

## Play

```
uv run any-karaoke                       # then Ctrl+O to pick a folder
uv run any-karaoke "path/to/song folder" # or open one straight away
```

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Open a karaoke folder |
| `Ctrl+Q` | Quit |

Drag the two sliders to balance the backing track against the vocals. The sliders only appear
while the mouse is inside the window.

## Configuration

`src/any_karaoke/game_config.py` holds the colors, frame rate, model names and output format. The
model cache location can be overridden with `ANY_KARAOKE_MODELS` so an installed package does not
download into its own install folder.

If the lyrics run slightly ahead of or behind the audio on your machine, adjust
`LYRICS_TIME_OFFSET` in the same file. Positive values show the lyrics earlier. Note that mp3
encoding adds a constant delay of about 25ms. Both stems get the same delay so they stay in sync
with each other, and that offset absorbs the rest.

## Development

```
uv run pytest
uv run black src tests
uv run flake8 src tests
```
