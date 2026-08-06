from dataclasses import dataclass

from .adb import run_adb


@dataclass
class DeviceInfo:
    serial: str
    state: str
    manufacturer: str
    model: str
    product: str
    device: str
    android_version: str
    build_id: str


def get_prop(serial: str, prop: str) -> str:
    return run_adb("-s", serial, "shell", "getprop", prop)


def get_device_info(serial: str) -> DeviceInfo:
    return DeviceInfo(
        serial=serial,
        state="device",
        manufacturer=get_prop(serial, "ro.product.manufacturer"),
        model=get_prop(serial, "ro.product.model"),
        product=get_prop(serial, "ro.product.name"),
        device=get_prop(serial, "ro.product.device"),
        android_version=get_prop(serial, "ro.build.version.release"),
        build_id=get_prop(serial, "ro.build.id"),
    )
