# MyViCon

A graphical application for combining video, audio tracks, subtitles, and fonts
into a single `.mkv` file using MKVToolNix.

## Download

A ready-to-use Windows build is available on the
[Releases](https://github.com/atnimak/MyViCon/releases) page.

Extract the archive and run `MyViCon.exe`. Python and MKVToolNix do not need
to be installed separately.

## Features

- Support for multiple audio and subtitle tracks.
- Automatic file matching by episode number: `S01E05`, `EP05`, `E05`, `- 05`.
- Filename-based matching for movies without episode numbers.
- Custom regular expressions for non-standard filenames.
- Language, track name, and default-track flag settings for each track.
- Preserves the original tracks, chapters, and attachments; only audio tracks
  are imported from external audio files.
- Support for `.ttf`, `.otf`, and `.ttc` font attachments.
- Match preview before muxing.
- Progress indicator and operation log.
- Settings are preserved between sessions.

## Usage

1. Select the folder containing the source video files.
2. Add the folders containing audio tracks and subtitles.
3. Select a font folder if needed.
4. Click **Preview** and verify the detected matches.
5. Click **Mux**.

Output files are saved to the selected folder or to `<video folder>\Merged`.

The `{base}` and `{episode}` placeholders are available for output filenames
and titles.

## Settings

Settings are stored in `myvicon_config.json` next to the application. If that
folder is not writable, `%APPDATA%\MyViCon` is used instead.

## Running from Source

Python 3.8 or later with `tkinter` is required. There are no external Python
dependencies.

```powershell
python app.py
```

`mkvmerge.exe` and `mkvpropedit.exe` must be placed in the `mkvtoolnix` folder
next to the application. Their paths can also be specified manually.

## Building

Install PyInstaller and run `build.bat`:

```powershell
pip install pyinstaller
.\build.bat
```

The compiled executable will be created at `dist\MyViCon.exe`. The
`mkvtoolnix` folder must be placed next to it.

## Supported Formats

- Video: `.mkv`, `.mp4`, `.m4v`, `.avi`, `.webm`
- Audio: `.mka`, `.mkv`, `.aac`, `.flac`, `.ac3`, `.eac3`, `.dts`, `.opus`,
  `.wav`, `.m4a`, `.mp3`, `.mp2`
- Subtitles: `.ass`, `.ssa`, `.srt`, `.sup`, `.mks`, `.vtt`, `.sub`
- Fonts: `.ttf`, `.otf`, `.ttc`

## Repository

[github.com/atnimak/MyViCon](https://github.com/atnimak/MyViCon)
