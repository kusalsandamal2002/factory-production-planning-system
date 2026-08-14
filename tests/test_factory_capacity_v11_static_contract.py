from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_master_data_top_metrics_removed_from_layout():
    src = read("app/ui/master_data_hub_page.py")
    assert "self.root.addLayout(self._build_metrics())" not in src


def test_factory_capacity_is_integrated_intelligence_workspace():
    src = read("app/ui/factory_capacity_page.py")
    for token in (
        "Factory Resource & Capacity Intelligence",
        "Production Lines",
        "Cavities",
        "Molds",
        "Casings",
        "Real Capacity",
        "Model Health",
    ):
        assert token in src


def test_capacity_callers_use_authoritative_resolver():
    for path in (
        "app/services/factory_planning_engine.py",
        "app/services/oven_capacity_service.py",
        "app/services/stock_planning_service.py",
        "app/services/factory_out_forecast_service.py",
        "app/services/factory_out_date_logic.py",
    ):
        assert "FactoryResourceIntelligenceService" in read(path), path


def test_line_and_cavity_delete_paths_are_non_destructive():
    line_src = read("app/ui/production_line_master_page.py")
    cavity_src = read("app/ui/cavities_master_page.py")
    assert "status='Retired'" in line_src
    assert "status = 'Retired'" in cavity_src or "status='Retired'" in cavity_src


def test_legacy_capacity_page_is_labelled_baseline():
    src = read("app/ui/capacity_master_page.py")
    assert "Legacy / Technical Capacity Baseline" in src
