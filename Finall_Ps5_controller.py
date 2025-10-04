from djitellopy import Tello
from ultralytics import YOLO
import cv2
import pygame
import time
import threading
import os
from datetime import datetime

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

# UPDATED BUTTON MAPPING
PS5_BUTTONS = {
    'X': 0,  # Takeoff
    'CIRCLE': 1,  # Land
    'SQUARE': 2,  # Emergency Stop
    'L1': 9,  # Start/Stop Recording
    'R1': 10,  # Take Screenshot
    'L2': 6,  # Down trigger (button)
    'R2': 7,  # Up trigger (button)
    'SHARE': 4,  # Toggle Detection - CHANGED TO 4
    'PS': 5,  # Quit
}

# Create directories
os.makedirs('sar_photos', exist_ok=True)
os.makedirs('sar_videos', exist_ok=True)

# Controller state
controller_state = {
    'left_right': 0, 'forward_back': 0, 'up_down': 0, 'yaw': 0,
    'takeoff': False, 'land': False, 'emergency': False,
    'detection_enabled': True, 'take_photo': False, 'toggle_recording': False
}

# Recording state
recording_state = {
    'is_recording': False, 'video_writer': None, 'video_filename': None,
    'photo_count': 0, 'recording_start_time': 0
}


def correct_tello_colors(frame):
    """Fix Tello's color issues"""
    if frame is None or frame.size == 0:
        return frame

    # Convert from BGR to RGB (Tello sends BGR, but we need RGB for display)
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Adjust colors to look more natural
    frame_corrected = cv2.convertScaleAbs(frame_rgb, alpha=1.3, beta=10)

    return frame_corrected


def setup_video_writer(frame_width, frame_height):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sar_videos/sar_mission_{timestamp}.avi"
    codec = cv2.VideoWriter_fourcc(*'XVID')
    video_writer = cv2.VideoWriter(filename, codec, 20.0, (frame_width, frame_height))
    return video_writer, filename


def take_screenshot(frame, detections_info):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sar_photos/sar_photo_{timestamp}.jpg"

        # Convert back to BGR for saving (OpenCV imwrite expects BGR)
        save_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR) if len(frame.shape) == 3 else frame

        success = cv2.imwrite(filename, save_frame)
        if success:
            recording_state['photo_count'] += 1
            print(f"✅ Screenshot saved: {filename}")
            print(f"   Detections: {detections_info}")
        return success
    except Exception as e:
        print(f"❌ Screenshot error: {e}")
        return False


def read_controller():
    print("🕹️ Controller reader started...")

    while True:
        try:
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    print(f"🔘 Button {event.button} pressed")

                    # Map buttons based on YOUR controller mapping
                    if event.button == PS5_BUTTONS['X']:
                        controller_state['takeoff'] = True
                        print("🛫 X Button - Takeoff!")
                    elif event.button == PS5_BUTTONS['CIRCLE']:
                        controller_state['land'] = True
                        print("🛬 Circle Button - Land!")
                    elif event.button == PS5_BUTTONS['SQUARE']:
                        controller_state['emergency'] = True
                        print("🆘 Square Button - Emergency Stop!")
                    elif event.button == PS5_BUTTONS['R1']:  # SCREENSHOT
                        controller_state['take_photo'] = True
                        print("📸 R1 Button - Screenshot!")
                    elif event.button == PS5_BUTTONS['L1']:  # RECORDING
                        controller_state['toggle_recording'] = True
                        print("🎥 L1 Button - Recording Toggle!")
                    elif event.button == PS5_BUTTONS['SHARE']:  # DETECTION TOGGLE - NOW BUTTON 4
                        controller_state['detection_enabled'] = not controller_state['detection_enabled']
                        status = "ENABLED" if controller_state['detection_enabled'] else "DISABLED"
                        print(f"🔍 Share Button - Detection: {status}")
                    elif event.button == PS5_BUTTONS['PS']:  # QUIT
                        print("⏹️ PS Button - Quitting!")

            # Read analog sticks
            left_x, left_y = joystick.get_axis(0), joystick.get_axis(1)
            right_x = joystick.get_axis(2)

            # Deadzone
            deadzone = 0.1
            controller_state['left_right'] = int(left_x * 100) if abs(left_x) > deadzone else 0
            controller_state['forward_back'] = int(-left_y * 100) if abs(left_y) > deadzone else 0
            controller_state['yaw'] = int(right_x * 100) if abs(right_x) > deadzone else 0

            # FIXED: Read trigger axes instead of buttons for R2/L2
            # PS5 triggers are usually axes 4 (L2) and 5 (R2)
            # They range from -1 (released) to 1 (fully pressed)
            l2_axis = joystick.get_axis(4)  # L2 trigger axis
            r2_axis = joystick.get_axis(5)  # R2 trigger axis

            # Convert from -1 to 1 range to 0 to 100 range
            l2_value = max(0, int((l2_axis + 1) * 50))  # 0 to 100
            r2_value = max(0, int((r2_axis + 1) * 50))  # 0 to 100

            # Use triggers for up/down control
            # R2 for up, L2 for down
            if r2_value > 10 and l2_value <= 10:
                controller_state['up_down'] = r2_value  # Up
            elif l2_value > 10 and r2_value <= 10:
                controller_state['up_down'] = -l2_value  # Down
            else:
                controller_state['up_down'] = 0  # Neutral

            # Debug trigger values (uncomment if needed)
            # if r2_value > 10 or l2_value > 10:
            #     print(f"L2: {l2_value}, R2: {r2_value}, UpDown: {controller_state['up_down']}")

            time.sleep(0.01)
        except Exception as e:
            print(f"Controller error: {e}")


