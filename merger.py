"""Построение плана сборки и запуск mkvmerge / mkvpropedit."""

import os
import subprocess
import sys
from dataclasses import dataclass, field

from episode_matcher import extract_episode, index_folder

AUDIO_EXTS = {".mka", ".mkv", ".aac", ".flac", ".ac3", ".eac3", ".dts", ".opus",
              ".wav", ".m4a", ".mp3", ".mp2"}
SUB_EXTS = {".ass", ".ssa", ".srt", ".sup", ".mks", ".vtt", ".sub"}
FONT_EXTS = {".ttf", ".otf", ".ttc"}
VIDEO_EXTS = {".mkv", ".mp4", ".m4v", ".avi", ".webm"}


@dataclass
class TrackMatch:
    source_name: str
    language: str
    default: bool
    path: str  # может быть "" если не найдено


@dataclass
class EpisodePlan:
    episode: int
    video: str
    base: str
    audio: list = field(default_factory=list)   # list[TrackMatch]
    subs: list = field(default_factory=list)     # list[TrackMatch]
    warnings: list = field(default_factory=list)
    name_matched: bool = False   # True, если дорожки сопоставлены по имени (фильм без номера)

    @property
    def has_all(self):
        return all(t.path for t in self.audio) and all(t.path for t in self.subs)

    @property
    def ready(self):
        """Готов ли план к сборке.

        Для серий требуется определённый номер (episode >= 0), для фильмов —
        успешное сопоставление по имени (name_matched).
        """
        return self.has_all and (self.episode >= 0 or self.name_matched)


def _pick(index, episode, warnings, label):
    """Выбрать один файл для серии из индекса, предупредить о дубликатах."""
    paths = index.get(episode)
    if not paths:
        return ""
    if len(paths) > 1:
        chosen = sorted(paths)[0]
        others = ", ".join(os.path.basename(p) for p in sorted(paths)[1:])
        warnings.append(f"{label}: найдено несколько файлов для серии {episode:02d}, "
                        f"выбран '{os.path.basename(chosen)}' (пропущены: {others})")
        return chosen
    return paths[0]


def list_files(folder, extensions, recursive=True):
    """Список путей к файлам в папке по расширениям (без учёта номера серии)."""
    files = []
    if not folder or not os.path.isdir(folder):
        return files
    walker = os.walk(folder) if recursive else [(folder, [], os.listdir(folder))]
    for root, _dirs, fs in walker:
        for fn in fs:
            if os.path.splitext(fn)[1].lower() in extensions:
                files.append(os.path.join(root, fn))
    return files


def _pick_by_name(files, video_base, warnings, label):
    """Выбрать файл, чьё имя соответствует имени видео (для фильмов без номера).

    Совпадением считается файл, чей stem начинается с имени видео
    (например, '<видео>.rus.srt' или '<видео>.Озвучка.mka'), либо равен ему.
    """
    base_low = video_base.lower()
    cands = []
    for p in files:
        stem = os.path.splitext(os.path.basename(p))[0].lower()
        if stem == base_low or stem.startswith(base_low):
            cands.append(p)
    if not cands:
        return ""
    if len(cands) > 1:
        chosen = sorted(cands)[0]
        others = ", ".join(os.path.basename(p) for p in sorted(cands)[1:])
        warnings.append(f"{label}: найдено несколько подходящих файлов, "
                        f"выбран '{os.path.basename(chosen)}' (пропущены: {others})")
        return chosen
    return cands[0]


def build_plan(config):
    """Построить список EpisodePlan по конфигу.

    Возвращает (plans, global_warnings).
    """
    warnings = []
    regex = config.episode_regex or None

    if not config.video_dir or not os.path.isdir(config.video_dir):
        return [], ["Не указана или не существует папка с оригиналами (видео)."]

    # Индексация источников
    audio_indexes = [
        (s, index_folder(s.dir, AUDIO_EXTS, regex))
        for s in config.audio_sources
    ]
    sub_indexes = [
        (s, index_folder(s.dir, SUB_EXTS, regex))
        for s in config.sub_sources
    ]

    plans = []
    for fname in sorted(os.listdir(config.video_dir)):
        full = os.path.join(config.video_dir, fname)
        if not os.path.isfile(full):
            continue
        if os.path.splitext(fname)[1].lower() not in VIDEO_EXTS:
            continue

        ep = extract_episode(fname, regex)
        base = os.path.splitext(fname)[0]
        plan = EpisodePlan(episode=ep if ep is not None else -1, video=full, base=base)

        if ep is None:
            # Фолбэк для фильмов/файлов без номера серии: сопоставляем по имени.
            plan.warnings.append(
                "Номер серии не определён — сопоставление по имени файла.")
            for src in config.audio_sources:
                files = list_files(src.dir, AUDIO_EXTS)
                path = _pick_by_name(files, base, plan.warnings,
                                     f"Озвучка '{src.name or src.dir}'")
                plan.audio.append(TrackMatch(src.name, src.language, src.default, path))
                if not path:
                    plan.warnings.append(
                        f"Не найдена озвучка '{src.name or src.dir}' по имени видео.")
            for src in config.sub_sources:
                files = list_files(src.dir, SUB_EXTS)
                path = _pick_by_name(files, base, plan.warnings,
                                     f"Субтитры '{src.name or src.dir}'")
                plan.subs.append(TrackMatch(src.name, src.language, src.default, path))
                if not path:
                    plan.warnings.append(
                        f"Не найдены субтитры '{src.name or src.dir}' по имени видео.")
            plan.name_matched = any(t.path for t in plan.audio) or any(t.path for t in plan.subs)
            plans.append(plan)
            continue

        for src, idx in audio_indexes:
            path = _pick(idx, ep, plan.warnings, f"Озвучка '{src.name or src.dir}'")
            plan.audio.append(TrackMatch(src.name, src.language, src.default, path))
            if not path:
                plan.warnings.append(f"Не найдена озвучка '{src.name or src.dir}' для серии {ep:02d}.")

        for src, idx in sub_indexes:
            path = _pick(idx, ep, plan.warnings, f"Субтитры '{src.name or src.dir}'")
            plan.subs.append(TrackMatch(src.name, src.language, src.default, path))
            if not path:
                plan.warnings.append(f"Не найдены субтитры '{src.name or src.dir}' для серии {ep:02d}.")

        plans.append(plan)

    if not plans:
        warnings.append("В папке оригиналов не найдено видеофайлов.")

    return plans, warnings


