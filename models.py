"""Модели данных и работа с конфигом (JSON рядом с программой)."""

import json
import os
import sys
from dataclasses import dataclass, field, asdict


CONFIG_NAME = "myvicon_config.json"


def _base_dir():
    """Папка рядом с программой.

    В собранном .exe (PyInstaller) __file__ указывает во временную папку _MEIxxxx,
    поэтому для «замороженного» приложения берём папку рядом с самим .exe.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def program_dir():
    """Папка рядом с программой (exe или скрипт)."""
    return _base_dir()


def program_config_path():
    """Путь к конфигу рядом с программой (предпочтительный)."""
    return os.path.join(_base_dir(), CONFIG_NAME)


def appdata_config_path():
    """Резервный путь к конфигу в %APPDATA%\\MyViCon."""
    root = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(root, "MyViCon", CONFIG_NAME)


# Путь по умолчанию (для чтения): рядом с программой.
CONFIG_PATH = program_config_path()


@dataclass
class Source:
    """Источник дополнительной дорожки (озвучка или субтитры)."""
    dir: str = ""
    name: str = ""            # имя дорожки (track name)
    language: str = "rus"     # ISO-код языка
    default: bool = False     # флаг дорожки по умолчанию
    kind: str = "audio"       # "audio" | "subtitle"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(
            dir=d.get("dir", ""),
            name=d.get("name", ""),
            language=d.get("language", "rus"),
            default=bool(d.get("default", False)),
            kind=d.get("kind", "audio"),
        )


@dataclass
class AppConfig:
    mkvmerge: str = ""
    mkvpropedit: str = ""
    video_dir: str = ""
    output_dir: str = ""
    fonts_dir: str = ""
    episode_regex: str = ""
    output_template: str = "{base} [RUS]"
    title_template: str = "{base}"
    last_dir: str = ""
    audio_sources: list = field(default_factory=list)  # list[Source]
    sub_sources: list = field(default_factory=list)     # list[Source]

    def to_dict(self):
        d = asdict(self)
        d["audio_sources"] = [s.to_dict() for s in self.audio_sources]
        d["sub_sources"] = [s.to_dict() for s in self.sub_sources]
        return d

    @classmethod
    def from_dict(cls, d):
        cfg = cls(
            mkvmerge=d.get("mkvmerge", ""),
            mkvpropedit=d.get("mkvpropedit", ""),
            video_dir=d.get("video_dir", ""),
            output_dir=d.get("output_dir", ""),
            fonts_dir=d.get("fonts_dir", ""),
            episode_regex=d.get("episode_regex", ""),
            output_template=d.get("output_template", "{base} [RUS]"),
            title_template=d.get("title_template", "{base}"),
            last_dir=d.get("last_dir", ""),
        )
        cfg.audio_sources = [Source.from_dict(x) for x in d.get("audio_sources", [])]
        cfg.sub_sources = [Source.from_dict(x) for x in d.get("sub_sources", [])]
        for s in cfg.audio_sources:
            s.kind = "audio"
        for s in cfg.sub_sources:
            s.kind = "subtitle"
        return cfg

    @classmethod
    def load(cls, path=None):
        """Прочитать конфиг: сначала рядом с программой, затем из %APPDATA%."""
        candidates = [path] if path else [program_config_path(), appdata_config_path()]
        for p in candidates:
            if p and os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        return cls.from_dict(json.load(f))
                except (OSError, ValueError):
                    continue
        return cls()

    def save(self, path=None):
        """Сохранить конфиг рядом с программой, при отказе — в %APPDATA%.

        Возвращает кортеж (путь, использован_резерв):
        - путь — куда фактически записан конфиг;
        - использован_резерв — True, если пришлось сохранить в %APPDATA%.
        """
        if path is not None:
            self._write(path)
            return path, False

        primary = program_config_path()
        try:
            self._write(primary)
            return primary, False
        except OSError:
            fallback = appdata_config_path()
            os.makedirs(os.path.dirname(fallback), exist_ok=True)
            self._write(fallback)
            return fallback, True

    def _write(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