def main():
    tello = Tello()
    model = YOLO('yolov8n.pt')

    print("🚀 Connecting to Tello...")
    tello.connect()
    battery = tello.get_battery()
    print(f"🔋 Battery: {battery}%")

    if battery < 20:
        print("⚠️ Warning: Low battery! Please charge before flying.")
        return

    tello.streamon()
    time.sleep(2)

    # Start controller thread
    controller_thread = threading.Thread(target=read_controller, daemon=True)
    controller_thread.start()

    print("\n🎮 UPDATED CONTROLS:")
    print("X Button (0): Takeoff")
    print("Circle Button (1): Land")
    print("Square Button (2): Emergency Stop")
    print("R1 Button (10): 📸 Take Screenshot")
    print("L1 Button (9): 🎥 Start/Stop Recording")
    print("Share Button (4): 🔍 Toggle Detection")
    print("PS Button (5): Quit")
    print("Left Stick: Forward/Back & Left/Right")
    print("Right Stick: Yaw (Rotate)")
    print("R2 Trigger (Axis): Up - Press gradually")
    print("L2 Trigger (Axis): Down - Press gradually")
    print("=" * 50)

    flying = False

    try:
        while True:
            frame = tello.get_frame_read().frame
            if frame is None:
                time.sleep(0.1)
                continue

            # FIX COLORS
            display_frame = correct_tello_colors(frame)

            # Object detection
            detections_info = "None"
            if controller_state['detection_enabled']:
                results = model(display_frame, verbose=False)
                if len(results) > 0:
                    annotated_frame = results[0].plot()
                    display_frame = annotated_frame

                    # Count detections
                    if results[0].boxes is not None:
                        detections = {}
                        for box in results[0].boxes:
                            name = model.names[int(box.cls[0])]
                            if float(box.conf[0]) > 0.5:
                                detections[name] = detections.get(name, 0) + 1
                        detections_info = ", ".join(
                            [f"{k}:{v}" for k, v in detections.items()]) if detections else "None"

            # Handle screenshot (R1 button)
            if controller_state['take_photo']:
                print("📸 Processing screenshot...")
                take_screenshot(display_frame, detections_info)
                controller_state['take_photo'] = False

            # Handle recording (L1 button)
            if controller_state['toggle_recording']:
                if not recording_state['is_recording']:
                    h, w = display_frame.shape[:2]
                    recording_state['video_writer'], recording_state['video_filename'] = setup_video_writer(w, h)
                    recording_state['is_recording'] = True
                    recording_state['recording_start_time'] = time.time()
                    print(f"🎥 Recording STARTED: {recording_state['video_filename']}")
                else:
                    recording_state['video_writer'].release()
                    recording_state['is_recording'] = False
                    duration = time.time() - recording_state['recording_start_time']
                    print(f"⏹️ Recording STOPPED: {duration:.1f}s")
                controller_state['toggle_recording'] = False

            # Write video if recording
            if recording_state['is_recording']:
                recording_state['video_writer'].write(cv2.cvtColor(display_frame, cv2.COLOR_RGB2BGR))
                rec_time = time.time() - recording_state['recording_start_time']
                cv2.putText(display_frame, f"🔴 REC {rec_time:.1f}s", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (255, 0, 0), 2)

            # UI Overlay
            cv2.putText(display_frame, f"Detections: {detections_info}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0), 2)
            status = "FLYING" if flying else "READY"
            cv2.putText(display_frame, f"Status: {status}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0) if flying else (0, 255, 255), 2)
            cv2.putText(display_frame, f"Photos: {recording_state['photo_count']}", (10, 120), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (255, 255, 255), 1)
            cv2.putText(display_frame, f"Battery: {tello.get_battery()}%", (10, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255, 255, 255), 1)

            # Show controls and trigger status
            cv2.putText(display_frame, "R1: Screenshot | L1: Record | Share: Detect", (10, 170),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            cv2.putText(display_frame, f"Up/Down: {controller_state['up_down']}", (10, 190), cv2.FONT_HERSHEY_SIMPLEX,
                        0.4, (255, 255, 255), 1)

            # Flight controls
            if controller_state['takeoff'] and not flying:
                tello.takeoff()
                flying = True
                controller_state['takeoff'] = False
            elif controller_state['land'] and flying:
                tello.land()
                flying = False
                controller_state['land'] = False
            elif controller_state['emergency']:
                tello.emergency()
                flying = False
                controller_state['emergency'] = False

            if flying:
                tello.send_rc_control(
                    controller_state['left_right'],
                    controller_state['forward_back'],
                    controller_state['up_down'],
                    controller_state['yaw']
                )

            # Display
            cv2.imshow("Tello SAR - Fixed Triggers!", display_frame)

            # Exit conditions (PS button or 'q' key)
            if joystick.get_button(PS5_BUTTONS['PS']):
                print("PS Button pressed - Exiting...")
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
        print("✅ Mission complete!")


if __name__ == "__main__":
    main()
