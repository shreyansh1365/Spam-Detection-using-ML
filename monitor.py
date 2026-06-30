import os
import hashlib
import mysql.connector
import time
import socket
import uuid
import getpass
import psutil
from datetime import datetime

import win32api
import win32file
import wmi


print("USB Monitoring Started...\n")

c = wmi.WMI()

def get_real_mac():

    for interface, addrs in psutil.net_if_addrs().items():

        stats = psutil.net_if_stats().get(interface)

        if not stats or not stats.isup:
            continue

        name = interface.lower()

        if (
            "vmware" in name
            or
            "virtual" in name
            or
            "vbox" in name
            or
            "loopback" in name
            or
            "hyper-v" in name
        ):
            continue

        for addr in addrs:

            if (
                "-" in str(addr.address)
                or
                ":" in str(addr.address)
            ):

                if len(addr.address) >= 17:

                    return addr.address

    return "UNKNOWN"


mac_address = get_real_mac()
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="midhani",
    database="usb_monitor"
)

cursor = conn.cursor()

def get_device_code(device_id):

    cursor.execute(
        """
        SELECT device_code
        FROM device_registry
        WHERE device_id=%s
        """,
        (device_id,)
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM device_registry
        """
    )

    count = cursor.fetchone()[0]

    code = f"DEV{count+1:03}"

    cursor.execute(
        """
        INSERT INTO device_registry
        (
        device_code,
        device_id
        )

        VALUES
        (
        %s,
        %s
        )
        """,
        (
            code,
            device_id
        )
    )

    conn.commit()

    return code

connected = {}

def get_hash(path):

    try:

        sha = hashlib.sha256()

        with open(
            path,
            "rb"
        ) as f:

            while True:

                chunk = f.read(
                    8192
                )

                if not chunk:
                    break

                sha.update(
                    chunk
                )

        return (
            sha.hexdigest()
        )

    except:

        return "UNKNOWN"
    
def scan_files(path):

    data = {}

    for root, dirs, files in os.walk(path):

        if "System Volume Information" in root:
            continue

        for file in files:

            fp = os.path.join(
                root,
                file
            )

            try:

                relative_path = os.path.relpath(fp, path)

                data[relative_path] = {

                    "hash":
                    get_hash(fp),

                    "size":
                    round(
                        os.path.getsize(fp)
                        /
                        1024
                        /
                        1024,
                        2
                    )

                }

            except:
                pass

    return data


previous_usb = {}
just_inserted = {}

while True:

    current = {}

    drives = (
        win32api
        .GetLogicalDriveStrings()
        .split("\000")[:-1]
    )

    for drive in drives:

        try:

            if (
                win32file.GetDriveType(
                    drive
                ) == 2
            ):

                for usb in c.Win32_DiskDrive():

                    if (
                        usb.InterfaceType
                        and
                        str(
                            usb.InterfaceType
                        ).upper()
                        == "USB"
                    ):

                        partitions = (
                            usb.associators(
                                "Win32_DiskDriveToDiskPartition"
                            )
                        )

                        matched = False

                        for p in partitions:

                            logical = (
                                p.associators(
                                    "Win32_LogicalDiskToPartition"
                                )
                            )

                            for ld in logical:

                                if (
                                    ld.DeviceID
                                    + "\\"
                                    ==
                                    drive
                                ):

                                    matched = True

                        if matched:

                            if drive in connected:
                                start_time = connected[drive]["start"]
                            else:
                                start_time = time.time()

                            current[
                                drive
                            ] = {

                                "name":
                                str(
                                    usb.Caption
                                ),

                                "id":
                                str(
                                    usb.PNPDeviceID
                                ),

                                "start":
                                start_time

                            }

                            break

        except Exception as e:

            print(
                "ERROR:",
                e
            )

    for drive in list(current):

        if drive not in connected:

            info = current[drive]
            device_code = get_device_code(info["id"])

            connected[drive] = info

            device_id = info["id"]

            previous_usb[device_id] = scan_files(drive + "\\")
            just_inserted[device_id] = True


            print("\nUSB INSERTED\n")
            print("Time:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            print("User:", getpass.getuser())
            print("System:", socket.gethostname())
            print("MAC Address:", mac_address.upper())
            print("Drive:", drive)
            print("USB Name:", info["name"])
            print("Device ID:", info["id"])
            print()
            print("Device code generated:", device_code)

            cursor.execute(
                """
                INSERT INTO usb_logs
                (
                event_time,
                username,
                system_name,
                drive_letter,
                usb_name,
                device_id,
                event_type,
                device_code,
                mac_address,
                duration_seconds
                )
                VALUES
                (
                NOW(),
                %s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                """,
                (
                    getpass.getuser(),
                    socket.gethostname(),
                    drive,
                    info["name"],
                    info["id"],
                    "INSERT",
                    device_code,
                    mac_address,
                    0,
                )
            )
            conn.commit()

    for drive in list(current):

        device_id = current[drive]["id"]

        now = scan_files(drive + "\\")
        if len(now) == 0:
           continue
        old = previous_usb.get(device_id, {})
        if just_inserted.get(device_id):
            previous_usb[device_id] = now
            just_inserted.pop(device_id)
            continue
        

        for file in now:
            if (
    file not in old
    or
    old[file]["hash"] != now[file]["hash"]
):
                print("PC → USB", file)
                cursor.execute(
                    """
                    INSERT INTO transfer_logs(
                    event_time,
                    username,
                    system_name,
                    device_code,
                    direction,
                    file_name,
                    file_size_mb,
                    sha256
                    )
                    VALUES(
                    NOW(),
                    %s,%s,%s,%s,%s,%s,%s
                    )
                    """,
                    (
                        getpass.getuser(),
                        socket.gethostname(),
                        get_device_code(current[drive]["id"]),
                        "PC_TO_USB",
                        file,
                        now[file]["size"],
                        now[file]["hash"]
                    )
                )
                conn.commit()

        for file in old:

         if file not in now:

           print("USB DELETE ->", file)

           cursor.execute(
            """
            INSERT INTO transfer_logs(
                event_time,
                username,
                system_name,
                device_code,
                direction,
                file_name,
                file_size_mb,
                sha256
            )
            VALUES(
                NOW(),
                %s,%s,%s,%s,%s,%s,%s
            )
            """,
            (
                getpass.getuser(),
                socket.gethostname(),
                get_device_code(current[drive]["id"]),
                "USB_DELETE",
                file,
                old[file]["size"],
                old[file]["hash"]
            )
        )

           conn.commit()
               

        previous_usb[device_id] = now

    for drive in list(connected):
        if drive not in current:
            duration = int(time.time() - connected[drive]["start"])

            print("\nUSB REMOVED\n")
            print("Time:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            print("Drive:", drive)
            print("USB Name:", connected[drive]["name"])
            print("Duration Connected:", duration, "seconds")
            print()

            cursor.execute(
                """
                INSERT INTO usb_logs(
                    event_time,
                    username,
                    system_name,
                    mac_address,
                    drive_letter,
                    usb_name,
                    device_id,
                    event_type,
                    duration_seconds
                )
                VALUES(
                    NOW(),
                    %s,%s,%s,%s,%s,%s,%s,%s
                )
                """,
                (
                    getpass.getuser(),
                    socket.gethostname(),
                    mac_address,
                    drive,
                    connected[drive]["name"],
                    connected[drive]["id"],
                    "REMOVE",
                    duration,
                )
            )
            conn.commit()

            device_id = connected[drive]["id"]

            del connected[drive]

            previous_usb.pop(device_id, None)
            just_inserted.pop(device_id, None)

    time.sleep(3)