#!/usr/bin/env python3
import subprocess
import sys
import re
import time
import glob
import os
import argparse
import json

# Optional YAML support
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# Known sensor names
SENSOR_NAMES = [
    "arducam-pivariety",
    # Add other sensors here
]

# GStreamer settings
NUM_BUFFERS = 20
DELAY_AFTER_TRIGGER = 0.5  # seconds
DEFAULT_TABLE_PATH = "/opt/arducam/arducam_i2c_map.json"


def clear_dmesg():
    """Clear kernel log buffer"""
    try:
        subprocess.run(["dmesg", "-C"], check=True)
        print("[+] Cleared dmesg buffer")
    except Exception as e:
        print("[-] Failed to clear dmesg:", e)


def trigger_sensor(video_dev):
    """Trigger sensor I2C activity via GStreamer"""
    print(f"[+] Triggering {video_dev} via GStreamer ({NUM_BUFFERS} buffers)...")
    pipeline = [
        "gst-launch-1.0", "-q",
        "v4l2src", f"device={video_dev}", f"num-buffers={NUM_BUFFERS}", "!", "video/x-raw,format=YUY2" ,"!", "fakesink"
    ]
    try:
        subprocess.run(pipeline, check=True)
        time.sleep(DELAY_AFTER_TRIGGER)
        return True
    except subprocess.CalledProcessError:
        print(f"[-] GStreamer pipeline failed for {video_dev}")
        return False


def parse_i2c_bus_from_dmesg(sensor_name):
    """Parse dmesg to detect I2C bus number"""
    try:
        dmesg_output = subprocess.check_output(["dmesg"], text=True)
    except Exception as e:
        print("[-] Failed to read dmesg:", e)
        return []

    buses = set()
    pattern = re.compile(rf"{re.escape(sensor_name)}\s+(\d+)-[0-9a-fA-F]+:")
    for line in dmesg_output.splitlines():
        if sensor_name in line:
            m = pattern.search(line)
            if m:
                buses.add(f"i2c-{m.group(1)}")
    return list(buses)


def detect_i2c_for_device(video_dev, sensor_names):
    """Detect I2C bus(es) for a given /dev/videoX"""
    clear_dmesg()
    success = trigger_sensor(video_dev)
    if not success:
        # Skip parsing if pipeline failed
        return {sensor: None for sensor in sensor_names}

    detected = {}
    for sensor in sensor_names:
        buses = parse_i2c_bus_from_dmesg(sensor)
        if buses:
            detected[sensor] = buses
        else:
            detected[sensor] = None
    return detected


def scan_all_devices(sensor_names):
    """Scan all /dev/video* devices and build mapping"""
    video_devs = sorted(glob.glob("/dev/video*"))
    mapping = {}
    for video_dev in video_devs:
        if "subdev" in video_dev:
            continue
        detected = detect_i2c_for_device(video_dev, sensor_names)

        entry = None
        for sensor, buses in detected.items():
            if buses:
                bus_name = buses[0]
                bus_num = int(bus_name.split("-")[1])
                entry = {"bus": bus_num, "addr": f"0x0c", "sensor": sensor}
                break
        mapping[os.path.basename(video_dev)] = entry
    return mapping


def save_mapping_table(mapping, path=None):
    if path is None:
        path = DEFAULT_TABLE_PATH

    if os.path.isdir(path):
        path = os.path.join(path, "arducam_i2c_map.json")

    os.makedirs(os.path.dirname(path), exist_ok=True)

    ext = os.path.splitext(path)[1].lower()
    if ext in ['.yaml', '.yml']:
        if not YAML_AVAILABLE:
            print("[-] PyYAML not installed, cannot save YAML")
            return
        with open(path, "w") as f:
            yaml.dump(mapping, f, default_flow_style=False)
    else:
        with open(path, "w") as f:
            json.dump(mapping, f, indent=4)
    print(f"[+] Saved mapping table to {path}")


def main():
    parser = argparse.ArgumentParser(description="Detect I2C bus for cameras")
    parser.add_argument("video_dev", nargs="?", help="Optional /dev/videoX device to scan")
    parser.add_argument("-t", "--table", nargs="?", const=True,
                        help="Save mapping table (optionally specify path/filename)")
    args = parser.parse_args()

    if args.video_dev:
        if not os.path.exists(args.video_dev):
            print(f"[-] {args.video_dev} does not exist")
            sys.exit(1)
        detected = detect_i2c_for_device(args.video_dev, SENSOR_NAMES)
        for sensor, buses in detected.items():
            if buses:
                print(f"[+] {args.video_dev} → sensor '{sensor}' on bus(es): {', '.join(buses)}")
            else:
                print(f"[-] {args.video_dev} → sensor '{sensor}': bus not detected")
    else:
        mapping = scan_all_devices(SENSOR_NAMES)
        for video, val in mapping.items():
            if val:
                print(f"[+] {video} → bus {val['bus']}, addr {val['addr']}, sensor {val['sensor']}")
            else:
                print(f"[-] {video} → no sensor detected")
        if args.table:
            path = args.table if isinstance(args.table, str) else None
            save_mapping_table(mapping, path)


if __name__ == "__main__":
    main()
