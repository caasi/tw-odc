"""Internationalization support for tw-odc CLI."""

import os
from importlib.resources import files

import i18n

_SUPPORTED = {"en", "zh-TW"}
_locale = "en"

# Configure i18nice
i18n.set("load_path", [str(files("tw_odc").joinpath("locales"))])
i18n.set("file_format", "json")
i18n.set("filename_format", "{locale}.{format}")
i18n.set("skip_locale_root_data", True)
i18n.set("fallback", "en")
i18n.set("on_missing_translation", lambda key, locale, **kwargs: key)


def _detect_env_locale() -> str:
    """Detect locale from LC_ALL or LANG environment variables."""
    env_val = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    # e.g. "zh_TW.UTF-8" → "zh-TW"
    code = env_val.split(".")[0]  # strip encoding
    if code.startswith("zh_TW") or code.startswith("zh-TW"):
        return "zh-TW"
    return "en"


def setup_locale(lang: str | None = None) -> None:
    """Initialize locale. Priority: explicit lang > env > default en."""
    global _locale
    if lang and lang in _SUPPORTED:
        _locale = lang
    elif lang is None:
        _locale = _detect_env_locale()
    else:
        _locale = "en"
    i18n.set("locale", _locale)


def get_locale() -> str:
    """Return the current locale string."""
    return _locale


def t(key: str, **kwargs) -> str:
    """Translate a message key with optional placeholders."""
    return i18n.t(key, locale=_locale, **kwargs)
