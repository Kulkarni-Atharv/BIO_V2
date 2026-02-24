"""
scripts/diag_runner.py
Run all pipeline checks and save a clean JSON report.
No emoji used — safe for all Windows consoles.
"""
import sys, os, json, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import (
    YUNET_PATH, MOBILEFACENET_PATH, EMBEDDINGS_FILE,
    NAMES_FILE, KNOWN_FACES_DIR, DETECTION_THRESHOLD, RECOGNITION_THRESHOLD
)

report = {}

# 1. Models exist
report["yunet_exists"]       = os.path.exists(YUNET_PATH)
report["mobilenet_exists"]   = os.path.exists(MOBILEFACENET_PATH)
report["embeddings_exists"]  = os.path.exists(EMBEDDINGS_FILE)
report["names_exists"]       = os.path.exists(NAMES_FILE)
report["faces_dir_exists"]   = os.path.exists(KNOWN_FACES_DIR)

# 2. Load models
try:
    det = cv2.FaceDetectorYN.create(YUNET_PATH, "", (320,320), DETECTION_THRESHOLD, 0.3, 5000)
    report["detector_loaded"] = True
except Exception as e:
    det = None
    report["detector_loaded"] = False
    report["detector_error"]  = str(e)

try:
    rec = cv2.dnn.readNetFromONNX(MOBILEFACENET_PATH)
    report["recognizer_loaded"] = True
except Exception as e:
    rec = None
    report["recognizer_loaded"] = False
    report["recognizer_error"]  = str(e)

# 3. Embeddings
try:
    emb   = np.load(EMBEDDINGS_FILE)
    names = json.load(open(NAMES_FILE))
    report["num_identities"]    = len(names)
    report["embeddings_shape"]  = list(emb.shape)
    report["names_match"]       = emb.shape[0] == len(names)
    report["identity_list"]     = names
except Exception as e:
    report["embeddings_error"]  = str(e)

# 4. Face folders
if os.path.exists(KNOWN_FACES_DIR):
    folders = [d for d in os.listdir(KNOWN_FACES_DIR)
               if os.path.isdir(os.path.join(KNOWN_FACES_DIR, d))]
    folder_info = {}
    for f in folders:
        imgs = [x for x in os.listdir(os.path.join(KNOWN_FACES_DIR, f))
                if x.lower().endswith(('.jpg','.jpeg','.png'))]
        folder_info[f] = len(imgs)
    report["face_folders"] = folder_info

# 5. Detection test on first sample image
if det and os.path.exists(KNOWN_FACES_DIR):
    test_img = None
    for root, dirs, files in os.walk(KNOWN_FACES_DIR):
        for f in files:
            if f.lower().endswith(('.jpg','.jpeg','.png')):
                test_img = os.path.join(root, f)
                break
        if test_img: break
    if test_img:
        img = cv2.imread(test_img)
        h, w = img.shape[:2]
        det.setInputSize((w, h))
        _, faces = det.detect(img)
        fc = len(faces) if faces is not None else 0
        report["detection_test"] = {"image": os.path.basename(test_img), "faces_found": fc}

# 6. FaceRecognizer
try:
    from core.recognizer import FaceRecognizer
    fr = FaceRecognizer()
    report["FaceRecognizer_ok"] = fr.detector is not None and fr.recognizer is not None
    report["FaceRecognizer_identities"] = len(fr.known_names)
except Exception as e:
    report["FaceRecognizer_ok"] = False
    report["FaceRecognizer_error"] = str(e)

# 7. Alignment
try:
    from core.alignment import StandardFaceAligner
    _ = StandardFaceAligner()
    report["aligner_ok"] = True
except ImportError:
    report["aligner_ok"] = False

# 8. Thresholds
report["detection_threshold"]   = DETECTION_THRESHOLD
report["recognition_threshold"] = RECOGNITION_THRESHOLD

# Save report
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diag_report.json")
with open(out, 'w') as f:
    json.dump(report, f, indent=2)

print("Report written to:", out)
print(json.dumps(report, indent=2))
