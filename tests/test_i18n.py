import os
import pytest
from tw_odc.i18n import setup_locale, t, get_locale


class TestSetupLocale:
    def test_default_is_en(self):
        setup_locale()
        assert get_locale() == "en"

    def test_explicit_lang(self):
        setup_locale("zh-TW")
        assert get_locale() == "zh-TW"

    def test_env_lang_zh_tw(self, monkeypatch):
        monkeypatch.setenv("LANG", "zh_TW.UTF-8")
        monkeypatch.delenv("LC_ALL", raising=False)
        setup_locale()
        assert get_locale() == "zh-TW"

    def test_env_lc_all_overrides_lang(self, monkeypatch):
        monkeypatch.setenv("LANG", "en_US.UTF-8")
        monkeypatch.setenv("LC_ALL", "zh_TW.UTF-8")
        setup_locale()
        assert get_locale() == "zh-TW"

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("LANG", "zh_TW.UTF-8")
        setup_locale("en")
        assert get_locale() == "en"

    def test_unknown_env_falls_back_to_en(self, monkeypatch):
        monkeypatch.setenv("LANG", "fr_FR.UTF-8")
        monkeypatch.delenv("LC_ALL", raising=False)
        setup_locale()
        assert get_locale() == "en"


class TestTranslation:
    def test_en_error_code(self):
        setup_locale("en")
        result = t("E004", provider="TestOrg")
        assert "TestOrg" in result
        assert "Provider not found" in result

    def test_zh_tw_error_code(self):
        setup_locale("zh-TW")
        result = t("E004", provider="測試機關")
        assert "測試機關" in result
        assert "找不到機關" in result

    def test_en_status_message(self):
        setup_locale("en")
        result = t("status.not_modified", filename="test.csv")
        assert "test.csv" in result
        assert "not modified" in result

    def test_zh_tw_status_message(self):
        setup_locale("zh-TW")
        result = t("status.not_modified", filename="test.csv")
        assert "test.csv" in result
        assert "未變更" in result

    def test_missing_key_returns_key(self):
        setup_locale("en")
        result = t("nonexistent.key")
        assert "nonexistent.key" in result
