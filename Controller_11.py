from djitellopy import Tello
from ultralytics import YOLO
import cv2
import pygame
import time
import threading

# Initialize Pygame
pygame.init()
pygame.joystick.init()

print("Searching for controllers...")
if pygame.joystick.get_count() == 0:
    print("❌ No controller found! Please connect your controller and run again.")
    exit()

# Initialize controller
joystick = pygame.joystick.Joystick(0)
joystick.init()
controller_name = joystick.get_name()
print(f"✅ Controller connected: {controller_name}")
print(f"   Axes: {joystick.get_numaxes()}, Buttons: {joystick.get_numbuttons()}")

# Detect controller type and set mappings
if "PS5" in controller_name or "PlayStation" in controller_name:
    print("🎮 PS5 Controller detected")
    # PS5 Mapping
    LEFT_JOYSTICK_X, LEFT_JOYSTICK_Y = 0, 1
    RIGHT_JOYSTICK_X, RIGHT_JOYSTICK_Y = 2, 3
    L2_AXIS, R2_AXIS = 4, 5
    X_BUTTON, CIRCLE_BUTTON = 0, 1
    SQUARE_BUTTON, TRIANGLE_BUTTON = 2, 3
    L1_BUTTON, R1_BUTTON = 4, 5
    SHARE_BUTTON, OPTIONS_BUTTON = 8, 9
    PS_BUTTON = 10
else:
    print("🎮 Xbox/Generic Controller detected (likely through DS4Windows)")
    # Xbox Mapping (via DS4Windows)
    LEFT_JOYSTICK_X, LEFT_JOYSTICK_Y = 0, 1
    RIGHT_JOYSTICK_X, RIGHT_JOYSTICK_Y = 2, 3
    L2_AXIS, R2_AXIS = 4, 5
    X_BUTTON, CIRCLE_BUTTON = 0, 1
    SQUARE_BUTTON, TRIANGLE_BUTTON = 2, 3
    L1_BUTTON, R1_BUTTON = 4, 5
    SHARE_BUTTON, OPTIONS_BUTTON = 6, 7
    PS_BUTTON = 8

# Controller state
controller_state = {
    'left_right': 0,
    'forward_back': 0,
    'up_down': 0,
    'yaw': 0,
    'takeoff': False,
    'land': False,
    'emergency': False,
    'detection_enabled': True
}


def read_controller():
    """Read controller input in separate thread"""
    print("🕹️ Controller reader started...")
    while True:
        try:
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    print(f"Button {event.button} pressed")
                    if event.button == X_BUTTON:
                        controller_state['takeoff'] = True
                        print("🛫 Takeoff command!")
                    elif event.button == CIRCLE_BUTTON:
                        controller_state['land'] = True
                        print("🛬 Land command!")
                    elif event.button == SQUARE_BUTTON:
                        controller_state['emergency'] = True
                        print("🆘 Emergency stop!")
                    elif event.button == SHARE_BUTTON:
                        controller_state['detection_enabled'] = not controller_state['detection_enabled']
                        status = "ENABLED" if controller_state['detection_enabled'] else "DISABLED"
                        print(f"🔍 Object detection: {status}")

            # Read analog sticks with deadzone
            left_x = joystick.get_axis(LEFT_JOYSTICK_X)
            left_y = joystick.get_axis(LEFT_JOYSTICK_Y)
            right_x = joystick.get_axis(RIGHT_JOYSTICK_X)

            # Read triggers for up/down
            if joystick.get_numaxes() > 5:  # PS5 controller
                l2 = (joystick.get_axis(L2_AXIS) + 1) / 2  # Convert from -1~1 to 0~1
                r2 = (joystick.get_axis(R2_AXIS) + 1) / 2
            else:  # Xbox controller via DS4Windows
                l2 = joystick.get_axis(4)
                r2 = joystick.get_axis(5)

            # Apply deadzone
            deadzone = 0.1
            controller_state['left_right'] = int(left_x * 100) if abs(left_x) > deadzone else 0
            controller_state['forward_back'] = int(-left_y * 100) if abs(left_y) > deadzone else 0  # Inverted!
            controller_state['yaw'] = int(right_x * 100) if abs(right_x) > deadzone else 0
            controller_state['up_down'] = int((r2 - l2) * 100)

            time.sleep(0.01)

        except Exception as e:
            print(f"Controller error: {e}")
            time.sleep(0.1)


