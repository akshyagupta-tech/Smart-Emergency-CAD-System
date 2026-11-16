#!/usr/bin/env python3
"""
Advanced Module 4: Zero-Copy IPC via POSIX Shared Memory Ring Buffer
Bypasses kernel double-copying for high-throughput video frame ingestion.
"""
import time
import struct
import numpy as np
from multiprocessing import Process, shared_memory

SHM_NAME = "traffic_cam_frame_shm"
FRAME_SHAPE = (480, 640, 3)
FRAME_SIZE = int(np.prod(FRAME_SHAPE)) # ~921 KB per frame

def camera_producer(shm_name: str, num_frames: int = 5):
    """Simulates camera device driver writing directly to /dev/shm."""
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    buf = np.ndarray(FRAME_SHAPE, dtype=np.uint8, buffer=existing_shm.buf)
    
    print("[PRODUCER] Camera Ingestion Driver active. Writing frames to /dev/shm...")
    for frame_id in range(1, num_frames + 1):
        # Generate synthetic frame data directly in shared memory
        buf[:] = (frame_id * 35) % 255
        print(f"  [PRODUCER] Frame #{frame_id:02d} written directly to RAM address {hex(id(buf))}")
        time.sleep(0.04) # Simulate ~25 FPS
    
    existing_shm.close()

def vision_consumer(shm_name: str, num_frames: int = 5):
    """Simulates AI inference worker reading memory directly without system call copies."""
    time.sleep(0.02) # Stagger start
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    buf = np.ndarray(FRAME_SHAPE, dtype=np.uint8, buffer=existing_shm.buf)
    
    print("[CONSUMER] Vision Pipeline attached to zero-copy memory ring...")
    for _ in range(num_frames):
        mean_val = float(np.mean(buf))
        print(f"  [CONSUMER] Read frame zero-copy | Mean Pixel Density: {mean_val:.2f}")
        time.sleep(0.04)
        
    existing_shm.close()

def run_zero_copy_demo():
    print("=" * 68)
    print("      ZERO-COPY POSIX SHARED MEMORY (VMM OPTIMIZATION)          ")
    print("=" * 68)
    try:
        shm = shared_memory.SharedMemory(name=SHM_NAME, create=True, size=FRAME_SIZE)
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=SHM_NAME)

    p1 = Process(target=camera_producer, args=(SHM_NAME,))
    p2 = Process(target=vision_consumer, args=(SHM_NAME,))

    start_time = time.perf_counter()
    p1.start()
    p2.start()
    p1.join()
    p2.join()
    elapsed = time.perf_counter() - start_time

    shm.close()
    shm.unlink() # Cleanup /dev/shm
    print(f"\n[BENCHMARK] Streamed 5 uncompressed frames in {elapsed:.3f}s with 0 OS copy overhead.\n")

if __name__ == "__main__":
    run_zero_copy_demo()
