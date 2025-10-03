from djitellopy import Tello
import cv2

# Initialize the Tello object
tello = Tello()

# Connect to the Tello
print("Connecting to Tello...")
tello.connect()
print(f"Battery: {tello.get_battery()}%")

# Start the video stream
print("Starting video stream...")
tello.streamon()

try:
    while True:
        # Get the current frame from Tello
        frame = tello.get_frame_read().frame

        # The frame comes in a weird format, we need to resize it
        frame = cv2.resize(frame, (360, 240))

        # Display the frame in a window
        cv2.imshow("Tello Live Feed", frame)

        # Wait for 1ms and check if 'q' was pressed to quit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    # Clean up - this runs even if you hit an error
    print("Landing and cleaning up...")
    tello.streamoff()
    cv2.destroyAllWindows()
    print("Done!")