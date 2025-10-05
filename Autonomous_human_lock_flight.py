from djitellopy import Tello
from ultralytics import YOLO
import cv2
import pygame
import time
import threading
import os
from datetime import datetime
import json

# Initialize Pygame
pygame.init()
pygame.joystick.init()

print("Searching for controllers...")
if pygame.joystick.get_count() == 0:
    print("❌ No controller found!")
    exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()
print(f"✅ Controller: {joystick.get_name()}")

# Button Mapping
PS5_BUTTONS = {
    'X': 0, 'CIRCLE': 1, 'SQUARE': 2, 'L1': 9, 'R1': 10,
    'L2': 6, 'R2': 7, 'SHARE': 4, 'PS': 5, 'TRIANGLE': 3
}

# Create directories
os.makedirs('sar_photos', exist_ok=True)
os.makedirs('sar_videos', exist_ok=True)
os.makedirs('profiles', exist_ok=True)

# Search and Rescue Profiles with HUMAN LOCK profile
SAR_PROFILES = {
    'manual_flight': {
        'name': '✈️ Manual Flight',
        'priority_objects': ['person', 'backpack', 'cell phone', 'chair', 'laptop', 'cup', 'book'],
        'search_pattern': 'manual',
        'altitude': 3,
        'speed': 40,
        'description': 'Full manual control with object detection display'
    },
    'human_lock': {
        'name': '🎯 Human Lock',
        'priority_objects': ['person'],  # ONLY look for humans
        'search_pattern': 'autonomous_scan',
        'altitude': 2,
        'speed': 20,
        'description': 'Autonomous human detection and tracking (2m indoor)'
    },
    'urban_rescue': {
        'name': '🏙️ Urban Rescue',
        'priority_objects': ['person', 'backpack', 'cell phone', 'handbag'],
        'search_pattern': 'grid',
        'altitude': 8,
        'speed': 30,
        'description': 'Search for people and personal items in urban areas'
    },
    'wilderness_search': {
        'name': '🌲 Wilderness Search',
        'priority_objects': ['person', 'backpack', 'suitcase', 'sports ball'],
        'search_pattern': 'spiral',
        'altitude': 12,
        'speed': 20,
        'description': 'Search for missing persons in natural environments'
    },
    'indoor_search': {
        'name': '🏠 Indoor Search',
        'priority_objects': ['person', 'cell phone', 'remote', 'book', 'laptop', 'bottle', 'cup'],
        'search_pattern': 'slow_grid',
        'altitude': 4,
        'speed': 15,
        'description': 'Search for people and common items in indoor spaces'
    },
    'small_room': {
        'name': '📦 Small Room Scan',
        'priority_objects': ['person', 'cell phone', 'remote', 'keyboard', 'mouse', 'cup'],
        'search_pattern': 'hover_scan',
        'altitude': 3,
        'speed': 10,
        'description': 'Detailed scan of small rooms and tight spaces'
    }
}

# Autonomous mission state
autonomous_state = {
    'phase': 'idle',  # idle, lifting, scanning, locking, approaching, holding
    'target_person': None,
    'scan_start_time': 0,
    'lock_start_time': 0,
    'current_yaw': 0,
    'scan_complete': False
}


# Save profiles to file
def save_profiles():
    with open('profiles/sar_profiles.json', 'w') as f:
        json.dump(SAR_PROFILES, f, indent=2)


# Load profiles from file
def load_profiles():
    global SAR_PROFILES
    try:
        with open('profiles/sar_profiles.json', 'r') as f:
            SAR_PROFILES.update(json.load(f))
    except FileNotFoundError:
        print("📁 No saved profiles found, using defaults")


# Controller state with profile support
controller_state = {
    'left_right': 0, 'forward_back': 0, 'up_down': 0, 'yaw': 0,
    'takeoff': False, 'land': False, 'emergency': False,
    'detection_enabled': True, 'take_photo': False, 'toggle_recording': False,
    'change_profile': False, 'start_autonomous': False
}

# Mission state
mission_state = {
    'current_profile': 'human_lock',  # Start with human lock profile
    'autonomous_mode': False,
    'objects_found': [],
    'mission_start_time': 0,
    'search_pattern_active': False
}

