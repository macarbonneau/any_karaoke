<p align="center">
  <img src="media/any_karaoke_logo.png" alt="Any Karaoke" width="200">
</p>

<h1 align="center">Any Karaoke</h1>

Turn any mp3 file into a karaoke track. The extractor splits the song into a backing track
and a vocal track, transcribes the vocals with whisperX and writes word aligned lyrics. The
player then plays both tracks with independent volume sliders while scrolling the lyrics.

## Quick start

| I want to | Run |
| --- | --- |
| Start the manager (add songs to the library) | `uv run any-karaoke-manager` |
| Extract one song without a window | `uv run any-karaoke-extract "song.mp3" "karaoke_library"` |
| Start the player | `uv run any-karaoke` |
| Play one song straight away | `uv run any-karaoke "karaoke_library/Song Title.ak"` |

First time only: `uv sync --extra extract` to install the extraction pipeline, and make sure the
`ffmpeg` CLI is on your PATH.

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

Torch comes from the PyTorch cu128 index rather than PyPI, because the default PyPI wheels are
CPU only on Windows. See [Troubleshooting](#troubleshooting) if the GPU is not picked up.

## The manager

```
uv run any-karaoke-manager
```

Pick an output folder, add one or more audio files, then press Start. Songs are processed one
after another and the whisperX model is loaded once for the whole queue, which is why batching is
faster than running the command line version per file.

| Control | What it does |
| --- | --- |
| Model | whisperX model. Drop to `medium` or `small` if `large-v3` will not fit in GPU memory |
| Format | `mp3` at 320kbps (default) or lossless `wav` |
| Skip songs already extracted | On by default. Uncheck it to re-extract and overwrite |
| Paste lyrics | Type or paste the lyrics for the selected song, used instead of the internet lookup. The Lyrics column reads `custom` once attached |
| Cancel | Stops after the current step, including part way through separation |
| Play selected | Opens the finished song in the karaoke player |
| Open folder | Reveals the finished .ak file in the file manager |

The log pane shows demucs and whisperX output, so model downloads and warnings are visible rather
than hidden.

The two windows can open each other. Play selected starts the player on a finished song, and the
player's File menu has Manage library (`Ctrl+M`) to come back here. Each runs as its own process,
so extracting the next song carries on while you sing.

Expect roughly half a minute per song on a warm GPU. The first run is much slower because the
whisperX and alignment models have to download.

## Extract from the command line

```
uv run any-karaoke-extract "path/to/song.mp3" "path/to/karaoke_library"
```

Options: `--whisper-model` (default `large-v3`) and `--format` (`mp3` or `wav`).

## What extraction produces

Either route creates a single `.ak` file named after the title tag, for example
`$10 Cowboy.ak`. One file holds the whole song, so it is easy to move around and share.

A `.ak` is a zip archive. Rename it to `.zip` and any archive tool opens it:

| Entry | Contents |
| --- | --- |
| `music.mp3` | Backing track (vocals removed) |
| `vocals.mp3` | Isolated vocals |
| `any_karaoke_file.json` | Title, artist, album, duration and timed lyrics |
| `lyrics_alignment.json` | Reference lyrics, timed (see below) |
| `asr_result.json` | Raw whisperX transcription |
| `alignment_result.json` | Forced alignment output |
| `online_lyrics.txt` | Lyrics from api.lyrics.ovh, when found |
| `pasted_lyrics.txt` | Lyrics you typed in, when you used Paste lyrics |
| `mp3_lyrics.txt` | Lyrics embedded in the ID3 tags, when present |

The audio is stored uncompressed (mp3 gains nothing from deflating) and the text entries are
compressed, so a song is about 17MB in total.

Stems are 320kbps mp3, roughly a fifth of the wav size. Use `--format wav` for lossless output.

Lyric lines come from the whisperX forced alignment, so each line also carries word level
timings under a `words` key.

### Reference lyrics

The lyrics that get sung and the lyrics the ASR heard are not the same thing. On the sample track
whisperX produced "Maybe that's a fact" where the real line is "Baby that's a fact", and "small
feet" for "small fee".

So the accurate words are kept separately in `lyrics_alignment.json`, and given timings taken from
the aligner: the right words on the aligner's clock.

```json
{
  "source": "online",
  "line_count": 42,
  "timing": {"matched": 184, "approximate": 18, "interpolated": 0, "unmatched": 0, "coverage": 1.0},
  "lines": [
    {"index": 0, "verse": 0, "text": "I'm a ten-dollar cowboy", "start": 19.74, "end": 21.74,
     "words": [{"word": "I'm", "start": 19.74, "end": 19.9, "timing": "matched"}]}
  ]
}
```

Blank lines in the source become verse numbers rather than being thrown away, since that grouping
helps the matching. `source` records where the words came from, in priority order: `pasted` if you
typed them in, otherwise `online` from api.lyrics.ovh, otherwise `id3` from the mp3 tags. When no
lyrics are found at all the file is not written.

### How the timings are worked out

`any_karaoke.lyrics_matcher.fill_lyrics_timings(scaffold, align_result)` does the matching. The two
word sequences run in the same order but disagree in places, so `difflib` finds the runs that agree
and those anchor the timeline. Each word records how its time was arrived at:

| `timing` | Meaning |
| --- | --- |
| `matched` | The same word appears in the aligner output, so the time is taken directly |
| `approximate` | A misheard word in the same position, for example "Baby" against "Maybe" |
| `interpolated` | The aligner has nothing here, so the gap between anchors is shared out by word length |

Comparison ignores case and punctuation, and splits on hyphens, so a written "ten-dollar" lines up
with a spoken "ten" and "dollar" and spans both. The result is forced to run forwards, so one bad
match cannot send the timeline backwards. `coverage` is the fraction of words that ended up with a
time; on the sample track it is 1.0, from 184 exact matches and 18 approximate.

The function is pure and does not touch the audio, so it can be re-run over an existing
`lyrics_alignment.json` and `alignment_result.json` from a `.ak` if you want to change how matching
works.

This file is what the player displays, so improving the matching improves what you sing along to.

Songs extracted before the `.ak` format were plain folders with these same files in them. The
player still opens those, through File then Open song folder (legacy).

## Play

```
uv run any-karaoke                     # then Ctrl+O to pick a song
uv run any-karaoke "path/to/Song.ak"   # or open one straight away
```

The player sings from `lyrics_alignment.json` when the song has it: the correct words rather than
what the ASR heard, in short singable lines rather than the aligner's long segments. Within the
line being sung, words fill in as they go past: white for the word on the beat, warm yellow behind
it, plain for what is still to come.

Songs without that file, including anything extracted before it existed, fall back to the
transcription in `any_karaoke_file.json` and show plain lines.

A menu bar sits at the top of the window. It stays hidden until the mouse moves into the top
strip, so it never covers the lyrics while you are singing.

| Menu | Item | Shortcut |
| --- | --- | --- |
| File | Open song (a `.ak` file) | `Ctrl+O` |
| File | Open song folder (legacy) | |
| File | Manage library (opens the manager) | `Ctrl+M` |
| File | Quit | `Ctrl+Q` |
| Playback | Pause / Resume | `Space` |
| Playback | Restart song | `R` |
| Playback | Stop | `S` |
| Playback | Guide vocals (mute or restore the vocal stem) | `V` |
| View | Fullscreen | `F11` |
| View | Lyrics earlier | `[` |
| View | Lyrics later | `]` |

Every shortcut works whether or not the bar is showing, and a short message confirms what
happened. Pause freezes the lyrics along with the audio.

If the lyrics drift against the singing, `[` and `]` shift them 100ms at a time while the song
plays. The View menu shows the current offset. That is a per song adjustment; set
`LYRICS_TIME_OFFSET` in `game_config.py` to change the starting value for every song.

A small mixer sits down the left, clear of the centred lyrics: two faders side by side, green for
the backing track and blue for the guide vocal, with a play/stop button underneath. Drag either
fader to balance them. Once a drag starts it keeps following the mouse, so you do not have to stay
on the narrow track.

The button stops whatever is playing, and starts the last song again afterwards. With nothing
loaded yet it asks for a song.

Like the menu bar, the mixer gets out of the way on its own. It appears whenever you move the
mouse and hides after a couple of seconds of stillness, so nothing covers the screen while you are
singing. `V` mutes the guide vocal outright and puts the fader back where it was afterwards.

## Configuration

`src/any_karaoke/game_config.py` holds the colors, frame rate, model names and output format. The
model cache location can be overridden with `ANY_KARAOKE_MODELS` so an installed package does not
download into its own install folder.

If the lyrics run slightly ahead of or behind the audio on your machine, adjust
`LYRICS_TIME_OFFSET` in the same file. Positive values show the lyrics earlier. Note that mp3
encoding adds a constant delay of about 25ms. Both stems get the same delay so they stay in sync
with each other, and that offset absorbs the rest.

## Troubleshooting

**Transcription is very slow.** Check that the GPU is being used:

```
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

A `+cpu` version means torch came from PyPI rather than the CUDA index. Transcription still works
but takes minutes instead of seconds. torch, torchaudio and torchvision are pinned to the PyTorch
cu128 index in `[tool.uv.sources]`. CUDA 12.8 is the first version that supports Blackwell
(sm_120) cards. To target a different CUDA version, change the index URL and re-run `uv lock`.

**`OSError: [WinError 127]` when torchaudio loads.** The torch and torchaudio versions do not
match. This happens if `requires-python` is loosened to allow 3.9, because the resolver then falls
back to whisperX 3.3.1, which declares `torch` and `torchaudio` with no version bounds and picks
an incompatible pair. Keep the floor at 3.10.

**`libtorchcodec` warnings on every run.** torchcodec supports FFmpeg 4 to 7 and yours is newer.
Harmless here, since whisperX decodes audio through the ffmpeg CLI rather than torchcodec.

**"not a karaoke song".** A `.ak` file (or a legacy folder) needs `any_karaoke_file.json` plus a
music and a vocals stem (`.mp3` or `.wav`). The message lists whatever is missing. A `.ak` that is
not a valid zip is rejected the same way.

## Development

```
uv run pytest
uv run black src tests
uv run flake8 src tests
```
