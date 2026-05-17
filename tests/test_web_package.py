from __future__ import annotations


def test_package_is_importable():
    import ngc_cams_web  # noqa: F401


def test_package_has_version_attribute():
    import ngc_cams_web

    assert isinstance(ngc_cams_web.__version__, str)
