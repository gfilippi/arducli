#!/usr/bin/env python3

import sys
import os
import json
import subprocess
import glob
import time
import argparse
from enum import Enum

# Ensure local i2c_tools.py can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from i2c_tools import I2CDevice

# Version
VERSION_MJR = 1
VERSION_MIN = 5

# Default mapping table path
DEFAULT_MAPPING_PATH = "/opt/arducam/arducam_i2c_map.json"

# Device register definitions
DEVICE_REG_BASE = 0x0100
PIXFORMAT_REG_BASE = 0x0200
FORMAT_REG_BASE = 0x0300
CTRL_REG_BASE = 0x0400
IPC_REG_BASE = 0x0600
STREAM_ON = (DEVICE_REG_BASE | 0x0000)
DEVICE_VERSION_REG = (DEVICE_REG_BASE | 0x0001)
SENSOR_ID_REG = (DEVICE_REG_BASE | 0x0002)
DEVICE_ID_REG = (DEVICE_REG_BASE | 0x0003)
FIRMWARE_SENSOR_ID_REG = (DEVICE_REG_BASE | 0x0005)
UNIQUE_ID_REG = (DEVICE_REG_BASE | 0x0006)
SYSTEM_IDLE_REG = (DEVICE_REG_BASE | 0x0007)
SOFT_VERSION_LEN_REG = (DEVICE_REG_BASE | 0x00F0)
SOFT_VERSION_INDEX_REG = (DEVICE_REG_BASE | 0x00F1)
SOFT_VERSION_REG = (DEVICE_REG_BASE | 0x00F2)
PIXFORMAT_INDEX_REG = (PIXFORMAT_REG_BASE | 0x0000)
PIXFORMAT_TYPE_REG = (PIXFORMAT_REG_BASE | 0x0001)
PIXFORMAT_ORDER_REG = (PIXFORMAT_REG_BASE | 0x0002)
MIPI_LANES_REG = (PIXFORMAT_REG_BASE | 0x0003)
RESOLUTION_INDEX_REG = (FORMAT_REG_BASE | 0x0000)
FORMAT_WIDTH_REG = (FORMAT_REG_BASE | 0x0001)
FORMAT_HEIGHT_REG = (FORMAT_REG_BASE | 0x0002)
CTRL_INDEX_REG = (CTRL_REG_BASE | 0x0000)
CTRL_ID_REG = (CTRL_REG_BASE | 0x0001)
CTRL_MIN_REG = (CTRL_REG_BASE | 0x0002)
CTRL_MAX_REG = (CTRL_REG_BASE | 0x0003)
CTRL_DEF_REG = (CTRL_REG_BASE | 0x0005)
CTRL_VALUE_REG = (CTRL_REG_BASE | 0x0006)
NO_DATA_AVAILABLE = 0xFFFFFFFE

# Pixel format mapping
pix_type_map = {
    0x2A: "RAW8",
    0x2B: "RAW10",
    0x2C: "RAW12",
    0x18: "YUV420_8BIT",
    0x19: "YUV420_10BIT",
    0x1E: "YUV422_8BIT",
    0x30: "JPEG",
}

raw_bayer_order = {
    0x0: "BGGR",
    0x1: "GBRG",
    0x2: "GRBG",
    0x3: "RGGB",
    0x4: "MONO",
}

yuv_order = {
    0x0: "YUYV",
    0x1: "YVYU",
    0x2: "UYVY",
    0x3: "VYUY",
}

control_id_map = {
    0x980902: "Saturation",
    0x98090c: "AWBMode",
    0x98090e: "RedGain",
    0x98090f: "BlueGain",
    0x98091a: "ColorTemperature",
    0x9a0901: "AEEnable",
    0x9a0919: "ExposureMetering",
    0x980911: "Exposure",
    0x981901: "TriggerMode",
    0x981906: "Framerate",
    0x9e0903: "AnalogueGain",
    0x9A090A: "Focus",
    0x980900: "brightness",
    0x980901: "contrast",
    0x98091B: "sharpness",
    0x980913: "gain",
}

ID_map = {
    0x980914: "horizontal_flip",
    0x980915: "vertical_flip",
    0x98190E: "strobe_width",
    0x98190F: "strobe_shift",
    0x9e0901: "vertical_blanking",
    0x9e0902: "horizontal_blanking",
    0x9f0902: "pixel_rate",
    0x98091C: "backlight_compensation",
}

ID_map.update(control_id_map)

class Level(Enum):
    WARNING = 2
    ERROR = 1
    INFO = 0

