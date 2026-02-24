"""
scripts/check_face_pipeline.py
Face detection & recognition pipeline diagnostic — ASCII-safe output.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import json
import numpy as np

from shared.config import (
    YUNET_PATH, MOBILEFACENET_PATH,
    EMBEDDINGS_FILE, NAMES_FILE, KNOWN_FACES_DIR,
    DETECTION_THRESHOLD, RECOGNITION_THRESHOLD
)

results = []

def check(label, ok, detail=""):
    icon = "PASS" if ok else "FAIL"
    print(f"  [{icon}]  {label}")
    if detail:
        print(f"          -> {detail}")
    results.append(ok)
    return ok


print("")
print("==============================================")
print("  BIO_V2  -  Face Pipeline Diagnostics")
print("==============================================")

# ── 1. Model files ────────────────────────────────────────────────────────────
print("\n--- 1. Model Files ---")
yunet_ok     = check("YuNet detector  (.onnx)", os.path.exists(YUNET_PATH),         YUNET_PATH)
mobilenet_ok = check("MobileFaceNet   (.onnx)", os.path.exists(MOBILEFACENET_PATH), MOBILEFACENET_PATH)

# ── 2. Load models ────────────────────────────────────────────────────────────
print("\n--- 2. Model Loading ---")
detector = None
recognizer = None

if yunet_ok:
    try:
        detector = cv2.FaceDetectorYN.create(
            YUNET_PATH, "", (320, 320), DETECTION_THRESHOLD, 0.3, 5000
        )
        check("cv2.FaceDetectorYN.create()", True)
    except Exception as e:
        check("cv2.FaceDetectorYN.create()", False, str(e))

if mobilenet_ok:
    try:
        recognizer = cv2.dnn.readNetFromONNX(MOBILEFACENET_PATH)
        check("cv2.dnn.readNetFromONNX()", True)
    except Exception as e:
        check("cv2.dnn.readNetFromONNX()", False, str(e))

# ── 3. Embeddings database ────────────────────────────────────────────────────
print("\n--- 3. Embeddings Database ---")
emb_ok  = check("embeddings.npy exists", os.path.exists(EMBEDDINGS_FILE))
name_ok = check("names.json exists",     os.path.exists(NAMES_FILE))

num_identities = 0
if emb_ok and name_ok:
    try:
        embeddings = np.load(EMBEDDINGS_FILE)
        with open(NAMES_FILE) as f:
            names = json.load(f)
        num_identities = len(names)
        shapes_match = embeddings.shape[0] == len(names)
        check(f"Embeddings shape: {embeddings.shape}  |  Names: {num_identities}", shapes_match,
              "MISMATCH - re-run encoder!" if not shapes_match else "OK")
        if names:
            print(f"          -> Identities: {', '.join(names)}")
        else:
            print(f"          -> WARNING: No identities registered yet.")
    except Exception as e:
        check("Read embeddings/names", False, str(e))

# ── 4. Known faces directory ──────────────────────────────────────────────────
print("\n--- 4. Known Faces Directory ---")
faces_dir_ok = check("known_faces/ exists", os.path.exists(KNOWN_FACES_DIR))
if faces_dir_ok:
    folders = [d for d in os.listdir(KNOWN_FACES_DIR)
               if os.path.isdir(os.path.join(KNOWN_FACES_DIR, d))]
    check(f"User sub-folders found: {len(folders)}", len(folders) > 0,
          "No users registered." if not folders else ", ".join(folders))

    for folder in folders:
        fpath = os.path.join(KNOWN_FACES_DIR, folder)
        imgs  = [f for f in os.listdir(fpath) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        check(f"  {folder}: {len(imgs)} image(s)", len(imgs) > 0,
              "EMPTY FOLDER!" if not imgs else "")

# ── 5. Detection test on a captured image ─────────────────────────────────────
print("\n--- 5. Detection Test (on stored face image) ---")
if detector and faces_dir_ok:
    test_img_path = None
    for root, dirs, files in os.walk(KNOWN_FACES_DIR):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                test_img_path = os.path.join(root, f)
                break
        if test_img_path:
            break

    if test_img_path:
        img = cv2.imread(test_img_path)
        h, w = img.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(img)
        face_count = len(faces) if faces is not None else 0
        check(f"Detected {face_count} face(s) in sample image", face_count >= 1,
              f"File: {os.path.basename(test_img_path)}  ({w}x{h})")
    else:
        print("  [SKIP]  No sample images found.")
else:
    print("  [SKIP]  Model not loaded or no face directory.")

# ── 6. FaceRecognizer instantiation ───────────────────────────────────────────
print("\n--- 6. FaceRecognizer Module ---")
try:
    from core.recognizer import FaceRecognizer
    fr = FaceRecognizer()
    ok = fr.detector is not None and fr.recognizer is not None
    check("FaceRecognizer() instantiated", ok,
          f"Loaded {len(fr.known_names)} identity/ies from DB")
    if ok and len(fr.known_names) > 0:
        print(f"          -> Names loaded: {', '.join(fr.known_names)}")
except Exception as e:
    check("FaceRecognizer() instantiated", False, str(e))

# ── 7. Alignment module ───────────────────────────────────────────────────────
print("\n--- 7. Alignment Module ---")
try:
    from core.alignment import StandardFaceAligner
    _ = StandardFaceAligner()
    check("StandardFaceAligner import OK", True)
except ImportError as e:
    check("StandardFaceAligner import OK", False, str(e) + " (will use fallback crop)")

# ── 8. Recognizer threshold config ───────────────────────────────────────────
print("\n--- 8. Thresholds ---")
check(f"DETECTION_THRESHOLD  = {DETECTION_THRESHOLD}  (recommend 0.5-0.7)", 0.4 <= DETECTION_THRESHOLD <= 0.8)
check(f"RECOGNITION_THRESHOLD = {RECOGNITION_THRESHOLD}  (recommend 0.65-0.75)", 0.55 <= RECOGNITION_THRESHOLD <= 0.85)

# ── Summary ───────────────────────────────────────────────────────────────────
passed = sum(results)
total  = len(results)
print("")
print("==============================================")
print(f"  RESULT: {passed}/{total} checks passed")
if passed == total:
    print("  Pipeline is HEALTHY - ready to run!")
elif passed >= total - 1:
    print("  Minor issues - see FAIL/WARNING above.")
else:
    print("  Issues found - fix FAIL items above.")
print("==============================================")
print("")
