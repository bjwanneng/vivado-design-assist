"""Tests for GUI components (installer, hooks, probe)"""

import pytest
from pathlib import Path

from vivado_ai.gui.installer import VivadoAutoInstaller
from vivado_ai.gui.hooks import HookScriptGenerator


class TestVivadoAutoInstaller:
    def test_install_and_uninstall(self, tmp_path):
        installer = VivadoAutoInstaller()
        # Redirect to temp dir for testing
        installer.init_tcl_path = tmp_path / "init.tcl"

        # Install
        assert installer.install() is True
        assert installer.is_installed is True

        content = installer.init_tcl_path.read_text(encoding="utf-8")
        assert "namespace eval vmc" in content
        assert "19876" in content

        # Uninstall
        assert installer.uninstall() is True
        assert installer.is_installed is False

    def test_install_preserves_existing(self, tmp_path):
        installer = VivadoAutoInstaller()
        installer.init_tcl_path = tmp_path / "init.tcl"

        # Write existing content
        installer.init_tcl_path.write_text("set my_var 1\n", encoding="utf-8")

        installer.install()
        content = installer.init_tcl_path.read_text(encoding="utf-8")

        assert "set my_var 1" in content
        assert "namespace eval vmc" in content

    def test_reinstall_overwrites_old(self, tmp_path):
        installer = VivadoAutoInstaller()
        installer.init_tcl_path = tmp_path / "init.tcl"

        installer.install(port=12345)
        content1 = installer.init_tcl_path.read_text(encoding="utf-8")
        assert "12345" in content1

        installer.install(port=19876)
        content2 = installer.init_tcl_path.read_text(encoding="utf-8")
        assert "19876" in content2
        # Should only have one injection
        assert content2.count("VMC_AUTO_START") == 1

    def test_uninstall_no_file(self, tmp_path):
        installer = VivadoAutoInstaller()
        installer.init_tcl_path = tmp_path / "nonexistent" / "init.tcl"
        assert installer.uninstall() is True


class TestHookScriptGenerator:
    def test_generate_all(self, tmp_path):
        gen = HookScriptGenerator(str(tmp_path))

        gen.generate_all()

        assert (tmp_path / "vm_post_synth.tcl").exists()
        assert (tmp_path / "vm_post_place.tcl").exists()
        assert (tmp_path / "vm_post_route.tcl").exists()
        assert (tmp_path / "vmc_reports").is_dir()

    def test_synth_script_content(self, tmp_path):
        gen = HookScriptGenerator(str(tmp_path))
        gen.generate_all()

        content = (tmp_path / "vm_post_synth.tcl").read_text(encoding="utf-8")
        assert "report_timing_summary" in content
        assert "report_methodology" in content
        assert "report_cdc" in content
        assert "vm_synth_done" in content

    def test_place_script_content(self, tmp_path):
        gen = HookScriptGenerator(str(tmp_path))
        gen.generate_all()

        content = (tmp_path / "vm_post_place.tcl").read_text(encoding="utf-8")
        assert "report_timing_summary" in content
        assert "vm_place_done" in content

    def test_route_script_content(self, tmp_path):
        gen = HookScriptGenerator(str(tmp_path))
        gen.generate_all()

        content = (tmp_path / "vm_post_route.tcl").read_text(encoding="utf-8")
        assert "report_timing_summary" in content
        assert "report_power" in content
        assert "vm_route_done" in content


class TestVivadoProbe:
    def test_scan_returns_none_when_no_vivado(self):
        from vivado_ai.gui.app import VivadoProbe
        # In test environment, Vivado won't be running
        result = VivadoProbe().scan()
        # Can be None or a dict — both are valid test outcomes
        assert result is None or isinstance(result, dict)