# Recording state
recording_state = {
    'is_recording': False, 'video_writer': None, 'video_filename': None,
    'photo_count': 0, 'recording_start_time': 0
}


def setup_video_writer(frame_width, frame_height):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sar_videos/sar_mission_{timestamp}.avi"
    codec = cv2.VideoWriter_fourcc(*'MJPG')
    fps = 10.0
    video_writer = cv2.VideoWriter(filename, codec, fps, (frame_width, frame_height))
    return video_writer, filename


def take_screenshot(display_frame, detections_info):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sar_photos/sar_photo_{timestamp}.jpg"
        success = cv2.imwrite(filename, display_frame)
        if success:
            recording_state['photo_count'] += 1
            print(f"✅ Screenshot: {filename}")
        return success
    except Exception as e:
        print(f"❌ Screenshot error: {e}")
        return False


def get_priority_objects():
    """Get priority objects from current profile"""
    profile = SAR_PROFILES[mission_state['current_profile']]
    return profile['priority_objects']


def analyze_detections(results, model):
    """Analyze detections based on current profile - ONLY humans for human_lock"""
    profile = SAR_PROFILES[mission_state['current_profile']]
    priority_objects = profile['priority_objects']

    detections = {}
    priority_detections = {}

    if results[0].boxes is not None:
        for box in results[0].boxes:
            class_id = int(box.cls[0])
            class_name = model.names[class_id]
            confidence = float(box.conf[0])

            # For human_lock profile, ONLY detect humans
            if mission_state['current_profile'] == 'human_lock' and class_name != 'person':
                continue  # Skip all non-human objects

            if confidence > 0.5:
                if class_name not in detections:
                    detections[class_name] = 0
                detections[class_name] += 1

                # Check if this is a priority object
                if class_name in priority_objects:
                    if class_name not in priority_detections:
                        priority_detections[class_name] = []
                    priority_detections[class_name].append({
                        'confidence': confidence,
                        'position': box.xyxy[0].tolist(),
                        'timestamp': time.time()
                    })

                    # Log important findings
                    if class_name not in mission_state['objects_found']:
                        mission_state['objects_found'].append(class_name)
                        print(f"🚨 PRIORITY OBJECT FOUND: {class_name}!")

    return detections, priority_detections


