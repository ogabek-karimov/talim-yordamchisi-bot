from app.i18n import SUPPORTED, catalog, missing_keys, t


def test_all_locales_present():
    assert set(SUPPORTED) == {"uz", "ru", "en", "kaa"}


def test_no_missing_keys_across_locales():
    gaps = missing_keys()
    assert gaps == {}, f"locale key gaps: {gaps}"


def test_fallback_to_uz_then_key():
    assert t("common.yes", "en") == "Yes"
    assert t("common.yes", "xx") == t("common.yes", "uz")  # unknown lang -> default/uz
    assert t("this.key.does.not.exist", "ru") == "this.key.does.not.exist"


def test_format_params():
    out = t("sub.plan_line", "en", title="1 month", days=30, stars=150)
    assert "30" in out and "150" in out and "1 month" in out


def test_catalog_is_complete_for_each_lang():
    keys_uz = set(catalog("uz"))
    for lang in SUPPORTED:
        assert set(catalog(lang)) == keys_uz