def build_mkvmerge_command(mkvmerge, plan, output, title):
    """Сформировать список аргументов для mkvmerge для одной серии."""
    cmd = [mkvmerge, "-o", output, "--title", title, plan.video]

    for t in plan.audio:
        if not t.path:
            continue
        cmd += [
            "--no-video", "--no-subtitles", "--no-buttons", "--no-track-tags",
            "--no-chapters", "--no-attachments", "--no-global-tags",
            "--language", f"-1:{t.language}",
            "--track-name", f"-1:{t.source_name}",
            "--default-track-flag", f"-1:{1 if t.default else 0}",
            t.path,
        ]

    for t in plan.subs:
        if not t.path:
            continue
        cmd += [
            "--no-video", "--no-audio", "--no-buttons", "--no-track-tags",
            "--no-chapters", "--no-attachments", "--no-global-tags",
            "--language", f"-1:{t.language}",
            "--track-name", f"-1:{t.source_name}",
            "--default-track-flag", f"-1:{1 if t.default else 0}",
            t.path,
        ]

    return cmd


def _no_window_kwargs():
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _run(cmd, log):
    """Запустить процесс, построчно передавая вывод в log(). Вернуть код возврата."""
    log("> " + subprocess.list2cmdline(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_no_window_kwargs(),
        )
    except FileNotFoundError:
        log(f"ОШИБКА: не найден исполняемый файл '{cmd[0]}'.")
        return 2

    for line in proc.stdout:
        line = line.rstrip()
        if line:
            log("  " + line)
    proc.wait()
    return proc.returncode


def collect_fonts(fonts_dir):
    fonts = []
    if not fonts_dir or not os.path.isdir(fonts_dir):
        return fonts
    for root, _dirs, files in os.walk(fonts_dir):
        for f in files:
            if os.path.splitext(f)[1].lower() in FONT_EXTS:
                fonts.append(os.path.join(root, f))
    return fonts


def run_merge(config, plans, log, should_stop=None, progress=None):
    """Выполнить сборку всех серий. Возвращает словарь со статистикой.

    progress — необязательный колбэк progress(done, total) для индикатора.
    """
    stats = {"ok": 0, "warnings": 0, "failed": 0, "skipped": 0, "font_errors": 0}

    os.makedirs(config.output_dir, exist_ok=True)
    fonts = collect_fonts(config.fonts_dir)

    total = len(plans)
    if progress:
        progress(0, total)

    for i, plan in enumerate(plans):
        if should_stop and should_stop():
            log("Остановлено пользователем.")
            break

        ep_label = f"{plan.episode:02d}" if plan.episode >= 0 else "??"
        log("")
        log("=" * 60)
        log(f"Серия {ep_label} — {plan.base}")
        log("=" * 60)

        if not plan.ready:
            log("ПРОПУЩЕНО: отсутствуют необходимые файлы.")
            for w in plan.warnings:
                log("  " + w)
            stats["skipped"] += 1
            if progress:
                progress(i + 1, total)
            continue

        for w in plan.warnings:
            log("  " + w)

        title = config.title_template.format(base=plan.base, episode=ep_label)
        out_name = config.output_template.format(base=plan.base, episode=ep_label) + ".mkv"
        output = os.path.join(config.output_dir, out_name)

        cmd = build_mkvmerge_command(config.mkvmerge, plan, output, title)
        rc = _run(cmd, log)

        if rc >= 2:
            log(f"ОШИБКА: mkvmerge завершился с ошибкой (серия {ep_label}).")
            stats["failed"] += 1
            if progress:
                progress(i + 1, total)
            continue
        elif rc == 1:
            log(f"ПРЕДУПРЕЖДЕНИЕ: серия {ep_label} создана, но с предупреждением mkvmerge.")
            stats["warnings"] += 1
        else:
            log(f"ГОТОВО: серия {ep_label} создана.")
            stats["ok"] += 1

        # Добавление шрифтов
        if fonts:
            if config.mkvpropedit and os.path.isfile(config.mkvpropedit):
                for font in fonts:
                    frc = _run([config.mkvpropedit, output, "--add-attachment", font], log)
                    if frc >= 2:
                        log(f"ПРЕДУПРЕЖДЕНИЕ: не удалось прикрепить шрифт '{os.path.basename(font)}'.")
                        stats["font_errors"] += 1
            else:
                log("ПРЕДУПРЕЖДЕНИЕ: mkvpropedit.exe не найден; шрифты не добавлены.")
                stats["font_errors"] += 1

        if progress:
            progress(i + 1, total)

    log("")
    log("=" * 60)
    log(f"Готово без предупреждений: {stats['ok']}")
    log(f"Готово с предупреждениями: {stats['warnings']}")
    log(f"Ошибки: {stats['failed']}")
    log(f"Пропущено: {stats['skipped']}")
    log(f"Ошибки прикрепления шрифтов: {stats['font_errors']}")
    log("=" * 60)
    return stats