class PivarietyCamera:
    def __init__(self, bus):
        self.bus = bus
        self.i2c_address = 0x0C
        try:
            self.i2c = I2CDevice(self.bus)
        except Exception as e:
            raise RuntimeError(f"Failed to open I2C bus {bus}: {e}")

    def readReg(self, register):
        return self.i2c.read_16_32(self.i2c_address, register)

    def writeReg(self, register, value):
        self.i2c.write_16_32(self.i2c_address, register, value)

def wait_for_free():
    time.sleep(0.05)

def logging(text, level=Level.INFO):
    prefix = "[INFO]" if level == Level.INFO else "[WARNING]" if level == Level.WARNING else "[ERROR]"
    print(f"{prefix}: {text}")

def enum_resolutions(camera):
    index = 0
    resolutions = []
    while True:
        camera.writeReg(RESOLUTION_INDEX_REG, index)
        val = camera.readReg(RESOLUTION_INDEX_REG)
        if val == NO_DATA_AVAILABLE:
            break
        width = camera.readReg(FORMAT_WIDTH_REG)
        height = camera.readReg(FORMAT_HEIGHT_REG)

        # Get max framerate from Framerate control
        camera.writeReg(CTRL_INDEX_REG, 0)
        max_fps = None
        ctrl_index = 0
        while True:
            camera.writeReg(CTRL_INDEX_REG, ctrl_index)
            ctrl_id = camera.readReg(CTRL_ID_REG)
            if ctrl_id == NO_DATA_AVAILABLE:
                break
            if ctrl_id == 0x981906:  # Framerate
                max_fps = camera.readReg(CTRL_MAX_REG)
                break
            ctrl_index += 1

        resolutions.append({"index": index, "width": width, "height": height, "max_fps": max_fps})
        index += 1
    return resolutions

# -------------------------------
# FIXED V4L2 OUTPUT (v1.5 update)
# -------------------------------
def list_formats(camera, extended=False):

    # Read pixel format from camera (no hardcoding anymore)
    camera.writeReg(PIXFORMAT_INDEX_REG, 0)
    pix_type = camera.readReg(PIXFORMAT_TYPE_REG)
    pix_order = camera.readReg(PIXFORMAT_ORDER_REG)

    pix_name = pix_type_map.get(pix_type, "Unknown")

    # Determine FOURCC
    if pix_type in [0x18, 0x19, 0x1E]:
        fourcc = yuv_order.get(pix_order, "YUYV")
    elif pix_type in [0x2A, 0x2B, 0x2C]:
        fourcc = raw_bayer_order.get(pix_order, "RGGB")
    elif pix_type == 0x30:
        fourcc = "MJPG"
    else:
        fourcc = "UNKN"

    resolutions = enum_resolutions(camera)

    print("ioctl: VIDIOC_ENUM_FMT")
    print("        Type: Video Capture\n")

    for res in resolutions:
        idx = res["index"]
        width = res["width"]
        height = res["height"]
        fps = res["max_fps"]

        print(f"        [{idx}]: '{fourcc}' ({pix_name})")

        if extended:
            print(f"                Size: Discrete {width}x{height}")
            if fps:
                interval = 1.0 / fps
                print(f"                        Interval: Discrete {interval:.3f}s ({fps:.3f} fps)")

def get_software_fw_version(camera):
    version_length = camera.readReg(SOFT_VERSION_LEN_REG) 
    if version_length == NO_DATA_AVAILABLE or version_length > 255:
        return "None"
    
    version = ""
    for i in range(version_length):
        camera.writeReg(SOFT_VERSION_INDEX_REG, i)
        ch = camera.readReg(SOFT_VERSION_REG)
        if ch > 255:
            continue
        version += chr(ch)
    return version

def parse_isp_fw_version(isp_fw_version):
    isp_id = (isp_fw_version & 0xFFFF0000) >> 16
    isp_id_high = (isp_id & 0xFF00) >> 8
    isp_id_low = (isp_id & 0x00FF)
    isp_fw_date = (isp_fw_version & 0xFFFF) 
    isp_fw_year = isp_fw_date >> 9
    isp_fw_month = (isp_fw_date >> 5) & 0x0F
    isp_fw_day = isp_fw_date & 0x1F

    return f"v{isp_id_high:x}.{isp_id_low:02x} 20{isp_fw_year:02d}/{isp_fw_month:02d}/{isp_fw_day:02d}"