def main():
    # Initialize Tello and YOLO
    tello = Tello()
    model = YOLO('yolov8n.pt')

    print("🚀 Connecting to Tello...")
    tello.connect()
    battery = tello.get_battery()
    print(f"🔋 Battery: {battery}%")

    if battery < 20:
        print("⚠️ Warning: Low battery! Please charge before flying.")

    tello.streamon()
    time.sleep(2)

    # Start controller thread
    controller_thread = threading.Thread(target=read_controller, daemon=True)
    controller_thread.start()

    print("\n🎮 CONTROLS:")
    print("X Button: Takeoff")
    print("Circle Button: Land")
    print("Square Button: Emergency Stop")
    print("Share Button: Toggle Detection")
    print("Left Stick: Forward/Back & Left/Right")
    print("Right Stick: Yaw (Rotate)")
    print("L2/R2 Triggers: Down/Up")
    print("PS Button: Quit")
    print("=" * 40)

    flying = False
    frame_count = 0

    try:
        while True:
            # Get video frame
            frame = tello.get_frame_read().frame
            if frame is None:
                continue

            # Process frame
            frame_corrected = cv2.convertScaleAbs(frame, alpha=1.2, beta=10)
            frame_rgb = cv2.cvtColor(frame_corrected, cv2.COLOR_BGR2RGB)

            # Object detection
            if controller_state['detection_enabled']:
                results = model(frame_rgb, verbose=False)
                annotated_frame = results[0].plot()

                # Count people
                people_count = 0
                if results[0].boxes is not None:
                    for box in results[0].boxes:
                        if model.names[int(box.cls[0])] == 'person' and float(box.conf[0]) > 0.5:
                            people_count += 1

                cv2.putText(annotated_frame, f"People: {people_count}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                annotated_frame = frame_rgb
                cv2.putText(annotated_frame, "DETECTION: OFF", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # Display status
            status = "FLYING" if flying else "READY"
            color = (0, 255, 0) if flying else (0, 255, 255)
            cv2.putText(annotated_frame, f"Status: {status}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            cv2.putText(annotated_frame, f"Battery: {tello.get_battery()}%", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Handle controller commands
            if controller_state['takeoff'] and not flying:
                print("🛫 Taking off!")
                tello.takeoff()
                flying = True
                controller_state['takeoff'] = False

            if controller_state['land'] and flying:
                print("🛬 Landing!")
                tello.land()
                flying = False
                controller_state['land'] = False

            if controller_state['emergency']:
                print("🆘 EMERGENCY STOP!")
                tello.emergency()
                flying = False
                controller_state['emergency'] = False

            # Control movement
            if flying:
                lr = controller_state['left_right']
                fb = controller_state['forward_back']
                ud = controller_state['up_down']
                yaw = controller_state['yaw']

                # Send RC controls
                tello.send_rc_control(lr, fb, ud, yaw)

                # Show controls on screen
                cv2.putText(annotated_frame, f"Controls: LR:{lr} FB:{fb} UD:{ud} Y:{yaw}",
                            (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            # Display video
            cv2.imshow("Tello - Controller SAR", annotated_frame)

            # Check for exit
            if joystick.get_button(PS_BUTTON):
                print("PS Button pressed - Exiting...")
                break

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            frame_count += 1
            time.sleep(0.03)

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        # Cleanup
        print("🛑 Cleaning up...")
        if flying:
            tello.land()
        tello.streamoff()
        cv2.destroyAllWindows()
        pygame.quit()
        print("✅ Mission complete!")


if __name__ == "__main__":
    main()