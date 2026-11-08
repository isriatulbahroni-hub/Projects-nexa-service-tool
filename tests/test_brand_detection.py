import pytest

from core.locked_device_recovery import _infer_brand_group
from core.tool_router import ToolRouter


@pytest.mark.parametrize(
    "identity, expected",
    [
        ({"manufacturer": "samsung", "brand": "samsung", "model": "SM-A546E"}, "Samsung"),
        ({"manufacturer": "Xiaomi", "brand": "Redmi", "model": "23053RN02A"}, "Xiaomi / Redmi / POCO"),
        ({"manufacturer": "OPPO", "brand": "OPPO", "model": "CPH2557"}, "OPPO / realme"),
        ({"manufacturer": "realme", "brand": "realme", "model": "RMX3630"}, "OPPO / realme"),
        ({"manufacturer": "vivo", "brand": "vivo", "model": "V2250"}, "vivo / iQOO"),
        ({"manufacturer": "INFINIX", "brand": "Infinix", "model": "X6833B"}, "Infinix / TECNO"),
        ({"manufacturer": "TECNO", "brand": "TECNO", "model": "CK7n"}, "Infinix / TECNO"),
        ({"manufacturer": "ITEL", "brand": "itel", "model": "A662L"}, "itel"),
        ({"manufacturer": "Google", "brand": "google", "model": "Pixel 8"}, "Google Pixel"),
        ({"manufacturer": "OnePlus", "brand": "OnePlus", "model": "CPH2449"}, "OnePlus"),
        ({"manufacturer": "HUAWEI", "brand": "HUAWEI", "model": "JAD-LX9"}, "Huawei / Honor"),
        ({"manufacturer": "HONOR", "brand": "HONOR", "model": "ELI-NX9"}, "Huawei / Honor"),
        ({"manufacturer": "motorola", "brand": "motorola", "model": "moto g54"}, "Motorola"),
        ({"manufacturer": "asus", "brand": "asus", "model": "ASUS_AI2302"}, "ASUS"),
        ({"manufacturer": "Sony", "brand": "Sony", "model": "XQ-DQ72"}, "Sony"),
        ({"manufacturer": "LENOVO", "brand": "Lenovo", "model": "TB-X606F"}, "Lenovo"),
        ({"manufacturer": "ADVAN", "brand": "advan", "model": "X"}, "Advan"),
    ],
)
def test_brand_group_for_common_brands(identity, expected):
    assert _infer_brand_group(identity) == expected


@pytest.mark.parametrize(
    "group",
    ["Samsung", "Xiaomi / Redmi / POCO", "OPPO / realme", "vivo / iQOO", "Infinix / TECNO",
     "Motorola", "Nokia / HMD", "Google Pixel", "OnePlus", "Huawei / Honor", "Sony", "ASUS",
     "Lenovo", "itel"],
)
def test_every_known_group_has_official_tool_hint(group):
    tools = ToolRouter().select_tools_for_device(group, "ADB", False, True)
    assert len(tools) > 2  # lebih dari sekadar ADB/Fastboot standar