def autonomous_human_lock(tello, frame, results, model):
    """Autonomous human lock OR manual flight based on profile"""
    current_profile = SAR_PROFILES[mission_state['current_profile']]

    # MANUAL FLIGHT MODE - Just show detections, no autonomous behavior
    if mission_state['current_profile'] == 'manual_flight':
        # In manual mode, we only analyze detections for display
        # No autonomous control - user has full control
        if autonomous_state['phase'] != 'manual':
            print("🎮 Manual Flight Mode - Full control enabled")
            autonomous_state['phase'] = 'manual'
        return  # Exit autonomous function, return control to user

    # AUTONOMOUS MODE (only for human_lock profile)
    if mission_state['current_profile'] != 'human_lock':
        return  # Exit if not in human_lock profile

    # ... rest of your existing autonomous code for human_lock ...
    # Phase 1: Lifting
    if autonomous_state['phase'] == 'idle':
        print("🚀 Starting autonomous human lock sequence...")
        autonomous_state['phase'] = 'lifting'
        autonomous_state['scan_start_time'] = time.time()
        autonomous_state['total_rotation'] = 0

    elif autonomous_state['phase'] == 'lifting':
        # Lift to 2 meters (safe indoor altitude)
        tello.send_rc_control(0, 0, 30, 0)  # Move up
        time.sleep(0.1)
        tello.send_rc_control(0, 0, 0, 0)  # Stop

        # Check if we've lifted enough
        if time.time() - autonomous_state['scan_start_time'] > 2.0:  # 2 seconds of lifting
            print("📡 Reached 2m altitude, starting 360° scan...")
            autonomous_state['phase'] = 'scanning'
            autonomous_state['scan_start_time'] = time.time()
            autonomous_state['total_rotation'] = 0

    # Phase 2: 360° Scan - FIXED COMPLETE ROTATION
    elif autonomous_state['phase'] == 'scanning':
        # Rotate at consistent speed
        rotation_speed = 15  # Slow and steady
        tello.send_rc_control(0, 0, 0, rotation_speed)

        # Update total rotation (approx 15° per 0.1 second)
        autonomous_state['total_rotation'] += 3  # Approximate degrees per loop

        print(f"🔄 Scanning... Rotated: {autonomous_state['total_rotation']}°")

        # Check for complete 360° rotation
        if autonomous_state['total_rotation'] >= 360:
            print("✅ 360° scan complete!")
            tello.send_rc_control(0, 0, 0, 0)  # Stop rotation
            autonomous_state['phase'] = 'scan_complete'
            autonomous_state['scan_complete_time'] = time.time()

        # Check for humans during scan
        if results[0].boxes is not None:
            for box in results[0].boxes:
                class_id = int(box.cls[0])
                class_name = model.names[class_id]
                if class_name == 'person' and float(box.conf[0]) > 0.6:
                    print("🎯 HUMAN DETECTED during scan! Locking on...")
                    autonomous_state['phase'] = 'locking'
                    autonomous_state['target_person'] = {
                        'position': box.xyxy[0].tolist(),
                        'confidence': float(box.conf[0]),
                        'lock_time': time.time()
                    }
                    tello.send_rc_control(0, 0, 0, 0)  # Stop rotation
                    break

    # Phase 3: Scan complete but no human found
    elif autonomous_state['phase'] == 'scan_complete':
        if not autonomous_state.get('target_person'):
            print("❌ No human found during 360° scan. Hovering...")
            tello.send_rc_control(0, 0, 0, 0)
            # Option: could restart scan after a delay
            if time.time() - autonomous_state['scan_complete_time'] > 5:
                print("🔄 Restarting scan...")
                autonomous_state['phase'] = 'scanning'
                autonomous_state['total_rotation'] = 0

    # ... rest of the phases (locking, approaching, holding) remain the same


def read_controller():
    print("🕹️ Controller reader started...")

    while True:
        try:
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    print(f"🔘 Button {event.button} pressed")

                    if event.button == PS5_BUTTONS['X']:
                        controller_state['takeoff'] = True
                    elif event.button == PS5_BUTTONS['CIRCLE']:
                        controller_state['land'] = True
                    elif event.button == PS5_BUTTONS['SQUARE']:
                        controller_state['emergency'] = True
                    elif event.button == PS5_BUTTONS['R1']:
                        controller_state['take_photo'] = True
                    elif event.button == PS5_BUTTONS['L1']:
                        controller_state['toggle_recording'] = True
                    elif event.button == PS5_BUTTONS['SHARE']:
                        controller_state['detection_enabled'] = not controller_state['detection_enabled']
                    elif event.button == PS5_BUTTONS['TRIANGLE']:
                        controller_state['change_profile'] = True
                    elif event.button == PS5_BUTTONS['PS']:
                        print("⏹️ PS Button - Quitting!")

            # Read analog sticks with LARGER deadzone for drift
            left_x, left_y = joystick.get_axis(0), joystick.get_axis(1)
            right_x = joystick.get_axis(2)

            # 🚨 INCREASED DEADZONE FROM 0.1 TO 0.25 TO FIX DRIFT
            deadzone = 0.25  # Much larger deadzone - joystick must move 25% before registering

            # Only send commands if outside deadzone
            controller_state['left_right'] = int(left_x * 100) if abs(left_x) > deadzone else 0
            controller_state['forward_back'] = int(-left_y * 100) if abs(left_y) > deadzone else 0
            controller_state['yaw'] = int(right_x * 100) if abs(right_x) > deadzone else 0

            # Debug drift (uncomment if you want to see the values)
            # if any([abs(left_x) > 0.1, abs(left_y) > 0.1, abs(right_x) > 0.1]):
            #     print(f"Sticks - X:{left_x:.2f}, Y:{left_y:.2f}, R:{right_x:.2f}")

            l2_axis = joystick.get_axis(4)
            r2_axis = joystick.get_axis(5)

            l2_value = max(0, int((l2_axis + 1) * 50))
            r2_value = max(0, int((r2_axis + 1) * 50))

            # Triggers need less movement to activate (they're more precise)
            trigger_deadzone = 0.1
            if r2_value > 10 and l2_value <= 10:
                controller_state['up_down'] = r2_value
            elif l2_value > 10 and r2_value <= 10:
                controller_state['up_down'] = -l2_value
            else:
                controller_state['up_down'] = 0

            time.sleep(0.01)
        except Exception as e:
            print(f"Controller error: {e}")


