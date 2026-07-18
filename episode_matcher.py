"""Определение номера серии из имени файла и сопоставление файлов между папками.

Логика максимально универсальна: перебираются несколько распространённых
шаблонов имён (S01E05, EP05, "- 05", " 05 "). Пользователь может задать
собственное регулярное выражение с группой захвата номера.
"""

import os
import re

# Шаблоны перебираются по порядку; берётся последняя непустая группа.
_PATTERNS = [
    re.compile(r"[Ss](\d{1,2})[\s._-]*[Ee](\d{1,4})"),                      # S01E05
    re.compile(r"(?:^|[^A-Za-z0-9])[Ee][Pp]?[\s._-]*(\d{1,4})(?![0-9])"),   # EP05 / E05
    re.compile(r"(?:^|[\s._])[-–—]\s*(\d{1,4})(?![0-9])"),                  # - 05
    re.compile(r"(?:^|[\s._([-])(\d{1,4})(?=[\s._)\]-]|$)"),                # отдельное число
]


def extract_episode(name, custom_regex=None):
    """Вернуть номер серии (int) из имени файла или None, если не найден."""
    stem = os.path.splitext(os.path.basename(name))[0]

    if custom_regex:
        try:
            m = re.search(custom_regex, stem)
        except re.error:
            m = None
        if m:
            groups = [g for g in m.groups() if g]
            if groups:
                try:
                    return int(groups[-1])
                except ValueError:
                    return None
            token = m.group(0)
            if token.isdigit():
                return int(token)
        return None

    for pat in _PATTERNS:
        m = pat.search(stem)
        if m:
            groups = [g for g in m.groups() if g]
            if groups:
                try:
                    return int(groups[-1])
                except ValueError:
                    continue
    return None


def index_folder(folder, extensions=None, custom_regex=None, recursive=True):
    """Проиндексировать папку: {номер_серии: [пути]}.

    extensions — множество допустимых расширений в нижнем регистре (с точкой),
    например {".mka", ".flac"}. Если None — берутся все файлы.
    """
    result = {}
    if not folder or not os.path.isdir(folder):
        return result

    walker = os.walk(folder) if recursive else [(folder, [], os.listdir(folder))]
    for root, _dirs, files in walker:
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if extensions is not None and ext not in extensions:
                continue
            ep = extract_episode(fname, custom_regex)
            if ep is None:
                continue
            result.setdefault(ep, []).append(os.path.join(root, fname))
    return result
