# arducli
This is a command line tool that leverages the Arducam i2c protocol to retrieve low-level
information from the camera module attached to a MIPI-CSI bus.

On some platforms (like ASTRIAL) we have some limitations that prevent v4l2-ctrl to correclty
expose all the parameters from Arducam modules. On top of this we can also retrieve extra
information for remote debugging about sensor type and camera firmware version.

# installation
Your platform does need python and some extra python extension (smbus) to use I2C commands.
Clone this repo and copy the content under the folder

```
/opt/arducam
```

which is the default location to be used for these scripts.
simple command line to use arducam i2c protocol and retrieve camera modules low-level information 

NOTE: it is mandatory to create /opt/arducam since the tool does save a mapping of all the csi devices
using file:

```
/opt/arducam/arducam_i2c_map.json
```

if you change the platform setuo by adding/removing CSI cameras please delete this file and re-run the tool

# usage
Upon installation run (once) the camera detection with the command:

```
/opt/arducam/ardu_i2c_detect.py -t /opt/arducam/arducam_i2c_map.json
```

Once installed you can use the tool in different ways.
## direct access to the i2c bus
If you know the I2C numbering (for example number 1) for your camera module you can probe that device direclty like this:

```
/opt/arducam/arducli.py -b 1
```

you will get all the parameters exposed by your camera module like this:

```
[INFO]: Loading mapping table from /opt/arducam/arducam_i2c_map.json
[INFO]: Device ID: 0x30
[INFO]: Device Version: 0x10
[INFO]: Sensor ID: 0xA56
[INFO]: PixelFormat Type: YUV422_8BIT, Order: UYVY, Lanes: 4
[INFO]: index: 0, 3840x2160
[INFO]: ID: 0x981906, control_name: Framerate MAX: 90, MIN: 1, DEF: 90
[INFO]: ID: 0x980911, control_name: Exposure MAX: 11111, MIN: 0, DEF: 0
[INFO]: ID: 0x9E0903, control_name: AnalogueGain MAX: 2239, MIN: 0, DEF: 0
[INFO]: ID: 0x9A090A, control_name: Focus MAX: 1023, MIN: 0, DEF: 210
[INFO]: ID: 0x98091C, control_name: backlight_compensation MAX: 1, MIN: 0, DEF: 0
[INFO]: ID: 0x98090C, control_name: AWBMode MAX: 1, MIN: 0, DEF: 1
[INFO]: ID: 0x98090E, control_name: RedGain MAX: 500, MIN: 100, DEF: 100
[INFO]: ID: 0x98090F, control_name: BlueGain MAX: 500, MIN: 100, DEF: 100
[INFO]: ID: 0x98091A, control_name: ColorTemperature MAX: 11000, MIN: 1000, DEF: 1000
[INFO]: ID: 0x980902, control_name: Saturation MAX: 1600, MIN: 0, DEF: 100

```
## indirect access from device name
If your camera is visible under the /dev/videoXX location it means it can be probed with a command like this:

```
/opt/arducam/arducli.py -d /dev/video4
```

NOTE: bus and device options are mutually exclusive.

# V4L2 notation
Sometime it is useful to have the same output style of Video4Linux so we have two more options to mimic the same output format

## --list-formats
Using this option you can type:

```
/opt/arducam/arducli.py -d /dev/video4 --list-formats
```

and you'll see something like:

```
[INFO]: Loading mapping table from /opt/arducam/arducam_i2c_map.json
        [0]: 'YUV422_8BIT' (YUV422_8BIT)
        [1]: 'YUV422_8BIT' (YUV422_8BIT)
        [2]: 'YUV422_8BIT' (YUV422_8BIT)
```

where each line is related to a different resolution

## --list-formats-ext
To get the full list of resoltutions and framerates use:

```
/opt/arducam/arducli.py -d /dev/video4 --list-formats-ext
```

and you should see something similar to:

```
[INFO]: Loading mapping table from /opt/arducam/arducam_i2c_map.json
        [0]: 'YUV422_8BIT' (YUV422_8BIT)
                Size: Discrete 3840x2160
                        Interval: Discrete 0.033s (15 fps)
        [1]: 'YUV422_8BIT' (YUV422_8BIT)
                Size: Discrete 1920x1080
                        Interval: Discrete 0.033s (60 fps)
        [2]: 'YUV422_8BIT' (YUV422_8BIT)
                Size: Discrete 1280x720
                        Interval: Discrete 0.033s (90 fps)
```