def main():
    tello = Tello()
    model = YOLO('yolov8n.pt')

    # Load saved profiles
    load_profiles()

    print("🚀 Connecting to Tello...")
    tello.connect()
    battery = tello.get_battery()
    print(f"🔋 Battery: {battery}%")

    tello.streamon()
    time.sleep(2)

    controller_thread = threading.Thread(target=read_controller, daemon=True)
    controller_thread.start()

    print("\n🎮 AUTONOMOUS HUMAN LOCK CONTROLS:")
    print("X Button: Takeoff + Start Autonomous")
    print("Circle Button: Land + Stop Autonomous")
    print("Square Button: Emergency Stop")
    print("R1 Button: 📸 Screenshot")
    print("L1 Button: 🎥 Recording")
    print("Share Button: Toggle Detection")
    print("Triangle Button: 🔄 Change Profile")
    print("PS Button: Quit")
    print("=" * 50)
    print("🤖 AUTONOMOUS SEQUENCE:")
    print("1. Lift to 6m altitude")
    print("2. 360° scan for humans")
    print("3. Lock on first human detected")
    print("4. Approach and maintain distance")
    print("5. Hold position")
    print("=" * 50)

    flying = False
    profile_index = 0
    profile_keys = list(SAR_PROFILES.keys())

    try:
        while True:
            raw_frame = tello.get_frame_read().frame
            if raw_frame is None:
                time.sleep(0.1)
                continue

            display_frame = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2RGB)

            # Handle profile change (Triangle button)
            if controller_state['change_profile']:
                profile_index = (profile_index + 1) % len(profile_keys)
                mission_state['current_profile'] = profile_keys[profile_index]
                current_profile = SAR_PROFILES[mission_state['current_profile']]
                print(f"🔄 Profile changed to: {current_profile['name']}")
                print(f"   Priority objects: {', '.join(current_profile['priority_objects'])}")
                controller_state['change_profile'] = False

            # Object detection with profile-based analysis
            detections_info = "None"
            priority_info = ""
            results = None

            if controller_state['detection_enabled']:
                results = model(display_frame, verbose=False)
                if len(results) > 0:
                    annotated_frame = results[0].plot()
                    display_frame = annotated_frame

                    # Analyze detections based on current profile
                    detections, priority_detections = analyze_detections(results, model)

                    if detections:
                        detections_info = ", ".join([f"{k}:{v}" for k, v in detections.items()])

                    if priority_detections:
                        priority_info = "PRIORITY: " + ", ".join(
                            [f"{k}({len(v)})" for k, v in priority_detections.items()])

            # Handle autonomous mode for human_lock profile
            if (mission_state['current_profile'] == 'human_lock' and
                    flying and
                    controller_state['detection_enabled'] and
                    results is not None):
                autonomous_human_lock(tello, raw_frame, results, model)

            # Handle screenshot
            if controller_state['take_photo']:
                take_screenshot(display_frame, detections_info)
                controller_state['take_photo'] = False

            # Handle recording
            if controller_state['toggle_recording']:
                if not recording_state['is_recording']:
                    h, w = display_frame.shape[:2]
                    recording_state['video_writer'], recording_state['video_filename'] = setup_video_writer(w, h)
                    recording_state['is_recording'] = True
                    recording_state['recording_start_time'] = time.time()
                    print(f"🎥 Recording STARTED")
                else:
                    recording_state['video_writer'].release()
                    recording_state['is_recording'] = False
                    duration = time.time() - recording_state['recording_start_time']
                    print(f"⏹️ Recording STOPPED: {duration:.1f}s")
                controller_state['toggle_recording'] = False

            # Write video
            if recording_state['is_recording']:
                recording_state['video_writer'].write(display_frame)
                rec_time = time.time() - recording_state['recording_start_time']
                cv2.putText(display_frame, f"🔴 REC {rec_time:.1f}s", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (255, 0, 0), 2)

            # UI Overlay with autonomous status
            current_profile = SAR_PROFILES[mission_state['current_profile']]

            cv2.putText(display_frame, f"Profile: {current_profile['name']}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 0), 2)

            # Show autonomous status
            if mission_state['current_profile'] == 'human_lock' and flying:
                status_color = (0, 255, 255)  # Yellow for autonomous
                cv2.putText(display_frame, f"AUTONOMOUS: {autonomous_state['phase'].upper()}", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
            else:
                cv2.putText(display_frame, f"Detections: {detections_info}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 255, 0), 2)

            if priority_info:
                cv2.putText(display_frame, priority_info, (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            status = "FLYING" if flying else "READY"
            color = (0, 255, 0) if flying else (0, 255, 255)
            cv2.putText(display_frame, f"Status: {status}", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            cv2.putText(display_frame, f"Photos: {recording_state['photo_count']}", (10, 150), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (255, 255, 255), 1)
            cv2.putText(display_frame, f"Battery: {tello.get_battery()}%", (10, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255, 255, 255), 1)

            # Autonomous phase info
            if mission_state['current_profile'] == 'human_lock':
                cv2.putText(display_frame, f"Phase: {autonomous_state['phase']}", (10, 190), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (255, 255, 255), 1)
                if autonomous_state['target_person']:
                    cv2.putText(display_frame, "TARGET LOCKED", (10, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0),
                                1)

            # Controls help
            cv2.putText(display_frame, "X: Start Auto | Circle: Land | Triangle: Profile", (10, 230),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            # Flight controls
            # Flight controls - Different behavior based on profile
            if controller_state['takeoff'] and not flying:
                tello.takeoff()
                flying = True
                mission_state['mission_start_time'] = time.time()

                # Initialize autonomous state only for human_lock profile
                if mission_state['current_profile'] == 'human_lock':
                    autonomous_state['phase'] = 'lifting'
                    autonomous_state['scan_start_time'] = time.time()
                    autonomous_state['lock_start_time'] = time.time()
                    print("🤖 Autonomous human lock sequence initiated!")
                else:
                    autonomous_state['phase'] = 'manual'
                    print("🎮 Manual flight mode active!")

                controller_state['takeoff'] = False

            elif controller_state['land'] and flying:
                tello.land()
                flying = False
                autonomous_state['phase'] = 'idle'
                autonomous_state['target_person'] = None
                controller_state['land'] = False

            elif controller_state['emergency']:
                tello.emergency()
                flying = False
                autonomous_state['phase'] = 'idle'
                autonomous_state['target_person'] = None
                controller_state['emergency'] = False

            # Manual control logic - updated for all profiles except active human_lock autonomous
            if flying:
                # If we're in manual flight mode OR not in active human_lock autonomous phase
                if (mission_state['current_profile'] == 'manual_flight' or
                        mission_state['current_profile'] != 'human_lock' or
                        autonomous_state['phase'] in ['idle', 'manual', 'holding', 'scan_complete']):
                    tello.send_rc_control(
                        controller_state['left_right'],
                        controller_state['forward_back'],
                        controller_state['up_down'],
                        controller_state['yaw']
                    )

            cv2.imshow(f"Tello SAR - {current_profile['name']}", display_frame)

            if joystick.get_button(PS5_BUTTONS['PS']):
                break
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            time.sleep(0.03)

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if flying:
            tello.land()
        if recording_state['is_recording']:
            recording_state['video_writer'].release()
        tello.streamoff()
        cv2.destroyAllWindows()
        pygame.quit()

        # Mission summary
        print(f"\n📊 MISSION SUMMARY:")
        print(f"   Profile: {SAR_PROFILES[mission_state['current_profile']]['name']}")
        print(f"   Photos taken: {recording_state['photo_count']}")
        print(f"   Autonomous Phase: {autonomous_state['phase']}")
        if autonomous_state['target_person']:
            print(f"   Target Locked: YES")
        print("✅ Mission complete!")


if __name__ == "__main__":
    main()