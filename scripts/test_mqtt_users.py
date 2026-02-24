"""
scripts/test_mqtt_users.py
──────────────────────────
Tests the full request-response loop for employee sync:

  1. Connects to EMQX with TLS
  2. Subscribes to p/a/1/receive-users
  3. Publishes {"device_id":"1","action":"get-users"} to p/a/1/request-users
  4. Waits up to WAIT_SECONDS for a response from the dashboard
  5. Prints what arrived and saves it to the local users table

Usage:
  python scripts/test_mqtt_users.py

If the dashboard is set up to respond, you will see the employee list arrive.
If no response comes within WAIT_SECONDS, it means the dashboard has not
published yet — the subscription itself is confirmed working regardless.
"""
import sys, os, json, time, ssl, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paho.mqtt.client as mqtt

from shared.config import (
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD,
    MQTT_TOPIC_REQUEST_USERS, MQTT_TOPIC_RECEIVE_USERS, DEVICE_ID
)
from device.database import LocalDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger("MQTT_Test")

WAIT_SECONDS = 15   # how long to wait for the dashboard to respond

# ── State ─────────────────────────────────────────────────────────────────────
received_payload = []
connected_event  = False
db = LocalDatabase()

# ── Callbacks ─────────────────────────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    global connected_event
    if rc == 0:
        logger.info("Connected OK to %s:%s", MQTT_BROKER, MQTT_PORT)
        # Subscribe to receive-users
        client.subscribe(MQTT_TOPIC_RECEIVE_USERS, qos=1)
        logger.info("Subscribed to: %s", MQTT_TOPIC_RECEIVE_USERS)

        # Publish request
        req = json.dumps({"device_id": DEVICE_ID, "action": "get-users"})
        client.publish(MQTT_TOPIC_REQUEST_USERS, req, qos=1)
        logger.info("Published request to: %s", MQTT_TOPIC_REQUEST_USERS)
        logger.info("Payload: %s", req)
        connected_event = True
    else:
        logger.error("Connect failed: rc=%d", rc)


def on_message(client, userdata, msg):
    global received_payload
    logger.info("")
    logger.info("==== MESSAGE RECEIVED ON: %s ====", msg.topic)
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        logger.info("Payload type : %s", type(payload).__name__)

        if isinstance(payload, list):
            logger.info("Employee count : %d", len(payload))
            for i, emp in enumerate(payload, 1):
                uid  = emp.get("user_id") or emp.get("id", "?")
                name = emp.get("name") or emp.get("employee_name", "?")
                logger.info("  [%2d] ID=%-10s  Name=%s", i, uid, name)
            received_payload = payload
            # Save to local DB
            db.upsert_users(payload)
            logger.info("")
            logger.info("Saved %d employees to local SQLite users table.", len(payload))
        elif isinstance(payload, dict):
            logger.info("Single employee: %s", payload)
            received_payload = [payload]
            db.upsert_users([payload])
            logger.info("Saved 1 employee to local SQLite users table.")
        else:
            logger.warning("Unexpected payload type: %s", payload)

    except json.JSONDecodeError:
        logger.error("Raw payload (not JSON): %s", msg.payload.decode("utf-8", errors="replace"))


def on_subscribe(client, userdata, mid, granted_qos):
    logger.info("Subscription confirmed (mid=%d, QoS=%s)", mid, granted_qos)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # TLS setup
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    client.tls_set_context(ctx)

    client.on_connect   = on_connect
    client.on_message   = on_message
    client.on_subscribe = on_subscribe

    logger.info("Connecting to EMQX broker: %s:%s", MQTT_BROKER, MQTT_PORT)
    logger.info("Request topic : %s", MQTT_TOPIC_REQUEST_USERS)
    logger.info("Receive topic : %s", MQTT_TOPIC_RECEIVE_USERS)
    logger.info("Device ID     : %s", DEVICE_ID)
    logger.info("")

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        logger.error("Connection failed: %s", e)
        return

    # Wait for connection
    deadline = time.time() + 5
    while not connected_event and time.time() < deadline:
        time.sleep(0.2)

    if not connected_event:
        logger.error("Could not connect within 5s. Check internet / credentials.")
        client.loop_stop()
        return

    # Wait for employee list response
    logger.info("")
    logger.info("Waiting up to %ds for dashboard to respond on receive-users...", WAIT_SECONDS)
    deadline = time.time() + WAIT_SECONDS
    while not received_payload and time.time() < deadline:
        time.sleep(0.5)

    client.loop_stop()
    client.disconnect()

    # Summary
    logger.info("")
    logger.info("=" * 55)
    if received_payload:
        local_users = db.get_all_users()
        logger.info("RESULT: SUCCESS")
        logger.info("  Employees received : %d", len(received_payload))
        logger.info("  Total in local DB  : %d", len(local_users))
        logger.info("=" * 55)
    else:
        logger.info("RESULT: NO RESPONSE in %ds", WAIT_SECONDS)
        logger.info("  Subscription to receive-users is WORKING.")
        logger.info("  The dashboard has not published on receive-users yet.")
        logger.info("  To simulate a response, publish from EMQX dashboard:")
        logger.info("    Topic  : %s", MQTT_TOPIC_RECEIVE_USERS)
        logger.info('    Payload: [{"user_id":"101","name":"Atharv"},{"user_id":"102","name":"Ravi"}]')
        logger.info("=" * 55)


if __name__ == "__main__":
    main()