def main():
    parser = argparse.ArgumentParser(description="Arducam CLI")
    parser.add_argument("-b", "--bus", type=int, help="Specify I2C bus number")
    parser.add_argument("-d", "--device", type=str, help="Specify /dev/videoX device")
    parser.add_argument("--list-formats", action="store_true", help="List pixel formats")
    parser.add_argument("--list-formats-ext", action="store_true", help="List pixel formats, resolution and max framerate")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show version info")
    args = parser.parse_args()

    if args.bus is not None and args.device is not None:
        logging("Options -b and -d are mutually exclusive", Level.ERROR)
        sys.exit(1)

    if args.verbose:
        print("=================================")
        print(f"             arducli.py        ")
        print(f" arducam command line interface")
        print(f"            v.{VERSION_MJR}.{VERSION_MIN} / 2025")
        print("=================================")

    # Load mapping table
    if os.path.exists(DEFAULT_MAPPING_PATH):
        logging(f"Loading mapping table from {DEFAULT_MAPPING_PATH}")
        with open(DEFAULT_MAPPING_PATH) as f:
            mapping = json.load(f)
    else:
        logging("Mapping table not found, please run ardu_i2c_detect.py first.", Level.ERROR)
        sys.exit(1)

    # Determine devices to probe
    devices_to_probe = []
    if args.bus is not None:
        devices_to_probe.append({"bus": args.bus, "name": "manual"})
    elif args.device is not None:
        dev_name = os.path.basename(args.device)
        if dev_name not in mapping or not mapping[dev_name]:
            logging(f"No mapping found for device {args.device}", Level.ERROR)
            sys.exit(1)
        devices_to_probe.append({"bus": mapping[dev_name]["bus"], "name": dev_name})
    else:
        for dev_name, info in mapping.items():
            if info:
                devices_to_probe.append({"bus": info["bus"], "name": dev_name})

    # Probe devices
    for dev in devices_to_probe:
        try:
            camera = PivarietyCamera(dev["bus"])
        except RuntimeError as e:
            logging(str(e), Level.ERROR)
            continue

        if args.list_formats or args.list_formats_ext:
            list_formats(camera, extended=args.list_formats_ext)
            continue

        # Full info probe
        device_id = camera.readReg(DEVICE_ID_REG)
        device_version = camera.readReg(DEVICE_VERSION_REG)
        sensor_id = camera.readReg(FIRMWARE_SENSOR_ID_REG)
        isp_fw_version = camera.readReg(UNIQUE_ID_REG)

        logging(f"Device ID: 0x{device_id:02X}")
        logging(f"Device Version: 0x{device_version:02X}")
        logging(f"Sensor ID: 0x{sensor_id:04X}")
        logging(f"ISP FW Version: {parse_isp_fw_version(isp_fw_version)}")
        logging(f"Software FW Version: {get_software_fw_version(camera)}")

        pix_index = 0
        while True:
            camera.writeReg(PIXFORMAT_INDEX_REG, pix_index)
            val = camera.readReg(PIXFORMAT_INDEX_REG)
            if val == NO_DATA_AVAILABLE:
                break

            pix_type = camera.readReg(PIXFORMAT_TYPE_REG)
            bayer_order = camera.readReg(PIXFORMAT_ORDER_REG)
            lanes = camera.readReg(MIPI_LANES_REG)

            dtype = pix_type_map.get(pix_type, "Unknown")
            order = None

            if pix_type in [0x2A, 0x2B, 0x2C]:
                order = raw_bayer_order.get(bayer_order, "Unknown")
            elif pix_type in [0x18, 0x19, 0x1E]:
                order = yuv_order.get(bayer_order, "Unknown")

            if order:
                logging(f"PixelFormat Type: {dtype}, Order: {order}, Lanes: {lanes}")
            else:
                logging(f"PixelFormat Type: {dtype}, Lanes: {lanes}")

            # Resolutions
            resolutions = enum_resolutions(camera)
            for res in resolutions:
                idx = res["index"]
                width = res["width"]
                height = res["height"]
                maxfps = res["max_fps"]
                logging(f"index: {idx}, {width}x{height}")

                # Controls
                ctrl_index = 0
                while True:
                    camera.writeReg(CTRL_INDEX_REG, ctrl_index)
                    ctrl_id = camera.readReg(CTRL_ID_REG)
                    if ctrl_id == NO_DATA_AVAILABLE:
                        break

                    camera.writeReg(CTRL_VALUE_REG, 0)
                    wait_for_free()
                    max_val = camera.readReg(CTRL_MAX_REG)
                    min_val = camera.readReg(CTRL_MIN_REG)
                    def_val = camera.readReg(CTRL_DEF_REG)
                    logging(f"ID: 0x{ctrl_id:06X}, control_name: {ID_map.get(ctrl_id, 'Unknown')} MAX: {max_val}, MIN: {min_val}, DEF: {def_val}")
                    ctrl_index += 1

            pix_index += 1

        camera.writeReg(PIXFORMAT_INDEX_REG, 0)

if __name__ == "__main__":
    main()

